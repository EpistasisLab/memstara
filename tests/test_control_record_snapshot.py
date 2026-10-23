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
    original = recovery.os.walk

    def counted(path, **kwargs):
        if path == tmp_path:
            scans.append(1)
        return original(path, **kwargs)

    monkeypatch.setattr(recovery.os, 'walk', counted)
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


def test_discovery_prunes_run_artifacts_but_finds_nested_archives(tmp_path, monkeypatch):
    folder = write_record(tmp_path, 'owned')
    artifact = folder / 'trace' / 'deep'
    artifact.mkdir(parents=True)
    wrapper = tmp_path / 'archive'
    nested = write_record(wrapper, 'older')
    visited = []
    original = recovery.os.scandir
    def tracked(path):
        visited.append(Path(path))
        return original(path)
    monkeypatch.setattr(recovery.os, 'scandir', tracked)
    assert {path.parent for path, _ in recovery.records(tmp_path)} == {folder, nested}
    assert artifact not in visited
    assert folder / 'trace' not in visited


def test_corrupt_archive_record_does_not_hide_valid_nested_run(tmp_path):
    (tmp_path / 'control_record.json').write_text('{broken')
    folder = write_record(tmp_path, 'valid')
    assert [path.parent for path, _ in recovery.records(tmp_path)] == [folder]


def test_catalog_snapshot_refreshes_and_isolates_returned_records(monkeypatch):
    from memstara.control import catalog as module
    reads = []
    def read(**kwargs):
        reads.append(kwargs)
        return [{'id': str(len(reads)), 'content': 'original'}]
    monkeypatch.setattr(module, '_read_catalog', read)
    with module.catalog_snapshot():
        first = module.catalog(include_hidden=True)
        first[0]['content'] = 'caller change'
        assert module.catalog(include_hidden=True)[0]['content'] == 'original'
        assert len(reads) == 1
        module.catalog(include_hidden=False)
        assert len(reads) == 2
    with module.catalog_snapshot():
        assert module.catalog(include_hidden=True)[0]['id'] == '3'
    assert module.catalog(include_hidden=True)[0]['id'] == '4'


def test_record_cache_observes_changes_deletions_and_defends_against_mutation(tmp_path):
    folder = write_record(tmp_path, 'run')
    first = recovery.records(tmp_path)
    first[0][1]['exit_code'] = 99
    assert recovery.records(tmp_path)[0][1]['exit_code'] == 0
    path = folder / 'control_record.json'
    data = json.loads(path.read_text())
    data['exit_code'] = 1
    path.write_text(json.dumps(data))
    assert recovery.records(tmp_path)[0][1]['exit_code'] == 1
    path.unlink()
    assert recovery.records(tmp_path) == []


def test_aliases_refresh_after_response(tmp_path, monkeypatch):
    from memstara.control import catalog as module
    path = tmp_path / 'aliases.json'
    monkeypatch.setenv('MEMSTARA_SKILL_ALIASES_PATH', str(path))
    path.write_text('{"old":"first"}')
    with module.catalog_snapshot():
        assert module.canonical_name('old') == 'first'
        path.write_text('{"old":"second"}')
        assert module.canonical_name('old') == 'first'
    assert module.canonical_name('old') == 'second'
