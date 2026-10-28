"""Web model restrictions must reject requests before network or disk side effects."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from memstara.control import model_policy, service


def handler(path, body):
    result = object.__new__(service.Handler)
    result.path = path
    result._refuse_stranger = lambda: False
    result._body = lambda: body
    result._send = Mock()
    return result


@pytest.mark.parametrize('provider', ['openai', 'anthropic', 'bedrock', 'local', 'openrouter', None])
@pytest.mark.parametrize('route', ['check', 'models'])
def test_other_providers_never_reach_model_services(monkeypatch, provider, route):
    from memstara import model_catalog, model_connections
    probe, listing = Mock(), Mock()
    monkeypatch.setattr(model_connections, 'check_and_save', probe)
    monkeypatch.setattr(model_catalog, 'list_provider_models', listing)
    request = handler(f'/control/model-connections/{route}', {'provider': provider})
    request.do_POST()
    assert request._send.call_args.args == (400, {'error': model_policy.MESSAGE})
    probe.assert_not_called()
    listing.assert_not_called()


def test_azure_connection_is_checked_normally(monkeypatch):
    from memstara import model_connections
    check = Mock(return_value={'id': 'checked'})
    monkeypatch.setattr(model_connections, 'check_and_save', check)
    body = {'provider': 'azure_foundry', 'model': 'deployment'}
    request = handler('/control/model-connections/check', body)
    request.do_POST()
    check.assert_called_once_with(body)
    assert request._send.call_args.args == (201, {'connection': {'id': 'checked'}})


def test_catalog_only_exposes_azure_foundry(monkeypatch):
    from memstara import model_catalog
    monkeypatch.setattr(model_catalog, 'catalog', lambda: {'providers': [
        {'id': 'openai'}, {'id': 'azure_foundry'}, {'id': 'anthropic'}]})
    request = handler('/control/model-catalog', {})
    request.do_GET()
    assert request._send.call_args.args == (200, {'providers': [{'id': 'azure_foundry'}]})


def test_capabilities_reject_disallowed_provider():
    request = handler('/control/model-capabilities?provider=openai&model=test', {})
    request.do_GET()
    assert request._send.call_args.args == (400, {'error': model_policy.MESSAGE})


@pytest.mark.parametrize('profiles,allowed', [([], False),
    ([{'provider': 'azure_foundry'}], True),
    ([{'provider': 'azure_foundry'}, {'provider': 'openai'}], False)])
def test_defaults_cannot_hide_disallowed_agent_assignment(profiles, allowed):
    result = model_policy.defaults_view({'profiles': profiles, 'source': 'project_env'})
    assert result['current_allowed'] is allowed
    assert all(p['provider'] == 'azure_foundry' for p in result['profiles'])


@pytest.mark.parametrize('action', ['add', 'update'])
@pytest.mark.parametrize('configuration', [
    {'provider': 'openai'}, {'stage_models': {'ml': {'provider': 'anthropic'}}},
    {'stage_models': {'ml': 'invalid'}}, {'model_connection_id': 'old-connection'}])
def test_pipeline_rejects_disallowed_configuration_before_save(monkeypatch, action, configuration):
    from memstara import model_connections
    monkeypatch.setattr(model_connections, 'load', lambda _: {'connection': {'provider': 'openai'}})
    mutate = Mock()
    monkeypatch.setattr(service, 'WORKSPACE', SimpleNamespace(mutate=mutate))
    request = handler('/control/pipelines', {'action': action, 'configuration': configuration})
    request.do_POST()
    assert request._send.call_args.args == (409, {'error': model_policy.MESSAGE})
    mutate.assert_not_called()


def test_saved_azure_connection_overrides_disallowed_server_defaults(monkeypatch):
    from memstara import model_connections, stage_models
    monkeypatch.setattr(stage_models, 'deployment_profiles', lambda: {'ml': {'provider': 'openai'}})
    with pytest.raises(ValueError, match='Only Azure Foundry'):
        model_policy.require_selection({}, use_defaults=True)
    monkeypatch.setattr(model_connections, 'load', lambda _: {'connection': {'provider': 'azure_foundry'}})
    model_policy.require_selection({'model_connection_id': 'checked'}, use_defaults=True)


def test_launch_rejects_disallowed_defaults_before_creating_run(monkeypatch):
    from memstara import operational, stage_models
    monkeypatch.setattr(stage_models, 'deployment_profiles', lambda: {'ml': {'provider': 'openai'}})
    monkeypatch.setattr(service, 'playbooks', lambda: {'playbooks': [], 'stages': []})
    monkeypatch.setattr(service, 'build_argv', lambda *args: [])
    monkeypatch.setattr(service, 'validate_selection', lambda _: None)
    check, create, start = Mock(), Mock(), Mock()
    monkeypatch.setattr(operational, 'check', check)
    monkeypatch.setattr(service, 'new_run_dir', create)
    request = handler('', {})
    request._launch({'knowledge_mode': 'llm_only', 'data_mode': 'proposal'}, SimpleNamespace(start=start))
    assert request._send.call_args.args[0] == 422
    assert 'Only Azure Foundry' in request._send.call_args.args[1]['error']
    for effect in (check, create, start):
        effect.assert_not_called()


def test_skill_draft_cannot_use_disallowed_provider(monkeypatch):
    from memstara import operational
    from memstara.control import skill_drafts
    start = Mock()
    monkeypatch.setattr(skill_drafts, 'start', start)
    monkeypatch.setattr(operational, 'agent_profile', lambda _: {'provider': 'openai'})
    request = handler('/control/skill-drafts', {'stage': 'hypothesis'})
    request.do_POST()
    assert request._send.call_args.args[0] == 400
    start.assert_not_called()
