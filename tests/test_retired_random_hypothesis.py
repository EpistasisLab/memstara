"""New-design boundaries retire random predictors without rewriting saved science."""
import copy
import json
from types import SimpleNamespace

import pytest
from memstara.control import catalog
from memstara.combinations import build_plan, validate_plan
from memstara.control.workspace import PipelineWorkspace


def configuration():
    return {'combination_skills': {'hypothesis': ['random_features'],
            'data': ['data_training_heavy'], 'ml': ['ml_logistic_regression'],
            'interpreter': ['shared-shap'], 'report': ['shared-addiction']}}


def test_random_is_hidden_but_historical_resolution_and_prompt_are_available():
    from memstara.pipeline.prompts import playbook_names, load_prompt
    assert 'random_features' not in playbook_names()
    assert 'random_features' not in {row['id'] for row in catalog.catalog()}
    assert catalog.resolve('random_features')['content']
    assert load_prompt('board/hypothesis', 'random_features')['system_prompt']
    plan = build_plan(configuration()['combination_skills'], random_start=True, start_index=0)
    assert validate_plan(plan) == plan


@pytest.mark.parametrize('body', [configuration(), {'playbook_hypothesis': 'random_features'},
                                   {'playbook_hypothesis': 'hypothesis_general, random_features'}])
def test_new_design_guard_rejects_direct_and_combination_selection(body):
    with pytest.raises(ValueError, match='unavailable for new MVP'):
        catalog.validate_new_design(body)


def test_alias_cannot_bypass_new_design_guard(tmp_path, monkeypatch):
    path = tmp_path / 'aliases.json'
    path.write_text(json.dumps({'old-random': 'random_features'}))
    monkeypatch.setenv('MEMSTARA_SKILL_ALIASES_PATH', str(path))
    with pytest.raises(ValueError, match='unavailable for new MVP'):
        catalog.validate_new_design({'playbook_hypothesis': 'old-random'})


def test_workspace_rejects_new_random_design_but_loads_historical_configuration(tmp_path):
    workspace = PipelineWorkspace(tmp_path/'workspace.json', lambda _: SimpleNamespace(running=lambda: None))
    with pytest.raises(ValueError, match='unavailable for new MVP'):
        workspace.mutate({'action': 'add', 'configuration': configuration()})
    item = workspace.mutate({'action': 'add', 'name': 'Original'})
    with pytest.raises(ValueError, match='unavailable for new MVP'):
        workspace.mutate({'action': 'update', 'id': item['id'], 'name': 'Changed',
                          'configuration': configuration()})
    assert workspace.items[0]['name'] == 'Original'
    historical = PipelineWorkspace.configuration(configuration())
    loaded, error = PipelineWorkspace.read_configuration(copy.deepcopy(historical))
    assert error is None and loaded['combination_skills']['hypothesis'] == ['random_features']


def test_standalone_http_start_rejects_random_before_launch():
    from memstara.control.service import Handler
    handler = object.__new__(Handler)
    sent = []
    handler._send = lambda status, value: sent.append((status, value))
    handler._launch = lambda *args: pytest.fail('Retired new design reached launcher')
    handler._start(configuration())
    assert sent[0][0] == 400
    assert 'unavailable for new MVP' in sent[0][1]['error']


def test_live_menu_profiles_hide_random_without_changing_historical_profiles(monkeypatch):
    from memstara import corpus_skills, research_inputs
    monkeypatch.setattr(research_inputs, 'list_inputs', lambda: [])
    menu = corpus_skills.menu_bindings()
    assert all('random_features' not in p['hypothesis'] for p in menu['profiles'].values())
    assert all('random_features' in p['hypothesis'] for p in corpus_skills.PROFILES.values())
    catalog.validate_new_design({'playbook_hypothesis': 'heart-failure-all-categories', 'combination_random_start': True})
