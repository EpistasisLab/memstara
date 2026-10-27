"""Driver integration with mocked paid calls and numerical fitting, using synthetic CSV only."""
import asyncio
import json
from unittest.mock import AsyncMock

import numpy as np
import pandas as pd
import pytest

from memstara import pilot_final
from memstara.pipeline import specialist_pilot as pilot
from memstara.pilot_ml import parameter_context


@pytest.fixture
def study(tmp_path, monkeypatch):
    frame = pd.DataFrame(np.arange(240).reshape(40, 6), columns=list('abcdef'))
    frame['outcome'] = [0, 1] * 20
    dataset = tmp_path / 'fixture.csv'
    frame.to_csv(dataset, index=False)
    def resolve(name):
        stage = ('interpreter' if name in ('shared-shap', 'shared-lime') else
                 'report' if name in ('shared-addiction', 'shared-hiv') else
                 'data' if name.startswith('data_') else 'ml' if name.startswith('ml_') else 'hypothesis')
        return {'id': name, 'stage': stage, 'source_hash': name, 'hash': name, 'title': name, 'content': name}
    monkeypatch.setattr(pilot, 'resolve', resolve)
    monkeypatch.setattr(pilot_final, 'resolve', resolve)
    def binding(name):
        return {'database_id': name, 'kind': 'markdown', 'path': str(tmp_path)}
    config = {'run_id': 'fixture', 'seed': 42, 'repetitions': 1, 'expected_combinations': 1,
              'dataset': str(dataset), 'target': 'outcome', 'outcome_description': 'Synthetic binary outcome',
              'choices': {'hypothesis': ['random_features'], 'data': ['data_training_heavy'],
                          'ml': ['ml_pilot_lr_focus'], 'interpreter': ['shared-shap'],
                          'report': ['shared-hiv']},
              'models': {'qwen': {'provider': 'local', 'model': 'qwen-fixture'},
                         'sonnet': {'provider': 'anthropic', 'model': 'sonnet-fixture'}},
              'knowledge': {name: binding(name) for name in ('addiction', 'hiv')},
              'skill_hashes': dict(pilot_final.SKILLS)}
    return config, tmp_path / 'study'


async def knowledge(binding, query):
    return {'database_id': binding['database_id'], 'documents': [{'id': 'doc1', 'text': query}]}


async def response(profile, system, payload):
    if 'feature_size' in payload:
        value = {'question': 'Fixture question', 'hypothesis': 'Fixture hypothesis', 'rationale': 'Fixture rationale',
                 'features': payload['required_features'] or payload['eligible_features'][:4],
                 'evidence_ids': ['doc1'] if payload['knowledge_evidence']['documents'] else []}
    elif 'schema' in payload:
        value = {'test_size': .5 if 'balanced' in system else .2, 'seed': 7, 'stratify': True}
    elif 'parameter_defaults' in payload:
        models = parameter_context()
        models['logistic_regression']['random_state'] = 7
        models['xgboost'].update(random_state=7, n_jobs=1)
        value = {'models': models, 'scale_numeric': True, 'threshold': .5,
                 'xai_rows': 2, 'lime_samples': 100, 'seed': 7}
    else:
        return {'text': 'Measured specialist report', 'usage': {'cost_estimate': .01}}
    return {'text': json.dumps(value), 'usage': {'cost_estimate': .01}}


def fit(dataset, target, features, data, ml, scope, output):
    output.mkdir()
    rows = [{'scope': scope, 'status': 'completed', 'result_id': family, 'model': family,
             'split_id': 'fixture-split', 'target': target, 'features': features, 'metrics': {'auroc': .7},
             'attributions': {method: {'status': 'completed', 'values': [1]} for method in ('shap', 'lime')}}
            for family in ('logistic_regression', 'xgboost')]
    pilot_final._save(output / 'paired-results.json', {'scope': scope, 'results': rows})
    return rows


