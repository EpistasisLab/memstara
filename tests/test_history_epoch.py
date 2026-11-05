"""A successful reset must never resurrect old API caches or in-flight reads."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'viewer/api'))
import history_epoch
import run_artifacts
from fastapi.responses import JSONResponse


def marker(root, revision, busy=False):
    (root/'history_epoch.json').write_text(json.dumps({'revision':revision,'busy':busy}))


def test_changed_epoch_discards_an_old_inflight_response(tmp_path,monkeypatch):
    monkeypatch.setattr(run_artifacts,'ROOT',tmp_path)
    monkeypatch.setattr(history_epoch,'_seen',None)
    marker(tmp_path,'old')
    async def next_request(request):
        marker(tmp_path,'new')
        return JSONResponse({'results':['must not leak old result']})
    response=asyncio.run(history_epoch.barrier(SimpleNamespace(url=SimpleNamespace(path='/api/runs')),next_request))
    assert response.status_code==503 and b'must not leak' not in response.body


def test_reset_barrier_blocks_reads_while_deletion_is_active(tmp_path,monkeypatch):
    monkeypatch.setattr(run_artifacts,'ROOT',tmp_path)
    monkeypatch.setattr(history_epoch,'_seen',None)
    marker(tmp_path,'old',True)
    async def next_request(request):raise AssertionError('Must not query partially cleared databases')
    response=asyncio.run(history_epoch.barrier(SimpleNamespace(url=SimpleNamespace(path='/api/runs')),next_request))
    assert response.status_code==503


def test_epoch_invalidation_clears_cached_totals_narratives_and_background_jobs(tmp_path,monkeypatch):
    import scene,telemetry,telemetry_totals,discovery,flat_history,explanation_outputs
    monkeypatch.setattr(run_artifacts,'ROOT',tmp_path)
    monkeypatch.setattr(history_epoch,'_seen',None)
    marker(tmp_path,'new')
    telemetry._cache['old']=(0,{'old':True})
    scene._snapshot_cache['old']=(0,{'old':True})
    telemetry_totals._cache=(0,{'old':True})
    flat_history._cache['old']=(0,{'old':True})
    discovery._live_ready[('old',)]=0
    run_artifacts._config_index={'old':{'run_tag':'old'}}
    run_artifacts._index_expires=float('inf')
    async def scenario():
        pending=asyncio.create_task(asyncio.sleep(60))
        telemetry._inflight['old']=pending
        async def next_request(request):return JSONResponse({'results':[]})
        response=await history_epoch.barrier(SimpleNamespace(url=SimpleNamespace(path='/api/runs')),next_request)
        assert response.status_code==200 and response.headers['X-Memstara-History-Revision']=='new'
        assert pending.cancelled()
    asyncio.run(scenario())
    assert not telemetry._cache and not telemetry._inflight and not scene._snapshot_cache
    assert telemetry_totals._cache is None and not discovery._live_ready and not flat_history._cache
    assert run_artifacts._config_index is None


def test_malformed_epoch_is_unavailable_not_old_success(tmp_path,monkeypatch):
    monkeypatch.setattr(run_artifacts,'ROOT',tmp_path)
    (tmp_path/'history_epoch.json').write_text('invalid')
    async def next_request(request):raise AssertionError('Invalid reset state must not expose history')
    response=asyncio.run(history_epoch.barrier(SimpleNamespace(url=SimpleNamespace(path='/api/runs')),next_request))
    assert response.status_code==503
