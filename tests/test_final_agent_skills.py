"""Final-stage instructions support supplied and registered custom skills."""
import pytest
from memstara.control import catalog
from memstara.pipeline.prompts import load_prompt


@pytest.mark.parametrize('role,book', [
    ('interpreter', 'shared-shap'),
    ('interpreter', 'shared-lime'),
    ('report', 'shared-heart-failure-cardiovascular'),
    ('report', 'shared-heart-failure-comorbidity'),
])
def test_current_skill_is_selectable_and_reaches_prompt(role, book, monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    item = catalog.resolve(book)
    assert item['stage'] == role
    catalog.validate_selection({f'playbook_{role}': book})
    assert item['content'] in load_prompt(f'board/{role}', book)['system_prompt']


@pytest.mark.parametrize('role', ['interpreter', 'report'])
def test_custom_final_stage_skills_are_registered_and_selectable(role, tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, 'user_dir', lambda: tmp_path)
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    item = catalog.register({'stage': role, 'name': 'my-instructions',
                             'content': '# Custom instructions\nCUSTOM_EVIDENCE_SENTINEL'})
    catalog.validate_selection({f'playbook_{role}': item['id']})
    assert 'CUSTOM_EVIDENCE_SENTINEL' in load_prompt(f'board/{role}', item['id'])['system_prompt']
    assert list(tmp_path.glob('*.json'))


@pytest.mark.parametrize('book', ['shared-shap', 'shared-lime'])
def test_interpreter_adds_transport_only_to_selected_skill(monkeypatch, book):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    content = catalog.resolve(book)['content']
    text = load_prompt('board/interpreter', book)['system_prompt']
    assert content in text
    wrapper = text.replace(content, '')
    assert 'submit_result' in wrapper
    assert 'complete Markdown output' in wrapper
    for instruction in ('Observed findings', 'Mandatory role boundary',
                        'Final evidence check', 'clinician-readable',
                        'takes precedence over attached skills', 'AUC'):
        assert instruction not in wrapper


def test_retired_explanation_skill_cannot_start_execution(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    with pytest.raises(ValueError, match='disabled for new execution'):
        catalog.validate_selection({'playbook_report': 'report_clinical_explanations'})
