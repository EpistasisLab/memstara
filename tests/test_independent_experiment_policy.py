"""No prior outcome channel for new experiments; old snapshots retain their meaning."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from memstara.pipeline import experiment_policy as policy, iteration_learning as learning
from memstara.pipeline.combination_questions import enabled as independent_questions
from memstara.pipeline.question_contract import make_contract
from memstara.pipeline.scientific_policy import check_primary_tools


def state():
    return {'mode': 'pipeline', 'dataset_sha256': 'input-hash', 'y_column': 'outcome',
            'hypothesis_policy': {'version': learning.VERSION, 'question_contract': 'fixed_target_v1'}}


@pytest.mark.parametrize('plan', [None, {'execution_order': 'all_pipelines_first'},
                                {'execution_order': 'pipeline_replicates_first'}])
def test_same_policy_for_single_and_combination_launches(plan):
    value = {**state(), 'combination_plan': plan}
    policy.freeze(value, SimpleNamespace())
    assert policy.enabled(value) and independent_questions(value)
    assert not learning.enabled(value)
    assert not value['hypothesis_policy']['prior_ml_feedback']
    with pytest.raises(ValueError, match='Prior replicate outcomes'):
        learning.read_feedback(value, 1)


@pytest.mark.parametrize('flag', ['continuous', 'no_curator'])
def test_conflicting_new_options_fail_before_agents(flag):
    with pytest.raises(ValueError):
        policy.freeze(state(), SimpleNamespace(**{flag: True}))


@pytest.mark.parametrize('resumed', [True, False])
def test_historical_feedback_policy_preserved_on_resume_and_retry(resumed):
    original = state()
    original['hypothesis_policy']['prior_ml_feedback'] = True
    before = copy.deepcopy(original)
    value = state()
    args = SimpleNamespace(retry_source_run='old', retry_experiment_policy=json.dumps(original))
    policy.freeze(value, args, previous=original if resumed else None)
    assert learning.enabled(value) and not policy.enabled(value)
    assert original == before and value['hypothesis_policy'] == original['hypothesis_policy']


def test_retry_cannot_silently_change_policy_or_inputs():
    with pytest.raises(ValueError, match='original experiment policy'):
        policy.freeze(state(), SimpleNamespace(retry_source_run='old'))
    original = {**state(), 'dataset_sha256': 'different'}
    with pytest.raises(ValueError, match='different inputs'):
        policy.freeze(state(), SimpleNamespace(retry_source_run='old',
                                               retry_experiment_policy=json.dumps(original)))


def test_independent_contract_rejects_lineage_and_feedback_tools():
    value = state()
    policy.freeze(value, SimpleNamespace())
    item = {'predictor_concepts': ['age'], 'source_ids': ['source'], 'okf_tags': ['cardiac'],
            'rationale': 'The supplied source describes the measured predictor.', 'parent_task_ids': [7]}
    with pytest.raises(ValueError, match='prior task outcomes'):
        make_contract(item, value)
    for stage in ['question0-1', 'hypothesis0']:
        with pytest.raises(ValueError, match='tool boundary'):
            check_primary_tools(stage, [{'tool_name': 'read_board'}])


def test_catalog_never_reads_historical_questions_or_scores(monkeypatch):
    from memstara import evaluation
    from memstara.mcp_servers import blackboard
    value = state()
    policy.freeze(value, SimpleNamespace())
    monkeypatch.setattr(evaluation, 'active_plan', lambda: value)
    def forbidden(*args, **kwargs):
        raise AssertionError('No historical rows may reach primary generation')
    monkeypatch.setattr(blackboard.asyncpg, 'connect', forbidden)
    result = json.loads(asyncio.run(blackboard.read_question_catalog()))
    assert result['questions'] == [] and result['duplicate_scope'] == 'current_replicate'
