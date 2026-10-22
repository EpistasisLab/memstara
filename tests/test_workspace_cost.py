import sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer' / 'api'))
from costs import summarize


def test_deduplicated_scoped_cost_excludes_other_runs():
    rows=[{'id':'a','status':'completed','cost_estimate':Decimal('0.125'),'tokens':20},
          {'id':'b','status':'completed','cost_estimate':900,'tokens':20}]
    result=summarize({'a'}, rows)
    assert result['usd']==0.125 and result['agent_runs']==1 and result['status']=='complete'


def test_missing_pricing_and_active_calls_are_partial():
    rows=[{'id':'a','status':'running','cost_estimate':None,'tokens':0},
          {'id':'b','status':'completed','cost_estimate':0,'tokens':50}]
    result=summarize({'a','b','missing'}, rows)
    assert result['status']=='partial' and result['missing_costs']==3 and result['pending_runs']==1


def test_empty_workspace_is_zero_but_missing_archive_is_not_complete():
    assert summarize(set(),[])['usd']==0
    assert summarize(set(),[],1)['status']=='partial'


def test_endpoint_deduplicates_shared_ids_across_archives(monkeypatch):
    import asyncio
    import costs
    from unittest.mock import AsyncMock
    run_id='11111111-1111-1111-1111-111111111111'
    monkeypatch.setattr(costs.run_artifacts,'lookup',lambda tag:{'calls':[{'run_id':run_id},{'run_id':run_id}]})
    conn=AsyncMock()
    conn.fetch.return_value=[{'id':run_id,'status':'completed','cost_estimate':0.3,'tokens':10}]
    async def guarded(store,read,fallback):return await read(conn)
    monkeypatch.setattr(costs.pools,'guarded',guarded)
    result=asyncio.run(costs.workspace_cost(['second','first','first']))
    assert result['run_tags']==['first','second']
    assert result['usd']==0.3 and result['agent_runs']==1
    assert len(conn.fetch.call_args.args[1])==1
    assert result['shared_agent_runs']==1
    assert [e['usd'] for e in result['executions']]==[0.3,0.3]


def test_breakdown_and_total_use_one_motoro_snapshot(monkeypatch):
    import asyncio
    import costs
    from unittest.mock import AsyncMock
    run_a='11111111-1111-1111-1111-111111111111'
    run_b='22222222-2222-2222-2222-222222222222'
    archives={'first':{'calls':[{'run_id':run_a},{'run_id':run_a}]},
              'second':{'calls':[{'run_id':run_b}]}}
    monkeypatch.setattr(costs.run_artifacts,'lookup',archives.get)
    conn=AsyncMock()
    conn.fetch.return_value=[
        {'id':run_a,'status':'completed','cost_estimate':Decimal('1.25'),'tokens':10},
        {'id':run_b,'status':'completed','cost_estimate':Decimal('2.50'),'tokens':10}]
    async def guarded(store,read,fallback):return await read(conn)
    monkeypatch.setattr(costs.pools,'guarded',guarded)
    result=asyncio.run(costs.workspace_cost(['second','first']))
    assert result['usd']==sum(e['usd'] for e in result['executions'])==3.75
    assert result['shared_agent_runs']==0
    assert [e['run_tag'] for e in result['executions']]==['first','second']
    assert all(e['updated_at']==result['updated_at'] for e in result['executions'])
    conn.fetch.assert_awaited_once()


def test_breakdown_preserves_unavailable_archives_and_pricing(monkeypatch):
    import asyncio
    import costs
    from unittest.mock import AsyncMock
    run_id='11111111-1111-1111-1111-111111111111'
    monkeypatch.setattr(costs.run_artifacts,'lookup',lambda tag:
                        {'calls':[{'run_id':run_id}]} if tag=='unpriced' else None)
    monkeypatch.setattr(costs.pools,'guarded',AsyncMock(return_value=[
        {'id':run_id,'status':'completed','cost_estimate':None,'tokens':10}]))
    result=asyncio.run(costs.workspace_cost(['unpriced','missing']))
    assert result['status']=='partial' and result['usd']==0
    assert result['executions'][0]['missing_archives']==1
    assert result['executions'][1]['missing_costs']==1
    assert all(e['status']=='partial' for e in result['executions'])


def test_database_failure_is_not_reported_as_zero(monkeypatch):
    import asyncio
    import costs
    import pytest
    from fastapi import HTTPException
    from unittest.mock import AsyncMock
    monkeypatch.setattr(costs.run_artifacts,'lookup',lambda tag:
                        {'calls':[{'run_id':'11111111-1111-1111-1111-111111111111'}]})
    monkeypatch.setattr(costs.pools,'guarded',AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as err:
        asyncio.run(costs.workspace_cost(['first']))
    assert err.value.status_code==503


def test_partially_priced_positive_subtotal_cannot_be_complete():
    row={'id':'a','status':'completed','cost_estimate':.25,'tokens':100,'pricing_incomplete':True}
    result=summarize({'a'},[row])
    assert result['usd']==.25 and result['status']=='partial' and result['missing_costs']==1


def test_invalid_amounts_are_not_reported_as_real_costs():
    for amount in (float('nan'),float('inf'),-1):
        result=summarize({'a'},[{'id':'a','status':'completed','cost_estimate':amount,'tokens':1}])
        assert result['status']=='partial' and result['usd']==0
