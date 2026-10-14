"""Final-stage skills resolve to the intended roles and accept custom instructions."""
import pytest
from memstara.control import catalog
from memstara.pipeline.prompts import load_prompt


@pytest.mark.parametrize('role,book', [
    ('interpreter', 'shared-anil-shap'),
    ('interpreter', 'shared-anil-lime'),
    ('report', 'shared-anil-addiction'),
    ('report', 'shared-anil-hiv'),
])
def test_current_skill_is_selectable_and_reaches_prompt(role, book, monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    item = catalog.resolve(book)
    assert item['stage'] == role
    catalog.validate_selection({f'playbook_{role}': book})
    assert item['content'] in load_prompt(f'board/{role}', book)['system_prompt']


@pytest.mark.parametrize('role', ['interpreter', 'report'])
def test_custom_skill_roundtrip_for_both_roles(role, tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, 'user_dir', lambda: tmp_path)
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    saved = catalog.register({'stage': role, 'name': 'my-instructions',
                              'content': '# Custom instructions\nCUSTOM_EVIDENCE_SENTINEL'})
    catalog.validate_selection({f'playbook_{role}': saved['id']})
    assert 'CUSTOM_EVIDENCE_SENTINEL' in load_prompt(f'board/{role}', saved['id'])['system_prompt']
    other = 'report' if role == 'interpreter' else 'interpreter'
    with pytest.raises(ValueError):
        catalog.validate_selection({f'playbook_{other}': saved['id']})


def test_interpreter_no_longer_requires_recommendations(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    text = load_prompt('board/interpreter', 'interpreter_factual_observations')['system_prompt']
    assert '**Research opportunity:**' not in text
    assert '**Actionability and threshold:**' not in text
    assert 'This boundary takes precedence over attached skills requesting recommendations.' in text


def test_retired_explanation_skill_cannot_start_execution(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    with pytest.raises(ValueError, match='disabled for execution'):
        catalog.validate_selection({'playbook_report': 'report_clinical_explanations'})
