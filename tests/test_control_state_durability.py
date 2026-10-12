"""Control restart evidence must use the same durable publication boundary."""

import json

import pytest

from memstara.control.recovery import save_record
from memstara.control.workspace import PipelineWorkspace
from memstara.pipeline import checkpoint


@pytest.mark.parametrize('kind', ['ownership', 'workspace'])
@pytest.mark.parametrize('failure', ['file_sync', 'replace', 'directory_sync'])
def test_control_save_reports_storage_failure_and_retains_complete_record(tmp_path, monkeypatch, kind, failure):
    path = tmp_path / ('control_record.json' if kind == 'ownership' else 'workspace.json')
    previous = {'run_tag': 'old'} if kind == 'ownership' else [{'id': 'old'}]
    path.write_text(json.dumps(previous))
    old_bytes = path.read_bytes()
    calls = 0
    real_sync = checkpoint.os.fsync

    def sync(fd):
        nonlocal calls
        calls += 1
        if (failure == 'file_sync' and calls == 1) or (failure == 'directory_sync' and calls == 2):
            raise OSError('synthetic disk failure')
        real_sync(fd)

    def replace(*args):
        raise OSError('synthetic disk failure')

    monkeypatch.setattr(checkpoint.os, 'fsync', sync)
    if failure == 'replace':
        monkeypatch.setattr(checkpoint.os, 'replace', replace)
    with pytest.raises(OSError, match='synthetic disk failure'):
        if kind == 'ownership':
            save_record({'run_tag': 'new', 'run_dir': str(tmp_path), 'popen': object()})
        else:
            workspace = PipelineWorkspace.__new__(PipelineWorkspace)
            workspace.path = path
            workspace.items = [{'id': 'new'}]
            workspace._save()
    if failure == 'directory_sync':
        saved = json.loads(path.read_text())
        assert saved['run_tag'] == 'new' if kind == 'ownership' else saved == [{'id': 'new'}]
        if kind == 'ownership':
            assert 'popen' not in saved
    else:
        assert path.read_bytes() == old_bytes
    assert list(tmp_path.iterdir()) == [path]
