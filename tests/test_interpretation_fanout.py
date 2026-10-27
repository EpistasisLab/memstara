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
        assert call.args[2] == 'view 1\n\nview 2'
        assert 'view 3' not in call.args[2]
    asyncio.run(check())


def test_combination_uses_current_loop_skill_without_extra_branches():
    import json
    async def check():
        conn=AsyncMock()
        skills={stage:[{'id':stage}] for stage in ('hypothesis','data','ml','interpreter','report')}
        skills['interpreter']=[{'id':'shared-shap'},{'id':'shared-lime'}]
        config={'interpretation_mode':'all_per_hypothesis','interpreters':3,
                'books':{'interpreter':['shared-shap','shared-lime']},
                'combination_plan':{'skills':skills,'total_loops':2,'combinations':2}}
        await expand(conn,10,config,trial=1)
        assert conn.execute.await_count==1
        branch=json.loads(conn.execute.call_args.args[2])['interpretation_branch']
        assert branch['skill']=='shared-lime'
        assert branch['total']==1 and branch['worker']=='interpret#1'
    asyncio.run(check())


def test_single_interpreter_preserves_exact_text_and_separate_limitations():
    import json
    async def check():
        text = "  # shared-shap\n\n| Confidence | Reproducibility |\n|---|---|\n| high | recorded |\n\n"
        conn = AsyncMock()
        conn.fetchval.return_value = None
        conn.fetch.return_value = [{'task_id': 4, 'status': 'done', 'error': '',
            'interpretation': text, 'evaluation': {'interpretation_branch': {
                'source_task_id': 4, 'slot': 1, 'total': 1, 'skill': 'shared-shap', 'worker': 'interpret#1'},
                'interpretation_limitations': '  Agent caveat\n'}}]
        await aggregate(conn, 4)
        assert conn.execute.call_args.args[2] == text
        item = json.loads(conn.execute.call_args.args[3])['interpretations'][0]
        assert item['text'] == text and item['limitations'] == '  Agent caveat\n'
    asyncio.run(check())


def test_submit_keeps_interpretation_and_limitations_separate(monkeypatch):
    from unittest.mock import MagicMock
    from memstara.mcp_servers import blackboard as bb
    import json
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    conn.fetchval.return_value = None
    conn.fetchrow.return_value = {'task_id': 1, 'task_type': 'interpret', 'trial': 0,
        'status': 'in_progress', 'claimed_by': 'interpret#1', 'evaluation': {},
        'subset_path': '', 'y_column': 'Y', 'columns': [], 'hypothesis': 'Question', 'perspective': ''}
    monkeypatch.setattr(bb, '_pipeline_run', lambda: '')
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {})
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    text = '  # Original agent output\n\n'
    caveat = '  A separately supplied caveat.\n'
    reply = json.loads(asyncio.run(bb.submit_result(1, worker='interpret#1', interpretation=text, limitations=caveat)))
    assert reply.get('ok'), reply
    writes = conn.execute.call_args_list
    record = next(json.loads(c.args[2]) for c in writes if c.args[0].startswith('UPDATE memstara_blackboard SET evaluation='))
    assert record['interpretation_limitations'] == caveat
    saved = next(c for c in writes if 'NULLIF($7' in c.args[0])
    assert saved.args[7] == text
