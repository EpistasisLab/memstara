import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


def module():
    spec = importlib.util.spec_from_file_location('restore_without_rebuild',
        Path(__file__).resolve().parents[1] / 'deployment/restore-experiments-without-rebuild.py')
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_merge_preserves_active_definition_and_restores_original_ids():
    restore = module()
    active = {'id': 'active', 'number': 3, 'configuration': {'untouched': True}}
    first, second = {'id': 'old1', 'number': 1}, {'id': 'old2', 'number': 2}
    assert restore.merge([active], [first, second]) == [first, second, active]
    assert restore.merge([first, second, active], [first, second]) == [first, second, active]
    with pytest.raises(ValueError, match='occupied'):
        restore.merge([active], [{'id': 'different', 'number': 3}])


def test_preflight_failure_never_stops_controller(monkeypatch):
    restore = module()
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        if argv[:3] == ['docker', 'compose', 'ps']:
            return SimpleNamespace(stdout='existing-container')
        if argv[1] == 'inspect':
            return SimpleNamespace(stdout='sha256:original')
        raise subprocess.CalledProcessError(1, argv, stderr='Recovery blocked')
    monkeypatch.setattr(restore, 'run', run)
    monkeypatch.setattr(restore.sys, 'argv', ['restore', '--restore', '1=original', '--apply'])
    with pytest.raises(subprocess.CalledProcessError):
        restore.main()
    assert not any(command[1] in ('stop', 'start', 'run') for command in calls)


def test_restore_failure_restarts_exact_original_container(tmp_path, monkeypatch):
    restore = module()
    workspace = tmp_path / 'outputs/runs/pipeline_workspace.json'
    workspace.parent.mkdir(parents=True)
    workspace.write_text('[]')
    plan = {'workspace': '/app/outputs/runs/pipeline_workspace.json', 'paused': [],
            'sha256': restore.hashlib.sha256(workspace.read_bytes()).hexdigest()}
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        if argv[:3] == ['docker', 'compose', 'ps']:
            return SimpleNamespace(stdout='existing-container')
        if argv[1] == 'inspect':
            return SimpleNamespace(stdout='sha256:original')
        if argv[1] == 'exec':
            return SimpleNamespace(stdout=json.dumps(plan))
        if argv[1] == 'run':
            assert 'sha256:original' in argv
            assert '--network' in argv and 'none' in argv
            raise subprocess.CalledProcessError(1, argv, stderr='Workspace changed')
        return SimpleNamespace(stdout='')
    from memstara.control import restore as definition_module
    monkeypatch.setattr(definition_module, 'definition', lambda *args: {'id': 'original-id', 'number': 1, 'name': 'Original'})
    monkeypatch.setattr(restore, 'ROOT', tmp_path)
    monkeypatch.setattr(restore, 'run', run)
    monkeypatch.setattr(restore.sys, 'argv', ['restore', '--restore', '1=original', '--apply'])
    with pytest.raises(subprocess.CalledProcessError):
        restore.main()
    assert calls[-1] == ['docker', 'start', 'existing-container']
    assert workspace.read_text() == '[]'
