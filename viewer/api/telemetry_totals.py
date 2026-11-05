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


def scoped_outcomes(execution):
    """Ignore legacy ordinal counters outside a retry's original frozen IDs.

    Actual call receipts remain untouched and every attempt still costs money.
    A presentation repair must never relabel or discard measured model usage.
    """
    config = execution.get('configuration') or {}
    selection = (config.get('retry_selection') or {}).get('loops')
    outcomes = dict(execution.get('outcomes') or {})
    if selection is not None:
        total = (config.get('combination_plan') or {}).get('total_loops',config.get('waves'))
        if (not isinstance(selection,list) or not selection
                or any(type(n) is not int or n<1 or (type(total) is int and n>total) for n in selection)):
            raise HTTPException(503,'Original retry combination IDs are unavailable')
        selected = set(selection)
        outcomes = {key:value for key,value in outcomes.items() if str(key).isdigit() and int(key) in selected}
    status = execution.get('execution_status') or {}
    numbered = [key for key in outcomes if str(key).isdigit()]
    if numbered and status.get('status') in ('failed','cancelled','interrupted'):
        latest = max(numbered,key=lambda key:int(key))
        if outcomes[latest].get('outcome') in ('running','analysis_complete'):
            outcomes[latest] = {**outcomes[latest],'outcome':'blocked' if status['status']=='failed' else 'interrupted'}
    return outcomes


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


def recorded_span(calls, rows):
    """Observed Motoro wall-clock span, not a sum or an assertion of liveness."""
    ids = {c['run_id'] for c in calls if c.get('run_id')}
    selected = {str(r['id']): r for r in rows if str(r['id']) in ids}
    spans = []
    complete = bool(ids) and len(selected) == len(ids)
    for row in selected.values():
        start = row.get('started_at')
        end = row.get('completed_at') or row.get('last_heartbeat_at')
        if not isinstance(start, datetime) or not isinstance(end, datetime) or end < start:
            complete = False
            continue
        spans.append((start.timestamp(), end.timestamp()))
        complete = complete and row.get('completed_at') is not None
    seconds = max(e for _, e in spans) - min(s for s, _ in spans) if spans else None
    return {'seconds': seconds, 'duration_status': 'recorded' if complete else 'partial',
            'duration_basis': 'Motoro first agent/step start to last recorded completion or heartbeat; '
            'includes gaps and parallel overlap, excludes unrecorded setup/finalization. '
            'An unfinished record is not proof that its process is running.'}


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
            'basis': 'Completed replicates with recorded boundaries, explicit replicate attribution and complete usage. '
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
        execution = {'tag': tag, 'pipeline_id': config['pipeline_id'],
                           'model': config.get('model'), 'provider': config.get('provider'), 'configuration': config,
                           'calls': call_loops(item['calls']), 'outcomes': outcomes,
                           'execution_status':item.get('pipeline') or {}}
        execution['outcomes'] = scoped_outcomes(execution)
        executions.append(execution)
    return configured, executions


def continued_usage(executions, rows):
    """One cumulative view per explicit retry chain, retaining all attempt costs."""
    from continuations import tags
    indexed = {e['tag']: e for e in executions}
    result = []
    for current in executions:
        history = tags(current['tag'])
        if any(t not in indexed for t in history):
            raise HTTPException(503, 'Continuation usage archive is unavailable')
        records = [{**indexed[t],'outcomes':scoped_outcomes(indexed[t])} for t in history]
        calls = [c for e in records for c in e['calls']]
        numbers = {c['loop'] for c in calls if c['loop'] is not None}
        numbers.update(int(n) for e in records for n in e['outcomes'] if str(n).isdigit() and int(n) > 0)
        loops = []
        for n in sorted(numbers):
            attempts = [e['outcomes'][str(n)] for e in records if str(n) in e['outcomes']]
            outcome = attempts[-1] if attempts else {}
            selected = [c for c in calls if c['loop'] == n]
            metric = loop_metrics(selected, rows, outcome)
            if len(attempts) > 1:
                # Failed attempts still cost money. Span includes retry gaps and
                # must not enter the fully measured per-attempt average cohort.
                metric.update(recorded_span(selected, rows), attribution='approximate')
            sources = [e['tag'] for e in records if str(n) in e['outcomes'] or any(c['loop'] == n for c in e['calls'])]
            loops.append({'number': n, 'run_tags': sources, **archive.identity(current['configuration'], n), **metric})
        result.append({'run_tag': current['tag'], 'run_tags': history,
                       'pipeline_id': current['pipeline_id'], 'model': current.get('model'),
                       'provider': current.get('provider'), **metrics(calls, rows),
                       **recorded_span(calls, rows), 'loops': loops,
                       'loop_summary': completed_summary(loops),
                       'unassigned': metrics([c for c in calls if c['loop'] is None], rows)})
    return result


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
                    loops = [{'number': n, **archive.identity(e.get('configuration', {}), n), **loop_metrics(
                        [c for c in e['calls'] if c['loop'] == n], rows,
                        e['outcomes'].get(str(n), {}))} for n in sorted(numbers)]
                    details.append({'run_tag': e['tag'], 'pipeline_id': e['pipeline_id'],
                                    'model': e.get('model'), 'provider': e.get('provider'),
                                    **metrics(e['calls'], rows), **recorded_span(e['calls'], rows), 'loops': loops,
                                    'loop_summary': completed_summary(loops),
                                    'unassigned': metrics([c for c in e['calls'] if c['loop'] is None], rows)})
                result = {'scope': 'All saved executions of pipelines currently in this workspace',
                          'updated_at': datetime.now(UTC).isoformat(),
                          'total': metrics(calls, rows), 'pipelines': pipelines, 'executions': details,
                          'experiments': await asyncio.to_thread(continued_usage, executions, rows),
                          'loop_summary': completed_summary([row for e in details for row in e['loops']])}
                _cache = (time.monotonic(), result)
                return result
    except TimeoutError:
        raise HTTPException(503, 'Totals lookup timed out; please retry.') from None
