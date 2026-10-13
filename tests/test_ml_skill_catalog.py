"""Only model choices are exposed; prior prompts remain loadable."""
import pytest
from memstara.control.catalog import catalog, resolve
from memstara.pipeline.prompts import load_prompt, playbook_names


def test_two_builtin_ml_choices_and_common_contract(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    assert {i['id'] for i in catalog() if i['stage'] == 'ml'} == {'ml_logistic_regression', 'ml_xgboost'}
    for name in ('ml_logistic_regression', 'ml_xgboost'):
        prompt = load_prompt('board/ml', name)['system_prompt']
        assert 'Common training, evaluation and result contract' in prompt
        assert 'both model artifacts and model_results' in prompt
        assert 'Clinical presentation and readiness judgments belong to downstream reporting' in prompt


@pytest.mark.parametrize('name', ['ml_governance', 'ml_pilot_lr_focus', 'ml_pilot_xgb_focus',
                                  'ml_reporting', 'ml_results_presenter', 'ml_scikit_knowledge'])
def test_legacy_ml_skills_remain_readable_but_not_selectable(name, monkeypatch):
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    assert name not in playbook_names()
    assert resolve(name)['stage'] == 'ml'
    prompt = load_prompt('board/ml', name)['system_prompt']
    assert 'Common training, evaluation and result contract' not in prompt
