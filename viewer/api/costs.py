"""Workspace cost estimates from distinct, explicitly scoped Motoro run IDs."""
import asyncio
import uuid
from datetime import UTC, datetime
from fastapi import HTTPException
from db import pools
import run_artifacts

SQL = """
SELECT r.id, r.status, r.cost_estimate,
       (r.token_usage->>'prompt_tokens' IS NOT NULL
        AND r.token_usage->>'completion_tokens' IS NOT NULL) AS tokens_recorded,
       COALESCE((r.token_usage->>'prompt_tokens')::bigint, 0)
       + COALESCE((r.token_usage->>'completion_tokens')::bigint, 0) AS tokens
FROM agent_runs r WHERE r.id = ANY($1::uuid[])
"""


def summarize(ids, rows, missing_archives=0):
    by_id = {str(row['id']): row for row in rows}
    total = 0.0
    missing = 0
    pending = 0
    for run_id in ids:
        row = by_id.get(str(run_id))
        if row is None:
            missing += 1
            continue
        cost = row['cost_estimate']
        # Motoro can record zero when pricing is unknown. Do not call it free.
        if cost is None or (float(cost) == 0 and (row['tokens'] > 0 or not row.get('tokens_recorded', True))):
            missing += 1
        else:
            total += float(cost)
        if row['status'] not in ('completed', 'failed', 'cancelled'):
            pending += 1
    return {'usd': total, 'currency': 'USD', 'estimated': True,
            'status': 'partial' if missing or pending or missing_archives else 'complete',
            'agent_runs': len(ids), 'missing_costs': missing, 'pending_runs': pending,
            'missing_archives': missing_archives,
            'updated_at': datetime.now(UTC).isoformat()}


async def workspace_cost(run_tags):
    tags = sorted(set(run_tags))
    if len(tags) > 32 or any(not tag or len(tag) > 180 for tag in tags):
        raise HTTPException(400, 'Choose up to 32 execution IDs')
    async def read(conn, ids):
        return await conn.fetch(SQL, list(ids))
    try:
        async with asyncio.timeout(4):
            artifacts = await asyncio.to_thread(lambda: [run_artifacts.lookup(tag) for tag in tags])
            ids = {uuid.UUID(call['run_id']) for a in artifacts if a
                   for call in a.get('calls', []) if call.get('run_id')}
            rows = await pools.guarded('core', lambda conn: read(conn, ids), None) if ids else []
            if rows is None:
                raise HTTPException(503, 'Cost records are temporarily unavailable')
            result = summarize(ids, rows, sum(a is None for a in artifacts))
            return {**result, 'run_tags': tags, 'scope': 'latest_execution_per_pipeline'}
    except TimeoutError:
        raise HTTPException(503, 'Cost lookup timed out') from None
    except ValueError:
        raise HTTPException(503, 'Execution cost references are incomplete') from None
