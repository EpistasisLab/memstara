"""Read-only, versioned result cache for output screens; never used by exports.

Postgres tuple versions detect updates as well as inserts and deletes. This does
not assume that a completed result can never receive a later Interpretation.
No schema changes, checkpoint writes or experiment mutations are required.
"""
import asyncio
from collections import OrderedDict

from fastapi import HTTPException
from db import pools
import queries
import scene
from display_results import results as project

_cache = OrderedDict()
_locks = {}
MAX_RUNS = 16
VERSIONS = """SELECT result_id, xmin::text AS version, ctid::text AS location
FROM memstara_results WHERE run_tag = $1 ORDER BY result_id"""
CHANGED = queries.RESULTS.replace("($1 = '' OR run_tag = $1)",
                                  "run_tag = $1 AND result_id = ANY($2::bigint[])")


async def results(tag):
    async with _locks.setdefault(tag, asyncio.Lock()):
        previous = _cache.get(tag, {})

        async def query(conn):
            # Versions and payloads describe one DB snapshot, even if a writer
            # updates a result between these SELECTs.
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                versions = await conn.fetch(VERSIONS, tag)
                changed = [v['result_id'] for v in versions if
                           previous.get(v['result_id'], (None,))[0] != (v['version'], v['location'])]
                loaded = {}
                for offset in range(0, len(changed), 32):
                    raw = await conn.fetch(CHANGED, tag, changed[offset:offset + 32])
                    rows = await asyncio.to_thread(lambda raw=raw: project(scene._result_rows(raw)))
                    loaded.update({r['result_id']: r for r in rows})
            updated = {}
            for version in versions:
                key = version['result_id']
                row = loaded[key] if key in loaded else previous[key][1]
                updated[key] = ((version['version'], version['location']), row)
            return updated

        updated = await pools.guarded('memstara', query, None)
        if updated is None:
            raise HTTPException(503, 'Saved results are temporarily unavailable; retained records are unchanged.')
        _cache[tag] = updated
        _cache.move_to_end(tag)
        while len(_cache) > MAX_RUNS:
            _cache.popitem(last=False)
        return [entry[1] for entry in updated.values()]
