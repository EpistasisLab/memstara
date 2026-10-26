"""Actual row membership, fitted classifiers and replay for the MVP two-way contract."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from memstara import data_allocation as allocation, evaluation
from memstara.comparisons import write_context
from memstara.reproducibility import replay


@pytest.mark.parametrize('skill,fraction', [('data_training_heavy', .3), ('data_balanced_stratified', .5)])
@pytest.mark.parametrize('engine', ['logistic_regression', 'xgboost'])
def test_two_way_handoff_fit_and_replay(tmp_path, monkeypatch, skill, fraction, engine):
    rng = np.random.default_rng(18)
    source = tmp_path / 'source.csv'
    pd.DataFrame({'x': rng.normal(size=100), 'z': rng.normal(size=100),
                  'target': [0, 1] * 50}).to_csv(source, index=False)
    plan = {'run_tag': 'two-way', 'config_hash': 'fixture', 'y_column': 'target',
            'partition_policy': allocation.TWO_WAY_VERSION, 'validation_partition': None,
            'data_allocation_policy': {'version': allocation.TWO_WAY_VERSION},
            'classifier_seed_policy': 'split_seed_v1', 'preprocessing_policy': 'analysis_ready_v1',
            'hypothesis_policy': {'version': 'iterative_discovery_v1'},
            'evaluation': evaluation.validate({'engine': engine, 'replicates': 3}),
            'comparison_policy': {'baseline_columns': []},
            'books': {'data': [skill]}, 'prompts': {f'board/data:{skill}': {'system_prompt': skill}},
            'dataset_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(source))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    monkeypatch.setattr(evaluation, 'active_plan', lambda: plan)
    task = {'task_id': 1, 'trial': 0, 'y_column': 'target', 'columns': ['x', 'z']}
    proposal = {'test_size': fraction, 'seed': 190347, 'stratify': True}
    spec = allocation.request(plan, 0)
    assert set(spec['schema']) == {'test_size', 'seed', 'stratify'}
    record = allocation.prepare(proposal, task, plan, source)
    write_context(source, task, plan, data_allocation=record)
    effective, restored = allocation.load_effective(source, plan, plan['evaluation'])
    assert restored == record and effective['replicates'] == 1
    split = record['replicates'][0]
    assert record['reserved_count'] == 0 and record['validation_partition'] is None
    assert len(split['test_rows']) == int(100 * fraction)
    assert set(split['train_rows']).isdisjoint(split['test_rows'])
    assert sorted(split['train_rows'] + split['test_rows']) == list(range(100))
    result = evaluation.score(source, 'target', effective, explain=False,
                              configuration={'parameters': {}, 'scale_numeric': False, 'threshold': .5})
    actual = result['evaluation']['replicates'][0]
    assert result['evaluation']['score_scope'] == 'two_way_test'
    assert actual['seed'] == actual['parameters']['random_state'] == proposal['seed']
    assert actual['split_id'] == split['split_id']
    assert result['n_test'] == len(split['test_rows'])
    assert replay(Path(result['evaluation']['reproducibility']['bundle_path']))['status'] == 'verified'
    with pytest.raises(ValueError, match='bounds'):
        allocation.validate({**proposal, 'test_size': .2}, spec, plan['evaluation'])
    with pytest.raises(ValueError, match='complete schema'):
        allocation.validate({**proposal, 'validation_seed': 42}, spec, plan['evaluation'])
    sidecar = source.with_suffix('.comparison.json')
    tampered = json.loads(sidecar.read_text())
    tampered['data_allocation']['replicates'][0]['test_rows'][0] = -1
    sidecar.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match='does not reproduce'):
        allocation.load_effective(source, plan, effective)


def test_two_way_never_starts_final_reserve_refit(tmp_path, monkeypatch):
    from memstara import final_validation
    def unexpected(*args, **kwargs):
        pytest.fail('Two-way execution tried to select/refit a reserve candidate')
    monkeypatch.setattr(final_validation, 'eligible_tasks', unexpected)
    result = final_validation.run(tmp_path, {'partition_policy': allocation.TWO_WAY_VERSION}, [])
    assert result['status'] == 'not_applicable'
    assert not (tmp_path / 'final_validation.json').exists()


def test_recorded_seed_cannot_be_replaced_by_agent_or_retry():
    from memstara.seed_schedule import create, seed_for
    schedule = create(1, 3, 'independent_pipelines')
    snapshot = {'data_allocation_policy': {'version': allocation.TWO_WAY_VERSION},
                'books': {}, 'prompts': {}, 'seed_schedule': schedule}
    spec = allocation.request(snapshot, 1)
    proposal = spec['required_data_plan']
    assert proposal == {'test_size': .3, 'stratify': True, 'seed': seed_for(schedule, 1, 2)}
    assert allocation.validate(proposal, spec, evaluation.DEFAULTS)['seed'] == proposal['seed']
    with pytest.raises(ValueError, match='frozen'):
        allocation.validate({**proposal, 'seed': (proposal['seed'] + 1) % 2147483648},
                            spec, evaluation.DEFAULTS)
    assert allocation.request(json.loads(json.dumps(snapshot)), 1)['required_data_plan'] == proposal

