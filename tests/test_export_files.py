"""Native exports retain complete evidence without one giant browser JSON string."""
import asyncio
import copy
import csv
import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import export_files as files
import linked_outputs


@pytest.fixture
def bundle():
    result = {'run_tag': 'original', 'result_id': 7, 'result_uid': 'original:7', 'task_id': 8,
        'trial': 0, 'iteration': 1, 'pipeline_number': 1, 'replicate_number': 1, 'auc': .75,
        'hypothesis': '=formula-looking text', 'interpretation_output_ids': ['int-1'],
        'explanation_output_ids': ['exp-1'], 'interpretation_status': 'complete', 'explanation_status': 'complete',
        'evaluation': {'model': 'lr', 'seed': 42, 'skills': {'hypothesis': ['test-skill']},
            'evaluation': {'replicates': [{'seed': 0, 'n_train': 80, 'n_test': 20, 'auc': .75,
                'parameters': {'C': .3, 'warm_start': False},
                'performance': {'test': {'threshold': .5, 'metrics': {'precision': 0, 'f1': 0},
                    'confusion_matrix': {'tn': 12, 'fp': 3, 'fn': 4, 'tp': 1}}}}]}}}
    return {'schema_version': 'linked_agent_outputs_v1', 'generated_at': '2026-11-05T00:00:00Z',
        'requested_run_tags': ['continued'], 'run_tags': ['original', 'continued'], 'results': [result],
        'interpretations': [{'output_id': 'int-1', 'run_tag': 'original', 'result_uids': ['original:7'], 'text': '\n# Exact 한글\n"quoted"\n'}],
        'explanations': [{'output_id': 'exp-1', 'run_tag': 'original', 'result_uids': ['original:7'], 'text': 'Original explanation.\n'}],
        'executions': [{'run_tag': 'original', 'schema_version': 'original-registry-version', 'results': [result],
            'agents': [{'agent_run_id': 'a', 'metadata': {'skill': 's'}}],
            'costs': [{'id': 1, 'receipt': {'usd': .2, 'private_nested': {'value': 'retained'}}}],
            'artifacts': [{'path': '/saved/file', 'sha256': 'unchanged'}]},
            {'run_tag': 'continued', 'results': []}], 'warnings': [{'code': 'explicit-warning'}]}


def read_csv(data):
    return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline='')))


def test_zip_contains_every_original_document_and_complete_evidence(bundle):
    original = copy.deepcopy(bundle)
    target, size = files.build_file(bundle, 'zip')
    try:
        assert size == len(target.read())
        target.seek(0)
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None
            assert set(archive.namelist()) == {'results.csv', 'results.json', 'interpretations.json',
                'explanations.json', 'complete_evidence.csv', 'complete_evidence.json', 'manifest.json', 'README.txt'}
            for key in ('results', 'interpretations', 'explanations'):
                assert json.loads(archive.read(key + '.json')) == bundle[key]
            assert json.loads(archive.read('complete_evidence.json')) == bundle['executions']
            manifest = json.loads(archive.read('manifest.json'))
            assert manifest['run_tags'] == ['original', 'continued']
            assert manifest['warnings'] == bundle['warnings']
            assert manifest['relationships']['result_key'] == 'result_uid'
            row = read_csv(archive.read('results.csv'))[0]
            assert row['Seed'] == '0' and row['Precision'] == '0' and row['F1'] == '0'
            assert row['N Train'] == '80' and row['N Test'] == '20'
            assert row['TN'] == '12' and row['TP'] == '1'
            assert row['Hypothesis'].startswith("'=formula")
            assert json.loads(row['interpretation_output_ids']) == ['int-1']
            evidence = read_csv(archive.read('complete_evidence.csv'))
            assert {row['record_type'] for row in evidence} == {'execution', 'agent', 'result', 'cost', 'artifact'}
            assert all(row['schema_version'] == 'memstara_complete_evidence_csv_v1' for row in evidence)
            cost = next(row for row in evidence if row['record_type'] == 'cost')
            assert json.loads(cost['record.receipt'])['private_nested']['value'] == 'retained'
    finally:
        target.close()
    assert bundle == original


def test_complete_csv_and_zip_csv_have_identical_contents(bundle):
    target, _ = files.build_file(bundle, 'complete')
    archive, _ = files.build_file(bundle, 'zip')
    try:
        csv_bytes = target.read()
        with zipfile.ZipFile(archive) as zipped:
            assert csv_bytes == zipped.read('complete_evidence.csv')
    finally:
        target.close()
        archive.close()


