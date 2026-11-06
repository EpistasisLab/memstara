import asyncio
import io
import json
import sys
import threading
import time
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import prepared_exports as exports
from test_export_files import bundle


@pytest.fixture(autouse=True)
def private_exports(tmp_path, monkeypatch):
    monkeypatch.setattr(exports, 'ROOT', tmp_path / 'downloads')
    monkeypatch.setattr(exports, 'HEARTBEAT', .01)


@pytest.mark.parametrize('kind', ['table', 'zip'])
def test_preparation_receipt_and_file_survive_separate_http_requests(kind, bundle, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    import history_epoch
    loader = AsyncMock(return_value=bundle)
    monkeypatch.setattr(exports, 'bundle', loader)
    monkeypatch.setattr(history_epoch, 'read', lambda: {'revision': 'prepared-test', 'busy': False})
    monkeypatch.setattr(history_epoch, 'invalidate', AsyncMock())
    client = TestClient(main.app)
    response = client.get('/api/experiments/prepare-download', params={'run_tags': 'continued', 'format': kind})
    assert response.headers['content-type'].startswith('application/x-ndjson')
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]['type'] == 'progress'
    ready = events[-1]
    assert ready['type'] == 'ready' and ready['kind'] == kind
    assert loader.await_args.args == (['continued'], kind == 'zip')
    assert 'on_progress' in loader.await_args.kwargs
    download = client.get(ready['download_url'])
    assert download.status_code == 200
    assert len(download.content) == ready['bytes'] == int(download.headers['x-memstara-export-bytes'])
    assert download.headers['x-memstara-export-results'] == '1'
    assert download.headers['cache-control'] == 'no-store'
    # A second request (possibly a different API worker) does not rebuild the file.
    assert client.get(ready['download_url']).content == download.content
    assert loader.await_count == 1
    if kind == 'zip':
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            assert archive.testzip() is None
            assert json.loads(archive.read('interpretations.json')) == bundle['interpretations']
            assert json.loads(archive.read('complete_evidence.json')) == bundle['executions']
        assert any(e.get('progress', {}).get('completedUnits') == 8 for e in events)
    else:
        assert b'interpretation_output_ids' in download.content
        assert b'private_nested' not in download.content


def test_slow_preparation_sends_heartbeats_without_inventing_percentage(monkeypatch):
    async def run():
        entered = asyncio.Event()
        async def waiting(*args, **kwargs):
            entered.set()
            await asyncio.Future()
        monkeypatch.setattr(exports, 'bundle', waiting)
        response = await exports.prepare(['continued'], 'zip')
        iterator = response.body_iterator
        first = json.loads(await anext(iterator))
        assert first['type'] == 'progress'
        await entered.wait()
        heartbeat = json.loads(await anext(iterator))
        assert heartbeat['heartbeat'] is True
        assert 'completedUnits' not in heartbeat['progress']
        await iterator.aclose()
        assert not exports._preparation_lock.locked()
        assert not list(exports.ROOT.glob('*'))
    asyncio.run(run())


def test_failure_is_reported_without_publishing_a_partial_download(monkeypatch):
    monkeypatch.setattr(exports, 'bundle', AsyncMock(side_effect=HTTPException(503, 'Saved results unavailable')))
    async def run():
        response = await exports.prepare(['continued'], 'table')
        return [json.loads(event) async for event in response.body_iterator]
    events = asyncio.run(run())
    assert events[-1] == {'type': 'error', 'message': 'Saved results unavailable'}
    assert not any(e['type'] == 'ready' for e in events)
    assert not list(exports.ROOT.glob('*'))


def test_disconnect_cancels_writer_and_removes_temporary_files(bundle, monkeypatch):
    entered = threading.Event()
    monkeypatch.setattr(exports, 'bundle', AsyncMock(return_value=bundle))
    def write(identifier, value, kind, report, cancelled):
        (exports.directory() / f'{identifier}.part').write_bytes(b'partial')
        entered.set()
        assert cancelled.wait(2)
        raise InterruptedError('cancelled')
    monkeypatch.setattr(exports, 'save', write)
    async def run():
        response = await exports.prepare(['continued'], 'zip')
        await anext(response.body_iterator)
        assert await asyncio.to_thread(entered.wait, 2)
        await response.body_iterator.aclose()
        assert not exports._preparation_lock.locked()
        assert not list(exports.ROOT.glob('*'))
    asyncio.run(run())


def test_expired_or_invalid_receipts_cannot_serve_arbitrary_files():
    for identifier in ('../secret', 'invalid', 'a' * 32):
        with pytest.raises(HTTPException) as error:
            exports.download(identifier)
        assert error.value.status_code == 404
    identifier = 'b' * 32
    (exports.directory() / f'{identifier}.json').write_text(json.dumps({'expires_at': time.time() - 1}))
    with pytest.raises(HTTPException) as error:
        exports.download(identifier)
    assert error.value.status_code == 410
