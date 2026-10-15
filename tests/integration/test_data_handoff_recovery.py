"""Exercise the actual MCP recovery transaction against an isolated database."""
import asyncio
import json

import pytest
from memstara.mcp_servers import blackboard as tools

pytestmark = pytest.mark.integration


async def test_missing_handoff_recovery_is_atomic_scoped_and_bounded(database, monkeypatch):
    monkeypatch.setattr(tools, '_pipeline_run', lambda: 'synthetic-recovery')
    task = await database.fetchval(
        "INSERT INTO memstara_blackboard(run_tag,trial,status,task_type,claimed_by,evaluation) "
        "VALUES ('synthetic-recovery',0,'in_progress','data','data#1','{\"preserve\":true}') RETURNING task_id")
    rejected = json.loads(await tools.recover_data_handoff(task, 'data#2'))
    assert 'error' in rejected
    for attempt in range(1, 6):
        replies = await asyncio.gather(tools.recover_data_handoff(task, 'data#1'),
                                       tools.recover_data_handoff(task, 'data#1'))
        assert sum(bool(json.loads(r).get('ok')) for r in replies) == 1
        row = await database.fetchrow('SELECT status, claimed_by, evaluation FROM memstara_blackboard WHERE task_id=$1', task)
        saved = json.loads(row['evaluation'])
        assert row['status'] == 'ready' and row['claimed_by'] == ''
        assert saved['preserve'] is True and saved['data_handoff_recovery_count'] == attempt
        await database.execute("UPDATE memstara_blackboard SET status='in_progress',claimed_by='data#1' WHERE task_id=$1", task)
    assert not json.loads(await tools.recover_data_handoff(task, 'data#1'))['ok']
    monkeypatch.setattr(tools, '_pipeline_run', lambda: 'another-run')
    assert not json.loads(await tools.recover_data_handoff(task, 'data#1'))['ok']
    assert await database.fetchval('SELECT status FROM memstara_blackboard WHERE task_id=$1', task) == 'in_progress'


async def test_committed_data_handoff_is_never_requeued(database, monkeypatch):
    monkeypatch.setattr(tools, '_pipeline_run', lambda: 'synthetic-completed')
    for stage, status in [('ml', 'ready'), ('interpret', 'done'), ('data', 'failed')]:
        task = await database.fetchval(
            "INSERT INTO memstara_blackboard(run_tag,trial,status,task_type,claimed_by) "
            "VALUES ('synthetic-completed',0,$1,$2,'data#1') RETURNING task_id", status, stage)
        assert not json.loads(await tools.recover_data_handoff(task, 'data#1'))['ok']
        row = await database.fetchrow('SELECT status, task_type FROM memstara_blackboard WHERE task_id=$1', task)
        assert (row['status'], row['task_type']) == (status, stage)
