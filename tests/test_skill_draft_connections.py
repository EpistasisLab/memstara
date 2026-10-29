"""AI drafts use the checked GUI model even with blank deployment defaults."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from memstara import model_connections as connections
from memstara.control import skill_drafts as drafts


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.delenv('MOTORO_ENCRYPTION_KEY', raising=False)
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', '')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', '')
    monkeypatch.setattr(connections, 'probe', lambda data: None)
    monkeypatch.setattr(drafts, '_jobs', {})
    return tmp_path


def save(model='selected-deployment'):
    return connections.check_and_save({'provider': 'azure_foundry', 'model': model,
        'api_base': 'https://example.services.ai.azure.com/anthropic',
        'api_key': 'synthetic-private-key'}, make_default=True)


def body(stage='hypothesis', **extra):
    return dict(stage=stage, domain='General', population='Adults', features='Age',
                constraints='None', model='selected-deployment', **extra)


@pytest.mark.parametrize('stage', ['hypothesis', 'data', 'ml'])
def test_checked_model_pinned_until_worker_finishes(store, monkeypatch, stage):
    first = save()
    listed = drafts.models()
    assert listed['model_connection_id'] == first['id']
    assert listed['agents'][stage]['model'] == 'selected-deployment'
    thread = Mock()
    monkeypatch.setattr(drafts.threading, 'Thread', thread)
    job = drafts.start(body(stage, model_connection_id=first['id']))
    pinned = thread.call_args.kwargs['args'][1]
    save('different-default')
    assert drafts.models()['agents'][stage]['model'] == 'different-default'
    assert drafts.models(first['id'])['agents'][stage]['model'] == 'selected-deployment'
    captured = {}
    def run(argv, **kw):
        captured.update(kw)
        assert 'synthetic-private-key' not in json.dumps(argv) + kw['input']
        from memstara.operational import agent_profile
        assert agent_profile(stage, kw['env'])['model'] == 'selected-deployment'
        assert kw['env']['MEMSTARA_AZURE_FOUNDRY_API_KEY'] == 'synthetic-private-key'
        return SimpleNamespace(returncode=0, stdout='SKILL_DRAFT:' + json.dumps({
            'stage': stage, 'content': '# Reviewable instructions', 'model': 'selected-deployment',
            **({'base_skill': pinned['base_skill']} if 'base_skill' in pinned else {})}))
    monkeypatch.setattr(drafts.subprocess, 'run', run)
    drafts._generate(job['id'], pinned)
    result = drafts.get(job['id'])
    assert result['status'] == 'ready'
    assert captured['env']['MEMSTARA_CONFIG_MODE'] == 'environment'
    assert 'synthetic-private-key' not in json.dumps(result)
    assert not list(store.glob('skills/*'))


def test_missing_pinned_connection_never_falls_back(store, monkeypatch):
    first = save()
    save('different-default')
    (store / 'private-model-connections' / (first['id'] + '.enc')).unlink()
    worker = Mock()
    monkeypatch.setattr(drafts.threading, 'Thread', worker)
    with pytest.raises(ValueError):
        drafts.start(body(model_connection_id=first['id']))
    worker.assert_not_called()


@pytest.mark.parametrize('stage', ['interpreter', 'report', 'explanation'])
def test_final_roles_use_checked_model(store, monkeypatch, stage):
    connection = save()
    thread = Mock()
    monkeypatch.setattr(drafts.threading, 'Thread', thread)
    drafts.start(body(stage, model_connection_id=connection['id']))
    request = thread.call_args.kwargs['args'][1]
    assert request['stage'] == ('report' if stage == 'explanation' else stage)
    assert request['model_connection_id'] == connection['id']
    assert request['model'] == 'selected-deployment'


def test_endpoint_uses_explicit_connection_and_reports_setup_errors(store):
    from memstara.control.service import Handler
    first = save()
    save('different-default')
    handler = object.__new__(Handler)
    handler._refuse_stranger = lambda: False
    handler._send = Mock()
    handler.path = '/control/skill-drafts/models?model_connection_id=' + first['id']
    handler.do_GET()
    code, data = handler._send.call_args.args
    assert code == 200 and data['agents']['ml']['model'] == 'selected-deployment'
    handler.path = '/control/skill-drafts/models?model_connection_id=invalid'
    handler.do_GET()
    assert handler._send.call_args.args[0] == 400
