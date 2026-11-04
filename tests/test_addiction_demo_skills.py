"""Offline catalog-to-agent wiring; no paid model execution."""
import pytest

from memstara.control.catalog import catalog, validate_selection
from memstara.pipeline.prompts import load_prompt

SKILLS = ['hiv-psychiatric-or-substance-use', 'addiction-sdoh', 'hiv-clinical-frailty',
          'hiv-okf-whole-graph', 'hiv-no-knowledge']


@pytest.mark.parametrize('name', SKILLS)
def test_demo_skill_can_be_selected_and_reaches_hypothesis_prompt(name, tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    item = next(item for item in catalog() if item['id'] == name)
    assert item['stage'] == 'hypothesis'
    validate_selection({'hypothesis_agents': 1, 'trials': 1, 'playbook_hypothesis': name})
    prompt = load_prompt('board/hypothesis', playbook=name)
    assert item['content'].strip() in prompt['system_prompt']
    assert '{{playbook}}' not in prompt['system_prompt']


def test_five_hiv_focuses_are_distinct_valid_selections(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    items = [item for item in catalog() if item['id'] in SKILLS]
    assert len({item['hash'] for item in items}) == 5
    validate_selection({'hypothesis_agents': 5, 'trials': 5,
                        'playbook_hypothesis': ','.join(SKILLS)})


def test_h1_is_or_scope_and_h0_is_knowledge_free(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    h1 = next(item for item in catalog() if item['id'] == 'hiv-psychiatric-or-substance-use')['content']
    h0 = next(item for item in catalog() if item['id'] == 'hiv-no-knowledge')['content']
    assert 'OR, not required co-occurrence' in h1
    assert 'Do not require both to be present' in h1
    assert 'Do not search, read or cite OKF' in ' '.join(h0.split())
