"""Offline catalog-to-agent wiring; no paid model execution."""
import pytest

from memstara.control.catalog import catalog, validate_selection
from memstara.pipeline.prompts import load_prompt

SKILLS = ['addiction-substance-use', 'addiction-sdoh', 'addiction-psychiatric']


@pytest.mark.parametrize('name', SKILLS)
def test_demo_skill_can_be_selected_and_reaches_hypothesis_prompt(name, tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    item = next(item for item in catalog() if item['id'] == name)
    assert item['stage'] == 'hypothesis'
    validate_selection({'hypothesis_agents': 1, 'trials': 1, 'playbook_hypothesis': name})
    prompt = load_prompt('board/hypothesis', playbook=name)
    assert item['content'].strip() in prompt['system_prompt']
    assert '{{playbook}}' not in prompt['system_prompt']


def test_three_demo_focuses_are_distinct_valid_selections(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    items = [item for item in catalog() if item['id'] in SKILLS]
    assert len({item['hash'] for item in items}) == 3
    validate_selection({'hypothesis_agents': 3, 'trials': 3,
                        'playbook_hypothesis': ','.join(SKILLS)})
