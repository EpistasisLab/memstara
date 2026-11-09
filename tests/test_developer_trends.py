"""Read-only trend attribution, retry retention, and honest missing measurements."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import developer_trends as trends


def call(identifier, loop, start, duration, stage='ml#1'):
    return {'run_id': identifier, 'loop': loop, 'started_at': start,
            'duration_seconds': duration, 'stage': stage, 'loop_source': 'recorded'}


def usage(identifier, inputs=100, outputs=20):
    return {'id': identifier, 'status': 'completed', 'input_tokens': inputs, 'output_tokens': outputs}


def record(tag, calls, outcomes):
    return {'tag': tag, 'configuration': {'pipeline_name': 'Study', 'waves': 8},
            'calls': calls, 'outcomes': outcomes}


def outcome(start, end, status='completed'):
    return {'started_at': start, 'ended_at': end, 'outcome': status}


def test_retry_keeps_prior_usage_deduplicates_ids_and_does_not_sum_parallel_time():
    a, b, c = call('a', 1, 10, 10), call('b', 1, 15, 10), call('c', 1, 100, 10, 'report')
    records = [record('old', [a, b], {'1': outcome(9, 26, 'interrupted')}),
               record('new', [a, c], {'1': outcome(99, 112)})]
    result = trends.summarize(records, [usage('a'), usage('b'), usage('c')])
    point = result['points'][0]
    assert point['calls'] == 3 and point['input_tokens'] == 300 and point['output_tokens'] == 60
    assert point['total_tokens'] == 360
    assert point['active_seconds'] == 25  # [10,25] plus [100,110], not 30 or 100.
    assert point['elapsed_seconds'] == 103
    assert point['attempts'] == 2 and point['run_tags'] == ['old', 'new']
    assert point['agents']['ml']['active_seconds'] == 15
    assert point['agents']['explanation']['total_tokens'] == 120


def test_only_completed_sorted_by_actual_start_not_loop_and_no_cross_loop_leak():
    result = trends.summarize([record('run', [call('a', 1, 100, 10), call('b', 2, 10, 3),
        call('c', 3, 200, 2), call('report', None, 210, 5, 'report')], {
        '1': outcome(100, 111), '2': outcome(10, 14), '3': outcome(200, None, 'running'),
        '4': {'outcome': 'completed'}})], [usage('a'), usage('b', 999), usage('report', 5000)])
    assert [p['loop'] for p in result['points']] == [2, 1, 4]
    assert result['points'][0]['input_tokens'] == 999
    assert result['points'][1]['input_tokens'] == 100
    assert result['points'][2]['total_tokens'] is None
    assert result['points'][2]['tokens_status'] == 'unavailable'
    assert result['unknown_order_count'] == 1 and result['excluded_replicates'] == 1
    assert result['unassigned_calls'] == 1


def test_partial_missing_and_invalid_clock_never_look_complete_or_zero():
    calls = [call('a', 1, 10, 3), call('b', 1, 5, -1)]
    m = trends.measures(calls, {'a': usage('a', 0, 0)})
    assert m['total_tokens'] == 0 and m['tokens_status'] == 'partial'
    assert m['active_seconds'] == 3 and m['active_status'] == 'partial'
    absent = trends.measures(calls, {})
    assert absent['input_tokens'] is None and absent['total_tokens'] is None
    assert trends.measures([], {})['active_seconds'] is None
    assert trends.interval(float('nan'), 20) is None
    assert trends.interval(True, 20) is None


def test_conflicting_invocation_ownership_fails_closed():
    records = [record('run', [call('a', 1, 0, 1), call('a', 2, 2, 1)], {})]
    with pytest.raises(HTTPException, match='Conflicting replicate'):
        trends.summarize(records, [])


def test_compact_history_only_and_explicit_lineage(monkeypatch, tmp_path):
    configs = {'old': {'waves': 5}, 'retry': {'waves': 5, 'retry_selection': {'loops': [3]}}}
    for tag in configs:
        directory = tmp_path / tag
        directory.mkdir()
        (directory / 'execution.json').write_text(json.dumps({'calls': [call(tag, 3, 1, 2)]}))
        (directory / 'iteration_outcomes.json').write_text(json.dumps({'1': outcome(0, 1), '3': outcome(1, 4)}))
    monkeypatch.setattr(trends.archive, 'config_for', configs.get)
    monkeypatch.setattr(trends.archive, 'directory_for', lambda tag: tmp_path / tag)
    monkeypatch.setattr(trends.archive, 'lookup', lambda *a: pytest.fail('Full history/output lookup is prohibited'))
    monkeypatch.setattr(trends, 'tags', lambda tag: ['old', 'retry'])
    result = trends.read_history('retry')
    assert [r['tag'] for r in result] == ['old', 'retry']
    assert set(result[0]['outcomes']) == {'1', '3'} and set(result[1]['outcomes']) == {'3'}
    (tmp_path / 'old' / 'execution.json').unlink()
    with pytest.raises(HTTPException, match='Compact execution metadata'):
        trends.read_history('retry')


def test_database_read_is_one_bulk_metadata_query_and_outage_is_not_zero(monkeypatch):
    identifier = '11111111-1111-1111-1111-111111111111'
    records = [record('run', [call(identifier, 1, 1, 2)], {'1': outcome(1, 4)})]
    monkeypatch.setattr(trends, 'read_history', lambda tag: records)
    conn = AsyncMock()
    conn.fetch.return_value = [usage(identifier)]
    async def guarded(name, query, fallback):
        assert name == 'core'
        return await query(conn)
    monkeypatch.setattr(trends.pools, 'guarded', guarded)
    data = asyncio.run(trends.trends('run'))
    assert data['points'][0]['total_tokens'] == 120
    conn.fetch.assert_awaited_once()
    query, ids = conn.fetch.call_args.args
    assert 'run_steps' not in query and 'input_data' not in query
    assert list(map(str, ids)) == [identifier]
    monkeypatch.setattr(trends.pools, 'guarded', AsyncMock(return_value=None))
    with pytest.raises(HTTPException, match='Motoro usage is unavailable'):
        asyncio.run(trends.trends('run'))


def test_catalog_retains_independent_fresh_runs_but_collapses_retry_chain(monkeypatch):
    configs = {'first': {'pipeline_name': 'same'}, 'fresh': {'pipeline_name': 'same'},
               'retry': {'pipeline_name': 'same', 'retry_selection': {'source_run_tag': 'first'}}}
    monkeypatch.setattr(trends.archive, 'configs', lambda: configs)
    monkeypatch.setattr(trends.archive, 'directory_for', lambda tag: None)
    assert {e['run_tag'] for e in trends.read_catalog()['experiments']} == {'fresh', 'retry'}
