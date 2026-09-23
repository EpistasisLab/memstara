"""Session-loss detection, cancellation and recovery without models or real DBs."""
import asyncio
import json
from unittest.mock import AsyncMock
import pytest
from memstara import blackboard as board
from memstara.pipeline import run_ownership as own
from memstara.pipeline.checkpoint import Checkpoint, RecoveryBlocked, atomic_json
from memstara.pipeline.exploration import ExecutionGate


class Connection:
    def __init__(self):
        self.closed=False
        self.listeners=[]
        self.fetchval=AsyncMock(return_value=True)
        self.execute=AsyncMock(return_value='SELECT 1')
    def is_closed(self): return self.closed
    def add_termination_listener(self, listener): self.listeners.append(listener)
    def remove_termination_listener(self, listener):
        if listener in self.listeners: self.listeners.remove(listener)
    def break_connection(self):
        self.closed=True
        for listener in list(self.listeners): listener(self)
    async def close(self, **kwargs): self.break_connection()
    def terminate(self): self.break_connection()


@pytest.fixture
def connection(monkeypatch):
    c=Connection()
    monkeypatch.setattr(board.asyncpg,'connect',AsyncMock(return_value=c))
    monkeypatch.setattr(board,'dsn',lambda:'unused')
    return c


def test_normal_completion_unlocks_without_false_loss(connection):
    async def run():
        async with board.run_lock('test'):
            own.require_ownership()
    asyncio.run(run())
    connection.execute.assert_awaited_once()
    assert not connection.listeners


def test_disconnect_cancels_work_and_never_queries_closed_session(connection):
    events=[]
    async def run():
        with pytest.raises(own.RunOwnershipLost):
            async with board.run_lock('test',on_lost=events.append):
                asyncio.get_running_loop().call_soon(connection.break_connection)
                await asyncio.sleep(10)
                pytest.fail('Work continued after losing ownership')
    asyncio.run(run())
    assert events==['lock_connection_closed']
    connection.execute.assert_not_awaited()


def test_unresponsive_connection_triggers_monitor(connection,monkeypatch):
    original=own.RunLease.__init__
    def init(self,*args,**kw): original(self,*args,**kw,interval=.001,timeout=.001)
    monkeypatch.setattr(own.RunLease,'__init__',init)
    connection.fetchval.side_effect=[True, TimeoutError()]
    async def run():
        with pytest.raises(own.RunOwnershipLost):
            async with board.run_lock('test'):
                await asyncio.sleep(10)
    asyncio.run(run())
    assert connection.closed


def test_existing_owner_is_not_displaced(connection):
    connection.fetchval.return_value=False
    async def run():
        with pytest.raises(board.BoardBusy):
            async with board.run_lock('same'):
                pytest.fail('A second driver must not start')
    asyncio.run(run())
    connection.execute.assert_not_awaited()


def test_cleanup_failure_preserves_original_exception(connection):
    connection.execute.side_effect=RuntimeError('Cleanup broke')
    async def run():
        with pytest.raises(ValueError,match='original'):
            async with board.run_lock('test'):
                raise ValueError('original')
    asyncio.run(run())
    assert connection.closed


def test_cleanup_warning_does_not_destroy_completed_status(connection,tmp_path):
    connection.execute.side_effect=RuntimeError('Cleanup broke')
    atomic_json(tmp_path/'pipeline_status.json',{'status':'completed','report_completed':True})
    async def run():
        with pytest.raises(own.RunLockCleanupError):
            async with board.run_lock('test'): pass
    asyncio.run(run())
    assert own.record_cleanup_warning(tmp_path)==0
    assert json.loads((tmp_path/'pipeline_status.json').read_text())['status']=='completed'
    assert own.infrastructure_status(tmp_path)['infrastructure_status']['status']=='cleanup_warning'


def test_uncertain_call_stays_blocked_and_saved_phase_never_repeats(connection,tmp_path):
    cp=Checkpoint(tmp_path)
    gate=ExecutionGate(tmp_path);gate.checkpoint=cp
    async def run():
        async def saved(): return 'already saved'
        await cp.phase('completed',saved)
        async def interrupted():
            connection.break_connection()
            await asyncio.sleep(10)
        with pytest.raises(own.RunOwnershipLost):
            async with board.run_lock('test',on_lost=lambda reason:own.record_interruption(tmp_path,reason)):
                await gate.call(interrupted)
    asyncio.run(run())
    state=json.loads(cp.path.read_text())
    assert not state['finished'] and state['phases']['completed']['result']=='already saved'
    assert 'active' in state['calls'].values()
    with pytest.raises(RecoveryBlocked,match='external effects'):
        Checkpoint(tmp_path,resume=True)
    assert json.loads((tmp_path/'pipeline_status.json').read_text())['status']=='interrupted'


def test_boundary_checkpoint_can_resume_without_repeating_completed_phase(connection,tmp_path):
    cp=Checkpoint(tmp_path)
    async def saved(): return 'saved result'
    async def run():
        with pytest.raises(own.RunOwnershipLost):
            async with board.run_lock('test'):
                await cp.phase('done',saved)
                connection.break_connection()
                await asyncio.sleep(1)
    asyncio.run(run())
    resumed=Checkpoint(tmp_path,resume=True)
    async def forbidden(): pytest.fail('Repeated completed work')
    assert asyncio.run(resumed.phase('done',forbidden))=='saved result'


def test_closed_session_detected_at_dispatch_even_before_listener(connection):
    async def run():
        with pytest.raises(own.RunOwnershipLost):
            async with board.run_lock('test'):
                connection.closed=True
                own.require_ownership()
    asyncio.run(run())
    connection.execute.assert_not_awaited()
