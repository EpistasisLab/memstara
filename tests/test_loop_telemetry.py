"""Loop isolation must be enforced before aggregating tool calls or displaying logs."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer' / 'api'))
import loop_history
import run_artifacts
import scene
import telemetry


def test_recorded_loop_wins_and_global_calls_stay_unassigned():
    calls = [dict(stage='question0-1', started_at=10),
             dict(stage='ml#1', started_at=12),
             dict(stage='question1-1', started_at=20),
             dict(stage='ml#1', started_at=21),
             dict(stage='report', started_at=22, loop=None),
             dict(stage='late-retry', started_at=23, loop=1)]
    assigned = loop_history.call_loops(calls)
    assert [c['loop'] for c in assigned] == [1, 1, 2, 2, None, 1]
    assert assigned[1]['loop_source'] == 'recorded_boundary'
    assert assigned[-1]['loop_source'] == 'recorded'
    assert 'loop' not in calls[0]
    assert loop_history.call_loops([{'stage':'ml#1'}])[0]['loop'] is None


def test_numbering_and_logs_do_not_leak_between_loops(tmp_path):
    assert loop_history.record_loop({'trial': 3}, {'trials': 3}) == 2
    assert loop_history.record_loop({'trial': 1}, {}) is None
    (tmp_path/'console.log').write_text('setup\n round 1/continuous\nfirst\n round 2/continuous\nsecond\n (6) wrap up at the end\nfinal\n')
    assert loop_history.read_log(tmp_path, 1)['lines'] == [' round 1/continuous', 'first']
    assert loop_history.read_log(tmp_path, 2)['lines'] == [' round 2/continuous', 'second']
    assert not loop_history.read_log(tmp_path, 3)['lines']
    assert 'final' in loop_history.read_log(tmp_path, None)['lines']


def test_snapshot_filters_tasks_results_and_core_ids_before_aggregation(tmp_path, monkeypatch):
    calls = [dict(stage='question0-1', started_at=10, run_id='first', status='completed'),
             dict(stage='question1-1', started_at=20, run_id='second', status='completed'),
             dict(stage='report', started_at=30, run_id='global', loop=None, status='completed')]
    async def board(tag):
        assert tag == 'selected'
        return [dict(task_id=i, trial=i, status='done') for i in (0, 1)]
    async def results(tag):
        return [dict(result_id=i, trial=i) for i in (0, 1)]
    observed=[]
    async def core(ids):
        observed.append(ids)
        return {key: [] for key in ['totals','open','access','touches','last_call','roster','recent','feed']}
    monkeypatch.setattr(scene,'_board',board)
    monkeypatch.setattr(scene,'_results',results)
    monkeypatch.setattr(scene,'_core_facts',core)
    monkeypatch.setattr(run_artifacts,'lookup',lambda tag: dict(calls=calls, config={'trials':1}, report=None, pipeline=None))
    monkeypatch.setattr(run_artifacts,'directory_for',lambda tag: tmp_path)
    monkeypatch.setattr(scene.pools,'health',SimpleNamespace(memstara=True, core=True, as_dict=lambda:{'core':{'up':True},'memstara':{'up':True}}))
    (tmp_path/'iteration_outcomes.json').write_text(json.dumps({'1':{'outcome':'completed'},'2':{'outcome':'blocked'},'3':{'outcome':'running'}}))
    one = asyncio.run(scene._snapshot_uncached('selected', 1, telemetry=True))
    assert [t['trial'] for t in one['board']['tasks']] == [0]
    assert [r['trial'] for r in one['results']] == [0]
    assert observed[-1] == ['first']
    assert one['telemetry']['unassigned_calls'] == 1
    assert [c['number'] for c in one['telemetry']['loops']] == [1,2,3]
    two = asyncio.run(scene._snapshot_uncached('selected', 2, telemetry=True))
    assert observed[-1] == ['second']
    assert two['results'][0]['trial'] == 1
    empty = asyncio.run(scene._snapshot_uncached('selected', 3, telemetry=True))
    assert observed[-1] == []
    assert empty['results'] == []
    with pytest.raises(HTTPException) as failure:
        asyncio.run(scene._snapshot_uncached('selected', 4, telemetry=True))
    assert failure.value.status_code == 404


def test_cache_is_keyed_by_execution_and_loop(monkeypatch):
    telemetry._cache.clear()
    async def fetch(tag, loop, telemetry=False):
        return {'run_tag':tag,'telemetry':{'loop':loop},'health':{'core':{'up':True},'memstara':{'up':True}}}
    monkeypatch.setattr(scene,'_snapshot_uncached',fetch)
    async def check():
        first=await telemetry.snapshot('one',1)
        second=await telemetry.snapshot('one',2)
        other=await telemetry.snapshot('two',1)
        assert first['telemetry']['loop'] == 1
        assert second['telemetry']['loop'] == 2
        assert other['run_tag'] == 'two'
    asyncio.run(check())
    telemetry._cache.clear()


def test_database_failure_retains_only_the_same_scope(monkeypatch):
    telemetry._cache.clear()
    old = {'run_tag':'one', 'telemetry':{'loop':1}, 'results':[{'trial':0}]}
    telemetry._cache[('one',1)] = (0, old)
    async def unavailable(tag, loop, telemetry=False):
        return {'run_tag':tag,'telemetry':{'loop':loop},'results':[],
                'health':{'core':{'up':False},'memstara':{'up':False}}}
    monkeypatch.setattr(scene,'_snapshot_uncached',unavailable)
    async def check():
        first = await telemetry.snapshot('one',1)
        assert first['stale'] and first['results'] == [{'trial':0}]
        other = await telemetry.snapshot('one',2)
        assert other['results'] == [] and other['telemetry']['loop'] == 2
    asyncio.run(check())
    telemetry._cache.clear()


def test_slow_first_load_survives_http_timeout_and_is_reused(monkeypatch):
    telemetry._cache.clear()
    telemetry._inflight.clear()
    monkeypatch.setattr(telemetry, 'REQUEST_WAIT', .01)
    calls = []
    async def check():
        ready = asyncio.Event()
        async def fetch(tag, loop, telemetry=False):
            calls.append((tag, loop))
            await ready.wait()
            return {'run_tag':tag, 'telemetry':{'loop':loop},
                    'health':{'core':{'up':True},'memstara':{'up':True}}}
        monkeypatch.setattr(scene, '_snapshot_uncached', fetch)
        with pytest.raises(HTTPException) as pending:
            await telemetry.snapshot('slow', 2)
        assert pending.value.status_code == 202
        assert pending.value.detail == {'status':'loading','run_tag':'slow','loop':2}
        task = telemetry._inflight[('slow', 2)]
        assert not task.cancelled() and not task.done()
        second = asyncio.create_task(telemetry.snapshot('slow', 2))
        ready.set()
        result = await second
        assert result['telemetry']['loop'] == 2
        assert calls == [('slow', 2)]
        assert (await telemetry.snapshot('slow', 2)) == result
    asyncio.run(check())
    telemetry._cache.clear()


def test_client_disconnect_does_not_cancel_shared_refresh(monkeypatch):
    telemetry._cache.clear()
    telemetry._inflight.clear()
    async def check():
        started, ready = asyncio.Event(), asyncio.Event()
        async def fetch(tag, loop, telemetry=False):
            started.set()
            await ready.wait()
            return {'run_tag':tag, 'telemetry':{'loop':loop},
                    'health':{'core':{'up':True},'memstara':{'up':True}}}
        monkeypatch.setattr(scene, '_snapshot_uncached', fetch)
        client = asyncio.create_task(telemetry.snapshot('shared', 1))
        await started.wait()
        client.cancel()
        with pytest.raises(asyncio.CancelledError):
            await client
        ready.set()
        assert (await telemetry.snapshot('shared', 1))['run_tag'] == 'shared'
    asyncio.run(check())
    telemetry._cache.clear()
