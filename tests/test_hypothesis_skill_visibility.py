"""Corpus-specific experiment choices preserve historical instructions."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from memstara.control import catalog
from memstara.pipeline import prompts


def test_catalog_contains_both_corpus_profiles_and_general_choice(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    ids = {i['id'] for i in catalog.catalog() if i['stage'] == 'hypothesis'}
    assert ids == {'addiction-sdoh', 'hiv-psychiatric-or-substance-use',
                   'hiv-okf-whole-graph', 'hiv-no-knowledge',
                   'heart-failure-cardiovascular', 'heart-failure-metabolic-renal',
                   'heart-failure-lifestyle-social', 'heart-failure-all-categories', 'hypothesis_general'}
    for name in ids:
        catalog.validate_selection({'playbook_hypothesis': name})


def test_superseded_hiv_domain_files_are_hidden_but_historically_resolvable(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    visible = {item['id'] for item in catalog.catalog()}
    for name in ('addiction-psychiatric', 'addiction-substance-use'):
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
