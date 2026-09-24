"""Bounded, scope-isolated refreshes that survive a short HTTP wait budget."""
import asyncio
import time
from fastapi import HTTPException
import scene

_cache = {}
_inflight = {}
REQUEST_WAIT = 2.0
REFRESH_DEADLINE = 65.0


async def _refresh(key):
    hit = _cache.get(key)
    try:
        fresh = await asyncio.wait_for(scene._snapshot_uncached(*key, telemetry=True), REFRESH_DEADLINE)
    except TimeoutError:
        if hit:
            return {**hit[1], 'stale': True}
        raise HTTPException(503, 'Telemetry refresh could not finish; retrying is safe.') from None
    if not (fresh['health']['memstara']['up'] and fresh['health']['core']['up']):
        fresh = {**(hit[1] if hit else fresh), 'health': fresh['health'], 'stale': True}
    if len(_cache) >= 64 and key not in _cache:
        _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
    _cache[key] = (time.monotonic(), fresh)
    return fresh


def _finished(key, task):
    if _inflight.get(key) is task:
        _inflight.pop(key, None)
    # A browser may have disconnected before the refresh failed.
    if not task.cancelled():
        task.exception()


async def snapshot(run_tag, loop):
    key = (run_tag, loop)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < 2:
        return hit[1]
    task = _inflight.get(key)
    if task is None:
        task = asyncio.create_task(_refresh(key))
        _inflight[key] = task
        task.add_done_callback(lambda done: _finished(key, done))
    try:
        # An HTTP timeout must not repeatedly cancel the first uncached lookup.
        # Concurrent clients and subsequent polls reuse the same bounded refresh.
        return await asyncio.wait_for(asyncio.shield(task), REQUEST_WAIT)
    except TimeoutError:
        if hit:
            return {**hit[1], 'stale': True}
        raise HTTPException(202, {'status': 'loading', 'run_tag': run_tag, 'loop': loop}) from None


def project(snapshot, view=None):
    """Return only a tab's records; retain the common snapshot shape for old clients."""
    if view is None:
        return snapshot
    sections = {
        'Totals': set(), 'Agents': {'agents'}, 'Activity': {'feed'},
        'Logs': {'loop_log'}, 'Access': {'access'}, 'Tasks': {'board'},
        'Results': {'results', 'board'},
    }[view]
    empty = {'agents': [], 'feed': [], 'access': [], 'results': [],
             'board': {'lanes': {}, 'tasks': []},
             'loop_log': {'lines': [], 'note': '', 'truncated': False}}
    return {**snapshot, **{k:v for k,v in empty.items() if k not in sections},
            'telemetry': {**snapshot['telemetry'], 'view': view,
                          'included_sections': sorted(sections)}}
