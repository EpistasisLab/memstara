"""Availability precedes generation without exposing labels, values or ML feedback."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline.feature_context import freeze_feature_context, instructions


def test_header_only_context_preserves_exact_names_and_matcher_meanings(tmp_path):
    dataset = tmp_path / 'cohort.csv'
    dataset.write_text('DX__I10__Essential hypertension,"LAB__HDL CHOLESTEROL, DIRECT",Y\nPRIVATE_PATIENT_VALUE,99,1\n')
    context = freeze_feature_context(dataset, 'Y')
    assert context['features'] == [
        {'column': 'DX__I10__Essential hypertension', 'meaning': 'Essential hypertension (I10)', 'kind': 'diagnosis'},
        {'column': 'LAB__HDL CHOLESTEROL, DIRECT', 'meaning': 'HDL CHOLESTEROL, DIRECT lab test', 'kind': 'lab'},
    ]
    assert 'PRIVATE_PATIENT_VALUE' not in json.dumps(context)
    prompt = instructions({'feature_context': context, 'y_column': 'Y', 'auc': .99})
    assert '0.99' not in prompt
    assert 'not a validated clinical data dictionary' in prompt


def test_missing_target_and_empty_predictors_fail_closed(tmp_path):
    dataset = tmp_path / 'cohort.csv'
    dataset.write_text('Y\n1\n')
    with pytest.raises(ValueError, match='No predictors'):
        freeze_feature_context(dataset, 'Y')
    with pytest.raises(ValueError, match='configured target'):
        freeze_feature_context(dataset, 'absent')
    with pytest.raises(ValueError, match='Outcome leaked'):
        instructions({'y_column': 'Y', 'feature_context': {'features': [{'column': 'Y'}]}})


def test_each_question_writer_receives_frozen_context_before_call(monkeypatch, tmp_path):
    from memstara import evaluation
    from memstara.pipeline import board
    dataset = tmp_path / 'cohort.csv'
    dataset.write_text('BMI,Y\n23,0\n')
    context = freeze_feature_context(dataset, 'Y')
    monkeypatch.setattr(evaluation, 'active_plan', lambda: {'feature_context': context, 'y_column': 'Y'})
    agent = AsyncMock()
    monkeypatch.setattr(board, 'call_agent', agent)
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': []}))
    asyncio.run(board.questions_for_wave(None, {'hypothesis': 'a', 'hypothesis2': 'b'},
                                        {'question': []}, run_tag='new', wave=0, want=2))
    assert {call.args[0] for call in agent.call_args_list} == {'a', 'b'}
    for call in agent.call_args_list:
        assert 'AVAILABLE PREDICTORS' in call.args[1]
        assert 'body mass index (BMI)' in call.args[1]
        assert 'do not invent a column' in call.args[1]
