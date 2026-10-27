"""Meeting 17/19/21/22/23: exercise the registered-input to real ML tool boundary.

Synthetic data only, no LLM or database. Unlike direct score() tests, this freezes
an ordinary run and crosses the Data handoff and supervised ML subprocess before
checking its saved evidence. Provider/DB and UI acceptance remain separate.
"""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from memstara import data_allocation, dataset_upload, research_inputs
from memstara.comparisons import write_context
from memstara.mcp_servers.ml import get_ml_configuration, train_and_score
from memstara.pipeline.snapshot import freeze


@pytest.mark.parametrize('engine', ['logistic_regression', 'xgboost'])
def test_registered_typed_data_reaches_frozen_split_real_ml_and_replay(tmp_path, monkeypatch, engine):
    monkeypatch.setattr(os, 'environ', dict(os.environ))
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path / 'registry'))
    output = tmp_path / 'outputs'
    output.mkdir()
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(output))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    frame = pd.DataFrame({
        'age_years': np.linspace(20, 80, 120),
        'disease_stage': [1., 2., 3., 2.] * 30,
        'group': ['a', 'b', 'b', 'c'] * 30,
        'event_count': [0., 1., 2., 3., 4., 5.] * 20,
        'outcome': [0, 1] * 60,
    })
    for column in frame.columns[:-1]:
        frame.loc[[7, 24, 53], column] = np.nan
    raw = frame.to_csv(index=False).encode()
    uploaded = dataset_upload.upload({
        'filename': 'synthetic.csv', 'content_base64': base64.b64encode(raw).decode(),
    })
    source = Path(uploaded['dataset_path'])
    assert source.read_bytes() == raw and uploaded['missing_cells'] == 12
    configuration = {
        'name': 'Meeting acceptance', 'dataset_path': str(source), 'knowledge_mode': 'llm_only',
        'target': {'column': 'outcome', 'positive_label': '1', 'negative_label': '0'},
        'missing_policy': 'reject', 'predictor_types': {},
    }
    rejected = research_inputs.register(configuration)
    assert not rejected['input_checks_passed']
    assert any(issue['code'] == 'missing_values' for issue in rejected['issues'])
    registered = research_inputs.register({**configuration, 'missing_policy': 'impute_train_v1'})
    assert registered['input_checks_passed'], registered['issues']
    profile = research_inputs.prepare(registered['id'])
    research_inputs.activate(profile)
    output = Path(os.environ['MEMSTARA_OUTPUT_DIR'])
    output.mkdir(parents=True, exist_ok=True)
    prepared = Path(profile['root']) / 'dataset.csv'
    prepared_bytes = prepared.read_bytes()
    assert pd.read_csv(prepared).isna().sum().sum() == 12
    run = output / 'run'
    run.mkdir()
    args = SimpleNamespace(
        evaluation=json.dumps({'engine': engine, 'test_size': .4, 'seed': 708,
                               'folds': 3, 'replicates': 1, 'search_trials': 1}),
        y_column='outcome', baseline_columns='[]', run_tag='meeting-acceptance',
        question='', hypothesis_agents=1, trials=1, waves=2, research_profile=profile,
    )
    snapshot = freeze(args, run, {'data': ['data_manual_split'], 'ml': ['ml_' + engine]})
    assert snapshot['partition_policy'] == 'two_way_stratified_v1'
    assert snapshot['validation_partition'] is None
    assert snapshot['hypothesis_policy']['prior_ml_feedback'] is False
    frozen_bytes = (run / 'config.json').read_bytes()
    predictor_types = snapshot['research_profile']['configuration']['predictor_types']
    assert predictor_types == {'age_years': 'continuous', 'disease_stage': 'categorical',
                               'group': 'categorical', 'event_count': 'continuous'}

    split_ids = []
    assert snapshot['seed_schedule']['policy'] == 'fixed_experiment_v1'
    assert len(set(snapshot['seed_schedule']['seeds'][0])) == 1
    for trial, expected_seed in enumerate(snapshot['seed_schedule']['seeds'][0]):
        subset = output / f'trial-{trial}.csv'
        subset.write_bytes(prepared_bytes)
        task = {'task_id': trial + 1, 'trial': trial, 'columns': list(frame.columns[:-1]),
                'y_column': 'outcome', 'evaluation': {}}
        required = data_allocation.request(snapshot, trial)['required_data_plan']
        assert required == {'test_size': .4, 'seed': expected_seed, 'stratify': True}
        with pytest.raises(ValueError, match='frozen'):
            data_allocation.prepare({**required, 'seed': 999}, task, snapshot, subset)
        record = data_allocation.prepare(required, task, snapshot, subset)
        write_context(subset, task, snapshot, data_allocation=record)
        context = json.loads(asyncio.run(get_ml_configuration(str(subset), 'outcome')))
        proposal = context['proposal_template']
        proposal['rationale'] = 'Synthetic fixed plan for meeting requirement acceptance'
        proposal['folds'] = 3
        if engine in ('xgboost', 'random_forest'):
            proposal['models'][engine]['parameters'].update(n_estimators=10, max_depth=2)
        result = json.loads(train_and_score(str(subset), 'outcome', seed=999,
                                           test_size=.2, ml_plan=proposal))
        assert not result.get('error') and result.get('status') != 'failed', result
        actual = result['evaluation']['replicates'][0]
        assert len(result['evaluation']['replicates']) == 1
        assert actual['seed'] == actual['effective_random_state'] == expected_seed
        assert actual['parameters']['random_state'] == expected_seed
        assert (actual['n_train'], actual['n_test']) == (72, 48)
        assert actual['split_id'] == record['replicates'][0]['split_id']
        split_ids.append(actual['split_id'])
        assert record['reserved_count'] == 0
        assert result['evaluation']['score_scope'] == 'two_way_test'
        bundle = Path(result['evaluation']['reproducibility']['bundle_path'])
        arrays = np.load(bundle / 'split-0.npz')
        train, test = arrays['train'], arrays['test']
        assert set(train).isdisjoint(test)
        assert sorted([*train, *test]) == list(range(len(frame)))
        assert actual['cv_folds'] == 3
        for fold in range(3):
            fit, validation = arrays[f'cv_{fold}_train'], arrays[f'cv_{fold}_validation']
            assert set(fit).isdisjoint(validation)
            assert set(fit) | set(validation) == set(train)
            assert set(fit).isdisjoint(test) and set(validation).isdisjoint(test)
        imputation = actual['imputation']
        assert imputation['fit_scope'] == 'training_partition'
        for column, kind in predictor_types.items():
            expected = (frame.iloc[train][column].mean() if kind == 'continuous'
                        else frame.iloc[train][column].mode().iloc[0])
            value = imputation['fill_values'][column]
            if kind == 'continuous':
                assert value == pytest.approx(expected)
            else:
                assert value == expected
        assert json.loads(subset.with_suffix('.evaluation.json').read_text()) == result
        # A retry uses the recorded completed result, rather than another fit.
        assert json.loads(train_and_score(str(subset), 'outcome', ml_plan=proposal)) == result
        env = {**os.environ, **{key: '1' for key in (
            'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')}}
        replay = subprocess.run([sys.executable, '-m', 'memstara.reproducibility', str(bundle)],
                                env=env, capture_output=True, text=True, timeout=60)
        assert replay.returncode == 0, replay.stdout + replay.stderr
        assert json.loads(replay.stdout)['status'] == 'verified'

    assert len(set(split_ids)) == 1
    assert (run / 'config.json').read_bytes() == frozen_bytes
    assert source.read_bytes() == raw and prepared.read_bytes() == prepared_bytes
    assert hashlib.sha256(prepared_bytes).hexdigest() == snapshot['dataset_sha256']
