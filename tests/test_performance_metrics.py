"""Measured CV/Test metrics, leakage boundaries, durable predictions and worker handoff."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sklearn import metrics

from memstara import evaluation, performance_metrics as performance
from memstara.reproducibility import replay
from test_paired_ml import experiment  # noqa: F401
from test_specialist_xai import skills, specification as _specification  # noqa: F401
from test_v1_configuration import clean_data as _clean_data

specification = _specification
clean_data = _clean_data


def test_metrics_match_independent_sklearn_calculations():
    y = np.array([0, 0, 0, 1, 1, 1, 0, 1])
    p = np.array([.05, .4, .8, .2, .35, .9, .25, .65])
    record = performance.binary_metrics(y, p, .35)
    measured = record['metrics']
    predicted = p >= .35
    precision, recall, _ = metrics.precision_recall_curve(y, p)
    expected = dict(auroc=metrics.roc_auc_score(y, p),
                    average_precision=metrics.average_precision_score(y, p),
                    pr_auc=metrics.auc(recall, precision), accuracy=metrics.accuracy_score(y, predicted),
                    sensitivity=metrics.recall_score(y, predicted),
                    specificity=metrics.recall_score(y, predicted, pos_label=0),
                    precision=metrics.precision_score(y, predicted),
                    negative_predictive_value=metrics.precision_score(y, predicted, pos_label=0),
                    f1=metrics.f1_score(y, predicted),
                    balanced_accuracy=metrics.balanced_accuracy_score(y, predicted),
                    brier_score=metrics.brier_score_loss(y, p), log_loss=metrics.log_loss(y, p))
    assert measured == pytest.approx(expected)
    assert record['confusion_matrix']['matrix'] == metrics.confusion_matrix(y, predicted).tolist()
    assert measured['average_precision'] != measured['pr_auc']
    json.dumps(record, allow_nan=False)


@pytest.mark.parametrize('y,p,missing', [([0, 1], [.1, .2], 'precision'),
                                      ([0, 1], [.8, .9], 'negative_predictive_value'),
                                      ([0, 0], [.1, .2], 'auroc')])
def test_undefined_metrics_are_null_with_reasons(y, p, missing):
    record = performance.binary_metrics(y, p, .5)
    assert record['metrics'][missing] is None
    assert record['undefined_reasons'][missing]
    json.dumps(record, allow_nan=False)


@pytest.mark.parametrize('y,p,threshold', [([0, 1], [0, float('nan')], .5),
                                         ([0, 2], [.1, .9], .5), ([0, 1], [.1], .5),
                                         ([0, 1], [.1, 1.1], .5), ([0, 1], [.1, .9], float('nan'))])
def test_invalid_predictions_fail_explicitly(y, p, threshold):
    with pytest.raises(ValueError):
        performance.binary_metrics(y, p, threshold)


def test_bootstrap_is_deterministic_conditional_and_never_fits(monkeypatch):
    from sklearn.pipeline import Pipeline
    monkeypatch.setattr(Pipeline, 'fit', lambda *a, **k: pytest.fail('Bootstrap must not fit'))
    y = np.array([0, 1] * 12)
    p = np.linspace(.1, .9, len(y))
    a = performance.bootstrap_intervals(y, p, .35, 72)
    assert a == performance.bootstrap_intervals(y, p, .35, 72)
    assert a['resamples'] == 1000 and a['confidence_level'] == .95
    for name, interval in a['intervals'].items():
        assert interval['valid_resamples'] <= 1000
        if interval['status'] == 'estimated':
            assert 0 <= interval['lower'] <= interval['upper']
            if name != 'log_loss':
                assert interval['upper'] <= 1
    assert 'class counts held fixed' in a['scope']
    assert 'training' in a['limitations']
    absent = performance.bootstrap_intervals(y, np.zeros(len(y)), .5, 72, samples=20)
    assert absent['intervals']['precision']['status'] == 'undefined_in_resamples'
    assert absent['intervals']['precision']['lower'] is None
    assert performance.bootstrap_intervals([0, 1], [.2, .8], .5, 1)['status'] == 'unavailable'


@pytest.fixture
def bounded_bootstrap(monkeypatch):
    original = performance.bootstrap_intervals
    monkeypatch.setattr(performance, 'bootstrap_intervals',
                        lambda *args: original(*args, samples=30))


@pytest.mark.parametrize('engine', ['logistic_regression', 'xgboost', 'random_forest'])
def test_cv_predictions_persist_reconstruct_metrics_and_replay(clean_data, bounded_bootstrap, engine):
    frame = pd.read_csv(clean_data)
    frame.loc[::7, 'x'] = np.nan
    frame.to_csv(clean_data, index=False)
    source = clean_data.read_bytes()
    result = evaluation.score(clean_data, 'outcome', {'engine': engine, 'folds': 3, 'search_trials': 2},
                              explain=False, missing_policy='impute_train_v1',
                              metrics_policy=performance.VERSION)
    run = result['evaluation']['replicates'][0]
    partitions = run['performance']
    assert partitions['training']['metrics_status'] == 'not_computed'
    assert 'metrics' not in partitions['training']
    cv = partitions['cross_validation']
    assert cv['summary']['auroc']['mean'] == pytest.approx(run['cv_auc'])
    bundle = Path(result['evaluation']['reproducibility']['bundle_path'])
    saved = json.loads((bundle / 'result.json').read_text())
    assert saved['evaluation']['replicates'][0]['performance'] == partitions
    split = np.load(bundle / 'split-0.npz')
    evidence = np.load(bundle / 'cv-predictions-0.npz')
    assert set(evidence['training_rows']) == set(split['train'])
    assert set(split['test']).isdisjoint(split['train'])
    assert list(evidence['labels']) == list(frame.iloc[split['train']]['outcome'])
    assert np.isfinite(evidence['oof_probability']).all()
    seen = []
    for fold in cv['folds']:
        number = fold['fold']
        fit = evidence[f'fold_{number}_fit']
        validation = evidence[f'fold_{number}_validation']
        assert set(fit).isdisjoint(validation)
        assert set(fit) | set(validation) == set(range(len(split['train'])))
        seen.extend(validation)
        actual_train = frame.iloc[split['train'][fit]]
        assert fold['imputation']['fill_values']['x'] == pytest.approx(actual_train.x.mean())
        assert fold['imputation']['fit_scope'] == 'training_fold_only'
        reconstructed = performance.binary_metrics(evidence['labels'][validation],
                                                   evidence['oof_probability'][validation], .5)
        assert fold['metrics'] == reconstructed['metrics']
        assert fold['confusion_matrix'] == reconstructed['confusion_matrix']
    assert sorted(seen) == list(range(len(split['train'])))
    for name, summary in cv['summary'].items():
        values = [row['metrics'][name] for row in cv['folds'] if row['metrics'][name] is not None]
        assert summary['mean'] == pytest.approx(np.mean(values))
        assert summary['std'] == pytest.approx(np.std(values, ddof=1))
    assert partitions['test']['metrics'] == performance.binary_metrics(
        split['labels'], split['probability'], .5)['metrics']
    assert partitions['test']['uncertainty']['status'] == 'completed'
    assert clean_data.read_bytes() == source
    assert replay(bundle)['status'] == 'verified'
    json.dumps(result, allow_nan=False)
    # Predictions participate in the manifest integrity check.
    (bundle / 'cv-predictions-0.npz').write_bytes(b'tampered')
    assert replay(bundle)['status'] == 'integrity_mismatch'


def test_test_predictions_and_selected_candidate_match_legacy(clean_data, bounded_bootstrap):
    plan = {'engine': 'logistic_regression', 'folds': 3, 'search_trials': 3}
    legacy = evaluation.score(clean_data, 'outcome', plan, explain=False, persist=False,
                              metrics_policy=performance.LEGACY)
    rich = evaluation.score(clean_data, 'outcome', plan, explain=False, persist=False,
                            metrics_policy=performance.VERSION)
    old = legacy['evaluation']['replicates'][0]
    new = rich['evaluation']['replicates'][0]
    assert {k: v for k, v in new.items() if k != 'performance'} == old
    assert 'performance' not in old


def test_cv_disabled_is_distinguished_from_missing_metrics(clean_data, bounded_bootstrap):
    result = evaluation.score(clean_data, 'outcome', {'engine': 'logistic_regression', 'folds': 0},
                              explain=False, persist=False, metrics_policy=performance.VERSION)
    record = result['evaluation']['replicates'][0]['performance']
    assert record['cross_validation']['status'] == 'not_performed'
    assert record['test']['metrics']['auroc'] is not None
    assert record['training']['n'] + record['test']['n'] == 100


def test_freeze_new_metrics_and_preserve_saved_contract(clean_data, tmp_path):
    from memstara.pipeline.snapshot import freeze
    args = SimpleNamespace(run_tag='metrics-fixture', question='Predict outcome', hypothesis_agents=1,
                           y_column='outcome', evaluation='{}', trials=1, waves=1)
    books = {'hypothesis': ['treatment-toxicity']}
    snapshot = freeze(args, tmp_path, books)
    assert snapshot['metrics_policy'] == performance.VERSION
    args.resume = True
    assert freeze(args, tmp_path, books) == snapshot
    old = copy.deepcopy(snapshot)
    old.pop('metrics_policy')
    # Recreate a valid historical frozen config without the new optional policy.
    import hashlib
    old.pop('config_hash')
    old['config_hash'] = hashlib.sha256(json.dumps(old, sort_keys=True).encode()).hexdigest()
    (tmp_path / 'config.json').write_text(json.dumps(old))
    assert 'metrics_policy' not in freeze(args, tmp_path, books)


def test_real_mcp_worker_persists_and_passes_metrics_to_both_specialists(specification):
    from memstara.mcp_servers.ml import train_and_score
    from memstara import specialist_xai
    path, snapshot, _, proposal = specification
    snapshot['metrics_policy'] = performance.VERSION
    proposal['folds'] = 3
    result = json.loads(train_and_score(str(path), 'Y', ml_plan=proposal))
    assert not result.get('error'), result
    saved = json.loads(path.with_suffix('.evaluation.json').read_text())
    for name, model in result['model_results'].items():
        measured = model['evaluation']['replicates'][0]['performance']
        assert measured['cross_validation']['fold_count'] == 3
        assert measured['test']['uncertainty']['resamples'] == 1000
        assert saved['model_results'][name]['evaluation']['replicates'][0]['performance'] == measured
        task = {'task_id': 1, 'trial': 0, 'subset_path': str(path), 'evaluation': result}
        for worker in ('interpret#1', 'interpret#2'):
            handoff = specialist_xai.handoff(snapshot, task, worker)
            assert handoff['models'][name]['evaluation']['replicates'][0]['performance'] == measured
    assert json.loads(train_and_score(str(path), 'Y', ml_plan=proposal)) == result
