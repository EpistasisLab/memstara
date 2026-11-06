"""Selected clears must not stop, delete or forget another experiment."""
import json
from pathlib import Path
import shutil
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from memstara.control import history, history_scope
from memstara.control.history_gate import execution_files_guard, selected_maintenance
from test_history_clear import Manager, record


@pytest.fixture
def selected(tmp_path, monkeypatch):
    root = tmp_path / 'outputs'
    (root / 'runs').mkdir(parents=True)
    (root / 'runs/pipeline_workspace.json').write_text('preserved settings')
    for tag, owner in [('first', 'a'), ('retry', 'a'), ('other', 'b')]:
        directory = root / 'runs' / tag
        directory.mkdir()
        (directory / 'control_record.json').write_text(json.dumps({'run_tag': tag, 'pipeline_id': owner}))
        (directory / 'report.md').write_text(tag)
        with execution_files_guard(directory):
            pass
    managers = {'a': Manager(active=True), 'b': Manager(active=True)}
    for key, manager in managers.items():
        manager.pipeline_id = key
    standalone = Manager(active=True)
    workspace = SimpleNamespace(lock=threading.RLock(), managers=managers,
        items=[{'id': 'a', 'name': 'Same name'}, {'id': 'b', 'name': 'Same name'}],
        manager=lambda key: managers[key])
    reset = history.HistoryReset(workspace, standalone, root=root, stop_timeout=.01)
    module = history.cleanup_module()
    calls = []
    async def main(apply, *, root, scope, on_phase=None):
        calls.append((apply, scope))
        if apply:
            on_phase('clearing_databases')
            on_phase('clearing_files')
            for path in scope['paths']:
                if Path(path).exists():
                    shutil.rmtree(path)
    monkeypatch.setattr(history, 'cleanup_module', lambda: SimpleNamespace(main=main, preserved=module.preserved))
    plan = {'pipeline_id': 'a', 'run_tags': ['first', 'retry'],
            'paths': [str(root/'runs'/tag) for tag in ['first', 'retry']],
            'runtime_run_ids': [], 'experiment_ids': []}
    monkeypatch.setattr(history_scope, 'plan', AsyncMock(return_value=plan))
    return reset, root, managers, standalone, calls, plan


def test_selected_clear_removes_all_attempts_without_stopping_other_runs(selected):
    reset, root, managers, standalone, calls, plan = selected
    reset._worker({**record(), 'scope': 'selected', 'pipeline_id': 'a', 'pipeline_name': 'Same name'})
    state = reset.status()
    assert state['state'] == 'completed' and state['scope'] == 'selected'
    assert state['execution_count'] == 2 and 'cleanup_plan' not in state
    assert managers['a'].signals == ['old'] and managers['a']._done == []
    assert managers['b'].active and managers['b'].signals == [] and managers['b']._done
    assert standalone.active and standalone.signals == []
    assert not (root/'runs/first').exists() and not (root/'runs/retry').exists()
    assert (root/'runs/other/report.md').read_text() == 'other'
    assert (root/'runs/pipeline_workspace.json').read_text() == 'preserved settings'
    assert calls == [(False, plan), (True, plan)]


def test_selected_backup_failure_never_deletes(selected, monkeypatch):
    reset, root, managers, _, calls, _ = selected
    monkeypatch.setattr(history, 'backup_history', AsyncMock(side_effect=RuntimeError('synthetic failure')))
    reset._worker({**record('backup'), 'scope': 'selected', 'pipeline_id': 'a'})
    assert reset.status()['state'] == 'failed' and not reset.status()['deletion_started']
    assert len(calls) == 1 and (root/'runs/first').exists()
    assert managers['b'].active and not managers['b'].signals


def test_selected_backup_contains_only_selected_execution_files_before_deletion(selected, monkeypatch):
    reset, root, _, _, calls, plan = selected
    async def backup(folder, identifier, paths, *, selection):
        assert selection['scope'] == 'selected' and selection['pipeline_id'] == 'a'
        assert selection['run_tags'] == plan['run_tags']
        assert set(map(str, paths)) == set(plan['paths'])
        assert all(path.exists() for path in paths)
        assert calls == [(False, plan)]
        assert (root/'runs/other/report.md').is_file()
        return {'id': identifier, 'location': 'verified-backup', 'download': '/download'}
    monkeypatch.setattr(history, 'backup_history', backup)
    reset._worker({**record('backup'), 'scope': 'selected', 'pipeline_id': 'a'})
    assert reset.status()['state'] == 'completed'
    assert reset.status()['backup']['location'] == 'verified-backup'
    assert (root/'runs/other/report.md').is_file()


