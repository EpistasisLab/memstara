"""Offline corpus-to-catalog-to-request-to-prompt checks; no inference."""
from pathlib import Path

import pytest

from memstara.corpus_skills import PROFILES, INDEX_PROFILES, corpus_profile
from memstara.control.catalog import catalog
from memstara.control.request import build_argv
from memstara.pipeline.prompts import load_prompt
from memstara.research_inputs import validate_skills


def profile(scope):
    index = next(key for key, value in INDEX_PROFILES.items() if value == scope)
    return {'configuration': {'name': 'Arbitrary name', 'knowledge_mode': 'okf', 'data_mode': 'dataset',
                              'target': {'column': 'outcome', 'description': 'Test outcome'}},
            'knowledge': {'hashes': {'index.md': index}}}


@pytest.mark.parametrize('scope', ['hiv', 'heart_failure'])
def test_corpus_profiles_have_three_distinct_specialties_and_random(scope):
    assert corpus_profile(profile(scope)) == scope
    selected = PROFILES[scope]['hypothesis']
    assert len(selected) == 4 and selected[-1] == 'random_features'
    validate_skills({'hypothesis': selected, 'report': PROFILES[scope]['report']}, profile(scope))
    for name in selected[:3]:
        item = next(item for item in catalog() if item['id'] == name)
        assert item['stage'] == 'hypothesis'
        assert item['content'].strip() in load_prompt('board/hypothesis', playbook=name)['system_prompt']


@pytest.mark.parametrize('scope,wrong', [('hiv', 'heart_failure'), ('heart_failure', 'hiv')])
def test_wrong_corpus_skills_rejected_for_single_and_combination_requests(scope, wrong, monkeypatch):
    import memstara.research_inputs as research
    monkeypatch.setattr(research, 'load', lambda identifier: profile(scope))
    monkeypatch.setattr('memstara.stage_models.deployment_profiles', lambda: {})
    for role in ('QUESTION', 'HYPOTHESIS', 'DATA', 'ML', 'INTERPRETATION', 'EXPLANATION'):
        monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER', 'openai')
        monkeypatch.setenv(f'MEMSTARA_{role}_MODEL', 'fixture')
    names = [item['id'] for item in catalog()]
    correct = PROFILES[scope]['hypothesis'][0]
    request = {'research_input_id': 'a' * 32, 'provider': 'openai', 'model': 'fixture',
               'playbook_hypothesis': correct, 'playbook_explanation': 'report_general'}
    assert correct in build_argv(request, [], names, ['hypothesis', 'report'])
    bad = PROFILES[wrong]['hypothesis'][0]
    with pytest.raises(ValueError, match='does not match the selected corpus'):
        build_argv({**request, 'playbook_hypothesis': bad}, [], names, ['hypothesis', 'report'])
    with pytest.raises(ValueError, match='does not match the selected corpus'):
        validate_skills({'hypothesis': [correct, bad, 'random_features']}, profile(scope))


def test_profile_binding_uses_actual_index_not_a_study_name_or_target(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_OKF_BUNDLE_DIR', str(tmp_path / 'HIV-HeartFailure'))
    assert corpus_profile() == 'general'
    assert corpus_profile({'configuration': {'name': 'HIV', 'knowledge_mode': 'okf', 'data_mode': 'dataset',
                              'target': {'column': 'outcome', 'description': 'Test outcome'}},
                           'knowledge': {'hashes': {'index.md': 'unknown'}}}) == 'general'
    assert corpus_profile(profile('hiv'), knowledge_mode='llm_only') == 'general'
    corpus = Path(__file__).resolve().parents[1] / 'examples/heart-failure/okf'
    monkeypatch.setenv('AGENTIC_OKF_BUNDLE_DIR', str(corpus))
    assert corpus_profile() == 'heart_failure'
    validate_skills({'hypothesis': PROFILES['heart_failure']['hypothesis']})
    with pytest.raises(ValueError, match='does not match the selected corpus'):
        validate_skills({'hypothesis': PROFILES['hiv']['hypothesis']})


def test_general_saved_choices_remain_executable_without_rewriting_history():
    for scope in ['hiv', 'heart_failure']:
        validate_skills({'hypothesis': ['hypothesis_general'], 'report': ['report_general']}, profile(scope))


@pytest.mark.parametrize('scope,wrong', [('hiv', 'heart_failure'), ('heart_failure', 'hiv')])
def test_two_explanations_reach_report_prompt_and_reject_wrong_corpus(scope, wrong, monkeypatch):
    import memstara.research_inputs as research
    monkeypatch.setattr(research, 'load', lambda identifier: profile(scope))
    monkeypatch.setattr('memstara.stage_models.deployment_profiles', lambda: {})
    for role in ('QUESTION', 'HYPOTHESIS', 'DATA', 'ML', 'INTERPRETATION', 'EXPLANATION'):
        monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER', 'openai')
        monkeypatch.setenv(f'MEMSTARA_{role}_MODEL', 'fixture')
    rows = {row['id']: row for row in catalog()}
    reports = PROFILES[scope]['report']
    assert len(reports) == 2
    assert len(PROFILES[scope]['hypothesis']) * 2 * 2 * 2 * len(reports) == 64
    for name in reports:
        assert rows[name]['stage'] == 'report'
        assert rows[name]['content'].strip() in load_prompt('board/report', playbook=name)['system_prompt']
        request = {'research_input_id': 'a' * 32, 'playbook_hypothesis': PROFILES[scope]['hypothesis'][0],
                   'playbook_explanation': name}
        assert name in build_argv(request, [], list(rows), ['hypothesis', 'report'])
    with pytest.raises(ValueError, match='Explanation skill does not match'):
        validate_skills({'report': PROFILES[wrong]['report']}, profile(scope))
    with pytest.raises(ValueError, match='Explanation skill does not match'):
        validate_skills({'report': reports}, profile(scope), knowledge_mode='llm_only')
