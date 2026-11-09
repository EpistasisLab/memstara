"""On-demand developer measurements. No prompts, model calls or runtime writes."""
import asyncio
import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import HTTPException
from db import pools
import run_artifacts as archive
from continuations import tags
from loop_history import call_loops
from telemetry_totals import scoped_outcomes

SQL = """SELECT id, status, started_at, completed_at,
    (token_usage->>'prompt_tokens')::bigint AS input_tokens,
    (token_usage->>'completion_tokens')::bigint AS output_tokens
    FROM agent_runs WHERE id = ANY($1::uuid[])"""


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def interval(start, end):
    if number(start) and number(end) and end >= start:
        return (start, end)
    return None


def union_seconds(spans):
    """Parallel activity is counted once; gaps between calls are excluded."""
    if not spans:
        return None
    ordered = sorted(spans)
    start, end = ordered[0]
    total = 0
    for left, right in ordered[1:]:
        if left > end:
            total += end - start
            start, end = left, right
        else:
            end = max(end, right)
    return total + end - start


def role(stage):
    stage = (stage or '').lower()
    for prefix, name in (('question', 'question'), ('hypothesis', 'hypothesis'),
                         ('data', 'data'), ('ml', 'ml'), ('interpreter', 'interpretation'),
                         ('interpretation', 'interpretation'), ('report', 'explanation'),
                         ('explanation', 'explanation')):
        if stage.startswith(prefix):
            return name
    return 'other'


def measures(calls, rows):
    calls = list({c['run_id']: c for c in calls if c.get('run_id')}.values())
    spans = []
    inputs, outputs = [], []
    missing_times = 0
    pending = False
    for call in calls:
        row = rows.get(call['run_id'], {})
        pending |= bool(row) and row.get('status') not in ('completed', 'failed', 'cancelled')
        for field, target in (('input_tokens', inputs), ('output_tokens', outputs)):
            value = row.get(field)
            if number(value) and value >= 0:
                target.append(value)
        start, duration = call.get('started_at'), call.get('duration_seconds')
        span = interval(start, start + duration) if number(start) and number(duration) else None
        if span is None:
            left, right = row.get('started_at'), row.get('completed_at')
            span = interval(left.timestamp(), right.timestamp()) if isinstance(left, datetime) and isinstance(right, datetime) else None
        if span is None:
            missing_times += 1
        else:
            spans.append(span)
    full = bool(calls) and len(inputs) == len(outputs) == len(calls) and not pending
    return {
        'calls': len(calls),
        'input_tokens': sum(inputs) if inputs else None,
        'output_tokens': sum(outputs) if outputs else None,
        'total_tokens': sum(inputs) + sum(outputs) if inputs and outputs else None,
        'tokens_status': 'complete' if full else 'partial' if inputs or outputs else 'unavailable',
        'active_seconds': union_seconds(spans),
        'active_status': 'recorded' if calls and not missing_times else 'partial' if spans else 'unavailable',
        'agent_span_seconds': max(e for _, e in spans) - min(s for s, _ in spans) if spans else None,
    }


def read_catalog():
    configs = archive.configs()
    parents = set()
    for tag, config in configs.items():
        if config.get('mode') == 'report_only':
            continue
        # Honor both modern frozen retry metadata and legacy lineage files.
        parent = (config.get('retry_selection') or {}).get('source_run_tag')
        directory = archive.directory_for(tag)
        lineage = archive.read_json(directory / 'retry_lineage.json') if directory else None
        parent = (lineage or {}).get('source_run_tag') or parent
        if parent:
            parents.add(parent)
    return {'experiments': [
        {'run_tag': tag, 'name': config.get('pipeline_name') or config.get('pipeline_id') or tag}
        for tag, config in sorted(configs.items(), reverse=True)
        if tag not in parents and config.get('mode') != 'report_only'
    ]}


def read_history(tag):
    if not archive.config_for(tag):
        raise HTTPException(404, 'Execution not found')
    records = []
    for source in tags(tag):
        directory, config = archive.directory_for(source), archive.config_for(source)
        if directory is None or not config:
            raise HTTPException(503, 'Continuation metadata is unavailable; no partial history was substituted')
        # Compact metadata only: do not load reports, agent prompts, traces or step histories.
        manifest = archive.read_json(directory / 'execution.json')
        if not isinstance(manifest, dict) or not isinstance(manifest.get('calls'), list):
            raise HTTPException(503, 'Compact execution metadata is unavailable for ' + source)
        outcomes = archive.read_json(directory / 'iteration_outcomes.json')
        if not isinstance(outcomes, dict):
            raise HTTPException(503, 'Replicate outcomes are unavailable for ' + source)
        execution = {'configuration': config, 'outcomes': outcomes,
                     'execution_status': archive.pipeline_state(directory) or {}}
        records.append({'tag': source, 'configuration': config,
                        'calls': call_loops(manifest['calls']), 'outcomes': scoped_outcomes(execution)})
    return records


