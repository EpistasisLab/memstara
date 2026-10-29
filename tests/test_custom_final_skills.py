"""Custom final-stage skills are persisted, role-checked and loaded verbatim."""
import pytest
from memstara.control import catalog
from memstara.pipeline.prompts import load_prompt
from memstara.corpus_skills import validate_hypotheses


@pytest.mark.parametrize('stage,field', [('interpreter', 'playbook_interpreter'), ('report', 'playbook_explanation')])
def test_custom_final_skill_execution_contract(tmp_path, monkeypatch, stage, field):
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    content = f'# Custom {stage}\nDescribe the measured findings and their limitations.'
    item = catalog.register({'stage': stage, 'name': 'uploaded', 'content': content})
    assert item in catalog.catalog()
    assert catalog.resolve(item['id']) == item
    catalog.validate_new_design({'combination_skills': {stage: [item['id']]}})
    catalog.validate_selection({field: item['id']})
    validate_hypotheses({stage: [item['id']]}, knowledge_mode='llm_only')
    assert content in load_prompt(f'board/{stage}', item['id'])['system_prompt']
    other_field = 'playbook_explanation' if stage == 'interpreter' else 'playbook_interpreter'
    with pytest.raises(ValueError):
        catalog.validate_selection({other_field: item['id']})
    with pytest.raises(ValueError):
        catalog.validate_selection({field: f'user-{stage}-not-registered'})
    # Registration never edits an existing saved version.
    changed = catalog.register({'stage': stage, 'name': 'uploaded', 'content': content + '\nNew instruction.'})
    assert changed['id'] != item['id']
    assert catalog.resolve(item['id'])['content'] == content
