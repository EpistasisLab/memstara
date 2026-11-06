import copy
import gzip
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import snapshot_response


def test_large_snapshot_keeps_all_results_and_negotiates_encoding():
    value = {'run_tag': 'selected', 'results': [{'id': i, 'text': 'Original text 한글\n' * 1000} for i in range(110)]}
    original = copy.deepcopy(value)
    compressed = snapshot_response.response(value, 'gzip, br')
    plain = snapshot_response.response(value, 'gzip;q=0')
    assert compressed.headers['content-encoding'] == 'gzip'
    assert 'content-encoding' not in plain.headers
    assert gzip.decompress(compressed.body) == plain.body
    assert json.loads(plain.body) == value == original
    assert len(compressed.body) < len(plain.body) / 10
    assert int(compressed.headers['content-length']) == len(compressed.body)
    assert compressed.headers['vary'] == 'Accept-Encoding'
    assert compressed.headers['cache-control'] == 'no-store'


def test_snapshot_http_route_serializes_off_loop_and_retains_json_types(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    import history_epoch
    threads = []
    value = {'run_tag': 'selected', 'results': [{'text': 'x' * 10000}],
             'created_at': datetime(2026, 11, 6, tzinfo=timezone.utc)}
    async def snapshot(tag):
        threads.append(('scene', threading.get_ident()))
        return value
    original = snapshot_response.response
    def render(*args):
        threads.append(('render', threading.get_ident()))
        return original(*args)
    monkeypatch.setattr(main.scene, 'snapshot', snapshot)
    monkeypatch.setattr(snapshot_response, 'response', render)
    monkeypatch.setattr(history_epoch, 'read', lambda: {'revision': 'test', 'busy': False})
    monkeypatch.setattr(history_epoch, 'invalidate', AsyncMock())
    response = TestClient(main.app).get('/api/snapshot?run_tag=selected', headers={'Accept-Encoding': 'gzip'})
    assert response.status_code == 200
    assert response.json()['results'] == value['results']
    assert response.json()['created_at'] == '2026-11-06T00:00:00+00:00'
    assert response.headers['content-encoding'] == 'gzip'
    assert dict(threads)['scene'] != dict(threads)['render']
