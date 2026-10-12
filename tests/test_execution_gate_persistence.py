"""A failed state publication must remain eligible for a later save."""

import json
import os

import pytest

from memstara.pipeline.exploration import ExecutionGate


@pytest.mark.parametrize('failure', ['replace', 'directory_sync'])
def test_failed_pause_publication_is_retried(tmp_path, monkeypatch, failure):
    gate = ExecutionGate(tmp_path)
    path = tmp_path / 'execution_control.json'
    assert json.loads(path.read_text())['state'] == 'running'
    (tmp_path / 'pause.request').touch()
    replace = os.replace
    sync = os.fsync
    publications = []
    sync_calls = 0

    def replace_once(source, destination):
        publications.append(str(destination))
        if failure == 'replace' and len(publications) == 1:
            raise OSError('synthetic failed publication')
        replace(source, destination)

    def sync_once(fd):
        nonlocal sync_calls
        sync_calls += 1
        if failure == 'directory_sync' and sync_calls == 2:
            raise OSError('synthetic failed publication')
        sync(fd)

    monkeypatch.setattr(os, 'replace', replace_once)
    monkeypatch.setattr(os, 'fsync', sync_once)
    with pytest.raises(OSError, match='synthetic failed publication'):
        gate.publish()
    if failure == 'replace':
        assert json.loads(path.read_text())['state'] == 'running'
    gate.publish()
    assert len(publications) == 2
    assert json.loads(path.read_text())['state'] == 'paused'
    assert not list(tmp_path.glob('*.tmp'))
    gate.publish()
    assert len(publications) == 2  # Only a successful save can suppress repeats.
