"""Aggregation must never double count, invent durations, or hide missing prices."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
from telemetry_totals import metrics, loop_metrics


def test_distinct_calls_and_partial_pricing():
    calls=[{'run_id':'one'},{'run_id':'one'},{'run_id':'missing'}]
    rows=[{'id':'one','tokens':50,'cost_estimate':0,'status':'completed'},
          {'id':'other','tokens':100,'cost_estimate':9,'status':'completed'}]
    result=metrics(calls,rows)
    assert result['calls']==2 and result['tokens']==50
    assert result['cost']['status']=='partial' and result['missing_calls']==1
    assert result['cost']['usd']==0


def test_duration_is_wall_clock_not_sum_of_parallel_calls():
    calls=[{'started_at':10,'duration_seconds':10},{'started_at':12,'duration_seconds':5}]
    approximate=loop_metrics(calls,[],{'outcome':'completed'})
    assert approximate['seconds']==10 and 'approximate' in approximate['duration_basis']
    recorded=loop_metrics(calls,[],{'outcome':'completed','started_at':9,'ended_at':22})
    assert recorded['seconds']==13 and recorded['duration_basis']=='recorded loop boundaries'
    assert loop_metrics([],[],{})['seconds'] is None


def test_conversation_reads_only_selected_loop_and_preserves_answer(monkeypatch):
    import asyncio
    import json
    from unittest.mock import AsyncMock
    import conversation
    first='11111111-1111-1111-1111-111111111111'
    other='22222222-2222-2222-2222-222222222222'
    monkeypatch.setattr(conversation.run_artifacts,'lookup',lambda tag:{'calls':[
        {'run_id':first,'stage':'hypothesis','loop':1}, {'run_id':other,'stage':'report','loop':2}]})
    conn=AsyncMock()
    conn.fetch.return_value=[{'id':first,'run_id':first,'started_at':None,
                             'output':json.dumps({'final_answer':'The actual answer.','thought':'not the answer'})}]
    async def guarded(name,read,fallback):return await read(conn)
    monkeypatch.setattr(conversation.pools,'guarded',guarded)
    result=asyncio.run(conversation.conversation('selected',1))
    sql,ids=conn.fetch.call_args.args
    assert 'messages AS MATERIALIZED' in sql
    assert 'text_fields.final_answer' in sql
    assert "telemetry_jsonb('s.output_data')" not in sql
    assert [str(i) for i in ids]==[first]
    assert result['messages'][0]['text']=='The actual answer.'
    assert result['messages'][0]['loop']==1
    assert result['messages'][1]['text']=='not the answer'
    assert result['messages'][1]['kind']=='thought'


def test_activity_text_uses_only_nonempty_recorded_fields():
    from conversation import text_outputs
    assert text_outputs({'thought':'I am mapping the available columns.', 'final_answer':'Done.'}) == [
        ('final_answer','Agent answer','Done.'), ('thought','Agent note','I am mapping the available columns.')]
    assert text_outputs({'tool_calls':[{'text':'not an agent message'}], 'thought':' ', 'message':False}) == []
    assert text_outputs(None) == []
    assert text_outputs({'final_answer':'Same', 'thought':'Same'}) == [('final_answer','Agent answer','Same')]


def test_token_completeness_and_deduplication():
    calls = [{'run_id': 'a'}, {'run_id': 'a'}]
    row = {'id': 'a', 'tokens': 20, 'tokens_recorded': False, 'cost_estimate': .1, 'status': 'completed'}
    result = metrics(calls, [row, row])
    assert result['tokens'] == 20 and result['tokens_status'] == 'partial'
    row['tokens_recorded'] = True
    row['status'] = 'running'
    assert metrics(calls, [row])['tokens_status'] == 'partial'


def test_completed_average_uses_same_complete_cohort_for_all_metrics():
    from telemetry_totals import completed_summary
    base = {'status': 'completed', 'seconds': 60, 'calls': 2, 'attribution': 'recorded',
            'duration_basis': 'recorded loop boundaries', 'cost': {'status': 'complete', 'usd': .2},
            'tokens': 100, 'tokens_status': 'complete'}
    rows = [base, {**base, 'seconds': 120, 'cost': {'status': 'complete', 'usd': .4}, 'tokens': 300},
            {**base, 'status': 'blocked'}, {**base, 'status': 'running'},
            {**base, 'tokens_status': 'partial'}, {**base, 'attribution': 'approximate'},
            {**base, 'duration_basis': 'archived agent-call span (approximate)'}]
    summary = completed_summary(rows)
    assert summary['sample_count'] == 2 and summary['excluded_completed'] == 3
    assert summary['other_loops'] == 2
    assert summary['seconds'] == {'mean': 90, 'median': 90, 'min': 60, 'max': 120}
    assert summary['tokens']['mean'] == 200
    assert round(summary['usd']['mean'], 5) == .3
    assert completed_summary([])['seconds'] is None


def test_invalid_loop_clock_is_unavailable_not_zero():
    result = loop_metrics([], [], {'outcome': 'completed', 'started_at': 20, 'ended_at': 10})
    assert result['seconds'] is None


def test_tab_projection_does_not_send_results_or_mutate_cached_history():
    from telemetry import project
    data={'telemetry':{'loop':None},'results':[{'expensive':'document'}],
          'agents':[{'name':'worker'}],'board':{'tasks':[{'task_id':1}],'lanes':{}},
          'feed':[], 'access':[], 'loop_log':{'lines':['a']}}
    agents=project(data,'Agents')
    assert agents['agents']==data['agents'] and agents['results']==[]
    assert agents['telemetry']['included_sections']==['agents']
    assert data['results']==[{'expensive':'document'}]
    assert project(data,'Results')['results']==data['results']
    assert project(data) is data


def test_motoro_span_uses_observed_timestamps_not_sum_or_local_clock():
    from datetime import UTC, datetime
    from telemetry_totals import recorded_span
    stamp = lambda n: datetime.fromtimestamp(n, UTC)
    calls = [{'run_id': 'a'}, {'run_id': 'b'}, {'run_id': 'a'}]
    rows = [{'id':'a','started_at':stamp(10),'completed_at':stamp(30)},
            {'id':'b','started_at':stamp(20),'last_heartbeat_at':stamp(40)}]
    result = recorded_span(calls, rows)
    assert result['seconds'] == 30 and result['duration_status'] == 'partial'
    rows[1]['completed_at'] = stamp(45)
    assert recorded_span(calls, rows)['seconds'] == 35
    assert recorded_span(calls, rows)['duration_status'] == 'recorded'
    assert recorded_span(calls, [])['seconds'] is None
    assert recorded_span(calls, rows[:1])['duration_status'] == 'partial'
