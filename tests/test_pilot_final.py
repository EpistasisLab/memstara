"""Offline provider and knowledge boundaries; never launch an experiment."""
import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from memstara import pilot_final
from memstara.pilot_models import for_stage, validate_profiles


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot_final, 'resolve', lambda key: {
        'id': key, 'source_hash': key, 'content': f'Instructions for {key}'})
    models = {'qwen': {'provider': 'local', 'model': 'qwen-fixture'},
              'sonnet': {'provider': 'anthropic', 'model': 'sonnet-fixture'}}
    config = {'models': models, 'skill_hashes': dict(pilot_final.SKILLS),
              'knowledge': {name: {'database_id': name, 'kind': 'markdown', 'path': str(tmp_path)}
                            for name in ('addiction', 'hiv')}}
    scope = {'run_id': 'fixture', 'combination_id': 1, 'question_id': 1}
    rows = [{'scope': scope, 'model': model, 'result_id': model, 'status': 'completed',
             'split_id': 'split', 'features': ['a', 'b', 'c', 'd'], 'target': 'outcome',
             'metrics': {'auc': .7}, 'attributions': {method: {'value': 1} for method in ('shap', 'lime')}}
            for model in ('logistic_regression', 'xgboost')]
    return config, {'scope': scope, 'results': rows}, tmp_path / 'run'


async def evidence(binding, query):
    return {'database_id': binding['database_id'], 'documents': [{'id': binding['database_id'], 'text': query}]}


def test_final_stages_route_models_preserve_pair_and_isolate_expert_evidence(prepared):
    config, bundle, output = prepared
    invoke = AsyncMock(side_effect=[{'text': name, 'usage': {'cost_estimate': .01}}
                                    for name in ('shap', 'lime', 'addiction', 'hiv')])
    status = asyncio.run(pilot_final.run_final_stages(config, bundle, output, invoke=invoke, knowledge=evidence))
    assert status['completed'] == ['shap', 'lime', 'addiction', 'hiv']
    calls = invoke.call_args_list
    assert [call.args[0]['model'] for call in calls] == ['qwen-fixture'] * 2 + ['sonnet-fixture'] * 2
    for call in calls[:2]:
        assert set(call.args[2]['models']) == {'logistic_regression', 'xgboost'}
    for expert, call in zip(('addiction', 'hiv'), calls[2:], strict=True):
        payload = call.args[2]
        assert [item['output'] for item in payload['interpretations']] == ['shap', 'lime']
        assert payload['knowledge_evidence']['documents'][0]['id'] == expert
    for name in pilot_final.SKILLS:
        assert (output / f'{name}.input.json').is_file()
        assert (output / f'{name}.md').read_text() == name
        assert json.loads((output / f'{name}.output.json').read_text())['usage']['cost_estimate'] == .01
    with pytest.raises(FileExistsError):
        asyncio.run(pilot_final.run_final_stages(config, bundle, output, invoke=invoke, knowledge=evidence))
    assert invoke.await_count == 4


def test_failure_pauses_before_following_agents(prepared):
    config, bundle, output = prepared
    invoke = AsyncMock(side_effect=[{'text': 'shap'}, RuntimeError('private provider detail')])
    with pytest.raises(RuntimeError):
        asyncio.run(pilot_final.run_final_stages(config, bundle, output, invoke=invoke, knowledge=evidence))
    status = json.loads((output / 'status.json').read_text())
    assert status['status'] == 'paused'
    assert status['completed'] == ['shap']
    assert status['stage'] == 'lime'
    assert invoke.await_count == 2
    assert not (output / 'addiction.input.json').exists()
    assert 'private provider detail' not in (output / 'status.json').read_text()


def test_mismatched_knowledge_identity_stops_before_paid_calls(prepared):
    config, bundle, output = prepared
    invoke = AsyncMock()
    with pytest.raises(ValueError, match='another expert'):
        asyncio.run(pilot_final.run_final_stages(config, bundle, output, invoke=invoke,
                    knowledge=AsyncMock(return_value={'database_id': 'wrong'})))
    invoke.assert_not_called()


def test_changed_skill_hash_stops_before_calls(prepared):
    config, bundle, output = prepared
    config['skill_hashes']['shap'] = 'outdated'
    invoke = AsyncMock()
    with pytest.raises(ValueError, match='pin the current'):
        asyncio.run(pilot_final.run_final_stages(config, bundle, output, invoke=invoke))
    invoke.assert_not_called()


def test_pause_request_stops_between_agents(prepared):
    config, bundle, output = prepared
    async def invoke(*args):
        (output / 'pause.request').touch()
        return {'text': 'shap'}
    with pytest.raises(RuntimeError, match='paused'):
        asyncio.run(pilot_final.run_final_stages(config, bundle, output, invoke=invoke, knowledge=evidence))
    status = json.loads((output / 'status.json').read_text())
    assert status['completed'] == ['shap']
    assert status['stage'] == 'lime'
    assert not (output / 'lime.input.json').exists()


@pytest.mark.parametrize('stage', ['hypothesis', 'data', 'ml', 'interpreter#2', 'report#2'])
def test_explicit_stage_routing(prepared, stage):
    config, _, _ = prepared
    family = 'sonnet' if stage.startswith('report') else 'qwen'
    assert for_stage(config['models'], stage) == config['models'][family]


@pytest.mark.parametrize('field,value', [('max_tokens', -1), ('temperature', float('nan')),
                                       ('model', ''), ('api_key', 'secret')])
def test_invalid_profile_rejected_before_any_stage(prepared, field, value):
    config, _, _ = prepared
    profiles = deepcopy(config['models'])
    profiles['sonnet'][field] = value
    with pytest.raises(ValueError):
        validate_profiles(profiles)
