import asyncio
import copy
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import output_results
import output_snapshot
import scene
import telemetry_totals


def result(index=1):
    fit = {'seed': index, 'auc': .81, 'parameters': {'C': .3},
           'performance': {'test': {'metrics': {'f1': .7}, 'threshold': .5,
                                    'confusion_matrix': {'tn': 10, 'fp': 2, 'fn': 1, 'tp': 3}}}}
    return {'result_id': index, 'trial': index - 1, 'iteration': index, 'run_tag': 'parent',
            'interpretation': 'Original interpretation ' * 1000,
            'evaluation': {'skills': {'hypothesis': ['whole-graph']},
                'evaluation': {'replicates': [fit]},
                'model_results': {'lr': {'model': 'lr', 'evaluation': {'replicates': [fit]}}},
                'interpretations': [{'slot': 1, 'status': 'done', 'text': 'Original branch ' * 1000}],
                'specialist_xai': {'large': [0.123456789] * 5000}}}


def test_summary_preserves_all_1200_results_and_metrics_without_documents():
    rows = [result(i) for i in range(1, 1201)]
    original = copy.deepcopy(rows)
    report = {'run_tags': ['parent', 'child'], 'text': 'Original final report',
              'explanation_outputs': [{'run_tag': 'parent', 'loop': i, 'result_id': i,
                'status': 'completed', 'text': 'Original explanation ' * 100} for i in range(1, 1201)]}
    summary = output_snapshot.make_summary('child', ['parent', 'child'],
        {'config': {'trials': 1, 'combination_plan': {'total_loops': 1200}}}, report, rows)
    assert summary['experiment']['result_combinations'] == 1200
    assert len(summary['report']['explanation_outputs']) == 1200
    for raw, shown in zip(rows, summary['results'], strict=True):
        assert raw['result_id'] == shown['result_id']
        assert raw['run_tag'] == shown['run_tag']
        assert raw['evaluation']['evaluation'] == shown['evaluation']['evaluation']
        assert raw['evaluation']['model_results'] == shown['evaluation']['model_results']
        assert shown['evaluation']['interpretations'][0]['has_text'] is True
        assert shown['interpretation'] == ''
    assert rows == original
    assert len(json.dumps(summary)) < len(json.dumps(rows)) / 20
    second = output_snapshot.make_summary('child', ['parent', 'child'],
        {'config': {'trials': 1, 'combination_plan': {'total_loops': 1200}}}, report, rows)
    assert second['output_revision'] == summary['output_revision']
    rows[0]['evaluation']['interpretations'][0]['text'] = 'Corrected branch'
    changed = output_snapshot.make_summary('child', ['parent', 'child'],
        {'config': {'trials': 1, 'combination_plan': {'total_loops': 1200}}}, report, rows)
    assert changed['output_revision'] != summary['output_revision']


def test_cold_preparation_survives_short_http_wait_and_is_single_flight(monkeypatch):
    async def run():
        monkeypatch.setattr(output_snapshot, '_cache', {})
        monkeypatch.setattr(output_snapshot, '_pending', {})
        monkeypatch.setattr(output_snapshot, 'WAIT', .01)
        gate = asyncio.Event()
        calls = []
        async def prepare(tag):
            calls.append(tag)
            await gate.wait()
            return {'run_tag': tag}
        monkeypatch.setattr(output_snapshot, 'prepare', prepare)
        for _ in range(2):
            with pytest.raises(HTTPException) as preparing:
                await output_snapshot.snapshot('child')
            assert preparing.value.status_code == 202
        assert calls == ['child']
        task = output_snapshot._pending['child']
        assert not task.cancelled()
        gate.set()
        assert await task == {'run_tag': 'child'}
    asyncio.run(run())


def test_detail_preserves_original_identity_and_text_for_retained_attempt(monkeypatch):
    rows = [result(1), {**result(2), 'run_tag': 'child'}]
    report = {'explanation_outputs': [{'loop': 1, 'run_tag': 'parent', 'text': 'Exact original explanation'}]}
    monkeypatch.setattr(output_snapshot, 'records', AsyncMock(return_value=(
        ['parent', 'child'], {'config': {'trials': 1}}, report, rows)))
    detail = asyncio.run(output_snapshot.detail('child', 1))
    assert detail['results'] == [rows[0]]
    assert detail['explanation_outputs'] == report['explanation_outputs']
    with pytest.raises(HTTPException):
        asyncio.run(output_snapshot.detail('child', 3))


def test_skill_choices_are_scoped_to_original_execution_and_exclude_prompts(monkeypatch):
    parent = {'books': {'hypothesis': ['old']}, 'combination_plan': {'skills': {
        'hypothesis': [{'id': 'old', 'hash': 'old-version'}]}}, 'prompts': {'private': 'not in summary'}}
    child = {'books': {'hypothesis': ['new']}, 'combination_plan': {'skills': {
        'hypothesis': [{'id': 'new', 'hash': 'new-version'}]}}}
    configs = {'parent': parent, 'child': child, 'unrelated': {'books': {'hypothesis': ['unrelated']}}}
    monkeypatch.setattr(output_snapshot, 'archive_scope', lambda tag: (
        ['parent', 'child'], {'config': child}, {}, configs))
    monkeypatch.setattr(output_results, 'results', AsyncMock(return_value=[]))
    history, item, report, rows = asyncio.run(output_snapshot.records('child'))
    summary = output_snapshot.make_summary('child', history, item, report, rows)
    assert set(summary['skill_configurations']) == {'parent', 'child'}
    assert summary['skill_configurations']['parent']['combination_plan']['skills']['hypothesis'][0]['hash'] == 'old-version'
    assert summary['skill_configurations']['child']['books']['hypothesis'] == ['new']
    assert 'prompts' not in summary['skill_configurations']['parent']


