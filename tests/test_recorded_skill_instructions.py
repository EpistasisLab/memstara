import json
from types import SimpleNamespace

import pytest

from memstara.control.skill_instructions import recorded_instructions
from test_control_query_routes import request


@pytest.fixture
def snapshot(tmp_path):
    stages = ['hypothesis', 'data', 'ml', 'interpreter', 'report']
    state = {'run_tag': 'saved-run', 'combination_plan': {'skills': {
        stage: [{'id': stage + '-skill', 'title': stage, 'hash': 'old-hash'}] for stage in stages}},
        'prompts': {f'board/{stage}:{stage}-skill': {'system_prompt': f'ORIGINAL {stage} instructions', 'goal': 'Saved goal'}
                    for stage in stages}, 'private_settings': 'MUST_NOT_BE_RETURNED'}
    (tmp_path / 'config.json').write_text(json.dumps(state))
    return tmp_path


@pytest.mark.parametrize('stage', ['hypothesis', 'data', 'ml', 'interpreter', 'report'])
def test_all_roles_read_frozen_instructions_without_current_library(snapshot, stage, monkeypatch):
    from memstara.control import catalog, service
    monkeypatch.setattr(catalog, 'resolve', lambda *args: pytest.fail('Must not substitute current instructions'))
    monkeypatch.setattr(service, 'RUNS', SimpleNamespace(locate=lambda tag: ('saved-run', snapshot)))
    status, result = request(service, f'/control/runs/saved-run/skill-instructions?stage={stage}&skill={stage}-skill&hash=old-hash')
    assert status == 200
    assert result['content'] == f'ORIGINAL {stage} instructions'
    assert result['run_tag'] == 'saved-run' and result['hash'] == 'old-hash'
    assert len(result['prompt_hash']) == 64
    assert 'MUST_NOT_BE_RETURNED' not in json.dumps(result)


@pytest.mark.parametrize('tag,stage,skill,version', [
    ('wrong-run', 'ml', 'ml-skill', 'old-hash'),
    ('saved-run', '../ml', 'ml-skill', 'old-hash'),
    ('saved-run', 'ml', 'ml-skill', 'new-hash'),
])
def test_wrong_identity_rejected(snapshot, tag, stage, skill, version):
    with pytest.raises(ValueError):
        recorded_instructions(snapshot, tag, stage, skill, version)


def test_missing_recorded_prompt_never_falls_back(snapshot):
    with pytest.raises(FileNotFoundError):
        recorded_instructions(snapshot, 'saved-run', 'interpreter', 'other-skill')


def test_unknown_run_returns_not_found(monkeypatch):
    from memstara.control import service
    monkeypatch.setattr(service, 'RUNS', SimpleNamespace(locate=lambda tag: None))
    assert request(service, '/control/runs/missing/skill-instructions?stage=ml&skill=ml-skill')[0] == 404
