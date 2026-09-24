"""Regression cases for unmappable questions and invalid follow-up lineage."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from memstara.pipeline import question_repair as repair, question_contract as qc
from memstara.pipeline import iteration_learning as learning
from memstara.mcp_servers import blackboard as bb


@pytest.fixture
def plan(tmp_path, monkeypatch):
    p = {'run_tag': 'r', 'config_hash': 'h', 'trials': 1, 'y_column': 'Y',
         'hypothesis_policy': {'version': learning.VERSION, 'question_contract': qc.VERSION},
         'feature_context': {'features': [{'column': 'F'}]}}
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(p))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(config))
    learning.save_feedback({'run_tag': 'r', 'config_hash': 'h', 'wave': 4,
                           'evidence': [{'task_id': x} for x in [805, 806, 807]]})
    return p


def proposal(**kw):
    return {'predictor_concepts': ['HIV Protease Inhibitors'], 'okf_tags': ['path'],
            'rationale': 'Grounded in a source and earlier observation.',
            'parent_task_ids': [805], 'learning_goal': 'Investigate another mechanism.',
            'origin_wave': 4, **kw}


def matcher(monkeypatch, candidates):
    result = SimpleNamespace(to_dict=lambda: {'concept': 'HIV Protease Inhibitors',
                             'candidates': candidates, 'note': 'Verified class mapping required'})
    monkeypatch.setattr('memstara.matcher.service.get_matcher',
                        lambda: SimpleNamespace(match_many=lambda concepts: [result]))


def test_invalid_question_id_and_omitted_lineage_return_actual_task_ids(plan):
    for parents in ([477], [], [805, 805]):
        with pytest.raises(ValueError) as exc:
            qc.make_contract(proposal(parent_task_ids=parents), plan)
        assert '[805, 806, 807]' in str(exc.value)
    assert qc.make_contract(proposal(parent_task_ids=[806]), plan)['parent_task_ids'] == [806]


@pytest.mark.parametrize('candidates', [[], [{'feature_name': 'Y'}], [{'feature_name': 'other-dataset'}]])
def test_no_candidates_or_outcome_cannot_pass_preflight(plan, monkeypatch, candidates):
    matcher(monkeypatch, candidates)
    result = asyncio.run(repair.preflight_mapping(qc.make_contract(proposal(), plan), plan))
    assert result['code'] == 'unmapped_predictor_concepts'
    assert result['unmapped'][0]['concept'] == 'HIV Protease Inhibitors'


def test_candidate_exists_does_not_rewrite_question(plan, monkeypatch):
    matcher(monkeypatch, [{'feature_name': 'F'}])
    contract = qc.make_contract(proposal(), plan)
    before = json.dumps(contract)
    assert asyncio.run(repair.preflight_mapping(contract, plan)) is None
    assert json.dumps(contract) == before


def test_retry_feedback_is_scoped_and_preserves_rejection(plan):
    repair.save_feedback(plan, 4, 'hypothesis', {'rejected': [{'why': 'Allowed IDs: 805, 806, 807'}]})
    assert '805, 806, 807' in repair.retry_instructions(plan, 4, 'hypothesis')
    assert repair.retry_instructions(plan, 5, 'hypothesis') == ''
    assert repair.retry_instructions(plan, 4, 'hypothesis#2') == ''
    with pytest.raises(ValueError):
        repair.retry_instructions({**plan, 'run_tag': 'other'}, 4, 'hypothesis')


def test_tool_rejects_before_insert_then_accepts_corrected_mapping(plan, monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: plan)
    monkeypatch.setattr(bb, '_pipeline_run', lambda: 'r')
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    conn.fetch.return_value = []
    conn.fetchval.return_value = 100
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    matcher(monkeypatch, [])
    first = json.loads(asyncio.run(bb.propose_questions([proposal()], origin_wave=4, writer='hypothesis')))
    assert not first['added'] and first['rejected'][0]['code'] == 'unmapped_predictor_concepts'
    conn.fetchval.assert_not_called()
    assert 'Verified class mapping required' in repair.retry_instructions(plan, 4, 'hypothesis')
    matcher(monkeypatch, [{'feature_name': 'F'}])
    second = json.loads(asyncio.run(bb.propose_questions([proposal()], origin_wave=4, writer='hypothesis')))
    assert second['added'][0]['question_id'] == 100
    conn.fetchval.assert_awaited_once()


def test_failed_proposal_without_task_is_available_in_next_loop(plan):
    repair.save_feedback(plan, 4, 'hypothesis', {'rejected': [{'why': 'Unmapped drug class'}]})
    assert 'Unmapped drug class' in repair.prior_failure_instructions(plan, 5, 'hypothesis')
    assert repair.prior_failure_instructions(plan, 4, 'hypothesis') == ''
    assert repair.prior_failure_instructions({**plan, 'run_tag': 'other'}, 5, 'hypothesis') == ''


def test_question_writer_retry_receives_exact_tool_failure(plan, monkeypatch):
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.pipeline import board
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: plan)
    prompts = []
    fresh = []
    async def tool(registry, name, args):
        if name == 'read_board':
            return {'tasks': []}
        return {'questions': list(fresh)}
    async def agent(agent_id, prompt, **kw):
        prompts.append(prompt)
        if len(prompts) == 1:
            repair.save_feedback(plan, 4, 'hypothesis',
                                 {'rejected': [{'why': 'Specific missing medication class mapping'}]})
        else:
            fresh.append({'question_id': 100, 'origin_run': 'r', 'origin_wave': 4})
    monkeypatch.setattr(board, 'call_board_tool', tool)
    monkeypatch.setattr(board, 'call_agent', agent)
    rows, blocked = asyncio.run(board.questions_for_wave(None, {'hypothesis': 'agent'},
                           {'question': []}, run_tag='r', wave=4, want=1))
    assert rows[0]['question_id'] == 100 and not blocked
    assert 'Specific missing medication class mapping' not in prompts[0]
    assert 'Specific missing medication class mapping' in prompts[1]


@pytest.mark.parametrize("error", [RuntimeError("unavailable"), ValueError("stale cache")])
def test_mapping_service_failure_is_not_reported_as_absent_concept(plan, monkeypatch, error):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: plan)
    monkeypatch.setattr(bb, '_pipeline_run', lambda: 'r')
    monkeypatch.setattr('memstara.matcher.service.get_matcher', MagicMock(side_effect=error))
    result = json.loads(asyncio.run(bb.propose_questions([proposal()], origin_wave=4)))
    assert result['rejected'][0]['code'] == 'mapping_preflight_unavailable'
    assert not result['added']


def test_invented_column_label_is_rejected_before_task_or_database(plan, monkeypatch):
    plan['feature_context']['features'] = [{'column': 'DX__B20__Human immunodeficiency virus disease'}]
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: plan)
    monkeypatch.setattr(bb, '_pipeline_run', lambda: 'r')
    connect = AsyncMock()
    monkeypatch.setattr(bb.asyncpg, 'connect', connect)
    result = json.loads(asyncio.run(bb.create_task('r', 1, 'question', 'hypothesis',
               ['DX__B20__Acquired immunodeficiency syndrome'], 'Y')))
    assert result['code'] == 'unknown_predictor_columns'
    assert result['same_code_columns']['DX__B20__Acquired immunodeficiency syndrome'] == [
        'DX__B20__Human immunodeficiency virus disease']
    connect.assert_not_awaited()
    assert qc.predictor_column_error(['DX__B20__Human immunodeficiency virus disease'], plan) is None
    assert qc.predictor_column_error(['Y'], plan)['code'] == 'unknown_predictor_columns'


def test_explicit_absent_icd_code_cannot_pass_via_semantic_neighbor(plan, monkeypatch):
    plan['feature_context']['features'] = [{'column': 'DX__F90.9__ADHD'}]
    matcher(monkeypatch, [{'feature_name': 'DX__F90.9__ADHD'}])
    failure = asyncio.run(repair.preflight_mapping({'predictor_concepts': [
        'Acquired immunodeficiency syndrome (ICD-10 B20)']}, plan))
    assert failure['code'] == 'unmapped_predictor_concepts'
    assert 'B20' in failure['unmapped'][0]['reason']


@pytest.mark.parametrize('code,child', [('F90','F90.9'), ('F43.2','F43.21')])
def test_explicit_icd_category_allows_actual_child_code(plan, monkeypatch, code, child):
    concept = f'Clinical concept (ICD-10 {code})'
    plan['feature_context']['features'] = [{'column': f'DX__{child}__condition'}]
    row = SimpleNamespace(to_dict=lambda: {'concept': concept, 'candidates': [{'feature_name': f'DX__{child}__condition'}]})
    monkeypatch.setattr('memstara.matcher.service.get_matcher', lambda: SimpleNamespace(match_many=lambda concepts: [row]))
    assert asyncio.run(repair.preflight_mapping({'predictor_concepts': [concept]}, plan)) is None
