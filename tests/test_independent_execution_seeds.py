"""Data settings seed modes, recorded replay and end-to-end split/model identity.

These checks use synthetic data and real local estimators, never paid providers.
"""
import json
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest

from memstara import data_allocation, evaluation, seed_schedule
from memstara.combinations import build_plan, loop_flavors, task_books
from memstara.comparisons import write_context
from memstara.pipeline.snapshot import freeze as freeze_snapshot


def state(skill='data_manual_split'):
    return {'partition_policy': 'two_way_stratified_v1', 'mode': 'pipeline',
            'dataset_sha256': 'input', 'y_column': 'outcome',
            'evaluation': {'seed': 708, 'test_size': .4},
            'combination_plan': {'combinations': 2, 'repetitions': 3, 'total_loops': 6,
                'skills': {stage: [{'id': skill}] if stage == 'data' else
                          [{'id': 'a'}, {'id': 'b'}] if stage == 'ml' else [{'id': stage}]
                          for stage in ('hypothesis', 'data', 'ml', 'interpreter', 'report')}}}


@pytest.mark.parametrize('skill', ['data_manual_split', 'data_training_heavy', 'data_balanced_stratified'])
def test_new_experiments_follow_data_settings_seed_mode(skill):
    first = state(skill)
    seed_schedule.freeze(first, SimpleNamespace())
    expected = [708] * 6 if skill == 'data_manual_split' else list(range(708, 714))
    assert [seed_schedule.task_seed(first, n) for n in range(6)] == expected
    assert first['seed_schedule']['policy'] == (seed_schedule.FIXED if skill == 'data_manual_split' else seed_schedule.INCREMENTING)


@pytest.mark.parametrize('recovery', ['resume', 'retry'])
def test_duplicate_execution_seed_in_record_blocks_recovery(recovery):
    original = state()
    original['seed_schedule'] = seed_schedule.create(2, 3, 'independent_pipelines')
    original['seed_policy'] = seed_schedule.VERSION
    original['seed_schedule']['seeds'][1][0] = original['seed_schedule']['seeds'][0][0]
    with pytest.raises(ValueError, match='Independent executions'):
        if recovery == 'resume':
            seed_schedule.freeze(state(), SimpleNamespace(), original)
        else:
            seed_schedule.freeze(state(), SimpleNamespace(retry_source_run='original',
                retry_seed_schedule=json.dumps({k: original[k] for k in
                    ('seed_schedule', 'dataset_sha256', 'y_column')})))


@pytest.mark.parametrize('policy', ['shared_replicates', 'pipeline_sequence_v1', 'independent_pipelines'])
def test_historical_records_are_preserved_without_new_draws(monkeypatch, policy):
    original = state()
    original['seed_schedule'] = (seed_schedule.sequential(2, 3, 708) if policy == 'pipeline_sequence_v1'
                                 else seed_schedule.create(2, 3, policy))
    original['seed_policy'] = seed_schedule.VERSION
    def unexpected(*args, **kwargs):
        pytest.fail('Recovery redrew a historical seed')
    monkeypatch.setattr(seed_schedule, 'create', unexpected)
    for retry in (False, True):
        restored = state()
        args = SimpleNamespace(retry_source_run='original', retry_seed_schedule=json.dumps({
            k: original[k] for k in ('seed_schedule', 'dataset_sha256', 'y_column')})) if retry else SimpleNamespace()
        seed_schedule.freeze(restored, args, None if retry else original)
        assert restored['seed_schedule'] == original['seed_schedule']


@pytest.mark.parametrize('order', ['all_pipelines_first', 'pipeline_replicates_first'])
@pytest.mark.parametrize('skill,fraction', [('data_manual_split', .4),
    ('data_training_heavy', .3), ('data_balanced_stratified', .5)])
def test_frozen_combinations_reach_real_split_and_model(tmp_path, monkeypatch, order, skill, fraction):
    rng = np.random.default_rng(923)
    source = tmp_path / 'data.csv'
    frame = pd.DataFrame({'x': rng.normal(size=100), 'z': rng.normal(size=100), 'u': rng.normal(size=100), 'v': rng.normal(size=100), 'outcome': [0, 1] * 50})
    frame.to_csv(source, index=False)
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(source))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', '')
    choices = {'hypothesis': ['hypothesis_general'], 'data': [skill],
               'ml': ['ml_logistic_regression', 'ml_xgboost'],
               'interpreter': ['shared-shap'], 'report': ['shared-addiction']}
    combination = build_plan(choices, 2, execution_order=order)
    args = SimpleNamespace(evaluation=json.dumps({'engine': 'logistic_regression', 'seed': 708,
            'test_size': .4, 'replicates': 1}), y_column='outcome', baseline_columns='[]',
        run_tag='seed-contract', question='', hypothesis_agents=1, trials=1, waves=4,
        combination_plan=json.dumps(combination))
    run = tmp_path / 'run'
    run.mkdir()
    snapshot = freeze_snapshot(args, run, {})
    saved = (run / 'config.json').read_bytes()
    assert snapshot['classifier_seed_policy'] == 'split_seed_v1'
    assert snapshot['seed_schedule']['policy'] == (seed_schedule.FIXED if skill == 'data_manual_split' else seed_schedule.INCREMENTING)
    assert [seed_schedule.task_seed(snapshot, n) for n in range(4)] == ([708] * 4 if skill == 'data_manual_split' else list(range(708, 712)))
    split_ids = []
    for trial in range(4):
        identity = loop_flavors(combination, trial + 1)
        expected = seed_schedule.seed_for(snapshot['seed_schedule'], identity['combination'], identity['repetition'])
        subset = tmp_path / f'trial-{trial}.csv'
        subset.write_bytes(source.read_bytes())
        task = {'task_id': trial + 1, 'trial': trial, 'columns': ['x', 'z', 'u', 'v'], 'y_column': 'outcome'}
        required = data_allocation.request(snapshot, trial)['required_data_plan']
        assert required == {'test_size': fraction, 'seed': expected, 'stratify': True}
        allocation = data_allocation.prepare(required, task, snapshot, subset)
        from memstara.pipeline.feature_selection import validate as validate_features
        task['evaluation'] = {'feature_selection': validate_features(task['columns'], snapshot, trial)}
        write_context(subset, task, snapshot, data_allocation=allocation)
        effective, _ = data_allocation.load_effective(subset, snapshot, snapshot['evaluation'])
        engine = task_books(snapshot, trial)['ml'][0].removeprefix('ml_')
        params = {'random_state': 999}
        if engine == 'xgboost':
            params.update(n_estimators=10, max_depth=2)
        result = evaluation.score(subset, 'outcome', {**effective, 'engine': engine}, explain=False,
            configuration={'parameters': params, 'scale_numeric': False, 'threshold': .5})
        actual = result['evaluation']['replicates'][0]
        assert actual['seed'] == actual['effective_random_state'] == expected
        assert actual['parameters']['random_state'] == expected
        assert actual['n_test'] == int(100 * fraction)
        assert actual['split_id'] == allocation['replicates'][0]['split_id']
        bundle = result['evaluation']['reproducibility']['bundle_path']
        model = joblib.load(f'{bundle}/model-0.joblib')
        assert model.named_steps['model'].random_state == expected
        split_ids.append(actual['split_id'])
    assert len(set(split_ids)) == (1 if skill == 'data_manual_split' else 4)
    # A full snapshot resume must preserve recorded configuration byte for byte.
    args.resume = True
    resumed = freeze_snapshot(args, run, {})
    assert resumed['seed_schedule'] == snapshot['seed_schedule']
    assert (run / 'config.json').read_bytes() == saved
