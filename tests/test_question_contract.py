"""The Q315 mismatch must fail before work is created, without a model or patient data."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from memstara.pipeline import question_contract as qc
from memstara.pipeline import board
from memstara.mcp_servers import blackboard as bb

PLAN = {'run_tag': 'new-run', 'y_column': 'FIXED_TARGET', 'evaluation': {},
        'config_hash': 'hash', 'hypothesis_policy': {'version': 'knowledge_only_v1',
                                                  'question_contract': qc.VERSION}}
ITEM = {'target': 'FIXED_TARGET', 'predictor_concepts': ['lactate', 'neuropathy'],
        'rationale': 'A documented knowledge path connects metabolic burden and disease severity.',
        'okf_tags': ['shared-pharmacology']}


def conn_fixture(monkeypatch):
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: PLAN)
    monkeypatch.setattr(bb, '_pipeline_run', lambda: PLAN['run_tag'])
    return conn


def test_canonical_question_and_hypothesis_share_target():
    contract = qc.make_contract(ITEM, PLAN)
    assert qc.question_text(contract) == 'Do lactate; neuropathy predict FIXED_TARGET?'
    assert qc.hypothesis_text(contract).endswith('predict FIXED_TARGET.')
    assert qc.validate_saved(contract, qc.question_text(contract), PLAN) == contract


@pytest.mark.parametrize('patch', [
    {'target': 'psychiatric condition'},
    {'text': 'Which markers predict a psychiatric condition?'},
    {'predictor_concepts': ['markers that predict psychiatric conditions']},
    {'predictor_concepts': ['FIXED_TARGET']},
    {'rationale': 'Prior trials had AUC 0.75 so reuse those features.'},
    {'predictor_concepts': ['negative importance columns']},
    {'predictor_concepts': []},
])
def test_mismatch_and_feedback_are_rejected(patch):
    with pytest.raises(ValueError):
        qc.make_contract({**ITEM, **patch}, PLAN)


def test_generator_receives_target_even_when_research_question_is_empty(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {**PLAN, 'question': ''})
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': []}))
    call = AsyncMock()
    monkeypatch.setattr(board, 'call_agent', call)
    asyncio.run(board.questions_for_wave(None, {'hypothesis': 'agent'}, {'question': []},
                                        run_tag='new-run', wave=14, want=1))
    prompt = call.call_args.args[1]
    assert "ONLY prediction target is 'FIXED_TARGET'" in prompt
    assert 'Do not use previous AUC' in prompt
    assert 'predictor_concepts' in prompt


def test_proposal_rejects_bad_target_without_inserting(monkeypatch):
    conn = conn_fixture(monkeypatch)
    conn.fetch.return_value = []
    reply = json.loads(asyncio.run(bb.propose_questions(json.dumps([{**ITEM, 'target': 'psychiatric'}]))))
    assert reply['rejected'] and not reply['added']
    conn.fetchval.assert_not_called()


def test_proposal_persists_server_generated_contract(monkeypatch):
    conn = conn_fixture(monkeypatch)
    conn.fetch.return_value = []
    conn.fetchval.return_value = 10
    reply = json.loads(asyncio.run(bb.propose_questions(json.dumps([ITEM]))))
    assert reply['added'][0]['text'] == qc.question_text(qc.make_contract(ITEM, PLAN))
    args = conn.fetchval.call_args.args
    assert json.loads(args[-1])['target'] == 'FIXED_TARGET'
    assert 'question_contract' in args[0]


@pytest.mark.parametrize('change', ['hypothesis', 'perspective', 'origin_run', 'claimed_run', 'contract'])
def test_task_rejects_inconsistent_or_foreign_question(monkeypatch, change):
    conn = conn_fixture(monkeypatch)
    contract = qc.make_contract(ITEM, PLAN)
    question = {'text': qc.question_text(contract), 'question_contract': contract,
                'origin_run': 'new-run', 'claimed_run': 'new-run'}
    hypothesis = qc.hypothesis_text(contract)
    perspective = question['text']
    if change == 'hypothesis': hypothesis = 'Predict psychiatric outcome instead.'
    elif change == 'perspective': perspective = 'A different question'
    elif change == 'contract': question['question_contract'] = {}
    else: question[change] = 'other-run'
    conn.fetchrow.return_value = question
    reply = json.loads(asyncio.run(bb.create_task('new-run', 0, perspective, hypothesis,
                     ['FEATURE_A'], 'FIXED_TARGET', ['path1'], 10)))
    assert 'error' in reply
    conn.fetchval.assert_not_called()


def test_task_carries_contract_into_evaluation(monkeypatch):
    conn = conn_fixture(monkeypatch)
    contract = qc.make_contract(ITEM, PLAN)
    conn.fetchrow.return_value = {'text': qc.question_text(contract), 'question_contract': contract,
                                  'origin_run': 'new-run', 'claimed_run': 'new-run'}
    conn.fetchval.return_value = 20
    reply = json.loads(asyncio.run(bb.create_task('new-run', 0, qc.question_text(contract),
                     qc.hypothesis_text(contract), ['FEATURE_A'], 'FIXED_TARGET', ['path1'], 10)))
    assert reply.get('task_id') == 20
    assert json.loads(conn.fetchval.call_args.args[-1])['question_contract'] == contract


def test_tampered_task_cannot_advance_to_next_stage(monkeypatch):
    conn = conn_fixture(monkeypatch)
    conn.fetchval.side_effect = ['new-run', {}]
    contract = qc.make_contract(ITEM, PLAN)
    conn.fetchrow.return_value = {'task_type':'data', 'status':'in_progress', 'claimed_by':'data',
        'subset_path':'', 'evaluation':{'question_contract':contract}, 'y_column':'WRONG_TARGET',
        'perspective':qc.question_text(contract), 'hypothesis':qc.hypothesis_text(contract)}
    reply = json.loads(asyncio.run(bb.submit_result(20, worker='data')))
    assert 'contract rejected' in reply['error']
    conn.execute.assert_not_called()


def test_extraction_rejects_other_target_before_reading_dataset(monkeypatch):
    from memstara.mcp_servers import data
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: PLAN)
    read = MagicMock()
    monkeypatch.setattr(data.pd, 'read_csv', read)
    result = json.loads(data.slice_columns(['FEATURE_A'], 'psychiatric', 'wrong'))
    assert 'fixed target' in result['error']
    read.assert_not_called()
