"""Extraction is common behavior; only allocation strategies are menu choices."""
import hashlib

from memstara.control.catalog import catalog, resolve, validate_selection
from memstara.pipeline.prompts import load_prompt, playbook_names


def test_catalog_contains_two_data_skills_and_manual_split_contract(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    assert {x['id'] for x in catalog() if x['stage'] == 'data'} == {
        'data_training_heavy', 'data_balanced_stratified', 'data_manual_split'}
    assert 'data_exact_features' not in playbook_names()


def test_exact_extraction_contract_applies_without_a_selectable_skill(monkeypatch):
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    for skill in ('', 'data_training_heavy', 'data_balanced_stratified', 'data_manual_split'):
        body = load_prompt('board/data', skill)['system_prompt']
        assert 'Use slice_columns to cut out exactly those columns plus that outcome' in body
        assert 'Do not add columns' in body
        assert 'Do not drop columns' in body
        assert 'Do not preprocess' in body
        assert 'REPORT THAT FACT in submit_result' in body
        assert 'Pass the file path produced' in body


def test_legacy_data_configuration_still_resolves_without_entering_menu(monkeypatch):
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    assert resolve('data_exact_features')['stage'] == 'data'
    validate_selection({'playbook_data': 'data_exact_features'})
    from memstara.paths import PLAYBOOKS_DIR
    before = (PLAYBOOKS_DIR / 'legacy/data_exact_features.md').read_text()
    assert hashlib.sha256(before.encode()).hexdigest() == (
        'c095690ff37a912135b4c74510fb3ebcd96d9e525de47c35e1d782d690daf805')
    assert before.strip() in load_prompt('board/data', 'data_exact_features')['system_prompt']
