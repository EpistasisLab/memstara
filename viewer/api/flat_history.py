"""Reuse immutable completed invocations; refresh active history on every read.

Only compact tool attribution is cached, never clinical datasets or full ML payloads.
Cache entries expire after an hour so manual archive corrections are eventually read.
The cache is per observer process and is not required for correctness after restart.
"""
import json
import time
from collections import OrderedDict
import queries

_cache = OrderedDict()
_COLUMNS = ('run_id','step_id','started_at','server','tool','arguments','result')


def compact(row):
    values = list(row[k] for k in _COLUMNS)
    if values[-1]:
        payload = json.loads(values[-1])
        if isinstance(payload, dict):
            values[-1] = json.dumps({k: payload[k] for k in ('task_id','run_tag','error') if k in payload})
    return tuple(values)


async def build_flat(conn, ids):
    states = await conn.fetch('SELECT id, completed_at FROM agent_runs WHERE id=ANY($1::uuid[])', ids)
    completed = {r['id']: r['completed_at'] for r in states}
    rows=[]; missing=[]; now=time.monotonic()
    for identifier in ids:
        hit=_cache.get(identifier)
        if hit and completed.get(identifier) is not None and hit[1]==completed[identifier] and now-hit[0]<3600:
            rows.extend(hit[2]); _cache.move_to_end(identifier)
        else:
            missing.append(identifier)
    # Keep each SQL statement below the server deadline. Cold archives are prepared
    # by a shared background read; completed batches survive a disconnected client.
    for start in range(0,len(missing),50):
        batch=missing[start:start+50]
        await conn.execute('TRUNCATE selected_run_ids')
        await conn.executemany('INSERT INTO selected_run_ids VALUES ($1)',[(v,) for v in batch])
        await conn.execute('ANALYZE selected_run_ids')
        await conn.execute(queries.SCOPED_FLAT_TEMP_TABLE)
        fresh=[compact(r) for r in await conn.fetch('SELECT * FROM flat')]
        rows.extend(fresh)
        grouped={identifier:[] for identifier in batch}
        for row in fresh:grouped[row[0]].append(row)
        for identifier in batch:
            if completed.get(identifier) is not None:
                _cache[identifier]=(time.monotonic(),completed[identifier],grouped[identifier])
                _cache.move_to_end(identifier)
        while len(_cache)>5000:_cache.popitem(last=False)
    await conn.execute('TRUNCATE selected_run_ids')
    await conn.executemany('INSERT INTO selected_run_ids VALUES ($1)',[(v,) for v in ids])
    await conn.execute('ANALYZE selected_run_ids')
    await conn.execute('''DROP TABLE IF EXISTS flat;
        CREATE TEMP TABLE flat (run_id uuid, step_id uuid, started_at timestamptz,
        server text, tool text, arguments jsonb, result text)''')
    if rows:
        # JSONB COPY requires a binary codec; use typed inserts for portable read-only sessions.
        await conn.executemany('INSERT INTO flat VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7)',rows)
