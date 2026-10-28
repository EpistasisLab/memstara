"""Matched experiment constraints cannot drift between guided and random routes."""
import copy
import json

import pytest

from memstara import controlled_comparison as control, ml_configuration as ml, evaluation
from memstara.pipeline import feature_selection as fs
from test_feature_selection import plan


def configured(mode='guided'):
    snapshot = plan(mode)
    snapshot['_selected_ml_primary'] = 'xgboost'
    snapshot['evaluation'] = evaluation.validate({'seed': 42, 'test_size': .25})
    snapshot['ml_configuration_policy'] = ml.policy()
    proposal = ml.context(snapshot, snapshot['evaluation'])['proposal_template']
    proposal['rationale'] = 'Same precommitted settings in both conditions'
    snapshot['controlled_comparison'] = control.freeze({'feature_count': 8, 'ml_plan': proposal}, snapshot)
    return snapshot


@pytest.mark.parametrize('mode', ['guided', 'random'])
def test_exact_count_and_deterministic_random_replay(mode):
    snapshot = configured(mode)
    selected = fs.context(snapshot, 0)
    columns = selected['required_features'] or [f'x{i}' for i in range(8)]
    assert len(columns) == 8
    assert fs.validate(columns, snapshot, 0)['actual_count'] == 8
    with pytest.raises(ValueError):
        fs.validate(columns[:-1], snapshot, 0)
    assert fs.context(json.loads(json.dumps(snapshot)), 0) == selected


def test_ml_settings_cannot_be_tuned():
    snapshot = configured()
    proposal = snapshot['controlled_comparison']['ml_plan']
    assert ml.context(snapshot, snapshot['evaluation'])['proposal_template'] == proposal
    assert ml.validate(proposal, snapshot, snapshot['evaluation']) == proposal
    changed = copy.deepcopy(proposal)
    changed['models']['xgboost']['parameters']['max_depth'] = 3
    with pytest.raises(ValueError, match='frozen controlled-comparison'):
        ml.validate(changed, snapshot, snapshot['evaluation'])


def test_data_split_cannot_drift():
    from memstara import data_allocation as data
    snapshot = configured()
    snapshot['data_allocation_policy'] = {'version': data.VERSION}
    snapshot['combination_plan']['skills']['data'] = [{'id': 'data_training_heavy'}]
    snapshot['prompts'] = {'board/data:data_training_heavy': {'system_prompt': 'fixture'}}
    spec = data.request(snapshot, 0)
    fixed = spec['required_data_plan']
    partition = snapshot.get('validation_partition') or {}
    assert fixed == {'test_size': .25, 'seed': 42, 'stratify': True,
                     'replicates': snapshot['evaluation']['replicates'],
                     'validation_seed': partition.get('seed', snapshot['evaluation']['seed']),
                     'validation_size': partition.get('fraction', .2)}
    assert data.validate(fixed, spec, snapshot['evaluation'])['seed'] == 42
    with pytest.raises(ValueError, match='frozen split'):
        data.validate({**fixed, 'seed': 7}, spec, snapshot['evaluation'])


@pytest.mark.parametrize('submission', ['omitted', 'missing_rationale', 'modified_settings'])
def test_frozen_execution_does_not_depend_on_llm_copy(submission):
    snapshot = configured()
    frozen = copy.deepcopy(snapshot['controlled_comparison']['ml_plan'])
    proposal = copy.deepcopy(frozen)
    if submission == 'omitted':
        proposal = None
    elif submission == 'missing_rationale':
        proposal.pop('rationale')
    else:
        proposal['models']['xgboost']['parameters']['max_depth'] = 7
    effective, receipt = ml.resolve(proposal, snapshot, snapshot['evaluation'])
    assert effective == frozen
    assert receipt['source'] == 'server_frozen'
    assert receipt['agent_proposal'] == proposal
    effective['models']['xgboost']['parameters']['max_depth'] = 8
    assert snapshot['controlled_comparison']['ml_plan'] == frozen


def test_free_configuration_still_requires_agent_rationale():
    snapshot = configured()
    proposal = snapshot.pop('controlled_comparison')['ml_plan']
    proposal.pop('rationale')
    with pytest.raises(ValueError, match='rationale'):
        ml.resolve(proposal, snapshot, snapshot['evaluation'])


@pytest.mark.parametrize('value', [[], False, {'feature_count': 3, 'ml_plan': {}},
                                   {'feature_count': True, 'ml_plan': {}}, {'feature_count': 8}])
def test_invalid_controls_rejected(value):
    with pytest.raises(ValueError):
        control.validate(value)
