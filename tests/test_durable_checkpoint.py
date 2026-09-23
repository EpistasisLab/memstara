"""Offline crash/recovery tests: no model, patient data, or database required."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from memstara.pipeline.checkpoint import Checkpoint, RecoveryBlocked, atomic_json, recovery_status
from memstara.pipeline.exploration import ExecutionGate, rounds


def test_process_death_preserves_completed_work_and_loop_budget(tmp_path):
    script = '''
import asyncio, os, sys
from pathlib import Path
from memstara.pipeline.checkpoint import Checkpoint, atomic_json
root=Path(sys.argv[1]); cp=Checkpoint(root)
async def work():
    with (root/'effects').open('a') as f: f.write('questions\\n')
    return [{'question_id': 7}]
asyncio.run(cp.phase('2:questions', work))
cp.advance(1, waves_run=2, seeded_total=2)
atomic_json(root/'resume_arguments.json', {'run_tag':'same-run'})
os._exit(137)
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], check=False)
    assert result.returncode == 137
    cp = Checkpoint(tmp_path, resume=True)
    async def forbidden():
        raise AssertionError('Completed external work must not repeat')
    assert asyncio.run(cp.phase('2:questions', forbidden)) == [{'question_id': 7}]
    assert (tmp_path/'effects').read_text() == 'questions\n'
    async def remaining():
        return [wave async for wave in rounds(4, False, tmp_path, start=cp.state['next_wave'])]
    assert asyncio.run(remaining()) == [2, 3]
    assert recovery_status(tmp_path)['recoverable']


def test_unknown_external_effects_block_replay(tmp_path):
    cp = Checkpoint(tmp_path)
    cp.call_started('external-call')
    with pytest.raises(RecoveryBlocked, match='external effects'):
        Checkpoint(tmp_path, resume=True)
    status = recovery_status(tmp_path)
    assert not status['recoverable'] and 'external effects' in status['recovery_blocked']


def test_interrupted_phase_and_corrupt_checkpoint_fail_closed(tmp_path):
    cp = Checkpoint(tmp_path)
    async def die():
        raise RuntimeError('Lost process')
    with pytest.raises(RuntimeError):
        asyncio.run(cp.phase('questions', die))
    with pytest.raises(RecoveryBlocked, match='operation was interrupted'):
        Checkpoint(tmp_path, resume=True)
    (tmp_path/'checkpoint.json').write_text('{')
    assert not recovery_status(tmp_path)['recoverable']


def test_completed_execution_cannot_resume(tmp_path):
    cp = Checkpoint(tmp_path)
    cp.finish()
    assert recovery_status(tmp_path) == {'recoverable': False}
    with pytest.raises(RecoveryBlocked, match='ended'):
        Checkpoint(tmp_path, resume=True)


def test_durable_pause_flushes_phase_before_waiting_for_next_call(tmp_path):
    async def scenario():
        cp = Checkpoint(tmp_path)
        gate = ExecutionGate(tmp_path)
        gate.checkpoint = cp
        calls = []
        async def work():
            calls.append('first')
            (tmp_path/'pause.request').touch()
            return {'artifact': 'saved'}
        assert await cp.phase('first', lambda: gate.call(work)) == {'artifact': 'saved'}
        restored = Checkpoint(tmp_path, resume=True)
        assert restored.state['phases']['first']['status'] == 'done'
        async def next_work():
            calls.append('next')
        task = asyncio.create_task(gate.call(next_work))
        await asyncio.sleep(.02)
        assert calls == ['first']
        (tmp_path/'pause.request').unlink()
        await asyncio.wait_for(task, 2)
        assert calls == ['first', 'next']
    asyncio.run(scenario())


def test_controller_resume_keeps_identity_and_appends_log(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.control import service, recovery
    monkeypatch.setattr(service, 'RUNS_DIR', tmp_path)
    root = tmp_path/'run'; root.mkdir()
    cp = Checkpoint(root)
    atomic_json(root/'resume_arguments.json', {'run_tag':'existing', 'pipeline_id':'pipeline-a'})
    recovery.save_record({'run_tag':'existing','pipeline_id':'pipeline-a','run_dir':str(root),
                          'pid':123,'exit_code':1,'started':'original','skill':''})
    (root/'control.log').write_text('original log\n')
    launches = []
    class Child:
        pid = 999
        def __init__(self, argv, **kw):
            launches.append(argv)
            assert kw['stdout'].mode == 'ab'
        def poll(self): return None
    monkeypatch.setattr(service.subprocess, 'Popen', Child)
    monkeypatch.setattr(service, 'identity', lambda pid: 'unique-process')
    manager = service._Runs('pipeline-a')
    assert manager.finished()[0]['recoverable']
    result = manager.pause('existing', False)
    assert result['recovered'] and result['run_tag'] == 'existing'
    assert '--resume' in launches[0] and 'existing' in launches[0]
    assert manager.running()['started'] == 'original'
    assert (root/'control.log').read_text() == 'original log\n'
    manager.pause('existing', False)
    assert len(launches) == 1
    assert not (root/'pause.request').exists()


def test_changed_code_is_not_silently_used_for_recovery(tmp_path, monkeypatch):
    from memstara.pipeline import checkpoint
    Checkpoint(tmp_path)
    monkeypatch.setattr(checkpoint, 'code_hash', lambda: 'different-code')
    with pytest.raises(RecoveryBlocked, match='code changed'):
        Checkpoint(tmp_path, resume=True)


def test_controller_refuses_unknown_effects_without_spawning(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.control import service, recovery
    monkeypatch.setattr(service, 'RUNS_DIR', tmp_path)
    root = tmp_path/'run'; root.mkdir()
    cp = Checkpoint(root)
    cp.call_started('unfinished-model-call')
    atomic_json(root/'resume_arguments.json', {'run_tag':'existing','pipeline_id':'a'})
    recovery.save_record({'run_tag':'existing','pipeline_id':'a','run_dir':str(root),
                          'pid':123,'exit_code':1,'started':'original'})
    def forbidden(*args, **kwargs):
        raise AssertionError('Must not launch a process while effects are uncertain')
    monkeypatch.setattr(service.subprocess, 'Popen', forbidden)
    manager = service._Runs('a')
    assert not manager.finished()[0]['recoverable']
    with pytest.raises(RuntimeError, match='external effects'):
        manager.pause('existing', False)


def test_resume_preserves_console_history(tmp_path):
    from memstara.logging_setup import tee_console
    path = tmp_path/'console.log'
    path.write_text('before crash\n')
    with tee_console(path, append=True):
        print('after resume')
    assert path.read_text() == 'before crash\nafter resume\n'
