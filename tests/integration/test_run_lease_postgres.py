"""Prove heartbeat ownership checks against actual advisory locks."""
import asyncio
import zlib
import pytest
from memstara.blackboard import run_lock
from memstara.pipeline import run_ownership as own

pytestmark = pytest.mark.integration


async def test_same_session_lock_verification_and_missing_lock(database, monkeypatch):
    original = own.RunLease.__init__
    monkeypatch.setattr(own.RunLease, '__init__',
                        lambda self, *a, **k: original(self, *a, **k, interval=.02))
    states = []
    with pytest.raises(own.RunOwnershipLost):
        async with run_lock('heartbeat-test', on_health=states.append):
            lease = own._current.get()
            first = lease.last_success
            await asyncio.sleep(.15)
            assert lease.last_success > first
            assert not lease.lost
            # Same connection remains live but no longer owns its execution lock.
            lease.monitor.cancel()
            await asyncio.gather(lease.monitor, return_exceptions=True)
            await lease.connection.execute('SELECT pg_advisory_unlock($1)', zlib.crc32(b'heartbeat-test'))
            lease.monitor = asyncio.create_task(lease.watch())
            await asyncio.sleep(1)
    assert states[-1]['reason'] == 'execution_lock_missing'
