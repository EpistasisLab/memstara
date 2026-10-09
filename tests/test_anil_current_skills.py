"""Shared specialist skills are exact current files, never archived substitutes."""
import pytest
from memstara.control import catalog
from memstara.pipeline.prompts import load_prompt


@pytest.fixture
def current(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, 'anil_dir', lambda: tmp_path)
    monkeypatch.setattr(catalog, 'user_dir', lambda: tmp_path / 'users')
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    (tmp_path / 'old').mkdir()
    for key, (filename, _, _) in catalog.ANIL_SKILLS.items():
        (tmp_path / filename).write_text(f'# Current skill\nCURRENT_{key}\n')
        (tmp_path / 'old' / filename).write_text('ARCHIVE_MUST_NOT_LOAD')
    return tmp_path


def test_four_distinct_skills_load_into_intended_prompts(current):
    items = catalog.anil_skills()
    assert len(items) == 4
    assert len({item['title'] for item in items}) == 4
    for item in items:
        prompt = load_prompt(f"board/{item['stage']}", item['id'])['system_prompt']
        assert f"CURRENT_{item['id']}" in prompt
        assert 'ARCHIVE_MUST_NOT_LOAD' not in prompt
        assert len(item['source_hash']) == 64
        wrong = 'report' if item['stage'] == 'interpreter' else 'interpreter'
        with pytest.raises(ValueError):
            load_prompt(f'board/{wrong}', item['id'])


def test_missing_current_file_never_falls_back_to_old(current):
    (current / 'SHAP-Interpretation.md').unlink()
    with pytest.raises(FileNotFoundError, match='no archive fallback'):
        catalog.resolve('shared-anil-shap')


def test_archive_symlink_is_rejected(current):
    p = current / 'SHAP-Interpretation.md'
    p.unlink()
    p.symlink_to(current / 'old' / p.name)
    with pytest.raises(ValueError, match='archive links'):
        catalog.anil_skills()


def test_source_edit_changes_provenance(current):
    before = catalog.resolve('shared-anil-shap')
    (current / 'SHAP-Interpretation.md').write_text('# Revised current instructions')
    after = catalog.resolve('shared-anil-shap')
    assert before['hash'] != after['hash']
    assert before['source_hash'] != after['source_hash']
