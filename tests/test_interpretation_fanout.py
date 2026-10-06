"""Per-skill routing and hypothesis-level aggregation contracts."""
import asyncio
from unittest.mock import AsyncMock
from memstara.interpretation_fanout import pending_slots, expand, aggregate
from memstara.pipeline.scheduler import StageWorkers


def test_only_the_assigned_free_worker_is_selected():
    tasks = [{'task_type': 'interpret', 'status': 'ready',
              'evaluation': {'interpretation_branch': {'slot': 3}}}]
    assert StageWorkers().available('interpreter', 3, 1, pending_slots(tasks)) == [3]
    assert pending_slots([{'task_type': 'interpret', 'status': 'ready'}]) is None


def test_legacy_snapshot_does_not_expand_and_new_snapshot_creates_all_slots():
    async def check():
        conn = AsyncMock()
        await expand(conn, 10, {'interpreters': 3})
        conn.execute.assert_not_called()
        await expand(conn, 10, {'interpretation_mode': 'all_per_hypothesis', 'interpreters': 3,
                               'books': {'interpreter': ['clinical', 'robustness', 'actionability']}})
        assert conn.execute.await_count == 3
        import json
        branches = [json.loads(c.args[2])['interpretation_branch'] for c in conn.execute.call_args_list]
        assert [b['worker'] for b in branches] == ['interpret#1', 'interpret#2', 'interpret#3']
        assert {b['source_task_id'] for b in branches} == {10}
    asyncio.run(check())


def test_aggregate_preserves_all_perspectives_and_marks_missing_results():
    async def check():
        import json
        conn = AsyncMock()
        conn.fetchval.return_value = 123
        conn.fetch.return_value = [
            {'task_id': i, 'status': status, 'error': '', 'interpretation': f'view {i}',
             'evaluation': {'interpretation_branch': {'source_task_id': 1, 'slot': i,
                            'total': 3, 'worker': f'interpret#{i}', 'skill': f'skill{i}'}}}
            for i, status in [(1, 'done'), (2, 'done'), (3, 'failed')]]
        await aggregate(conn, 1)
        call = conn.execute.call_args
        summary = json.loads(call.args[3])
        assert len(summary['interpretations']) == 3
        assert not summary['interpretations_complete']
        assert 'view 1' in call.args[2] and 'view 2' in call.args[2]
        assert 'view 3' not in call.args[2]
    asyncio.run(check())


def test_combination_uses_current_loop_skill_without_extra_branches():
    import json
    async def check():
        conn=AsyncMock()
        skills={stage:[{'id':stage}] for stage in ('hypothesis','data','ml','interpreter','report')}
        skills['interpreter']=[{'id':'shared-anil-shap'},{'id':'shared-anil-lime'}]
        config={'interpretation_mode':'all_per_hypothesis','interpreters':3,
                'books':{'interpreter':['shared-anil-shap','shared-anil-lime']},
                'combination_plan':{'skills':skills,'total_loops':2,'combinations':2}}
        await expand(conn,10,config,trial=1)
        assert conn.execute.await_count==1
        branch=json.loads(conn.execute.call_args.args[2])['interpretation_branch']
        assert branch['skill']=='shared-anil-lime'
        assert branch['total']==1 and branch['worker']=='interpret#1'
    asyncio.run(check())
