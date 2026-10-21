"""Read local cost evidence without rewriting historical run records."""
import json
import math
from collections import defaultdict
from fastapi import HTTPException
import run_artifacts


def details(tag):
    directory = run_artifacts.directory_for(tag)
    if directory is None or not directory.is_dir():
        raise HTTPException(404, 'Execution not found')
    records, malformed = [], 0
    path = directory / 'cost_ledger.jsonl'
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or not row.get('id'):
                    raise ValueError('Invalid record')
                records.append(row)
            except (ValueError, TypeError):
                malformed += 1
    records = list({r['id']:r for r in records}.values())
    groups = defaultdict(lambda: {'calls':0, 'priced_calls':0, 'usd':0., 'input_tokens':0, 'output_tokens':0})
    for row in records:
        amount = row.get('usd')
        known = row.get('status') == 'estimated' and type(amount) in (int,float) and math.isfinite(amount) and amount >= 0
        if not known:
            row['usd'] = None
        group = groups[(row.get('stage','Unknown'),row.get('model','Unknown'))]
        group['calls'] += 1
        group['priced_calls'] += int(known)
        group['usd'] += amount if known else 0
        group['input_tokens'] += row.get('prompt_tokens') or 0
        group['output_tokens'] += row.get('completion_tokens') or 0
    artifact = run_artifacts.lookup(tag) or {}
    saved_calls = run_artifacts.read_json(directory / 'runs.json')
    calls = saved_calls if isinstance(saved_calls, list) else artifact.get('calls', [])
    expected = sum(c.get('llm_requests') or 0 for c in calls)
    unknown = sum(r['usd'] is None for r in records) + malformed
    status = run_artifacts.read_json(directory / 'pipeline_status.json') or {}
    active = status.get('status') not in ('completed','failed','interrupted','cancelled')
    complete = bool(records) and not unknown and len(records) >= expected and not active
    return {'run_tag':tag, 'currency':'USD', 'estimated':True,
            'status':'complete' if complete else 'partial' if records else 'unavailable',
            'usd':sum(g['usd'] for g in groups.values()), 'recorded_calls':len(records),
            'unpriced_calls':unknown, 'expected_calls':expected, 'active':active,
            'coverage_note':'Recorded request attempts only. Provider-side usage without a returned usage record cannot be priced. Historical executions may predate this ledger.',
            'groups':[{'stage':k[0],'model':k[1],**v} for k,v in groups.items()], 'records':records}


def summarize_motoro(tag, calls, runs, steps):
    """Aggregate persisted Motoro amounts only; never apply a token rate."""
    by_id = {c['run_id']: c for c in calls if c.get('run_id')}
    run_ids = {str(r['id']) for r in runs}
    missing = len(set(by_id) - run_ids)
    active = any(r['status'] not in ('completed','failed','cancelled') for r in runs)
    records = []
    malformed = 0
    for step in steps:
        raw = step['llm_call']
        try:
            raw = json.loads(raw) if isinstance(raw,str) else raw
            values = raw if isinstance(raw,list) else raw.get('calls', [raw]) if isinstance(raw,dict) else []
            if not isinstance(values,list):
                raise ValueError('Invalid call collection')
            for index, value in enumerate(values):
                if not isinstance(value,dict):
                    malformed += 1
                    continue
                call = by_id.get(str(step['run_id']))
                if call is None:
                    continue
                amount = value.get('cost_estimate')
                # Motoro 0.10.0 uses zero for missing prices too; do not call it free.
                known = type(amount) in (int,float) and math.isfinite(amount) and amount > 0
                records.append({'id':f"{step['id']}:{index}", 'agent_run_id':str(step['run_id']),
                    'stage':call.get('stage'), 'loop':call.get('loop'), 'model':value.get('model'),
                    'provider':None, 'source':value.get('pricing_source'), 'record_source':'motoro',
                    'usd':amount if known else None, 'reported_cost_estimate':amount,
                    'status':'estimated' if known else 'unknown', 'price_receipt':None,
                    'reason':None if known else 'Motoro did not record an unambiguous price',
                    **{k:value.get(k) for k in ('prompt_tokens','completion_tokens','cache_read_input_tokens',
                                               'cache_creation_input_tokens','latency_ms')}})
        except (ValueError, TypeError):
            malformed += 1
    records = list({r['id']:r for r in records}.values())
    groups = defaultdict(lambda: {'calls':0,'priced_calls':0,'usd':0.,'input_tokens':0,'output_tokens':0})
    for record in records:
        group = groups[(record['stage'],record['model'])]
        group['calls'] += 1
        group['priced_calls'] += record['usd'] is not None
        group['usd'] += record['usd'] or 0
        group['input_tokens'] += record['prompt_tokens'] or 0
        group['output_tokens'] += record['completion_tokens'] or 0
    unknown = sum(r['usd'] is None for r in records) + malformed
    represented = {r['agent_run_id'] for r in records}
    missing += sum(str(r['id']) not in represented for r in runs)
    return {'run_tag':tag, 'source':'motoro', 'currency':'USD', 'estimated':True,
        'status':'complete' if records and not (unknown or active or missing) else 'partial' if records else 'unavailable',
        'usd':sum(g['usd'] for g in groups.values()), 'recorded_calls':len(records),
        'expected_calls':len(records), 'unpriced_calls':unknown, 'missing_runs':missing, 'active':active,
        'coverage_note':'Persisted Motoro LLM call records only. Motoro agent totals are stored to six decimal places, so request subtotals may differ slightly due to rounding. Requests not persisted by Motoro are not included. Missing or ambiguous zero prices stay unknown; no local rate or ledger substitutes for Motoro.',
        'groups':[{'stage':k[0],'model':k[1],**v} for k,v in groups.items()], 'records':records}


async def motoro_details(tag, loop=None):
    from motoro_records import references, read_core
    calls, ids = await references(tag, loop)
    async def read(conn):
        runs = await conn.fetch('SELECT id,status FROM agent_runs WHERE id=ANY($1::uuid[])', list(ids))
        steps = await conn.fetch('''SELECT id,run_id,llm_call::text AS llm_call FROM run_steps
            WHERE run_id=ANY($1::uuid[]) AND llm_call IS NOT NULL ORDER BY started_at,id''', list(ids))
        return runs, steps
    runs, steps = await read_core(read) if ids else ([],[])
    return {**summarize_motoro(tag, calls, runs, steps), 'loop':loop}
