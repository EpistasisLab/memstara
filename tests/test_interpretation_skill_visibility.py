"""Hiding built-in alternatives must not change historical prompt loading."""
import pytest
from memstara.control import catalog
from memstara.pipeline import prompts


def test_only_current_anil_interpretation_choices_visible(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path / 'users'))
    monkeypatch.setattr(catalog, 'specialist_dir', lambda: tmp_path)
    for name in ('SHAP-Interpretation.md', 'LIME-Interpretation.md'):
        (tmp_path / name).write_text('# Synthetic shared skill\nRead both models.')
    assert {x['id'] for x in catalog.catalog() if x['stage'] == 'interpreter'} == {
        'shared-shap', 'shared-lime'}
    assert not prompts.HIDDEN_PLAYBOOKS.intersection(prompts.playbook_names())


@pytest.mark.parametrize('name', sorted(n for n in prompts.HIDDEN_PLAYBOOKS if n.startswith('interpreter_')))
def test_hidden_skills_still_resolve_and_load_without_changing_file(name, monkeypatch):
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    path = prompts.PLAYBOOKS_DIR / (name + '.md')
    original = path.read_bytes()
    item = catalog.resolve(name)
    assert item['stage'] == 'interpreter'
    assert item['content'] in prompts.load_prompt('board/interpreter', name)['system_prompt']
    catalog.validate_selection({'playbook_interpreter': name})
    assert path.read_bytes() == original
