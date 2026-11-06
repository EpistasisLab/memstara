"""Bounded, read-only evidence reads with deadlines scoped to the export transaction.

The live screen uses a 3.5-second SQL deadline. Exporting hundreds of MiB must
not inherit that deadline or fetch all cost receipts in one network operation.
No global pool setting is changed; SET LOCAL is reverted on commit/rollback.
"""
import asyncio
import logging

from fastapi import HTTPException
from db import pools
from experiments import decode

logger = logging.getLogger('uvicorn.error.viewer')
BATCH_SIZE = 8
QUERY_TIMEOUT = 30


async def rows(conn, sql, *args, decoder=decode):
    cursor = await conn.cursor(sql, *args, timeout=QUERY_TIMEOUT)
    result = []
    while batch := await cursor.fetch(BATCH_SIZE, timeout=QUERY_TIMEOUT):
        result.extend(await asyncio.to_thread(lambda: [decoder(row) for row in batch]))
    return result


async def read(callback, stage):
    async def transaction(conn):
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            await conn.execute("SET LOCAL statement_timeout = '30000'", timeout=QUERY_TIMEOUT)
            return await callback(conn)

    result = await pools.guarded('memstara', transaction, None)
    if result is None:
        logger.warning('Linked export database read failed: stage=%s', stage)
        raise HTTPException(503, f'Export could not read {stage}. No partial file was exported; retry when the database is available.')
    return result


async def results(tags, decoder):
    return await read(lambda conn: rows(conn,
        'SELECT * FROM memstara_results WHERE run_tag = ANY($1::text[]) ORDER BY result_id',
        tags, decoder=decoder), 'saved results')


async def execution(tag):
    async def fetch(conn):
        record = await conn.fetchrow('SELECT * FROM memstara_executions WHERE run_tag=$1',
                                     tag, timeout=QUERY_TIMEOUT)
        if not record:
            # Return a marker through guarded(), which otherwise consumes HTTPException.
            return {'not_registered': True}
        value = await asyncio.to_thread(decode, record)
        for key, table, order in [('agents', 'memstara_execution_agents', 'started_at, agent_run_id'),
                                  ('costs', 'memstara_execution_costs', 'id'),
                                  ('artifacts', 'memstara_execution_artifacts', 'path')]:
            value[key] = await rows(conn, f'SELECT * FROM {table} WHERE run_tag=$1 ORDER BY {order}', tag)
        # Linked exports already hold the authoritative result snapshot. Do not fetch
        # and decode the same large evaluations here only to replace them afterward.
        return value

    value = await read(fetch, 'execution registry')
    if value.get('not_registered'):
        raise HTTPException(404, 'Execution is not registered')
    return value