def test_all_stages_connected_and_completed_results_are_not_rerun(study):
    config, output = study
    invoke = AsyncMock(side_effect=response)
    result = asyncio.run(pilot.run_study(config, output, invoke=invoke, knowledge=knowledge, fit=fit))
    assert result['status'] == 'completed'
    assert invoke.await_count == 5
    assert [call.args[0]['model'] for call in invoke.call_args_list] == ['qwen-fixture'] * 4 + ['sonnet-fixture']
    interpreter = invoke.call_args_list[3].args[2]
    assert set(interpreter['models']) == {'logistic_regression', 'xgboost'}
    assert interpreter['research_context']['question'] == 'Fixture question'
    explanation = invoke.call_args_list[4].args[2]
    assert explanation['interpretations'][0]['output'] == 'Measured specialist report'
    assert explanation['knowledge_evidence']['database_id'] == 'hiv'
    assert explanation['research_context'] == interpreter['research_context']
    assert json.loads((output / 'comparison.json').read_text())['completed_combinations'][0]['question']
    asyncio.run(pilot.run_study(config, output, resume=True, invoke=invoke, knowledge=knowledge, fit=fit))
    assert invoke.await_count == 5


def test_failure_stops_and_explicit_resume_reuses_prior_paid_stages(study):
    config, output = study
    async def failing(profile, system, payload):
        if payload.get('expert'):
            raise RuntimeError('fixture failure')
        return await response(profile, system, payload)
    invoke = AsyncMock(side_effect=failing)
    with pytest.raises(RuntimeError):
        asyncio.run(pilot.run_study(config, output, invoke=invoke, knowledge=knowledge, fit=fit))
    status = json.loads((output / 'status.json').read_text())
    assert status['status'] == 'paused'
    assert status['completed_combinations'] == 0
    resumed = AsyncMock(side_effect=response)
    asyncio.run(pilot.run_study(config, output, resume=True, invoke=resumed, knowledge=knowledge, fit=fit))
    assert resumed.await_count == 1
    assert resumed.call_args.args[0]['model'] == 'sonnet-fixture'


def test_full_cartesian_schedule_runs_each_condition_once_with_mocked_services(study):
    config, output = study
    config['expected_combinations'] = 64
    config['choices']['hypothesis'] = ['guided-a', 'guided-b', 'guided-c', 'random_features']
    config['choices']['data'] += ['data_balanced_stratified']
    config['choices']['ml'] += ['ml_pilot_xgb_focus']
    config['choices']['interpreter'] += ['shared-lime']
    config['choices']['report'] += ['shared-addiction']
    config['hypothesis_knowledge'] = {name: config['knowledge']['hiv'] for name in
                                    config['choices']['hypothesis'] if name != 'random_features'}
    invoke = AsyncMock(side_effect=response)
    result = asyncio.run(pilot.run_study(config, output, invoke=invoke, knowledge=knowledge, fit=fit))
    assert result['completed_combinations'] == 64
    assert invoke.await_count == 64 * 5
    saved = json.loads((output / 'comparison.json').read_text())['completed_combinations']
    assert {row['scope']['combination_id'] for row in saved} == set(range(1, 65))
    assert len(list(output.glob('combination-*/completed.json'))) == 64


def test_numerical_failure_stops_before_interpretation_and_next_combination(study):
    config, output = study
    config['choices']['data'].append('data_balanced_stratified')
    config['expected_combinations'] = 2
    def failing_fit(*args):
        raise ValueError('Synthetic numerical failure')
    invoke = AsyncMock(side_effect=response)
    with pytest.raises(ValueError, match='numerical failure'):
        asyncio.run(pilot.run_study(config, output, invoke=invoke, knowledge=knowledge, fit=failing_fit))
    assert invoke.await_count == 3
    assert not (output / 'combination-002').exists()
    assert json.loads((output / 'status.json').read_text())['stage'] == 'paired_ml_and_xai'


def test_resume_refuses_changed_completed_artifacts(study):
    config, output = study
    invoke = AsyncMock(side_effect=response)
    asyncio.run(pilot.run_study(config, output, invoke=invoke, knowledge=knowledge, fit=fit))
    (output / 'combination-001' / 'final' / 'shap.md').write_text('changed')
    with pytest.raises(ValueError, match='artifact changed'):
        asyncio.run(pilot.run_study(config, output, resume=True, invoke=invoke, knowledge=knowledge, fit=fit))
    assert invoke.await_count == 5
