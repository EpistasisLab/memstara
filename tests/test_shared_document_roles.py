"""Shared reference documents must never masquerade as selectable skills."""
import pytest

from memstara.control import catalog
from memstara.pipeline.prompts import load_prompt


@pytest.fixture
def shared(monkeypatch, tmp_path):
    monkeypatch.setenv('MEMSTARA_SHARED_SKILLS_DIR', str(tmp_path))
    monkeypatch.delenv('MEMSTARA_RESULTS_SKILL_PATH', raising=False)
    monkeypatch.delenv('MEMSTARA_ML_REFERENCE_PATH', raising=False)
    monkeypatch.setenv('MEMSTARA_SKILL_ALIASES_PATH', str(tmp_path / 'aliases.json'))
    monkeypatch.setattr(catalog, 'user_dir', lambda: tmp_path / 'user')
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    (tmp_path / 'ml-results.md').write_text('---\nname: ml-skill\n---\n# ML Results Presenter\nPresent results.')
    (tmp_path / 'ml-reference.md').write_text(
        '---\nformat: OKF\n---\n# Practical Machine Learning\nREFERENCE_SENTINEL')
    return tmp_path


def test_roles_and_original_files(shared):
    before = {p.name: p.read_bytes() for p in shared.glob('*.md')}
    assert catalog.resolve('shared-ml-results')['stage'] == 'report'
    assert not catalog.resolve('shared-ml-reference')
    assert catalog.reference_knowledge()[0]['kind'] == 'reference'
    assert {p.name: p.read_bytes() for p in shared.glob('*.md')} == before


def test_reference_is_additive_and_only_for_ml(shared):
    prompt = load_prompt('board/ml', 'ml_governance')['system_prompt']
    assert 'REFERENCE_SENTINEL' in prompt
    assert catalog.resolve('ml_governance')['content'] in prompt
    report = load_prompt('board/report', 'shared-ml-results')['system_prompt']
    assert 'Present results.' in report
    assert 'REFERENCE_SENTINEL' not in report
    assert 'REFERENCE_SENTINEL' not in load_prompt('board/hypothesis')['system_prompt']


@pytest.mark.parametrize('book', ['shared-ml-results', 'shared-ml-reference'])
def test_wrong_ml_role_rejected_in_api_and_cli(shared, book):
    with pytest.raises(ValueError):
        catalog.validate_selection({'playbook_ml': book})
    with pytest.raises(ValueError):
        load_prompt('board/ml', book)


def test_frozen_historical_prompt_preserved(shared, monkeypatch):
    frozen = {'goal': 'original', 'system_prompt': 'unchanged original'}
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {
        'prompts': {'board/ml:shared-ml-reference': frozen}})
    assert load_prompt('board/ml', 'shared-ml-reference') == frozen


def test_missing_optional_reference(shared):
    (shared / 'ml-reference.md').unlink()
    assert catalog.reference_knowledge() == []
    assert 'ML tool reference knowledge' not in load_prompt('board/ml')['system_prompt']


def test_deployment_alias_resolves_without_changing_saved_prompt(shared, monkeypatch):
    (shared / 'aliases.json').write_text('{"legacy-results": "shared-ml-results"}')
    assert catalog.resolve('legacy-results')['id'] == 'shared-ml-results'
    assert 'Present results.' in load_prompt('board/report', 'legacy-results')['system_prompt']
    frozen = {'goal': 'original', 'system_prompt': 'historical text'}
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {
        'prompts': {'board/report:legacy-results': frozen}})
    assert load_prompt('board/report', 'legacy-results') == frozen
