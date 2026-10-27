"""Acknowledged pauses survive process loss; unknown effects stay blocked."""
import asyncio
import json
import subprocess
import sys
from contextlib import asynccontextmanager

import pytest

from memstara.pipeline import paused_recovery as recovery
from memstara.pipeline.checkpoint import Checkpoint, RecoveryBlocked, atomic_json
from memstara.pipeline.exploration import ExecutionGate


def frozen(root):
    atomic_json(root/'config.json', {'pause_recovery_policy': recovery.VERSION,
                                   'run_tag': 'test-run', 'config_hash': 'frozen'})


class Board:
    def __init__(self, rows=()):
        self.rows, self.writes, self.closed = rows, [], False

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetch(self, query, tag):
        assert tag == 'test-run' and 'FOR UPDATE' in query
        return self.rows

    async def execute(self, query, tag):
        assert tag == 'test-run'
        self.writes.append(query)

    async def close(self):
        self.closed = True

    async def connect(self, dsn):
        return self


def test_paused_agent_process_death_restarts_only_incomplete_agent(tmp_path):
    frozen(tmp_path)
    script = '''
import asyncio, os, sys
from pathlib import Path
from memstara.pipeline.checkpoint import Checkpoint
from memstara.pipeline.exploration import ExecutionGate
from memstara.pipeline.request_pause import mark_waiting
root=Path(sys.argv[1]); cp=Checkpoint(root); gate=ExecutionGate(root); gate.checkpoint=cp
async def done(): return {'saved': 'prior output'}
async def agent(*args, **kwargs):
    with (root/'requests').open('a') as f: f.write('first\\n')
    (root/'pause.request').touch()
    mark_waiting(True)
    os._exit(137)
async def run():
    await cp.phase('0:questions', done)
    await cp.phase('0:seed', lambda: gate.call(agent, 'agent-id', 'prompt', stage='hypothesis1', tools=[]))
asyncio.run(run())
'''
    assert subprocess.run([sys.executable, '-c', script, str(tmp_path)]).returncode == 137
    cp = Checkpoint(tmp_path, resume=True)
    board = Board()
    asyncio.run(recovery.reconcile(cp, 'test-run', board.connect, 'test'))
    (tmp_path/'pause.request').unlink()
    gate = ExecutionGate(tmp_path)
    gate.checkpoint = cp
    async def forbidden():
        raise AssertionError('Completed output must not be regenerated')
    async def fresh(*args, **kwargs):
        with (tmp_path/'requests').open('a') as f:
            f.write('fresh\n')
        return {'created': True}
    assert asyncio.run(cp.phase('0:questions', forbidden)) == {'saved': 'prior output'}
    assert asyncio.run(cp.phase('0:seed', lambda: gate.call(fresh, 'new-id', 'prompt', stage='hypothesis1', tools=[]))) == {'created': True}
    assert (tmp_path/'requests').read_text() == 'first\nfresh\n'
    assert len(list((tmp_path/'pause_recoveries').glob('*.json'))) == 1
    assert board.closed and len(board.writes) == 2


@pytest.mark.parametrize('damage', ['missing', 'corrupt', 'foreign', 'unknown_tool', 'code'])
def test_unproven_pause_cannot_resume(tmp_path, monkeypatch, damage):
    frozen(tmp_path)
    cp = Checkpoint(tmp_path)
    meta = recovery.metadata(tmp_path, ('id','prompt'), {'stage':'data#1', 'tools':[]}, None)
    if damage == 'unknown_tool':
        meta = recovery.metadata(tmp_path, (), {'stage':'data#1', 'tools':[{'name':'send_email'}]}, None)
    if damage == 'foreign':
        meta['run_tag'] = 'different-run'
    cp.call_started('unfinished', meta)
    if damage != 'missing':
        recovery.paused(tmp_path, 'unfinished', meta)
    if damage == 'corrupt':
        atomic_json(tmp_path/'paused_agents/unfinished.json', {'metadata':meta, 'digest':'wrong'})
    if damage == 'code':
        monkeypatch.setattr('memstara.pipeline.checkpoint.code_hash', lambda:'different')
    with pytest.raises(RecoveryBlocked):
        Checkpoint(tmp_path, resume=True)


def test_reconciliation_checks_owner_and_only_releases_unfinished_rows(tmp_path):
    frozen(tmp_path)
    cp = Checkpoint(tmp_path)
    meta = recovery.metadata(tmp_path, (), {'stage':'ml#1', 'tools':[]}, None)
    cp.call_started('ml', meta)
    recovery.paused(tmp_path, 'ml', meta)
    wrong = Board([{'task_id':1, 'task_type':'ml', 'claimed_by':'unrelated'}])
    before = cp.path.read_bytes()
    with pytest.raises(RecoveryBlocked, match='ownership'):
        asyncio.run(recovery.reconcile(cp, 'test-run', wrong.connect, 'test'))
    assert not wrong.writes and wrong.closed and cp.path.read_bytes() == before
    correct = Board([{'task_id':1, 'task_type':'ml', 'claimed_by':'ml#1'}])
    asyncio.run(recovery.reconcile(cp, 'test-run', correct.connect, 'test'))
    assert "WHERE run_tag=$1 AND status='in_progress'" in correct.writes[0]
    assert 'evaluation=' not in correct.writes[0]
    assert not cp.state['calls']


def test_completed_agent_survives_enclosing_phase_commit_gap(tmp_path):
    frozen(tmp_path)
    cp = Checkpoint(tmp_path)
    gate = ExecutionGate(tmp_path)
    gate.checkpoint = cp
    calls = []
    async def agent(*args, **kwargs):
        calls.append(1)
        return {'report':'complete'}
    async def interrupted():
        await gate.call(agent, 'old-id', 'same prompt', stage='report', tools=[])
        raise RuntimeError('Process lost before phase commit')
    with pytest.raises(RuntimeError):
        asyncio.run(cp.phase('final_report', interrupted))
    cp = Checkpoint(tmp_path, resume=True)
    board = Board()
    asyncio.run(recovery.reconcile(cp, 'test-run', board.connect, 'test'))
    gate.checkpoint = cp
    result = asyncio.run(cp.phase('final_report', lambda: gate.call(agent, 'new-id', 'same prompt', stage='report', tools=[])))
    assert result == {'report':'complete'} and calls == [1]
