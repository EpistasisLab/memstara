"""Offline checks for adaptive lineage, information scope and untouched validation rows."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from memstara import evaluation
from memstara.pipeline import iteration_learning as learning, question_contract as qc, board
from memstara.mcp_servers import blackboard as bb


@pytest.fixture
def plan(tmp_path, monkeypatch):
    plan = {'run_tag': 'this-run', 'config_hash': 'frozen', 'trials': 1, 'y_column': 'TARGET',
            'evaluation': evaluation.validate({}), 'hypothesis_policy': {
                'version': learning.VERSION, 'question_contract': qc.VERSION}}
    path = tmp_path / 'run_config.json'
    path.write_text(json.dumps(plan))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(path))
    return plan


def task(**extra):
    return {'task_id': 7, 'run_tag': 'this-run', 'trial': 0, 'status': 'done',
            'perspective': 'Do baseline markers predict TARGET?', 'hypothesis': 'A predicts TARGET.',
            'auc': .54, 'interpretation': 'Weak predictive evidence; test an alternative mechanism.', **extra}


def item(**extra):
    return {'target': 'TARGET', 'predictor_concepts': ['alternate mechanism'],
            'rationale': 'Knowledge suggests an alternative to weak prior AUC.', 'origin_wave': 1,
            'parent_task_ids': [7], 'learning_goal': 'Test whether the alternative mechanism explains the observation.',
            'okf_tags': ['mechanisms'], **extra}


def test_feedback_excludes_foreign_future_and_unfinished_tasks(plan):
    rows = [task(), task(task_id=8, run_tag='other'), task(task_id=9, trial=1),
            task(task_id=10, status='in_progress'), task(task_id=11, status='failed', error='Fit failed')]
    context = learning.summarize(rows, plan, 1)
    assert [t['task_id'] for t in context['evidence']] == [7, 11]
    assert context['evidence'][1]['auc'] is None
    assert 'technical failure' in learning.instructions(context)


def test_followup_contract_carries_target_and_lineage(plan):
    learning.save_feedback(learning.summarize([task()], plan, 1))
    contract = qc.make_contract(item(), plan)
    assert contract['kind'] == 'evidence_informed_refinement'
    assert contract['parent_task_ids'] == [7]
    assert qc.validate_saved(contract, qc.question_text(contract), plan) == contract
    assert qc.hypothesis_text(contract).endswith('predict TARGET.')


@pytest.mark.parametrize('patch', [
    {'parent_task_ids': []}, {'parent_task_ids': [8]}, {'parent_task_ids': [7, 7]},
    {'parent_task_ids': ['7']}, {'learning_goal': ''}, {'target': 'OTHER'}, {'origin_wave': -1},
])
def test_invalid_lineage_or_target_is_rejected(plan, patch):
    learning.save_feedback(learning.summarize([task()], plan, 1))
    with pytest.raises(ValueError):
        qc.make_contract(item(**patch), plan)


def test_first_iteration_remains_knowledge_driven(plan):
    learning.save_feedback(learning.summarize([], plan, 0))
    clean = item(origin_wave=0, parent_task_ids=[], rationale='A knowledge path links these mechanisms.')
    assert qc.make_contract(clean, plan)['kind'] == 'primary_knowledge_driven'
    with pytest.raises(ValueError, match='knowledge-only'):
        qc.make_contract({**clean, 'rationale': 'Previous trials had high AUC.'}, plan)


def test_feedback_file_cannot_be_reused_by_another_run(plan):
    learning.save_feedback(learning.summarize([task()], plan, 1))
    with pytest.raises(ValueError, match='different run'):
        learning.read_feedback({**plan, 'run_tag': 'other'}, 1)


def test_next_question_turn_receives_observed_results(plan, monkeypatch):
    async def tool(registry, name, args):
        if name == 'read_board':
            assert args == {'run_tag': 'this-run'}
            return {'tasks': [task()]}
        return {'questions': []}
    monkeypatch.setattr(board, 'call_board_tool', tool)
    call = AsyncMock()
    monkeypatch.setattr(board, 'call_agent', call)
    asyncio.run(board.questions_for_wave(None, {'hypothesis': 'agent'}, {'question': []},
                                        run_tag='this-run', wave=1, want=1))
    prompt = call.call_args.args[1]
    assert '0.54' in prompt and 'Weak predictive evidence' in prompt
    assert 'parent_task_ids' in prompt and 'learning_goal' in prompt
    assert 'Do not use previous AUC' not in prompt


def test_propose_persists_followup_and_allows_changed_nearby_question(plan, monkeypatch):
    learning.save_feedback(learning.summarize([task()], plan, 1))
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    conn.fetch.return_value = []
    conn.fetchval.return_value = 99
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    monkeypatch.setattr(bb, '_near_duplicate', lambda *args: (10, .95))
    response = json.loads(asyncio.run(bb.propose_questions(json.dumps([item()]), origin_run='this-run', origin_wave=1)))
    assert response['added'][0]['question_id'] == 99
    saved = json.loads(conn.fetchval.call_args.args[-1])
    assert saved['parent_task_ids'] == [7]
    assert saved['kind'] == 'evidence_informed_refinement'


def test_reserved_rows_never_enter_train_or_exploratory_test(plan, monkeypatch):
    y = pd.Series(np.arange(200) % 2)
    partition = evaluation.discovery_partition(y, 42)
    assert partition == evaluation.discovery_partition(y, 42)
    plan['validation_partition'] = partition
    monkeypatch.setattr(evaluation, 'active_plan', lambda: plan)
    for _, train, test in evaluation.evaluation_splits(y, evaluation.validate({'replicates': 3})):
        assert set(train).isdisjoint(test)
        assert set(train) | set(test) == set(partition['exploration_rows'])
        assert len(train) + len(test) == 160
    with pytest.raises(evaluation.DataQualityError, match='rows'):
        evaluation.evaluation_splits(y[:-1], evaluation.validate({}))


def test_iterative_scoring_preserves_reserve_and_provenance(plan, tmp_path, monkeypatch):
    rng = np.random.default_rng(9)
    frame = pd.DataFrame({'x': rng.normal(size=200), 'TARGET': np.arange(200) % 2})
    path = tmp_path / 'synthetic.csv'
    frame.to_csv(path, index=False)
    plan['validation_partition'] = evaluation.discovery_partition(frame.TARGET, 42)
    monkeypatch.setattr(evaluation, 'active_plan', lambda: plan)
    result = evaluation.score(path, 'TARGET', evaluation.validate({}))
    assert result['n_train'] + result['n_test'] == 160
    assert result['evaluation']['score_scope'] == 'adaptive_exploration'
    assert result['evaluation']['validation_reserve']['reserved_count'] == 40
    assert result['evaluation']['validation_reserve']['status'] == 'reserved_not_evaluated'
    assert 'exploration_rows' not in result['evaluation']['validation_reserve']
    json.dumps(result, allow_nan=False)


def test_missing_feedback_never_silently_becomes_an_independent_question(plan, monkeypatch):
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(side_effect=[{'questions': []}, {'error': 'DB unavailable'}]))
    call = AsyncMock()
    monkeypatch.setattr(board, 'call_agent', call)
    with pytest.raises(RuntimeError, match='prior iteration'):
        asyncio.run(board.questions_for_wave(None, {'hypothesis': 'agent'}, {'question': []},
                                            run_tag='this-run', wave=1, want=1))
    call.assert_not_called()


def test_create_task_persists_lineage_and_rejects_wrong_iteration(plan, monkeypatch):
    learning.save_feedback(learning.summarize([task()], plan, 1))
    contract = qc.make_contract(item(), plan)
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    conn.fetchrow.return_value = {'text': qc.question_text(contract), 'question_contract': contract,
                                 'origin_run': 'this-run', 'claimed_run': 'this-run'}
    conn.fetchval.return_value = 101
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    args = dict(run_tag='this-run', trial=1, perspective=qc.question_text(contract),
                hypothesis=qc.hypothesis_text(contract), columns=['FEATURE'], y_column='TARGET',
                okf_concept_ids=['knowledge-1'], question_id=99)
    result = json.loads(asyncio.run(bb.create_task(**args)))
    assert 'error' not in result
    stored = json.loads(conn.fetchval.call_args.args[-1])
    assert stored['question_contract']['parent_task_ids'] == [7]
    assert stored['hypothesis_policy']['kind'] == 'evidence_informed_refinement'
    conn.fetchval.reset_mock()
    wrong = json.loads(asyncio.run(bb.create_task(**{**args, 'trial': 0})))
    assert 'iteration' in wrong['error']
    conn.fetchval.assert_not_called()


def test_missing_iteration_context_is_a_clear_contract_error(plan):
    with pytest.raises(ValueError, match='Frozen feedback is unavailable'):
        qc.make_contract(item(), plan)
