"""Four telemetry scopes, deduplicated by execution and agent invocation IDs."""
import asyncio
import time
import uuid
import statistics
import math
from datetime import UTC, datetime
from fastapi import HTTPException
from db import pools
import costs
import run_artifacts as archive
from loop_history import call_loops

_cache = None
_lock = asyncio.Lock()


def metrics(calls, rows):
    ids = {c['run_id'] for c in calls if c.get('run_id')}
    selected = list({str(r['id']): r for r in rows if str(r['id']) in ids}.values())
    cost = costs.summarize(ids, selected)
    missing_tokens = len(ids) - len(selected) + sum(not r.get('tokens_recorded', True) for r in selected)
    pending = any(r['status'] not in ('completed', 'failed', 'cancelled') for r in selected)
    return {'calls': len(ids), 'tokens': sum(r['tokens'] for r in selected),
            'tokens_status': 'partial' if missing_tokens or pending else 'complete',
            'missing_token_records': missing_tokens,
            'cost': cost, 'missing_calls': len(ids) - len(selected)}


def loop_metrics(calls, rows, outcome):
    starts = [c['started_at'] for c in calls if isinstance(c.get('started_at'), (int, float))]
    ends = [c['started_at'] + c['duration_seconds'] for c in calls
            if isinstance(c.get('started_at'), (int, float)) and isinstance(c.get('duration_seconds'), (int, float))]
    start, end = outcome.get('started_at'), outcome.get('ended_at')
    basis = 'recorded loop boundaries'
    if start is None:
        start, end = min(starts, default=None), max(ends, default=None)
        basis = 'archived agent-call span (approximate)'
    running = outcome.get('outcome') in ('running', 'analysis_complete')
    stop = time.time() if running else end
    seconds = (stop - start if all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, stop))
               and stop >= start else None)
    attribution = 'recorded' if all(c.get('loop_source', 'recorded') == 'recorded' for c in calls) else 'approximate'
    return {**metrics(calls, rows), 'seconds': seconds, 'duration_basis': basis,
            'attribution': attribution,
            'status': outcome.get('outcome', 'recorded')}


def completed_summary(loops):
    """Use one common, fully measured cohort for all three averages."""
    completed = [row for row in loops if row['status'] == 'completed']
    eligible = [row for row in completed if row['seconds'] is not None and row['calls'] > 0
                and row['duration_basis'] == 'recorded loop boundaries'
                and row['attribution'] == 'recorded' and row['cost']['status'] == 'complete'
                and row['tokens_status'] == 'complete']
    def distribution(values):
        return {'mean': statistics.mean(values), 'median': statistics.median(values),
                'min': min(values), 'max': max(values)} if values else None
    return {'sample_count': len(eligible), 'completed_count': len(completed),
            'excluded_completed': len(completed) - len(eligible),
            'other_loops': len(loops) - len(completed),
            'seconds': distribution([row['seconds'] for row in eligible]),
            'usd': distribution([row['cost']['usd'] for row in eligible]),
            'tokens': distribution([row['tokens'] for row in eligible]),
            'basis': 'Completed Loops with recorded boundaries, explicit Loop attribution and complete usage. '
                     'Wall-clock time includes waits and pauses. Failed, blocked, interrupted, running and '
                     'approximate or partial records are excluded.'}


def inventory():
    workspace = archive.read_json(archive.ROOT / 'pipeline_workspace.json')
    if not isinstance(workspace, list):
        raise HTTPException(503, 'Pipeline inventory is unavailable; no zero total is assumed.')
    configured = {p['id']: p for p in workspace}
    executions = []
    for tag, config in archive.configs().items():
        if config.get('pipeline_id') not in configured:
            continue
        item = archive.lookup(tag)
        if not item:
            continue
        directory = archive.directory_for(tag)
        outcomes = archive.read_json(directory / 'iteration_outcomes.json') or {}
        executions.append({'tag': tag, 'pipeline_id': config['pipeline_id'],
                           'model': config.get('model'), 'provider': config.get('provider'),
                           'calls': call_loops(item['calls']), 'outcomes': outcomes})
    return configured, executions


async def totals():
    global _cache
    try:
        async with asyncio.timeout(5):
            async with _lock:
                if _cache and time.monotonic() - _cache[0] < 4:
                    return _cache[1]
                configured, executions = await asyncio.to_thread(inventory)
                calls = [c for e in executions for c in e['calls']]
                ids = {uuid.UUID(c['run_id']) for c in calls if c.get('run_id')}
                async def query(conn):
                    return [dict(r) for r in await conn.fetch(costs.SQL, list(ids))]
                rows = await pools.guarded('core', query, None) if ids else []
                if rows is None:
                    raise HTTPException(503, 'Usage records are unavailable; totals are not zero.')
                rows = await asyncio.to_thread(costs.with_ledgers, rows, [e['tag'] for e in executions])
                pipelines = []
                for key, definition in configured.items():
                    records = [e for e in executions if e['pipeline_id'] == key]
                    pipelines.append({'id': key, 'name': definition['name'],
                                      'executions': len(records),
                                      **metrics([c for e in records for c in e['calls']], rows)})
                details = []
                for e in executions:
                    numbers = {c['loop'] for c in e['calls'] if c['loop'] is not None}
                    numbers.update(int(n) for n in e['outcomes'] if str(n).isdigit() and int(n) > 0)
                    loops = [{'number': n, **loop_metrics(
                        [c for c in e['calls'] if c['loop'] == n], rows,
                        e['outcomes'].get(str(n), {}))} for n in sorted(numbers)]
                    details.append({'run_tag': e['tag'], 'pipeline_id': e['pipeline_id'],
                                    'model': e.get('model'), 'provider': e.get('provider'),
                                    **metrics(e['calls'], rows), 'loops': loops,
                                    'loop_summary': completed_summary(loops),
                                    'unassigned': metrics([c for c in e['calls'] if c['loop'] is None], rows)})
                result = {'scope': 'All saved executions of pipelines currently in this workspace',
                          'updated_at': datetime.now(UTC).isoformat(),
                          'total': metrics(calls, rows), 'pipelines': pipelines, 'executions': details,
                          'loop_summary': completed_summary([row for e in details for row in e['loops']])}
                _cache = (time.monotonic(), result)
                return result
    except TimeoutError:
        raise HTTPException(503, 'Totals lookup timed out; please retry.') from None
