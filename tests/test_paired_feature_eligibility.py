"""Prevent random and guided hypotheses from selecting predictors rejected by LR."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from memstara.evaluation import validate_clean_dataset
from memstara.pipeline.feature_context import freeze_feature_context
from memstara.pipeline import feature_selection as fs


def dataset(tmp_path, complete=24):
    path = tmp_path / 'data.csv'
    frame = pd.DataFrame({f'feature_{i}': [(j + i) % 5 for j in range(40)] for i in range(complete)})
    frame['partial'] = [None, 1] * 20
    frame['empty'] = None
    frame['Y'] = [0, 1] * 20
    frame.to_csv(path, index=False)
    return path


def test_snapshot_filters_before_sampling_and_preserves_replay(tmp_path, monkeypatch):
    from memstara.pipeline import snapshot
    from memstara.feature_reproduction import replay
    path = dataset(tmp_path)
    original = path.read_bytes()
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(path))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', '')
    monkeypatch.setenv('MEMSTARA_OUTCOME_COLUMN', '')
    monkeypatch.setenv('AGENTIC_OKF_BUNDLE_DIR', str(tmp_path / 'no-knowledge'))
    monkeypatch.setattr(snapshot, 'load_prompt', lambda *args: {})
    stages = ('hypothesis', 'data', 'ml', 'interpreter', 'report')
    plan = {'version': 1, 'total_loops': 200, 'combinations': 1,
            'skills': {s: [{'id': 'random_features' if s == 'hypothesis' else ''}] for s in stages}}
    args = SimpleNamespace(evaluation='{"engine":"xgboost"}', y_column='Y',
        baseline_columns='[]', run_tag='fixture', question='', hypothesis_agents=1,
        trials=1, waves=200, combination_plan=json.dumps(plan))
    run = tmp_path / 'run'
    run.mkdir()
    frozen = snapshot.freeze(args, run, {})
    assert frozen['missing_value_policy'] == 'reject'
    policy = frozen['feature_selection_policy']
    assert policy['eligibility']['excluded_columns'] == ['partial', 'empty']
    assert policy['eligibility']['eligible_count'] == 24
    assert policy['pool_source'] == 'frozen_complete_predictor_catalog'
    frame = pd.read_csv(path)
    counts = set()
    for loop in range(200):
        selected = fs.context(frozen, loop)['required_features']
        counts.add(len(selected))
        assert not frame[selected].isna().any().any()
        fs.validate(selected, frozen, loop)
    assert min(counts) == 4 and max(counts) == 20
    subset = tmp_path / 'subset.csv'
    frame[fs.context(frozen, 0)['required_features'] + ['Y']].to_csv(subset, index=False)
    validate_clean_dataset(subset, 'Y', allow_missing=False)
    frozen['combination_plan']['skills']['hypothesis'] = [{'id': 'guided'}]
    with pytest.raises(ValueError, match='frozen eligible pool'):
        fs.validate(['feature_0', 'feature_1', 'feature_2', 'partial'], frozen, 0)
    assert path.read_bytes() == original
    assert replay(run / 'feature_reproduction')['random_loops_replayed'] == 200


def test_insufficient_complete_predictors_fail_before_generation(tmp_path):
    path = dataset(tmp_path, complete=3)
    with pytest.raises(ValueError, match='at least four complete'):
        freeze_feature_context(path, 'Y', require_complete=True)


def test_header_only_selected_mode_retains_native_missing_candidates(tmp_path):
    context = freeze_feature_context(dataset(tmp_path), 'Y')
    assert 'partial' in {r['column'] for r in context['features']}
    assert 'eligibility' not in context


def test_control_refuses_insufficient_pool_without_starting_run(tmp_path, monkeypatch):
    pytest.importorskip('motoro')
    from memstara.control import service
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(dataset(tmp_path, complete=3)))
    monkeypatch.setattr(service, 'skills', lambda: [])
    monkeypatch.setattr(service, 'playbooks', lambda: {'playbooks': [], 'stages': []})
    monkeypatch.setattr(service, 'build_argv', lambda *args: ['--y-column', 'Y'])
    monkeypatch.setattr(service, 'validate_selection', lambda *args: None)
    def forbidden(*args, **kwargs):
        pytest.fail('An insufficient candidate pool must not create or launch a run')
    monkeypatch.setattr(service, 'new_run_dir', forbidden)
    monkeypatch.setattr(service.RUNS, 'start', forbidden)
    responses = []
    handler = object.__new__(service.Handler)
    handler._send = lambda status, body: responses.append((status, body))
    service.Handler._start(handler, {'y_column': 'Y', 'evaluation': {'engine': 'xgboost'},
                                    'combination_skills': {'hypothesis': ['random_features']}})
    assert responses[0][0] == 422
    assert 'at least four complete' in responses[0][1]['error']
