"""Use genuine asyncpg cursors and verify export deadlines never leak to UI reads."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'viewer/api'))
import export_records
from linked_outputs import decoded

pytestmark = pytest.mark.integration


async def test_large_result_batches_preserve_rows_and_local_deadline(database, monkeypatch):
    await database.executemany(
        "INSERT INTO memstara_results (run_tag, trial, evaluation) VALUES ('export-test', $1, $2::jsonb)",
        [(i, json.dumps({'evidence': 'x' * 100000, 'index': i})) for i in range(19)],
    )

    async def guarded(which, callback, fallback):
        return await callback(database)

    monkeypatch.setattr(export_records.pools, 'guarded', guarded)
    await database.execute("SET statement_timeout = '3500'")
    result = await export_records.results(['export-test'], decoded)
    assert [row['trial'] for row in result] == list(range(19))
    assert all(row['evaluation']['evidence'] == 'x' * 100000 for row in result)
    assert await database.fetchval('SHOW statement_timeout') == '3500ms'

    # The export may exceed a screen query's deadline, and must restore it afterward.
    await database.execute("SET statement_timeout = '1'")
    async def slow_read(conn):
        await conn.execute('SELECT pg_sleep(0.03)', timeout=30)
        assert await conn.fetchval('SHOW transaction_read_only') == 'on'
        return True
    assert await export_records.read(slow_read, 'test') is True
    assert await database.fetchval('SHOW statement_timeout') == '1ms'
    await database.execute("SET statement_timeout = '3500'")

    async def broken(conn):
        raise RuntimeError('synthetic interruption')
    with pytest.raises(RuntimeError):
        await export_records.read(broken, 'test')
    assert await database.fetchval('SHOW statement_timeout') == '3500ms'
    assert not database.is_in_transaction()
