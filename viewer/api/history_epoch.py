"""Reset-aware read barriers and per-worker cache invalidation.

The controller publishes a small marker on the existing read-only runs mount.
The viewer stays SELECT-only: it never calls a reset or writes the marker.
"""
import asyncio
import json
import sys
from fastapi.responses import JSONResponse
import run_artifacts

_seen = None
_lock = asyncio.Lock()


def read():
    try:
        value = json.loads((run_artifacts.ROOT/'history_epoch.json').read_text())
    except FileNotFoundError:
        return {'revision': 'initial', 'busy': False}
    if not isinstance(value, dict) or type(value.get('busy')) is not bool:
        raise ValueError('Invalid history maintenance marker')
    return value


async def invalidate():
    """Drop evidence caches and stop old refreshes before serving the new epoch."""
    tasks = []
    for name, attributes in {
        'discovery': ('_live_reads', '_live_ready', '_semantic_jobs'),
        'telemetry': ('_cache', '_inflight'),
        'scene': ('_snapshot_cache', '_snapshot_locks'),
        'flat_history': ('_cache',),
    }.items():
        module = sys.modules.get(name)
        if not module:
            continue
        for attribute in attributes:
            value = getattr(module, attribute, None)
            if isinstance(value, dict):
                for item in value.values():
                    if isinstance(item, asyncio.Task) and not item.done():
                        item.cancel()
                        tasks.append(item)
                value.clear()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    totals = sys.modules.get('telemetry_totals')
    if totals:
        totals._cache = None
    outputs = sys.modules.get('explanation_outputs')
    if outputs:
        for name in ('_outputs_at_version', 'trace_output'):
            cache = getattr(outputs, name, None)
            if hasattr(cache, 'cache_clear'):
                cache.cache_clear()
    with run_artifacts._index_lock:
        run_artifacts._config_index = None
        run_artifacts._index_expires = 0.0
        run_artifacts._matches.clear()
        run_artifacts._config_at_version.cache_clear()


async def barrier(request, call_next):
    global _seen
    try:
        before = read()
        key = (before.get('revision', 'initial'), before.get('busy', False))
        async with _lock:
            if key != _seen:
                await invalidate()
                _seen = key
        if before.get('busy') and request.url.path != '/api/health':
            return JSONResponse({'detail': 'Experiment history maintenance is in progress.'}, status_code=503)
        response = await call_next(request)
        after = read()
        if before != after:
            async with _lock:
                await invalidate()
                _seen = None
            return JSONResponse({'detail': 'Experiment history changed. Refresh the current view.'}, status_code=503)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Memstara-History-Revision'] = str(after.get('revision', 'initial'))
        return response
    except (OSError, ValueError):
        return JSONResponse({'detail': 'History maintenance state is unavailable.'}, status_code=503)
