"""Workspace polling scans history once without making recovery stale."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from memstara.control import recovery


def write_record(root, tag, pipeline_id='a'):
    folder = root / 'nested' / tag
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'control_record.json').write_text(json.dumps({
        'run_tag': tag, 'pipeline_id': pipeline_id, 'exit_code': 0,
        'run_dir': str(folder), 'started': tag,
    }))
    return folder


def test_workspace_http_scans_once_and_refreshes_next_request(tmp_path, monkeypatch):
    from memstara.control import service
    monkeypatch.setattr(service, 'RUNS_DIR', tmp_path)
    scans = []
    original = Path.glob

    def counted(path, pattern):
        if path == tmp_path and pattern == '**/control_record.json':
            scans.append(1)
        return original(path, pattern)

    monkeypatch.setattr(Path, 'glob', counted)
    for i in range(15):
        write_record(tmp_path, f'run-{i}', str(i))
    managers = {}

    def listing():
        result = []
        for i in range(15):
            manager = managers.setdefault(str(i), service._Runs(str(i)))
            assert manager.running() is None
            assert manager.finished()
            result.extend(manager.history_records())
        return result

    monkeypatch.setattr(service, 'WORKSPACE', SimpleNamespace(list=listing))
    handler = object.__new__(service.Handler)
    handler.path = '/control/pipelines'
    handler._refuse_stranger = lambda: False
    sent = []
    handler._send = lambda code, payload: sent.append((code, payload))
    handler.do_GET()
    assert len(scans) == 1
    assert len(sent[-1][1]['pipelines']) == 15
    write_record(tmp_path, 'new-run', '0')
    handler.do_GET()
    assert len(scans) == 2
    assert len(sent[-1][1]['pipelines']) == 16
    assert sent[-1][0] == 200


def test_snapshot_does_not_cache_process_liveness(tmp_path, monkeypatch):
    folder = write_record(tmp_path, 'live')
    record = json.loads((folder / 'control_record.json').read_text())
    record.update(exit_code=None, pid=123, process_identity='original')
    (folder / 'control_record.json').write_text(json.dumps(record))
    monkeypatch.setattr(recovery, 'identity', lambda pid: 'original')
    with recovery.record_snapshot():
        live, _ = recovery.recover(tmp_path, 'a')
        assert live is not None
        monkeypatch.setattr(recovery, 'identity', lambda pid: 'reused-pid')
        live, finished = recovery.recover(tmp_path, 'a')
        assert live is None
        assert finished[0]['exit_code'] == 1


def test_snapshot_is_thread_local_and_cleared_after_error(tmp_path):
    write_record(tmp_path, 'old')
    with pytest.raises(RuntimeError), recovery.record_snapshot():
        assert len(recovery.records(tmp_path)) == 1
        write_record(tmp_path, 'new')
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(lambda: len(recovery.records(tmp_path))).result() == 2
        assert len(recovery.records(tmp_path)) == 1
        raise RuntimeError('response failed')
    assert len(recovery.records(tmp_path)) == 2
