"""Synthetic legacy shapes, failed DDL and bounded startup lock waits."""

import asyncio
import json

import asyncpg
import pytest

from memstara import blackboard

pytestmark = pytest.mark.integration


async def legacy_rows(database):
    """A targeted old shape, not a claim about a specific released version."""
    task = await database.fetchval(
        "INSERT INTO memstara_blackboard(run_tag,trial,status,task_type,hypothesis) "
        "VALUES ('upgrade-test',0,'done','interpret','Synthetic hypothesis') RETURNING task_id")
    result = await database.fetchval(
        "INSERT INTO memstara_results(task_id,run_tag,trial,auc,interpretation) "
        "VALUES ($1,'upgrade-test',0,0.75,'Synthetic evidence') RETURNING result_id", task)
    question = await database.fetchval(
        "INSERT INTO memstara_questions(text,text_key) "
        "VALUES ('Synthetic question','synthetic question') RETURNING question_id")
    for table in ('memstara_blackboard', 'memstara_results'):
        for column in ('y_column', 'model', 'evaluation', 'hypothesis_id', 'match_trace'):
            await database.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
    for column in ('question_contract', 'writer', 'claimed_run', 'claimed_by', 'claimed_at'):
        await database.execute(f'ALTER TABLE memstara_questions DROP COLUMN {column}')
    await database.execute('ALTER TABLE memstara_results DROP CONSTRAINT memstara_results_task_id_fkey')
    await database.execute('ALTER TABLE memstara_results ALTER COLUMN task_id SET NOT NULL')
    await database.execute(
        'ALTER TABLE memstara_results ADD CONSTRAINT memstara_results_task_id_fkey '
        'FOREIGN KEY(task_id) REFERENCES memstara_blackboard(task_id) ON DELETE CASCADE')
    return task, result, question


async def test_additive_upgrade_preserves_legacy_evidence_and_detaches_deleted_tasks(database):
    task, result, question = await legacy_rows(database)
    await blackboard.create()
    row = await database.fetchrow('SELECT * FROM memstara_results WHERE result_id=$1', result)
    assert row['auc'] == 0.75 and row['interpretation'] == 'Synthetic evidence'
    assert row['y_column'] == row['model'] == row['hypothesis_id'] == ''
    assert json.loads(row['evaluation']) == {}
    assert json.loads(row['match_trace']) == []
    assert await database.fetchval(
        'SELECT text FROM memstara_questions WHERE question_id=$1', question) == 'Synthetic question'
    await blackboard.create()
    assert await database.fetchrow('SELECT * FROM memstara_results WHERE result_id=$1', result) == row
    await database.execute('DELETE FROM memstara_blackboard WHERE task_id=$1', task)
    retained = await database.fetchrow('SELECT * FROM memstara_results WHERE result_id=$1', result)
    assert retained['task_id'] is None
    assert retained['interpretation'] == 'Synthetic evidence'


async def test_failed_upgrade_rolls_back_all_ddl_and_preserves_rows(database, monkeypatch):
    _, result, _ = await legacy_rows(database)
    original = blackboard.SCHEMA
    monkeypatch.setattr(blackboard, 'SCHEMA', original + '\nSELECT 1 / 0;')
    with pytest.raises(asyncpg.DivisionByZeroError):
        await blackboard.create()
    assert not await database.fetchval(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() "
        "AND table_name='memstara_results' AND column_name='evaluation')")
    assert await database.fetchval(
        'SELECT interpretation FROM memstara_results WHERE result_id=$1', result) == 'Synthetic evidence'
    assert await database.fetchval(
        "SELECT confdeltype::text FROM pg_constraint WHERE conrelid='memstara_results'::regclass "
        "AND conname='memstara_results_task_id_fkey'") == 'c'
    monkeypatch.setattr(blackboard, 'SCHEMA', original)
    await blackboard.create()
    assert json.loads(await database.fetchval(
        'SELECT evaluation FROM memstara_results WHERE result_id=$1', result)) == {}


async def test_upgrade_lock_timeout_is_bounded_and_retry_succeeds(database):
    async with database.transaction():
        await database.execute('LOCK TABLE memstara_blackboard IN ACCESS SHARE MODE')
        # Exercise the actual entry point's 3s lock timeout, not a mocked driver.
        with pytest.raises(asyncpg.LockNotAvailableError):
            await asyncio.wait_for(blackboard.create(), timeout=12)
        assert await database.fetchval('SELECT count(*) FROM memstara_blackboard') == 0
    await blackboard.create()
