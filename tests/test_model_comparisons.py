"""Real offline paired ML fits; no LLM calls or patient data."""
import json

import numpy as np
import pandas as pd
import pytest

from memstara import comparisons as c, evaluation as e
from memstara.pipeline.iteration_learning import summarize


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    rng = np.random.default_rng(7)
    n = 240
    signal = rng.normal(size=n)
    frame = pd.DataFrame({'age': rng.normal(size=n), 'signal': signal, 'noise': rng.normal(size=n),
                          'Y': (signal + rng.normal(size=n) * .7 > 0).astype(int)})
    path = tmp_path / 'subset.csv'
    frame.to_csv(path, index=False)
    plan = e.validate({'engine': 'logistic_regression', 'folds': 3, 'search_trials': 2, 'replicates': 2})
    snapshot = {'config_hash': 'experiment', 'run_tag': 'run', 'y_column': 'Y', 'trials': 1,
                'evaluation': plan, 'comparison_policy': {'baseline_columns': ['age']},
                'validation_partition': e.discovery_partition(frame.Y, 42)}
    monkeypatch.setattr(e, 'active_plan', lambda: snapshot)
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.setattr(e, '_explain', lambda *a: ({}, {'status': 'completed'}))
    task = {'columns': ['signal', 'noise'], 'y_column': 'Y', 'evaluation': {'feature_mapping': [
        {'concept': 'mechanism', 'column': 'signal'}, {'concept': 'context', 'column': 'noise'}]}}
    c.write_context(path, task, snapshot)
    return path, plan, snapshot, task


def test_paired_real_models_same_parameters_and_reserved_rows(experiment):
    path, plan, snapshot, _ = experiment
    result = c.score_comparisons(path, 'Y', plan, snapshot)
    variants = result['comparison']['variants']
    assert len(variants) == 4 and all(v['status'] == 'completed' for v in variants)
    assert result['features'] == ['age', 'signal', 'noise']
    assert result['comparison']['timing_status'] == 'unverified'
    assert 'not been verified' in result['comparison']['interpretation_limit']
    base, full, removed_signal, _ = variants
    assert full['auc'] > base['auc'] and removed_signal['auc'] < full['auc']
    assert full['delta_from_baseline'] == pytest.approx(full['auc'] - base['auc'])
    reference = full['replicates']
    for variant in variants:
        assert 'Y' not in variant['features']
        for measured, ref in zip(variant['replicates'], reference, strict=True):
            assert (measured['seed'], measured['split_id'], measured['parameters']) == (
                ref['seed'], ref['split_id'], ref['parameters'])
            assert measured['n_train'] + measured['n_test'] == len(snapshot['validation_partition']['exploration_rows'])
    assert result['comparison']['validation_reserve']['status'] == 'reserved_not_evaluated'
    json.dumps(result, allow_nan=False)


def test_empty_baseline_honest_reference_and_single_group(experiment):
    path, plan, snapshot, task = experiment
    snapshot['comparison_policy']['baseline_columns'] = []
    task['columns'] = ['age', 'signal', 'noise']
    task['evaluation']['feature_mapping'] = [{'concept': 'combined', 'column': col} for col in task['columns']]
    c.write_context(path, task, snapshot)
    result = c.score_comparisons(path, 'Y', plan, snapshot)['comparison']
    assert not result['baseline_configured']
    assert result['variants'][0]['auc'] == .5
    assert result['variants'][-1]['features'] == []
    assert result['variants'][-1]['method'] == 'training_prevalence_only'


def test_failed_ablation_preserves_full_result(experiment, monkeypatch):
    path, plan, snapshot, _ = experiment
    original = e.score
    def partial(*args, **kwargs):
        if kwargs.get('predictors') == ['age', 'noise']:
            raise RuntimeError('SECRET DATA MUST NOT APPEAR')
        return original(*args, **kwargs)
    monkeypatch.setattr(e, 'score', partial)
    result = c.score_comparisons(path, 'Y', plan, snapshot)
    assert result['auc'] > .5
    assert result['comparison']['status'] == 'partial'
    assert result['comparison']['variants'][2]['status'] == 'failed'
    assert 'SECRET' not in json.dumps(result)


def test_context_cannot_cross_runs_or_changed_data(experiment):
    path, plan, snapshot, _ = experiment
    with pytest.raises(ValueError, match='frozen task'):
        c.score_comparisons(path, 'Y', plan, {**snapshot, 'config_hash': 'another'})
    path.write_text(path.read_text() + '\n')
    with pytest.raises(ValueError, match='frozen task'):
        c.score_comparisons(path, 'Y', plan, snapshot)


def test_baseline_validation_and_exact_extraction(experiment):
    path, _, snapshot, task = experiment
    for invalid in ('age', ['Y'], [123], ['absent']):
        with pytest.raises(ValueError):
            c.validate_baseline(invalid, 'Y', path)
    assert c.validate_baseline(['age', '', 'age'], 'Y', path) == ['age']
    with pytest.raises(ValueError, match='exactly'):
        c.write_context(path, {**task, 'columns': ['signal']}, snapshot)


def test_feedback_carries_measured_comparison_without_target(experiment):
    _, _, snapshot, _ = experiment
    result = {'variants': [{'id': 'expanded', 'delta_from_baseline': .04}]}
    feedback = summarize([{'task_id': 1, 'run_tag': 'run', 'trial': 0, 'status': 'done',
                           'columns_used': ['age', 'Y'], 'evaluation': {'comparison': result}}], snapshot, 1)
    assert feedback['evidence'][0]['features'] == ['age']
    assert feedback['evidence'][0]['comparison']['variants'][0]['delta_from_baseline'] == .04


def test_real_data_to_ml_artifact_includes_baseline_and_comparisons(experiment, monkeypatch):
    from memstara.mcp_servers import data, ml
    path, plan, snapshot, task = experiment
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(path))
    monkeypatch.setenv('MEMSTARA_OUTCOME_COLUMN', 'Y')
    extracted = json.loads(data.slice_columns(['signal', 'noise'], 'Y', 'handoff'))
    assert not extracted.get('error')
    assert set(extracted['columns_used']) == {'signal', 'noise', 'age', 'Y'}
    from pathlib import Path
    subset = Path(extracted['path'])
    c.write_context(subset, task, snapshot)
    measured = json.loads(ml.train_and_score(str(subset), 'Y'))
    assert not measured.get('error') and measured['comparison']['status'] == 'completed'
    artifact = json.loads(subset.with_suffix('.evaluation.json').read_text())
    assert artifact == measured
    assert artifact['config_hash'] == snapshot['config_hash']
    assert 'Y' not in artifact['features']


def test_control_transports_baseline_and_blocks_target(monkeypatch):
    from memstara.control.request import build_argv
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'test')
    args = build_argv({'baseline_columns': ['age', '', 'age'], 'y_column': 'Y'}, [])
    assert json.loads(args[args.index('--baseline-columns') + 1]) == ['age']
    with pytest.raises(ValueError, match='target'):
        build_argv({'baseline_columns': ['Y'], 'y_column': 'Y'}, [])
