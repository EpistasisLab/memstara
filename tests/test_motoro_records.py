"""Runtime provenance, scope isolation and unavailable records cannot be substituted."""
import asyncio
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import motoro_records as records
import cost_details
import costs

RUN='11111111-1111-1111-1111-111111111111'
ARCHIVE={'calls':[{'run_id':RUN,'stage':'ml','loop':1,'seq':0,'status':'completed','cost':999}]}


def mock_database(monkeypatch, conn):
    monkeypatch.setattr(records.run_artifacts,'lookup',lambda tag:ARCHIVE)
    async def guarded(store, callback, fallback):
        assert store=='core'
        return await callback(conn)
    monkeypatch.setattr(records.pools,'guarded',guarded)


def test_runtime_state_and_usage_come_from_motoro_not_archive(monkeypatch):
    conn=AsyncMock();conn.fetch.return_value=[{'id':RUN,'status':'failed','token_usage':'{"prompt_tokens":12}','cost_estimate':.04}]
    mock_database(monkeypatch,conn)
    value=asyncio.run(records.execution('selected',1))
    assert value['source']=='motoro'
    call=value['calls'][0]
    assert call['record']['status']=='failed'
    assert call['record']['token_usage']=={'prompt_tokens':12}
    assert call['record']['cost_estimate']==.04
    assert call['loop']==1 and 'cost' not in call
    assert conn.fetch.call_args.args[1]==[uuid.UUID(RUN)]
    conn.fetch.reset_mock()
    assert asyncio.run(records.execution('selected',2))['calls']==[]
    conn.fetch.assert_not_called()


def test_missing_record_is_explicit_not_replaced_with_archive(monkeypatch):
    conn=AsyncMock();conn.fetch.return_value=[];mock_database(monkeypatch,conn)
    call=asyncio.run(records.execution('selected'))['calls'][0]
    assert call['availability']=='missing' and call['record'] is None


def test_outage_not_empty_success(monkeypatch):
    monkeypatch.setattr(records.run_artifacts,'lookup',lambda tag:ARCHIVE)
    monkeypatch.setattr(records.pools,'guarded',AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as error:asyncio.run(records.execution('selected'))
    assert error.value.status_code==503


def test_other_execution_cannot_read_run_payload(monkeypatch):
    monkeypatch.setattr(records.run_artifacts,'lookup',lambda tag:ARCHIVE)
    db=AsyncMock();monkeypatch.setattr(records.pools,'guarded',db)
    with pytest.raises(HTTPException) as error:asyncio.run(records.run('selected',uuid.uuid4()))
    assert error.value.status_code==404
    db.assert_not_called()


def test_full_run_keeps_io_and_snapshots_but_redacts_credentials(monkeypatch):
    record={'id':RUN,'input':'research task','output':'answer','state_snapshot':{'iteration':3},
            'config_snapshot':{'model':'model','api_key':'private'}, 'model_config_overrides':{'temperature':1}}
    conn=AsyncMock();conn.fetch.return_value=[{'record':json.dumps(record)}];mock_database(monkeypatch,conn)
    result=asyncio.run(records.run('selected',RUN))['record']
    assert result['input']=='research task' and result['output']=='answer'
    assert result['config_snapshot']=={'model':'model','api_key':'[REDACTED]'}
    assert result['state_snapshot']=={'iteration':3}
    assert 'WHERE id=$1' in conn.fetch.call_args.args[0]


def test_cost_details_sum_only_persisted_motoro_amounts():
    calls=ARCHIVE['calls']
    runs=[{'id':RUN,'status':'completed'}]
    steps=[{'id':'s1','run_id':RUN,'llm_call':json.dumps({'model':'m','cost_estimate':.25,'prompt_tokens':10,'completion_tokens':2,'latency_ms':54,'cache_read_input_tokens':3})},
           {'id':'s2','run_id':RUN,'llm_call':{'model':'m','cost_estimate':0,'prompt_tokens':10}}]
    value=cost_details.summarize_motoro('selected',calls,runs,steps+steps)
    assert value['usd']==.25 and value['recorded_calls']==2
    assert value['status']=='partial' and value['unpriced_calls']==1
    assert value['records'][0]['latency_ms']==54
    assert value['records'][0]['cache_read_input_tokens']==3
    assert value['records'][1]['usd'] is None
    assert value['records'][0]['price_receipt'] is None


def test_cost_endpoint_reads_core_only(monkeypatch):
    conn=AsyncMock();conn.fetch.side_effect=[[{'id':RUN,'status':'completed'}],[{'id':'s','run_id':RUN,'llm_call':{'model':'m','cost_estimate':.5}}]]
    mock_database(monkeypatch,conn)
    monkeypatch.setattr(cost_details,'details',lambda tag:pytest.fail('Local ledger must not be read'))
    assert asyncio.run(cost_details.motoro_details('selected'))['usd']==.5
    assert 'run_steps' in conn.fetch.call_args.args[0]


def test_workspace_totals_ignore_local_ledger(monkeypatch):
    conn=AsyncMock();conn.fetch.return_value=[{'id':RUN,'status':'completed','cost_estimate':.3,'tokens':12}]
    mock_database(monkeypatch,conn)
    monkeypatch.setattr(costs,'with_ledgers',lambda *args:pytest.fail('Local override must not be applied'))
    assert asyncio.run(costs.workspace_cost(['selected']))['usd']==.3


def test_cost_details_filter_loop_before_reading_motoro(monkeypatch):
    other='22222222-2222-2222-2222-222222222222'
    conn=AsyncMock();conn.fetch.side_effect=[[{'id':RUN,'status':'completed'}],[{'id':'s','run_id':RUN,'llm_call':{'model':'m','cost_estimate':.5}}]]
    mock_database(monkeypatch,conn)
    monkeypatch.setattr(records.run_artifacts,'lookup',lambda tag:{'calls':[
        *ARCHIVE['calls'],{'run_id':other,'stage':'ml','loop':2,'seq':1}]})
    result=asyncio.run(cost_details.motoro_details('selected',1))
    assert result['loop']==1 and result['usd']==.5
    for call in conn.fetch.call_args_list:
        assert [str(x) for x in call.args[1]]==[RUN]
    conn.fetch.reset_mock()
    empty=asyncio.run(cost_details.motoro_details('selected',3))
    assert empty['loop']==3 and empty['status']=='unavailable'
    conn.fetch.assert_not_called()