def test_512_mib_evidence_is_streamed_and_compressed_without_dropping_records(bundle):
    # Repeated references occupy only 1 MiB of source memory but serialize to 512 MiB.
    payload = 'x' * (1024 * 1024)
    bundle['executions'] = [{'run_tag': 'original', 'costs': [{'id': index, 'receipt': {'payload': payload}} for index in range(512)]}]
    target, size = files.build_file(bundle, 'zip')
    try:
        assert size < 5 * 1024 * 1024
        with zipfile.ZipFile(target) as archive:
            assert archive.getinfo('complete_evidence.json').file_size > 512 * 1024 * 1024
            assert archive.getinfo('complete_evidence.csv').file_size > 512 * 1024 * 1024
            assert archive.testzip() is None
    finally:
        target.close()


def test_download_receipt_streaming_and_file_cleanup(bundle, monkeypatch):
    monkeypatch.setattr(linked_outputs, 'bundle', AsyncMock(return_value=bundle))
    real = files.build_file
    opened = []

    def capture(*args):
        target, size = real(*args)
        opened.append(target)
        return target, size

    monkeypatch.setattr(files, 'build_file', capture)

    async def run():
        response = await files.download(['continued'], 'zip')
        assert response.media_type == 'application/zip'
        assert response.headers['X-Memstara-Export-Results'] == '1'
        assert response.headers['X-Memstara-Export-Executions'] == '2'
        chunks = [chunk async for chunk in response.body_iterator]
        assert sum(map(len, chunks)) == int(response.headers['Content-Length'])
        assert int(response.headers['X-Memstara-Export-Bytes']) == int(response.headers['Content-Length'])
        assert opened[0].closed

    asyncio.run(run())
    linked_outputs.bundle.assert_awaited_once_with(['continued'], True)


def test_failed_file_creation_is_not_a_successful_download(bundle, monkeypatch):
    monkeypatch.setattr(linked_outputs, 'bundle', AsyncMock(return_value=bundle))

    def fail(*args):
        raise OSError('synthetic disk failure')

    monkeypatch.setattr(files, 'build_file', fail)
    with pytest.raises(Exception) as caught:
        asyncio.run(files.download(['continued'], 'zip'))
    assert caught.value.status_code == 503
    assert 'synthetic disk failure' not in caught.value.detail


def test_real_http_route_delivers_a_complete_zip_and_rejects_unknown_formats(bundle, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    import history_epoch
    monkeypatch.setattr(linked_outputs, 'bundle', AsyncMock(return_value=bundle))
    monkeypatch.setattr(history_epoch, 'read', lambda: {'revision': 'download-test', 'busy': False})
    monkeypatch.setattr(history_epoch, 'invalidate', AsyncMock())
    # No lifespan context: this synthetic route test must never open real DB pools.
    client = TestClient(main.app)
    response = client.get('/api/experiments/linked-download?run_tags=continued&format=zip')
    assert response.status_code == 200 and response.headers['content-type'] == 'application/zip'
    assert len(response.content) == int(response.headers['content-length'])
    assert response.headers['cache-control'] == 'no-store'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read('complete_evidence.json')) == bundle['executions']
    assert client.get('/api/experiments/linked-download?run_tags=continued&format=invalid').status_code == 422


def test_concurrent_large_preparations_are_rejected_without_loading_another_snapshot(bundle, monkeypatch):
    async def run():
        entered, finish = asyncio.Event(), asyncio.Event()

        async def snapshot(*args):
            entered.set()
            await finish.wait()
            return bundle

        loader = AsyncMock(side_effect=snapshot)
        monkeypatch.setattr(linked_outputs, 'bundle', loader)
        first = asyncio.create_task(files.download(['continued'], 'zip'))
        await entered.wait()
        try:
            with pytest.raises(Exception) as caught:
                await files.download(['continued'], 'zip')
            assert caught.value.status_code == 429
            assert caught.value.headers['Retry-After'] == '10'
        finally:
            finish.set()
            response = await first
            await response.background()
        assert loader.await_count == 1

    asyncio.run(run())


def test_client_disconnect_closes_the_private_temporary_file(bundle, monkeypatch):
    monkeypatch.setattr(linked_outputs, 'bundle', AsyncMock(return_value=bundle))
    real = files.build_file
    opened = []

    def capture(*args):
        target, size = real(*args)
        opened.append(target)
        return target, size

    monkeypatch.setattr(files, 'build_file', capture)

    async def run():
        response = await files.download(['continued'], 'zip')

        async def disconnect():
            return {'type': 'http.disconnect'}

        await response({'type': 'http', 'asgi': {'spec_version': '2.0'}}, disconnect, AsyncMock())
        assert opened[0].closed

    asyncio.run(run())
