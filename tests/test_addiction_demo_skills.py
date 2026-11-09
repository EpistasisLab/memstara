"""Offline catalog-to-agent wiring; no paid model execution."""
import pytest

from memstara.control.catalog import catalog, validate_selection
from memstara.pipeline.prompts import load_prompt

SKILLS = ['addiction-psychiatric', 'addiction-substance-use',
          'hiv-okf-whole-graph', 'hiv-no-knowledge', 'hiv-medication-treatment-pathways',
          'hiv-okf-whole-graph-v3']


@pytest.mark.parametrize('name', SKILLS)
def test_demo_skill_can_be_selected_and_reaches_hypothesis_prompt(name, tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    item = next(item for item in catalog() if item['id'] == name)
    assert item['stage'] == 'hypothesis'
    validate_selection({'hypothesis_agents': 1, 'trials': 1, 'playbook_hypothesis': name})
    prompt = load_prompt('board/hypothesis', playbook=name)
    assert item['content'].strip() in prompt['system_prompt']
    assert '{{playbook}}' not in prompt['system_prompt']


def test_hiv_focuses_are_distinct_valid_selections(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    items = [item for item in catalog() if item['id'] in SKILLS]
    assert len({item['hash'] for item in items}) == len(SKILLS)
    validate_selection({'hypothesis_agents': len(SKILLS), 'trials': len(SKILLS),
                        'playbook_hypothesis': ','.join(SKILLS)})


def test_separate_domains_and_knowledge_free_control(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    psychiatric = next(item for item in catalog() if item['id'] == 'addiction-psychiatric')['content']
    substance = next(item for item in catalog() if item['id'] == 'addiction-substance-use')['content']
    h0 = next(item for item in catalog() if item['id'] == 'hiv-no-knowledge')['content']
    assert 'Focus on psychiatric disorders' in psychiatric
    assert 'Focus on substance use disorders' in substance
    assert 'Do not look for, request or use any other source of information' in ' '.join(h0.split())