def test_scope_validation_and_request_identity(selected, monkeypatch):
    reset, _, _, _, _, _ = selected
    monkeypatch.setattr(history.threading, 'Thread', lambda **kwargs: SimpleNamespace(start=lambda: None))
    body = {'mode': 'no_backup', 'confirmation': history.SELECTED_CONFIRMATION,
            'scope': 'selected', 'pipeline_id': 'a', 'request_id': str(uuid4())}
    for overrides in [{'pipeline_id': 'missing'}, {'pipeline_id': '../a'}, {'scope': 'all'},
                      {'confirmation': history.CONFIRMATION}, {'pipeline_id': None}]:
        with pytest.raises(ValueError):
            reset.begin({**body, **overrides})
    first = reset.begin(body)
    assert reset.begin(body)['id'] == first['id']
    with pytest.raises(ValueError, match='different scope'):
        reset.begin({**body, 'pipeline_id': 'b'})


def test_partial_failure_keeps_durable_scope_and_cannot_switch_experiments(selected, monkeypatch):
    reset, _, _, _, _, plan = selected
    value = {**record(), 'scope': 'selected', 'pipeline_id': 'a', 'cleanup_plan': plan,
             'state': 'failed', 'deletion_started': True, 'blocked': True}
    reset._save(value)
    monkeypatch.setattr(history.threading, 'Thread', lambda **kwargs: SimpleNamespace(start=lambda: None))
    body = {'mode': 'backup', 'confirmation': history.SELECTED_CONFIRMATION,
            'scope': 'selected', 'pipeline_id': 'a', 'request_id': str(uuid4())}
    with pytest.raises(ValueError, match='original scope'):
        reset.begin({**body, 'pipeline_id': 'b'})
    reset.begin(body)
    assert reset._read()['cleanup_plan'] == plan
    assert reset._read()['deletion_started'] and reset._read()['blocked']


def test_selected_lease_does_not_wait_on_unrelated_execution_or_ml(selected):
    _, root, _, _, _, plan = selected
    with execution_files_guard(root/'runs/other'):
        with selected_maintenance(root, plan['paths']):
            pass
    with execution_files_guard(root/'runs/first'):
        with pytest.raises(RuntimeError, match='still active'):
            with selected_maintenance(root, plan['paths']):
                pytest.fail('Selected run lease must exclude deletion')


def test_inherited_ml_descriptor_prevents_clear_after_parent_closes(selected):
    import os
    _, root, _, _, _, plan = selected
    with execution_files_guard(root/'runs/first') as lock:
        child = os.dup(lock.fileno())
    try:
        with pytest.raises(RuntimeError, match='still active'):
            with selected_maintenance(root, plan['paths']):
                pytest.fail('Inherited descriptor must retain the lease')
    finally:
        os.close(child)
    with selected_maintenance(root, plan['paths']):
        pass


def test_safe_paths_reject_sources_settings_and_symlinks(selected, tmp_path):
    _, root, _, _, _, _ = selected
    for path in [root, root/'runs', root/'runs/pipeline_workspace.json',
                 root/'research_inputs/study.json', tmp_path/'outside']:
        with pytest.raises(RuntimeError):
            history_scope.validate_paths(root, [path])
    (root/'runs/link').symlink_to(root/'runs/other', target_is_directory=True)
    with pytest.raises(RuntimeError):
        history_scope.validate_paths(root, [root/'runs/link'])


def test_selected_memory_plan_never_deletes_shared_agent_memory():
    module = history.cleanup_module()
    plan = module.runtime_cleanup_plan({'agent_runs', 'memory_entries'},
        {'agent_runs': {'id'}, 'memory_entries': {'agent_id', 'run_id'}}, [], include_agent_memories=False)
    predicate = dict(plan)['memory_entries']
    assert 'agent_id' not in predicate and 'run_id' in predicate
    plan = module.runtime_cleanup_plan({'agent_runs', 'memory_entries'},
        {'memory_entries': {'agent_id'}}, [], include_agent_memories=False)
    assert 'FALSE' in dict(plan)['memory_entries']
