"""Corpus-specific experiment choices preserve historical instructions."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from memstara.control import catalog
from memstara.pipeline import prompts


def test_catalog_contains_both_corpus_profiles_and_general_choice(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    ids = {i['id'] for i in catalog.catalog() if i['stage'] == 'hypothesis'}
    assert ids == {'addiction-psychiatric', 'addiction-substance-use',
                   'hiv-okf-whole-graph', 'hiv-no-knowledge', 'hiv-medication-treatment-pathways',
                   'hiv-okf-whole-graph-v3',
                   'heart-failure-cardiovascular', 'heart-failure-metabolic-renal',
                   'heart-failure-lifestyle-social', 'heart-failure-all-categories', 'hypothesis_general'}
    for name in ids:
        catalog.validate_selection({'playbook_hypothesis': name})


def test_excluded_hiv_files_are_hidden_but_historically_resolvable(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    visible = {item['id'] for item in catalog.catalog()}
    for name in ('hiv-psychiatric-or-substance-use', 'addiction-sdoh', 'hiv-clinical-frailty'):
        assert name not in visible
        assert catalog.resolve(name)['content'].strip()
        assert prompts.load_prompt('board/hypothesis', name)['system_prompt']


@pytest.mark.parametrize('name', sorted(prompts.DISABLED_HYPOTHESIS_SKILLS))
def test_disabled_skills_preserve_files_and_historical_loading(name, monkeypatch):
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    path = prompts.PLAYBOOKS_DIR / (name + '.md')
    before = path.read_bytes()
    assert catalog.resolve(name)['stage'] == 'hypothesis'
    assert prompts.load_prompt('board/hypothesis', name)['system_prompt']
    with pytest.raises(ValueError, match='disabled for execution'):
        catalog.validate_selection({'playbook_hypothesis': name})
    assert path.read_bytes() == before


@pytest.mark.parametrize('combination', [False, True])
def test_disabled_hypothesis_cannot_reach_execution(tmp_path, combination):
    from memstara.pipeline.board import run
    args = SimpleNamespace(playbook_hypothesis='' if combination else 'hypothesis_research',
                           combination_plan=json.dumps({'skills': {'hypothesis': [{'id': 'hypothesis_research'}]}})
                           if combination else '')
    with pytest.raises(ValueError, match='disabled for execution'):
        asyncio.run(run(args, tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_hiv_menu_offers_v3_alongside_existing_approved_skills(tmp_path, monkeypatch):
    from memstara import corpus_skills, research_inputs
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    monkeypatch.setattr(research_inputs, 'visible_inputs', lambda: [])
    expected = ['addiction-psychiatric', 'addiction-substance-use', 'hiv-okf-whole-graph',
                'hiv-no-knowledge', 'hiv-medication-treatment-pathways', 'hiv-okf-whole-graph-v3']
    offered = corpus_skills.menu_bindings()['profiles']['hiv']['hypothesis']
    assert offered == expected
    visible = {item['id']: item for item in catalog.catalog()}
    for name in offered:
        assert visible[name]['stage'] == 'hypothesis'
        catalog.validate_new_design({'playbook_hypothesis': name})
    catalog.validate_new_design({'combination_skills': {'hypothesis': expected}})
    profile = {'configuration': {}, 'knowledge': {'hashes': {'index.md': next(
        key for key, scope in corpus_skills.INDEX_PROFILES.items() if scope == 'hiv')}}}
    corpus_skills.validate_hypotheses({'hypothesis': expected}, profile)


def test_v3_is_separate_and_does_not_replace_frozen_v2(monkeypatch):
    from memstara import evaluation

    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    v2 = catalog.resolve('hiv-okf-whole-graph')
    v3 = catalog.resolve('hiv-okf-whole-graph-v3')
    assert v2['title'] == 'HIV — Whole Knowledge Graph (V2)'
    assert v3['title'] == 'HIV — Whole Knowledge Graph: Integrated Predictors (V3)'
    assert v2['hash'] != v3['hash']
    prompt = prompts.load_prompt('board/hypothesis', v3['id'])
    assert v3['content'].strip() in prompt['system_prompt']
    frozen = {'goal': 'Original saved goal', 'system_prompt': 'Original saved V2 instructions'}
    monkeypatch.setattr(evaluation, 'active_plan', lambda: {
        'prompts': {'board/hypothesis:hiv-okf-whole-graph': frozen}})
    assert prompts.load_prompt('board/hypothesis', 'hiv-okf-whole-graph') == frozen


def test_registered_medication_skill_is_exactly_the_reviewed_document():
    reviewed = Path(__file__).resolve().parents[1] / 'docs/skill-drafts/hiv-medication-treatment-pathways-reviewed.md'
    registered = prompts.PLAYBOOKS_DIR / 'hiv-medication-treatment-pathways.md'
    assert registered.read_bytes() == reviewed.read_bytes()
    item = catalog.resolve('hiv-medication-treatment-pathways')
    assert item['title'] == 'HIV — Medication and Treatment Pathways'
    assert item['content'].strip() in prompts.load_prompt('board/hypothesis', item['id'])['system_prompt']


@pytest.mark.parametrize('name', sorted(prompts.RETIRED_HYPOTHESIS_SKILLS))
def test_retired_hiv_choices_preserve_history_but_reject_new_designs(name, tmp_path, monkeypatch):
    from memstara import corpus_skills
    from memstara.control.workspace import PipelineWorkspace
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    original = (prompts.PLAYBOOKS_DIR / (name + '.md')).read_bytes()
    assert name not in prompts.playbook_names()
    assert name not in {item['id'] for item in catalog.catalog()}
    assert catalog.resolve(name)['content']
    assert prompts.load_prompt('board/hypothesis', name)['system_prompt']
    # Reading and resuming frozen designs retains compatibility.
    catalog.validate_selection({'playbook_hypothesis': name})
    profile = {'configuration': {}, 'knowledge': {'hashes': {'index.md': next(
        key for key, scope in corpus_skills.INDEX_PROFILES.items() if scope == 'hiv')}}}
    corpus_skills.validate_hypotheses({'hypothesis': [name]}, profile)
    loaded, error = PipelineWorkspace.read_configuration({'playbook_hypothesis': name})
    assert error is None and loaded['playbook_hypothesis'] == name
    for body in ({'playbook_hypothesis': name}, {'combination_skills': {'hypothesis': [name]}}):
        with pytest.raises(ValueError, match='unavailable for new designs'):
            catalog.validate_new_design(body)
    alias = tmp_path / 'aliases.json'
    alias.write_text(json.dumps({'old-hybrid': name}))
    monkeypatch.setenv('MEMSTARA_SKILL_ALIASES_PATH', str(alias))
    with pytest.raises(ValueError, match='unavailable for new designs'):
        catalog.validate_new_design({'playbook_hypothesis': 'old-hybrid'})
    assert (prompts.PLAYBOOKS_DIR / (name + '.md')).read_bytes() == original
