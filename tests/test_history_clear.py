"""Destructive workflows use isolated files/fake databases, never the installation."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import tarfile
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from memstara.control import history
from memstara.control.history_gate import execution_guard, maintenance_guard, epoch, ensure_idle, quiescent_ml


class Manager:
    pipeline_id = None
    def __init__(self, active=False):
        self.active, self.signals = active, []
        self._lock = threading.Lock()
        self._live, self._done = None, [{'run_tag': 'old'}]
    def running(self):
        return {'run_tag': 'old'} if self.active else None
    def terminate(self, tag):
        self.signals.append(tag)
        self.active = False


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path/'outputs'; root.mkdir()
    runs = root/'runs'; runs.mkdir()
    (runs/'pipeline_workspace.json').write_text('[{"configuration":"preserve"}]')
    run = runs/'old'; run.mkdir()
    (run/'control_record.json').write_text(json.dumps({'run_tag':'old','pipeline_id':None,'exit_code':0}))
    (run/'report.md').write_text('saved result')
    manager = Manager()
    workspace = SimpleNamespace(lock=threading.RLock(), managers={}, items=[], factory=lambda key:manager)
    reset = history.HistoryReset(workspace,manager,root=root,stop_timeout=.01)
    module = history.cleanup_module()
    events = []
    async def cleanup(apply, *, root, on_phase=None):
        events.append('clear' if apply else 'plan')
        if apply:
            on_phase('clearing_databases')
            on_phase('clearing_files')
            for target in module.targets(root):
                shutil.rmtree(target) if target.is_dir() else target.unlink()
    fake = SimpleNamespace(main=cleanup, targets=module.targets, preserved=module.preserved)
    monkeypatch.setattr(history,'cleanup_module',lambda:fake)
    return reset,root,manager,events


def record(mode='no_backup'):
    from memstara.control.recovery import identity
    return {'id':str(uuid4()),'request_id':str(uuid4()),'state':'stopping','revision':'initial',
            'mode':mode,'deletion_started':False,'blocked':False,
            'owner_pid':os.getpid(),'owner_identity':identity(os.getpid())}


def test_unconfirmed_and_path_injection_requests_never_queue_jobs(setup):
    reset,root,_,_=setup
    for body in ({}, {'mode':'no_backup','confirmation':'yes','request_id':str(uuid4())},
                 {'mode':'backup','confirmation':history.CONFIRMATION,'request_id':str(uuid4()),'root':'/'},
                 {'mode':'backup','confirmation':history.CONFIRMATION,'request_id':'../'}):
        with pytest.raises(ValueError): reset.begin(body)
    assert not reset.state_path.exists() and (root/'runs/old/report.md').exists()


def test_queue_blocks_launches_and_deduplicates_uncertain_requests(setup,monkeypatch):
    reset,root,_,_=setup
    class Thread:
        def __init__(self,**kwargs):pass
        def start(self):pass
    monkeypatch.setattr(history.threading,'Thread',Thread)
    body={'mode':'backup','confirmation':history.CONFIRMATION,'request_id':str(uuid4())}
    first=reset.begin(body)
    assert reset.begin(body)['id']==first['id'] and epoch(root)['busy']
    with pytest.raises(RuntimeError):ensure_idle(root)
    with pytest.raises(RuntimeError):reset.begin({**body,'request_id':str(uuid4())})
    with pytest.raises(ValueError):reset.begin({**body,'mode':'no_backup'})


def test_driver_lease_and_pending_marker_prevent_start_delete_race(tmp_path):
    with execution_guard(tmp_path):
        with pytest.raises(RuntimeError,match='still active'):
            with maintenance_guard(tmp_path):pytest.fail('writer acquired an active lease')
    with maintenance_guard(tmp_path):
        with pytest.raises(RuntimeError,match='maintenance'):
            with execution_guard(tmp_path):pytest.fail('reader started during deletion')


def test_orphaned_ml_worker_lease_prevents_deletion(tmp_path):
    import fcntl
    directory=tmp_path/'research_inputs/prepared/study/derived';directory.mkdir(parents=True)
    with (directory/'.paired-ml.lock').open('a') as worker:
        fcntl.flock(worker,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError,match='ML child is still active'):
            with quiescent_ml(tmp_path):pytest.fail('must wait for inherited worker lease')
    with quiescent_ml(tmp_path):pass


def test_clear_without_backup_preserves_settings_and_clears_runtime_pointers(setup,monkeypatch):
    reset,root,manager,events=setup
    backup=AsyncMock(side_effect=AssertionError('No backup requested'))
    monkeypatch.setattr(history,'backup_history',backup)
    before=(root/'runs/pipeline_workspace.json').read_bytes()
    reset._worker(record())
    state=reset.status()
    assert state['state']=='completed' and not epoch(root)['busy']
    assert not (root/'runs/old').exists() and manager._done==[]
    assert (root/'runs/pipeline_workspace.json').read_bytes()==before
    assert events==['plan','clear']
    backup.assert_not_called()


def test_verified_backup_completes_before_first_deletion(setup,monkeypatch):
    reset,root,_,events=setup
    async def backup(root,identifier,paths):
        assert (root/'runs/old/report.md').is_file()
        assert events==['plan'] and paths
        events.append('backup_verified')
        return {'id':identifier,'location':'private-backup','download':'/download'}
    monkeypatch.setattr(history,'backup_history',backup)
    reset._worker(record('backup'))
    assert reset.status()['state']=='completed'
    assert events==['plan','backup_verified','clear']


def test_backup_failure_preserves_all_history_and_releases_maintenance(setup,monkeypatch):
    reset,root,_,events=setup
    monkeypatch.setattr(history,'backup_history',AsyncMock(side_effect=OSError('private credentials')))
    reset._worker(record('backup'))
    state=reset.status()
    assert state['state']=='failed' and state['failed_phase']=='backing_up'
    assert not state['deletion_started'] and not epoch(root)['busy']
    assert (root/'runs/old/report.md').is_file() and events==['plan']
    assert 'private credentials' not in json.dumps(state)


def test_partial_deletion_is_honest_blocks_launch_and_can_be_explicitly_retried(setup,monkeypatch):
    reset,root,_,_=setup
    module=history.cleanup_module()
    original=module.main
    async def fail(apply,**kwargs):
        if apply:
            kwargs['on_phase']('clearing_databases')
            raise RuntimeError('simulated second database commit failure')
    module.main=fail
    reset._worker(record())
    state=reset.status()
    assert state['state']=='failed' and state['blocked'] and epoch(root)['busy']
    with pytest.raises(RuntimeError):ensure_idle(root)
    module.main=original
    reset._worker(record())
    assert reset.status()['state']=='completed' and not epoch(root)['busy']


def test_active_execution_is_terminated_and_timeout_prevents_deletion(setup,monkeypatch):
    reset,root,manager,events=setup
    manager.active=True
    monkeypatch.setattr(manager,'terminate',lambda tag:manager.signals.append(tag))
    reset._worker(record())
    assert manager.signals==['old'] and events==[]
    assert reset.status()['state']=='failed' and not reset.status()['deletion_started']
    assert (root/'runs/old/report.md').exists()


def test_cleanup_rejects_unknown_or_escaping_targets_and_keeps_epoch_metadata(setup):
    _,root,_,_=setup
    module=history.cleanup_module()
    (root/'runs/history_epoch.json').write_text('{}')
    assert [p.name for p in module.targets(root)]==['old']
    unknown=root/'runs/unknown'; unknown.write_text('do not delete')
    with pytest.raises(RuntimeError,match='Unrecognized'):module.targets(root)
    unknown.unlink()
    logs=root/'logs';logs.mkdir();(logs/'escape').symlink_to(root.parent/'outside')
    with pytest.raises(RuntimeError,match='escapes'):module.targets(root)


def test_complete_backup_contains_both_databases_files_and_verified_manifest(setup,monkeypatch):
    _,root,_,_=setup
    monkeypatch.setenv('MEMSTARA_DATABASE_URL','postgresql://synthetic:private@board/database')
    monkeypatch.setenv('MOTORO_DATABASE_URL','postgresql://synthetic:private@runtime/database')
    calls=[]
    async def utility(args,**kwargs):
        calls.append(args)
        assert 'private' not in ' '.join(args)
        if args[0]=='pg_dump':Path(args[-1]).write_bytes(b'synthetic PG dump')
    monkeypatch.setattr(history,'utility',utility)
    key=str(uuid4())
    result=asyncio.run(history.backup_history(root,key,[root/'runs/old']))
    reset,_,_,_=setup
    bundle=reset.backup_file(key)
    with tarfile.open(bundle) as archive:
        assert set(archive.getnames())=={'board.dump','runtime.dump','execution-files.tar.gz','manifest.json'}
        with tarfile.open(fileobj=archive.extractfile('execution-files.tar.gz'),mode='r:gz') as files:
            assert files.extractfile('runs/old/report.md').read()==b'saved result'
    assert result['id']==key and [c[0] for c in calls]==['pg_dump','pg_restore','pg_dump','pg_restore']
    bundle.write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='verification'):reset.backup_file(key)


def test_failed_database_backup_has_no_complete_marker(setup,monkeypatch):
    _,root,_,_=setup
    monkeypatch.setenv('MEMSTARA_DATABASE_URL','postgresql://synthetic')
    monkeypatch.setattr(history,'utility',AsyncMock(side_effect=RuntimeError('dump failed')))
    with pytest.raises(RuntimeError):asyncio.run(history.backup_history(root,str(uuid4()),[root/'runs/old']))
    assert not list((root/'history-backups').rglob('COMPLETE.json'))
    assert (root/'runs/old/report.md').exists()


@pytest.mark.parametrize('database_failure',[False,True])
def test_real_cleanup_sql_preserves_definitions_and_files_until_database_commit(tmp_path,monkeypatch,database_failure):
    import asyncpg
    module=history.cleanup_module()
    root=tmp_path/'outputs';(root/'runs/old').mkdir(parents=True)
    (root/'runs/old/control_record.json').write_text('{}')
    (root/'runs/pipeline_workspace.json').write_text('saved configuration')
    owned,custom=uuid4(),uuid4()
    board_tables=set(module.BOARD_TABLES)
    board,runtime=AsyncMock(),AsyncMock()
    board_counts={t:1 for t in board_tables}
    for conn in (board,runtime):
        conn.transaction=MagicMock(return_value=SimpleNamespace(start=AsyncMock(),commit=AsyncMock(),rollback=AsyncMock()))
    async def board_fetch(sql,*args):
        if 'pg_tables' in sql:return [{'tablename':t} for t in board_tables]
        if 'pg_constraint' in sql:return []
        if 'agent_run_id' in sql:return [{'agent_run_id':custom}]
        raise AssertionError(sql)
    async def runtime_fetch(sql,*args):
        if 'pg_tables' in sql:return [{'tablename':'agents'},{'tablename':'agent_runs'}]
        if 'JOIN agents' in sql:return [{'id':owned}]
        if 'pg_constraint' in sql or 'information_schema' in sql:return []
        raise AssertionError(sql)
    async def board_execute(sql,*args):
        if sql.startswith('DELETE FROM'):
            if database_failure:raise RuntimeError('synthetic database failure')
            table=sql.split('"')[1];board_counts[table]=0
    async def board_count(sql,*args):return board_counts[sql.split('"')[1]]
    board.fetch.side_effect=board_fetch;runtime.fetch.side_effect=runtime_fetch
    board.execute.side_effect=board_execute;board.fetchval.side_effect=board_count
    runtime.fetchval.return_value=0
    monkeypatch.setattr(asyncpg,'connect',AsyncMock(side_effect=[board,runtime]))
    monkeypatch.setenv('MEMSTARA_DATABASE_URL','postgresql://synthetic')
    monkeypatch.setenv('MOTORO_DATABASE_URL','postgresql://synthetic')
    if database_failure:
        with pytest.raises(RuntimeError):asyncio.run(module.main(True,root=root))
        assert (root/'runs/old/control_record.json').exists()
        assert board.transaction().commit.await_count==runtime.transaction().commit.await_count==0
        assert board.transaction().rollback.await_count==runtime.transaction().rollback.await_count==1
    else:
        asyncio.run(module.main(True,root=root))
        assert not (root/'runs/old').exists()
        assert not any(board_counts.values())
        assert board.transaction().commit.await_count==runtime.transaction().commit.await_count==1
        deletes=[c for c in runtime.execute.call_args_list if c.args[0].startswith('DELETE')]
        assert len(deletes)==1 and set(deletes[0].args[1])=={owned,custom}
        assert all('DELETE FROM public."agents"' not in c.args[0] for c in runtime.execute.call_args_list)
    assert (root/'runs/pipeline_workspace.json').read_text()=='saved configuration'


def test_unknown_board_cascade_dependency_is_rejected_before_deletion():
    module=history.cleanup_module()
    with pytest.raises(RuntimeError,match='Unknown dependency'):
        module.validate_board_dependencies([{'parent':'memstara_executions','child':'saved_settings','child_schema':'public'}])
    module.validate_board_dependencies([{'parent':'memstara_executions','child':'memstara_execution_agents','child_schema':'public'}])
