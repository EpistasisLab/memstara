"""Paused recovery against a disposable PostgreSQL schema."""
import json

import asyncpg
import pytest

from memstara.blackboard import dsn
from memstara.pipeline.checkpoint import Checkpoint, atomic_json, RecoveryBlocked
from memstara.pipeline import paused_recovery as recovery

pytestmark = pytest.mark.integration


async def test_reconcile_preserves_completed_and_foreign_tasks(database, tmp_path):
    atomic_json(tmp_path/'config.json', {'run_tag':'paused', 'config_hash':'frozen',
                                       'pause_recovery_policy':recovery.VERSION})
    cp = Checkpoint(tmp_path)
    meta = recovery.metadata(tmp_path, (), {'stage':'ml#1', 'tools':[]}, None)
    cp.call_started('ml', meta)
    recovery.paused(tmp_path, 'ml', meta)
    for tag, status, stage, worker in [('paused','in_progress','ml','ml#1'),
                                      ('paused','done','interpret',''),
                                      ('other','in_progress','ml','ml#1')]:
        await database.execute(
            "INSERT INTO memstara_blackboard(run_tag,trial,status,task_type,claimed_by,evaluation) "
            "VALUES ($1,0,$2,$3,$4,'{\"saved\":true}')",
            tag,
            status,
            stage,
            worker,
        )
    await recovery.reconcile(cp, 'paused', asyncpg.connect, dsn())
    rows = await database.fetch('SELECT run_tag,status,claimed_by,evaluation FROM memstara_blackboard ORDER BY task_id')
    assert [(r['run_tag'],r['status'],r['claimed_by']) for r in rows] == [
        ('paused','ready',''), ('paused','done',''), ('other','in_progress','ml#1')]
    assert all(json.loads(r['evaluation']) == {'saved':True} for r in rows)
    assert not cp.state['calls']
    # Reconciliation can repeat after a SQL commit/checkpoint publication gap.
    original = json.loads(next((tmp_path/'pause_recoveries').glob('*.json')).read_text())
    cp.state = original
    cp.save()
    await recovery.reconcile(cp, 'paused', asyncpg.connect, dsn())
    assert not cp.state['calls']


async def test_foreign_owner_blocks_without_changing_database(database, tmp_path):
    atomic_json(tmp_path/'config.json', {'run_tag':'paused', 'config_hash':'frozen',
                                       'pause_recovery_policy':recovery.VERSION})
    cp = Checkpoint(tmp_path)
    meta = recovery.metadata(tmp_path, (), {'stage':'data#1', 'tools':[]}, None)
    cp.call_started('data', meta)
    recovery.paused(tmp_path, 'data', meta)
    await database.execute(
        "INSERT INTO memstara_blackboard(run_tag,trial,status,task_type,claimed_by) "
        "VALUES ('paused',0,'in_progress','data','different-worker')"
    )
    with pytest.raises(RecoveryBlocked, match='ownership'):
        await recovery.reconcile(cp, 'paused', asyncpg.connect, dsn())
    assert await database.fetchval('SELECT status FROM memstara_blackboard') == 'in_progress'
    assert cp.state['calls'] == {'data':'active'}