def test_version_cache_fetches_only_changed_rows_and_observes_deletes(monkeypatch):
    async def run():
        from collections import OrderedDict
        monkeypatch.setattr(output_results, '_cache', OrderedDict())
        monkeypatch.setattr(output_results, '_locks', {})
        monkeypatch.setattr(scene, '_result_rows', lambda rows: rows)
        versions = {1: 'a', 2: 'b'}
        payloads = {1: result(1), 2: result(2)}
        fetched = []
        class Connection:
            @asynccontextmanager
            async def transaction(self, **options):
                assert options == {'isolation': 'repeatable_read', 'readonly': True}
                yield
            async def fetch(self, sql, tag, ids=None):
                assert tag == 'parent'
                if ids is None:
                    return [{'result_id': i, 'version': v, 'location': str(i)} for i, v in versions.items()]
                fetched.append(ids)
                return [payloads[i] for i in ids]
        async def guarded(store, query, fallback):
            assert store == 'memstara'
            return await query(Connection())
        monkeypatch.setattr(output_results.pools, 'guarded', guarded)
        first = await output_results.results('parent')
        assert len(first) == 2
        second = await output_results.results('parent')
        assert second[0] is first[0]
        assert fetched == [[1, 2]]
        versions[1] = 'updated'
        payloads[1] = {**payloads[1], 'interpretation': 'Late interpretation'}
        versions[3] = 'new'
        payloads[3] = result(3)
        del versions[2]
        third = await output_results.results('parent')
        assert fetched[-1] == [1, 3]
        assert [r['result_id'] for r in third] == [1, 3]
        assert third[0]['interpretation'] == 'Late interpretation'
        monkeypatch.setattr(output_results.pools, 'guarded', AsyncMock(return_value=None))
        with pytest.raises(HTTPException):
            await output_results.results('parent')
        assert list(output_results._cache['parent']) == [1, 3]
    asyncio.run(run())


def test_usage_index_preserves_totals_missing_costs_and_duplicate_call_deduplication():
    calls = [{'run_id': 'one'}, {'run_id': 'one'}, {'run_id': 'missing'}]
    rows = [{'id': 'one', 'status': 'completed', 'tokens': 42, 'cost_estimate': .25}]
    indexed = {'one': rows[0]}
    before, after = telemetry_totals.metrics(calls, rows), telemetry_totals.metrics(calls, indexed)
    before['cost'].pop('updated_at')
    after['cost'].pop('updated_at')
    assert before == after
    assert telemetry_totals.recorded_span(calls, rows) == telemetry_totals.recorded_span(calls, indexed)


def test_summary_http_conditional_response_and_detail_scope(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    import history_epoch
    monkeypatch.setattr(history_epoch, 'read', lambda: {'revision': 'test', 'busy': False})
    monkeypatch.setattr(history_epoch, 'invalidate', AsyncMock())
    value = {'run_tag': 'selected', 'output_revision': 'revision1', 'stale': False, 'results': [result()]}
    monkeypatch.setattr(output_snapshot, 'snapshot', AsyncMock(return_value=value))
    detail = AsyncMock(return_value={'run_tag': 'selected', 'loop': 12, 'results': [result()]})
    monkeypatch.setattr(output_snapshot, 'detail', detail)
    client = TestClient(main.app)
    first = client.get('/api/output-summary?run_tag=selected')
    assert first.status_code == 200
    assert first.json()['results'] == value['results']
    assert client.get('/api/output-summary?run_tag=selected',
                      headers={'If-None-Match': first.headers['etag']}).status_code == 304
    value['stale'] = True
    stale = client.get('/api/output-summary?run_tag=selected', headers={'If-None-Match': first.headers['etag']})
    assert stale.status_code == 200 and stale.json()['stale'] is True
    assert client.get('/api/output-detail?run_tag=selected&loop=12').status_code == 200
    detail.assert_awaited_once_with('selected', 12)
    assert client.get('/api/output-detail?run_tag=selected&loop=0').status_code == 422


def test_history_reset_invalidates_new_caches_and_cancels_old_preparations(monkeypatch):
    async def run():
        import history_epoch
        task = asyncio.create_task(asyncio.sleep(60))
        usage = asyncio.create_task(asyncio.sleep(60))
        monkeypatch.setattr(output_snapshot, '_cache', {'old': (0, {})})
        monkeypatch.setattr(output_snapshot, '_pending', {'old': task})
        monkeypatch.setattr(output_results, '_cache', {'old': {}})
        monkeypatch.setattr(telemetry_totals, '_pending', usage)
        await history_epoch.invalidate()
        assert task.cancelled() and usage.cancelled()
        assert not output_snapshot._cache and not output_results._cache
        assert telemetry_totals._pending is None
    asyncio.run(run())
