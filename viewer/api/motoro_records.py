"""Authoritative Motoro records, joined only through saved invocation IDs.

Memstara owns execution/loop attribution; all runtime fields below come from Motoro.
Large input/output and configuration payloads are fetched only on explicit selection.
"""
import asyncio
import json
import re
import uuid
from fastapi import HTTPException
from db import pools
import run_artifacts
from loop_history import call_loops


def redacted(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if re.search(r'(?i)(api[-_]?key|authorization|password|secret|credential|access[-_]?token|refresh[-_]?token|dsn|database_url)', k) else redacted(v) for k,v in value.items()}
    if isinstance(value, list):
        return [redacted(v) for v in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = None
        if isinstance(parsed, (dict,list)):
            return json.dumps(redacted(parsed), ensure_ascii=False)
        value = re.sub(r'(?i)\bBearer\s+[^\s"\']+', 'Bearer [REDACTED]', value)
        return re.sub(r'://[^/\s:@]+:[^@\s]+@', '://[REDACTED]@', value)
    return value


async def references(tag, loop=None):
    artifact = await asyncio.to_thread(run_artifacts.lookup, tag)
    if not artifact:
        raise HTTPException(404, 'Execution archive not found')
    calls = [c for c in call_loops(artifact.get('calls', [])) if loop is None or c['loop'] == loop]
    try:
        ids = {uuid.UUID(c['run_id']) for c in calls if c.get('run_id')}
    except (TypeError,ValueError):
        raise HTTPException(503, 'Recorded invocation references are invalid') from None
    return calls, ids


async def read_core(callback):
    try:
        async with asyncio.timeout(10):
            rows = await pools.guarded('core', callback, None)
    except TimeoutError:
        raise HTTPException(503, 'Motoro records timed out; retry is safe') from None
    if rows is None:
        raise HTTPException(503, 'Motoro records are unavailable; no local substitute is used')
    return rows


async def execution(tag, loop=None):
    calls, ids = await references(tag, loop)
    async def read(conn):
        return await conn.fetch('''SELECT r.id, r.agent_id, r.status, r.started_at, r.completed_at,
            r.last_heartbeat_at, r.token_usage, r.cost_estimate, r.error
            FROM agent_runs r WHERE r.id = ANY($1::uuid[])''', list(ids))
    rows = await read_core(read) if ids else []
    indexed = {str(r['id']): redacted(dict(r)) for r in rows}
    result = []
    for call in calls:
        record = indexed.get(call.get('run_id'))
        if record:
            usage = record.get('token_usage')
            record['token_usage'] = json.loads(usage) if isinstance(usage,str) else usage
        result.append({'run_id':call.get('run_id'), 'stage':call.get('stage'),
                       'loop':call.get('loop'), 'loop_source':call.get('loop_source'),
                       'seq':call.get('seq'), 'record':record,
                       'availability':'available' if record else 'missing'})
    return {'run_tag':tag, 'loop':loop, 'source':'motoro', 'calls':result,
            'note':'Runtime fields are read from Motoro. Pipeline and loop attribution comes from Memstara. A stored running state is not proof of process liveness.'}


async def run(tag, run_id):
    _, ids = await references(tag)
    identity = uuid.UUID(str(run_id))
    if identity not in ids:
        raise HTTPException(404, 'Invocation does not belong to this execution')
    async def read(conn):
        return await conn.fetch('SELECT row_to_json(r)::text AS record FROM agent_runs r WHERE id=$1', identity)
    rows = await read_core(read)
    if not rows:
        raise HTTPException(404, 'Motoro invocation record not found')
    return {'run_tag':tag, 'run_id':str(identity), 'source':'motoro',
            'record':redacted(json.loads(rows[0]['record'])),
            'note':'Original recorded fields; credential fields are redacted. Missing fields remain missing.'}