def summarize(records, rows):
    indexed = {str(row['id']): row for row in rows}
    grouped = defaultdict(lambda: {'calls': {}, 'attempts': [], 'run_tags': []})
    owners = {}
    unassigned = set()
    for record in records:
        for raw, outcome in record['outcomes'].items():
            if not str(raw).isdigit() or int(raw) < 1:
                continue
            item = grouped[int(raw)]
            item['attempts'].append((record['tag'], outcome))
            item['run_tags'].append(record['tag'])
        for call in record['calls']:
            identifier, loop = call.get('run_id'), call.get('loop')
            if not identifier:
                continue
            if identifier in owners and owners[identifier] != loop:
                raise HTTPException(503, 'Conflicting replicate attribution; measurements withheld')
            owners[identifier] = loop
            if loop is None:
                unassigned.add(identifier)
                continue
            grouped[loop]['calls'][identifier] = call
            grouped[loop]['run_tags'].append(record['tag'])
    points = []
    excluded = 0
    for loop, item in grouped.items():
        attempts = item['attempts']
        if not attempts or attempts[-1][1].get('outcome') != 'completed':
            excluded += 1
            continue
        calls = list(item['calls'].values())
        boundaries = [interval(o.get('started_at'), o.get('ended_at')) for _, o in attempts]
        known = [span for span in boundaries if span is not None]
        starts = [c['started_at'] for c in calls if number(c.get('started_at'))]
        first = min([s for s, _ in known] + starts, default=None)
        last = attempts[-1][1].get('ended_at')
        elapsed = interval(first, last)
        by_role = defaultdict(list)
        for call in calls:
            by_role[role(call.get('stage'))].append(call)
        points.append({
            'loop': loop, **archive.identity(records[-1]['configuration'], loop),
            'run_tag': attempts[-1][0], 'run_tags': list(dict.fromkeys(item['run_tags'])),
            'attempts': len(attempts), 'started_at': first,
            'ended_at': last if number(last) else None,
            'elapsed_seconds': elapsed[1] - elapsed[0] if elapsed else None,
            'elapsed_status': 'recorded' if elapsed and all(boundaries) else 'partial' if elapsed else 'unavailable',
            'attribution': 'recorded' if calls and all(c.get('loop_source') == 'recorded' for c in calls) else 'approximate',
            **measures(calls, indexed),
            'agents': {name: measures(selected, indexed) for name, selected in sorted(by_role.items())},
        })
    # Never silently sort by Loop number: retry selections can execute out of order.
    points.sort(key=lambda p: (p['started_at'] is None, p['started_at'] or 0, p['loop']))
    for order, point in enumerate(points, 1):
        point['order'] = order
    config = records[-1]['configuration']
    return {'run_tag': records[-1]['tag'], 'run_tags': [r['tag'] for r in records],
            'name': config.get('pipeline_name') or config.get('pipeline_id') or records[-1]['tag'],
            'updated_at': datetime.now(UTC).isoformat(), 'points': points,
            'excluded_replicates': excluded, 'unassigned_calls': len(unassigned),
            'unknown_order_count': sum(p['started_at'] is None for p in points)}


async def trends(tag):
    try:
        async with asyncio.timeout(20):
            records = await asyncio.to_thread(read_history, tag)
            ids = {uuid.UUID(c['run_id']) for r in records for c in r['calls'] if c.get('run_id')}
            async def query(conn):
                return [dict(row) for row in await conn.fetch(SQL, list(ids))]
            rows = await pools.guarded('core', query, None) if ids else []
            if rows is None:
                raise HTTPException(503, 'Motoro usage is unavailable; missing measurements are not zero')
            return await asyncio.to_thread(summarize, records, rows)
    except TimeoutError:
        raise HTTPException(503, 'Trend lookup timed out; refresh to retry') from None
    except ValueError:
        raise HTTPException(503, 'Invalid saved invocation identity; measurements withheld') from None
