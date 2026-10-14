"""New designs use current server models; saved designs remain reproducible."""
import json

import pytest

from memstara.control.workspace import PipelineWorkspace


def profiles(model):
    return {role: {'provider': 'azure_foundry', 'model': model}
            for role in ('non_explanation_agents', 'explanation_agent')}


class Idle:
    def __init__(self, key):
        pass

    def running(self):
        return None


@pytest.mark.parametrize('legacy', [False, True])
def test_new_design_discards_copied_models_but_preserves_research(tmp_path, monkeypatch, legacy):
    path = tmp_path / 'models.json'
    path.write_text(json.dumps(profiles('claude-haiku-5-5')))
    monkeypatch.setenv('MEMSTARA_STAGE_MODELS_PATH', str(path))
    workspace = PipelineWorkspace(tmp_path / 'workspace.json', Idle)
    old = profiles('claude-sonnet-5')
    if legacy:
        old = dict(zip(('qwen', 'sonnet'), old.values(), strict=True))
    request = {'waves': 4, 'provider': 'openai', 'model': 'qwen--qwen38-27b', 'stage_models': old}
    added = workspace.mutate({'action': 'add', 'configuration': request})
    assert added['configuration']['stage_models'] == {}
    assert added['configuration']['provider'] == added['configuration']['model'] == ''
    assert added['configuration']['waves'] == 4
    assert request['model'] == 'qwen--qwen38-27b'
    restored = PipelineWorkspace(workspace.path, Idle)
    assert restored.items[0]['configuration']['stage_models'] == {}
    # Existing explicit profiles are preserved for review, not silently changed.
    updated = restored.mutate({'action': 'update', 'id': added['id'],
                              'configuration': {**added['configuration'], 'stage_models': profiles('custom-model')}})
    assert updated['configuration']['stage_models'] == profiles('custom-model')


def test_invalid_defaults_do_not_fall_back_to_copied_models(tmp_path, monkeypatch):
    path = tmp_path / 'models.json'
    path.write_text('broken')
    monkeypatch.setenv('MEMSTARA_STAGE_MODELS_PATH', str(path))
    workspace = PipelineWorkspace(tmp_path / 'workspace.json', Idle)
    item = workspace.mutate({'action': 'add', 'configuration': {'stage_models': profiles('old')}})
    assert item['configuration']['stage_models'] == {}
    assert workspace.path.exists()
