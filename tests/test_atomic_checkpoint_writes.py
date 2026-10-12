"""Concurrent saves and interrupted writes retain complete checkpoint documents."""
import json
import threading
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from memstara.pipeline import checkpoint


def test_concurrent_writers_do_not_share_a_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / 'status.json'
    barrier = threading.Barrier(2)
    replace = checkpoint.os.replace

    def synchronized_replace(source, destination):
        barrier.wait(timeout=5)
        replace(source, destination)

    monkeypatch.setattr(checkpoint.os, 'replace', synchronized_replace)
    payloads = [{'writer': 1, 'payload': 'first'}, {'writer': 2, 'payload': 'second'}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(checkpoint.atomic_json, target, value) for value in payloads]
        for future in futures:
            future.result(timeout=10)
    assert json.loads(target.read_text()) in payloads
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('failure', ['serialization', 'file_sync', 'replace'])
def test_failed_save_retains_old_bytes_and_cleans_its_temporary_file(tmp_path, monkeypatch, failure):
    target = tmp_path / 'checkpoint.json'
    old = b'{"previous": "complete"}\n'
    target.write_bytes(old)
    unrelated = tmp_path / 'another-writer.tmp'
    unrelated.write_text('Do not remove another writer\'s file')
    value = {'new': 'complete'}

    def denied(*args):
        raise OSError('synthetic persistence failure')

    if failure == 'serialization':
        value['new'] = object()
        expected = TypeError
    else:
        monkeypatch.setattr(checkpoint.os, 'fsync' if failure == 'file_sync' else 'replace', denied)
        expected = OSError
    with pytest.raises(expected):
        checkpoint.atomic_json(target, value)
    assert target.read_bytes() == old
    assert {p.name for p in tmp_path.iterdir()} == {target.name, unrelated.name}
    assert unrelated.read_text() == "Do not remove another writer's file"


def test_directory_sync_failure_does_not_claim_success_or_corrupt_new_document(tmp_path, monkeypatch):
    target = tmp_path / 'checkpoint.json'
    calls = []
    real_sync = checkpoint.os.fsync

    def fail_second_sync(fd):
        calls.append(fd)
        if len(calls) == 2:
            raise OSError('directory durability not confirmed')
        return real_sync(fd)

    monkeypatch.setattr(checkpoint.os, 'fsync', fail_second_sync)
    with pytest.raises(OSError, match='durability not confirmed'):
        checkpoint.atomic_json(target, {'saved': True})
    assert json.loads(target.read_text()) == {'saved': True}
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('moment', ['before_replace', 'after_replace'])
def test_process_exit_never_exposes_a_partial_destination(tmp_path, moment):
    target = tmp_path / 'checkpoint.json'
    target.write_text('{"previous": "complete"}')
    script = '''
import os, sys
from memstara.pipeline import checkpoint
replace = checkpoint.os.replace
def terminate(source, destination):
    if sys.argv[2] == 'after_replace':
        replace(source, destination)
    os._exit(137)
checkpoint.os.replace = terminate
checkpoint.atomic_json(sys.argv[1], {'new': 'complete'})
'''
    result = subprocess.run([sys.executable, '-c', script, str(target), moment], check=False, timeout=15)
    assert result.returncode == 137
    assert json.loads(target.read_text()) == (
        {'previous': 'complete'} if moment == 'before_replace' else {'new': 'complete'}
    )
    # Abrupt exit bypasses cleanup. A later writer must not reuse that orphan.
    checkpoint.atomic_json(target, {'recovered': 'complete'})
    assert json.loads(target.read_text()) == {'recovered': 'complete'}
