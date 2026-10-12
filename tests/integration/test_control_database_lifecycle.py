"""Combine real control HTTP restarts, execution gating and PostgreSQL ownership."""

import asyncio
import sys
from pathlib import Path

import asyncpg
import pytest

from memstara.blackboard import BoardBusy, dsn, run_lock

pytestmark = pytest.mark.integration

# The same isolated HTTP harness is also exercised without a database in default CI.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_control_process_restart import WORKER, exercise_restart  # noqa: E402


async def test_restart_pause_end_preserve_database_ownership(database, tmp_path):
    await database.execute('CREATE TABLE lifecycle_ticks (id integer PRIMARY KEY)')
    worker = WORKER.replace(
        'from memstara.pipeline.exploration import ExecutionGate',
        'from memstara.pipeline.exploration import ExecutionGate\n'
        'from memstara.blackboard import run_lock\n'
        'from memstara.pipeline.run_ownership import _current')
    worker = worker.replace(
        "        atomic_json(root / 'ticks.json', {'count': counter})",
        "        await _current.get().connection.execute('INSERT INTO lifecycle_ticks VALUES ($1)', counter)\n"
        "        atomic_json(root / 'ticks.json', {'count': counter})")
    worker = worker.replace(
        'try:\n    asyncio.run(main())',
        'async def owned():\n'
        "    async with run_lock('synthetic-restart'):\n"
        '        await main()\n'
        'try:\n    asyncio.run(owned())')
    counts = {}

    async def verify(stage):
        if stage != 'ended':
            with pytest.raises(BoardBusy):
                async with run_lock('synthetic-restart'):
                    pytest.fail('A second worker acquired the active execution')
        else:
            async with run_lock('synthetic-restart'):
                pass
        conn = await asyncpg.connect(dsn())
        try:
            counts[stage] = await conn.fetchval('SELECT count(*) FROM lifecycle_ticks')
            assert counts[stage] > 0
            if stage == 'paused':
                await asyncio.sleep(.35)
                assert await conn.fetchval('SELECT count(*) FROM lifecycle_ticks') == counts[stage]
        finally:
            await conn.close()

    await asyncio.to_thread(exercise_restart, tmp_path, worker,
                            lambda stage: asyncio.run(verify(stage)))
    assert counts['ended'] > counts['paused'] >= counts['restarted']
    assert await database.fetchval('SELECT count(*) FROM lifecycle_ticks') == counts['ended']


async def test_committed_database_effect_is_not_replayed_after_worker_crash(database, tmp_path):
    from memstara.pipeline.checkpoint import Checkpoint, RecoveryBlocked

    await database.execute('CREATE TABLE lifecycle_effects (id integer PRIMARY KEY)')
    script = '''
import asyncio, os, sys
from pathlib import Path
from memstara.blackboard import run_lock
from memstara.pipeline.checkpoint import Checkpoint
from memstara.pipeline.exploration import ExecutionGate
from memstara.pipeline.run_ownership import _current
async def main():
    root = Path(sys.argv[1])
    checkpoint = Checkpoint(root)
    gate = ExecutionGate(root)
    gate.checkpoint = checkpoint
    async with run_lock('synthetic-crash'):
        async def effect():
            await _current.get().connection.execute('INSERT INTO lifecycle_effects VALUES (1)')
            os._exit(137)
        await gate.call(effect)
asyncio.run(main())
'''
    proc = await asyncio.create_subprocess_exec(
        sys.executable, '-c', script, str(tmp_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), 20)
        assert proc.returncode == 137, stderr.decode()
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    assert await database.fetchval('SELECT count(*) FROM lifecycle_effects') == 1
    async with run_lock('synthetic-crash'):
        with pytest.raises(RecoveryBlocked, match='external effects require review'):
            Checkpoint(tmp_path, resume=True)
    assert await database.fetchval('SELECT count(*) FROM lifecycle_effects') == 1
