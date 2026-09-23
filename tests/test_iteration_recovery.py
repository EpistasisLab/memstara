"""Regressions from empty iterations; synthetic evidence and no paid model calls."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from memstara.pipeline import board, question_contract as qc
from memstara.pipeline.exploration import record_round, write_progress, round_summary, finalize_rounds
from memstara.pipeline.recovery import ensure_artifact
from memstara.mcp_servers import blackboard as bb

PLAN = {'run_tag': 'run-a', 'y_column': 'Y', 'evaluation': {},
        'hypothesis_policy': {'question_contract': qc.VERSION},
        'recovery_policy': {'version': 'artifact_checked_v1'}}
ITEM = {'predictor_concepts': ['delirium'], 'source_ids': ['path-1'], 'okf_tags': ['symptom-bridge'],
        'rationale': 'Concrete phenotype from the documented path.'}
MAPPING = [{'concept': 'delirium', 'column': 'F1', 'source_id': 'path-1',
            'rationale': 'The measured indicator records the documented clinical phenotype.'}]


def test_missing_target_is_bound_but_explicit_mismatch_is_rejected():
    assert qc.make_contract(ITEM, PLAN)['target'] == 'Y'
    with pytest.raises(ValueError, match='target'):
        qc.make_contract({**ITEM, 'target': 'OTHER'}, PLAN)


@pytest.mark.parametrize('concept', ['SYMPTOMMANIFESTATIONOFDISEASE', 'ISA',
                                    'SYMPTOMMANIFESTATIONOFDISEASE (psychiatric endpoints)'])
def test_relation_names_cannot_become_predictors(concept):
    with pytest.raises(ValueError, match='graph relation'):
        qc.make_contract({**ITEM, 'predictor_concepts': [concept]}, PLAN)


def test_clinical_acronyms_remain_valid():
    assert qc.make_contract({**ITEM, 'predictor_concepts': ['CD4', 'MCV']}, PLAN)


def test_mapping_must_cover_the_question_and_actual_selected_features():
    contract = qc.make_contract(ITEM, PLAN)
    assert qc.validate_mapping(MAPPING, contract, ['F1'], ['path-1']) == MAPPING
    for mapping, cols in [(None, ['F1']), (MAPPING, ['F1', 'F2']),
                          ([{**MAPPING[0], 'concept': 'unrelated'}], ['F1']),
                          ([{**MAPPING[0], 'source_id': 'invented'}], ['F1'])]:
        with pytest.raises(ValueError):
            qc.validate_mapping(mapping, contract, cols, ['path-1'])


def connection(monkeypatch):
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    conn.fetch.return_value = []
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: PLAN)
    monkeypatch.setattr(bb, '_pipeline_run', lambda: 'run-a')
    return conn


def test_array_tool_input_and_legacy_json_both_work(monkeypatch):
    conn = connection(monkeypatch)
    conn.fetchval.return_value = 1
    for payload in ([ITEM], json.dumps([ITEM])):
        result = json.loads(asyncio.run(bb.propose_questions(payload)))
        assert result['added'][0]['text'] == 'Do delirium predict Y?'
    result = json.loads(asyncio.run(bb.propose_questions([{**ITEM, 'okf_tags': 'symptom-bridge'}])))
    assert result['rejected'][0]['why'] == 'okf_tags must be an array of strings'


def test_mcp_schema_exposes_fields_to_the_actual_model():
    schema = asyncio.run(bb.mcp.list_tools())
    proposal = next(tool for tool in schema if tool.name == 'propose_questions')
    serialized = json.dumps(proposal.inputSchema)
    for field in ('predictor_concepts', 'parent_task_ids', 'learning_goal', 'okf_tags'):
        assert field in serialized


def test_create_retry_returns_existing_task_without_insert(monkeypatch):
    conn = connection(monkeypatch)
    contract = qc.make_contract(ITEM, PLAN)
    question = {'text': qc.question_text(contract), 'question_contract': contract,
                'origin_run': 'run-a', 'claimed_run': 'run-a'}
    existing = {'task_id': 10, 'question_id': 1, 'status': 'done', 'task_type': 'interpret'}
    conn.fetchrow.side_effect = [question, existing]
    result = json.loads(asyncio.run(bb.create_task('run-a', 0, question['text'],
                       qc.hypothesis_text(contract), ['F1'], 'Y', ['path-1'], 1, MAPPING)))
    assert result['task_id'] == 10 and result['reused']
    conn.fetchval.assert_not_called()
    assert any('pg_advisory_xact_lock' in call.args[0] for call in conn.execute.call_args_list)
    conn.close.assert_awaited_once()


def test_create_requires_mapping_before_new_task(monkeypatch):
    conn = connection(monkeypatch)
    contract = qc.make_contract(ITEM, PLAN)
    question = {'text': qc.question_text(contract), 'question_contract': contract,
                'origin_run': 'run-a', 'claimed_run': 'run-a'}
    conn.fetchrow.return_value = question
    result = json.loads(asyncio.run(bb.create_task('run-a', 0, question['text'],
                       qc.hypothesis_text(contract), ['F1'], 'Y', ['path-1'], 1)))
    assert 'feature_mapping' in result['error']
    conn.fetchval.assert_not_called()


def test_call_failure_after_commit_is_not_replayed():
    async def scenario():
        present = AsyncMock(side_effect=[False, True])
        invoke = AsyncMock(side_effect=ConnectionError('reply lost after commit'))
        assert await ensure_artifact(invoke, present) == (True, None)
        invoke.assert_awaited_once()
    asyncio.run(scenario())


def test_completed_call_without_artifact_retries_only_twice():
    invoke = AsyncMock()
    ok, reason = asyncio.run(ensure_artifact(invoke, AsyncMock(return_value=False)))
    assert not ok and reason and invoke.await_count == 2


def test_existing_artifact_and_unavailable_database_never_replay():
    invoke = AsyncMock()
    assert asyncio.run(ensure_artifact(invoke, AsyncMock(return_value=True))) == (True, None)
    with pytest.raises(ConnectionError):
        asyncio.run(ensure_artifact(invoke, AsyncMock(side_effect=ConnectionError())))
    invoke.assert_not_awaited()


def test_cancellation_does_not_become_another_attempt():
    invoke = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ensure_artifact(invoke, AsyncMock(return_value=False)))
    invoke.assert_awaited_once()


def test_question_recovery_retains_same_wave_and_does_not_repeat_existing(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: PLAN)
    existing = {'question_id': 2, 'origin_run': 'run-a', 'origin_wave': 3, 'times_used': 0}
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': [existing]}))
    invoke = AsyncMock()
    monkeypatch.setattr(board, 'call_agent', invoke)
    result, dry = asyncio.run(board.questions_for_wave(None, {'hypothesis': 'agent'}, {'question': []},
                                                     run_tag='run-a', wave=3, want=1))
    assert result == [existing] and not dry
    invoke.assert_not_awaited()


def test_old_and_foreign_questions_are_not_recycled(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: PLAN)
    rows = [{'question_id': 1, 'origin_run': 'run-a', 'origin_wave': 2},
            {'question_id': 2, 'origin_run': 'other', 'origin_wave': 3}]
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': rows}))
    invoke = AsyncMock()
    monkeypatch.setattr(board, 'call_agent', invoke)
    assert asyncio.run(board.questions_for_wave(None, {'hypothesis': 'agent'}, {'question': []},
                                               run_tag='run-a', wave=3, want=1)) == ([], True)
    assert invoke.await_count == 2


def test_nine_attempts_with_one_result_are_not_nine_completed_iterations(tmp_path):
    record_round(tmp_path, 1, 'completed')
    for iteration in range(2, 10):
        record_round(tmp_path, iteration, 'blocked', 'No mapped task')
    write_progress(tmp_path, 9, 'hypothesis')
    state = json.loads((tmp_path / 'progress.json').read_text())
    assert state['exploration']['attempted'] == 9
    assert state['exploration']['completed'] == 1
    assert state['exploration']['blocked'] == 8
    assert not state['iteration_completed']
    record_round(tmp_path, 9, 'blocked')
    assert round_summary(tmp_path)['attempted'] == 9  # idempotent status write


def test_report_required_to_count_a_finished_round(tmp_path):
    record_round(tmp_path, 1, 'analysis_complete')
    assert round_summary(tmp_path)['completed'] == 0
    finalize_rounds(tmp_path, False)
    assert round_summary(tmp_path)['blocked'] == 1
    record_round(tmp_path, 2, 'analysis_complete')
    finalize_rounds(tmp_path, True)
    assert round_summary(tmp_path)['completed'] == 1


def test_stop_and_infrastructure_failure_close_only_unfinished_rounds(tmp_path):
    from memstara.pipeline.exploration import close_active_round
    record_round(tmp_path, 1, 'running')
    write_progress(tmp_path, 1, 'ml')
    close_active_round(tmp_path, 'interrupted', 'Stopped')
    assert round_summary(tmp_path)['outcome'] == 'interrupted'
    assert round_summary(tmp_path)['completed'] == 0
    record_round(tmp_path, 2, 'running')
    close_active_round(tmp_path, 'blocked', 'Database unavailable')
    assert round_summary(tmp_path)['blocked'] == 1
    record_round(tmp_path, 3, 'completed')
    close_active_round(tmp_path, 'interrupted', 'Stopped after saving')
    assert round_summary(tmp_path)['completed'] == 1


def test_bounded_pipeline_launch_does_not_change_saved_continuous_settings(monkeypatch):
    from types import SimpleNamespace
    from memstara.control import service
    saved = {'configuration': {'continuous': True, 'waves': 1, 'trials': 1}, 'name': 'test'}
    monkeypatch.setattr(service, 'WORKSPACE', SimpleNamespace(start=lambda key, launch, **options: launch('manager', saved)))
    handler = object.__new__(service.Handler)
    handler._launch = MagicMock()
    handler._send = MagicMock()
    handler._start({'pipeline_id': 'p1', 'iteration_limit': 10})
    assert handler._launch.call_args.args[0] == {'continuous': False, 'waves': 10, 'trials': 1}
    assert saved['configuration']['continuous'] is True and saved['configuration']['waves'] == 1
    handler._launch.reset_mock()
    handler._start({'pipeline_id': 'p1', 'iteration_limit': True})
    handler._launch.assert_not_called()
    assert handler._send.call_args.args[0] == 409


def test_question_keeps_source_documents_and_rejects_unknown_frozen_reference():
    plan = {**PLAN, 'knowledge_hashes': {'path-1.md': 'digest'}}
    assert qc.make_contract(ITEM, plan)['source_ids'] == ['path-1']
    with pytest.raises(ValueError, match='frozen knowledge'):
        qc.make_contract({**ITEM, 'source_ids': ['invented']}, plan)
    with pytest.raises(ValueError, match='source_ids'):
        qc.make_contract({**ITEM, 'source_ids': []}, plan)


def test_submit_schema_requires_worker_identity():
    tool = next(t for t in asyncio.run(bb.mcp.list_tools()) if t.name == 'submit_result')
    assert 'worker' in tool.inputSchema['required']


def test_permuted_features_are_the_same_question():
    assert bb._question_key('Do anemia; cough; pain predict Y?') == bb._question_key('Do Pain; Anemia; Cough predict Y?')
    assert bb._question_key('Do anemia; cough predict Y?') != bb._question_key('Do anemia; pain predict Y?')


def test_interpretation_retry_is_bounded_and_keeps_ml_artifact(monkeypatch):
    conn = connection(monkeypatch)
    evidence = {'auc': 0.55, 'explanation': {'method': 'shap'}}
    row = {'status': 'in_progress', 'task_type': 'interpret', 'claimed_by': 'interpret#1', 'evaluation': evidence}
    conn.fetchrow.return_value = row
    reply = json.loads(asyncio.run(bb.recover_interpretation(10, 'interpret#1')))
    assert reply['status'] == 'ready'
    updated = json.loads(conn.execute.call_args.args[-1])
    assert updated['auc'] == .55 and updated['explanation'] == evidence['explanation']
    assert updated['interpretation_recovery_count'] == 1
    conn.fetchrow.return_value = {**row, 'evaluation': updated}
    reply = json.loads(asyncio.run(bb.recover_interpretation(10, 'interpret#1')))
    assert not reply['ok'] and 'limit' in reply['reason']
    conn.fetchrow.return_value = {**row, 'claimed_by': 'interpret#2'}
    assert 'error' in json.loads(asyncio.run(bb.recover_interpretation(10, 'interpret#1')))


def test_returned_interpreter_retries_without_failing_or_replaying_ml(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: PLAN)
    monkeypatch.setattr(board, 'board_state', AsyncMock(return_value={'tasks':[
        {'task_id':10, 'status':'in_progress', 'task_type':'interpret', 'claimed_by':'interpret#1'},
        {'task_id':11, 'status':'in_progress', 'task_type':'interpret', 'claimed_by':'interpret#2'}]}))
    tool=AsyncMock(return_value={'ok':True,'status':'ready'})
    monkeypatch.setattr(board,'call_board_tool',tool)
    asyncio.run(board.settle_finished_workers(None,'run-a',{'interpret#1'}))
    tool.assert_awaited_once()
    assert tool.call_args.args[1] == 'recover_interpretation'
    assert tool.call_args.args[2]['task_id'] == 10


def test_completed_agent_interpretation_is_committed_without_another_model_call(monkeypatch):
    from memstara.pipeline.recovery import complete_interpretation
    text = '\n'.join(f'**{label}:** Evidence-based explanation with uncertainty and limitations.' for label in (
        'Assessment', 'Biological/clinical meaning', 'How the model uses the features',
        'Actionability and threshold', 'Limitations and next validation'))
    assert complete_interpretation(text)
    assert not complete_interpretation('Task completed successfully')
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: PLAN)
    monkeypatch.setattr(board,'_TRACE_DIR',None)
    monkeypatch.setattr(board,'board_state',AsyncMock(return_value={'tasks':[
        {'task_id':1,'task_type':'interpret','status':'in_progress','claimed_by':'interpret#1'}]}))
    tool=AsyncMock(return_value={'ok':True,'status':'done'})
    monkeypatch.setattr(board,'call_board_tool',tool)
    asyncio.run(board.settle_finished_workers(None,'run-a',{'interpret#1'},
                {'interpret#1':(text,{'status':'completed','run_id':'agent-run'})}))
    tool.assert_awaited_once()
    assert tool.call_args.args[1] == 'submit_result'
    assert tool.call_args.args[2] == {'task_id':1,'worker':'interpret#1','interpretation':text}


def test_ambiguous_or_failed_agent_output_is_not_saved_as_an_interpretation(monkeypatch):
    text=' '.join(label+': sufficient evidence text '*10 for label in (
        'Assessment','Biological/clinical meaning','How the model uses the features',
        'Actionability and threshold','Limitations and next validation'))
    monkeypatch.setattr('memstara.evaluation.active_plan',lambda:PLAN)
    monkeypatch.setattr(board,'board_state',AsyncMock(return_value={'tasks':[
        {'task_id':1,'task_type':'interpret','status':'in_progress','claimed_by':'interpret#1'}]}))
    tool=AsyncMock(return_value={'ok':True,'status':'ready'})
    monkeypatch.setattr(board,'call_board_tool',tool)
    asyncio.run(board.settle_finished_workers(None,'run-a',{'interpret#1'},
                {'interpret#1':(text,{'status':'failed'})}))
    assert tool.call_args.args[1] == 'recover_interpretation'
