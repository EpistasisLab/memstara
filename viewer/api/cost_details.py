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


def azure_summary():
    path = run_artifacts.ROOT / 'azure_costs.json'
    try:
        data = json.loads(path.read_text())
        return {k:data[k] for k in ('status','retrieved_at','period','scope_type','totals','basis')}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status':'unavailable','basis':'Azure Cost Management has not been synchronized. No billed amount is assumed.'}
