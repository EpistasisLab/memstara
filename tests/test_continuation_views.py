"""Retried work belongs to one displayed experiment, with original provenance."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import continuations
import costs
import run_artifacts as archive


@pytest.fixture
def history(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, 'ROOT', tmp_path)
    identity = {'pipeline_id': 'experiment', 'dataset_sha256': 'dataset', 'y_column': 'target', 'trials': 1}
    ids = ['11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222']
    for i, tag in enumerate(('old', 'retry', 'fresh')):
        directory = tmp_path / tag
        directory.mkdir()
        config = {**identity, 'run_tag': tag}
        if tag == 'retry':
            config['retry_selection'] = {'source_run_tag': 'old', 'loops': [2, 3]}
            (directory / 'retry_lineage.json').write_text(json.dumps({'source_run_tag': 'old'}))
        (directory / 'config.json').write_text(json.dumps(config))
        calls = [{'run_id': ids[min(i, 1)], 'loop': i + 1}]
        (directory / 'execution.json').write_text(json.dumps({'calls': calls}))
    return tmp_path, ids


def test_explicit_chain_only_fresh_runs_stay_separate(history):
    assert continuations.tags('retry') == ['old', 'retry']
    assert continuations.tags('fresh') == ['fresh']
    assert continuations.expand(['retry', 'old', 'retry']) == ['old', 'retry']


def test_legacy_phantom_retry_ordinals_cannot_hide_completed_usage_tiles(monkeypatch):
    import copy
    import telemetry_totals as telemetry
    chain={'original':['original'],'retry':['original','retry'],'latest':['original','retry','latest']}
    monkeypatch.setattr(continuations,'tags',lambda tag:chain[tag])
    def execution(tag,start,end):
        config={'combination_plan':{'total_loops':64,'combinations':64,'repetitions':1,
                                   'execution_order':'all_pipelines_first'},'trials':1}
        if start>1:config['retry_selection']={'loops':list(range(start,65))}
        return {'tag':tag,'pipeline_id':'p','configuration':config,'calls':[],
                'outcomes':{str(n):{'outcome':'completed'} for n in range(start,end+1)}}
    executions=[execution('original',1,28),execution('retry',29,49),execution('latest',50,64)]
    executions[1]['outcomes'].update({str(n):{'outcome':'blocked'} for n in (22,23,24)})
    executions[1]['outcomes']['50']={'outcome':'running'}
    executions[1]['execution_status']={'status':'failed'}
    original=copy.deepcopy(executions)
    usage=telemetry.continued_usage(executions,[])[-1]
    assert len(usage['loops'])==64
    assert all(loop['status']=='completed' for loop in usage['loops'])
    assert telemetry.scoped_outcomes(executions[1])['50']['outcome']=='blocked'
    assert all(str(n) not in telemetry.scoped_outcomes(executions[1]) for n in (22,23,24))
    assert executions==original


@pytest.mark.parametrize('damage', ['missing', 'other_study', 'cycle', 'unreadable', 'disagreement'])
def test_broken_history_never_becomes_a_smaller_complete_total(history, damage):
    root, _ = history
    if damage == 'unreadable':
        (root / 'retry/retry_lineage.json').write_text('{')
    elif damage == 'disagreement':
        (root / 'retry/retry_lineage.json').write_text('{"source_run_tag":"fresh"}')
    else:
        path = root / 'old/config.json'
        config = json.loads(path.read_text())
        if damage == 'missing':
            path.unlink()
        elif damage == 'other_study':
            config['dataset_sha256'] = 'different'
        else:
            config['retry_selection'] = {'source_run_tag': 'retry'}
        if damage != 'missing':
            path.write_text(json.dumps(config))
        archive._index_expires = 0
    with pytest.raises(HTTPException):
        continuations.tags('retry')


def test_workspace_cost_retains_prior_failed_attempts_without_double_count(history, monkeypatch):
    _, ids = history
    rows = [{'id': ids[0], 'status': 'failed', 'cost_estimate': 2, 'tokens': 100},
            {'id': ids[1], 'status': 'completed', 'cost_estimate': 3, 'tokens': 200}]
    conn = AsyncMock()
    conn.fetch.return_value = rows
    async def read(store, callback, fallback):
        return await callback(conn)
    monkeypatch.setattr(costs.pools, 'guarded', read)
    result = asyncio.run(costs.workspace_cost(['retry', 'old']))
    assert result['usd'] == 5 and result['agent_runs'] == 2
    assert result['shared_agent_runs'] == 1
    assert result['executions'][1]['usd'] == 5
    assert result['executions'][1]['run_tags'] == ['old', 'retry']
    conn.fetch.assert_awaited_once()


def test_results_keep_original_execution_and_trial(history, monkeypatch):
    import main
    import output_results
    async def results(tag):
        return [{'result_id': 1 if tag == 'old' else 2, 'trial': 0 if tag == 'old' else 1}]
    monkeypatch.setattr(output_results, 'results', results)
    monkeypatch.setattr(main.scene, '_board', AsyncMock(return_value=[]))
    monkeypatch.setattr(main.pools.health, 'as_dict', lambda: {'memstara': {'up': True}})
    result = asyncio.run(main.pipeline_results('retry'))
    assert [(r['run_tag'], r['iteration']) for r in result['results']] == [('old', 1), ('retry', 2)]


def test_report_text_is_not_rewritten_or_relabelled(history, monkeypatch):
    saved = {tag: {'report': {'text': tag, 'explanation_outputs': [
        {'loop': i + 1, 'result_id': i + 1, 'text': f'Original {tag}\n', 'status': 'completed'}]}}
        for i, tag in enumerate(('old', 'retry'))}
    monkeypatch.setattr(archive, 'lookup', saved.get)
    report = continuations.reports(['old', 'retry'], saved['retry'])
    assert report['text'] == 'retry'
    assert [o['run_tag'] for o in report['explanation_outputs']] == ['old', 'retry']
    assert report['explanation_outputs'][0]['text'] == 'Original old\n'


def test_usage_accumulates_repeated_loop_attempts_and_excludes_fresh(history):
    from telemetry_totals import continued_usage
    _, ids = history
    config = archive.config_for('retry')
    executions = [{'tag': tag, 'pipeline_id': 'experiment', 'configuration': config,
                   'calls': [{'run_id': ids[i], 'loop': 2}],
                   'outcomes': {'2': {'outcome': status, 'started_at': 10, 'ended_at': 20}}}
                  for i, (tag, status) in enumerate((('old', 'blocked'), ('retry', 'completed')))]
    rows = [{'id': ids[0], 'status': 'failed', 'cost_estimate': 2, 'tokens': 100},
            {'id': ids[1], 'status': 'completed', 'cost_estimate': 3, 'tokens': 200}]
    result = continued_usage(executions, rows)[1]
    assert result['calls'] == 2 and result['cost']['usd'] == 5 and result['tokens'] == 300
    assert len(result['loops']) == 1
    assert result['loops'][0]['status'] == 'completed'
    assert result['loops'][0]['cost']['usd'] == 5
    assert result['loop_summary']['excluded_completed'] == 1


def test_snapshot_accumulates_findings_but_live_calls_remain_current(history, monkeypatch):
    import scene
    async def results(tag):
        return [{'result_id': 1 if tag == 'old' else 2, 'trial': 0 if tag == 'old' else 1}]
    core = AsyncMock(return_value={'open': [], 'touches': []})
    monkeypatch.setattr(scene, 'list_runs', AsyncMock(return_value=[]))
    monkeypatch.setattr(scene, '_board', AsyncMock(return_value=[]))
    monkeypatch.setattr(scene, '_results', results)
    monkeypatch.setattr(scene, '_core_facts', core)
    monkeypatch.setattr(scene, '_build_scene', lambda *args: {'agents': []})
    monkeypatch.setattr(scene, '_agent_totals', lambda *args: [])
    monkeypatch.setattr(scene, '_access', lambda *args: {})
    monkeypatch.setattr(scene, '_feed', lambda *args: [])
    result = asyncio.run(scene._snapshot_uncached('retry'))
    assert [r['run_tag'] for r in result['results']] == ['old', 'retry']
    assert result['report']['run_tags'] == ['old', 'retry']
    assert result['run_tag'] == 'retry' and result['board']['tasks'] == []
    assert core.call_args.args[0] == [history[1][1]]


def test_request_cost_evidence_uses_one_query_for_both_execution_attempts(history, monkeypatch):
    import cost_details
    import motoro_records
    ids = history[1]
    conn = AsyncMock()
    conn.fetch.side_effect = [
        [{'id': key, 'status': 'completed'} for key in ids],
        [{'id': f'step-{i}', 'run_id': key, 'llm_call': {'cost_estimate': i + 1}}
         for i, key in enumerate(ids)]]
    async def read(callback):
        return await callback(conn)
    monkeypatch.setattr(motoro_records, 'read_core', read)
    result = asyncio.run(cost_details.motoro_details('retry', include_continuations=True))
    assert result['usd'] == 3 and result['recorded_calls'] == 2
    assert [r['run_tag'] for r in result['records']] == ['old', 'retry']
    assert {str(key) for key in conn.fetch.call_args.args[1]} == set(ids)


def test_live_summary_uses_same_continuation_scope_as_tiles(history, monkeypatch):
    import discovery
    conn = AsyncMock()
    conn.fetch.return_value = []
    async def read(store, callback, fallback):
        return await callback(conn)
    monkeypatch.setattr(discovery.pools, 'guarded', read)
    result = asyncio.run(discovery.live_outputs(['retry']))
    assert result['run_tags'] == ['old', 'retry']
    assert result['continuation_groups'] == {'retry': ['old', 'retry']}
    assert all(call.args[1] == ['old', 'retry'] for call in conn.fetch.call_args_list)
    conn.fetch.reset_mock()
    fresh = asyncio.run(discovery.live_outputs(['fresh']))
    assert fresh['run_tags'] == ['fresh']
    assert all(call.args[1] == ['fresh'] for call in conn.fetch.call_args_list)
