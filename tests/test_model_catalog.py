"""Motoro metadata must control both the GUI choices and actual frozen requests."""
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from memstara import model_catalog as catalog, model_connections as connections


def test_catalog_comes_from_installed_motoro():
    from motoro.schemas.agent import LLMProvider, ModelConfig
    from motoro.services.model_capabilities import CATALOG
    result = catalog.catalog()
    assert result['source'] == 'motoro'
    assert {row['id'] for row in result['providers']} == {p.value for p in LLMProvider}
    for entry in CATALOG:
        row = next(r for r in catalog.choices(entry.provider) if r['model'] == entry.model)
        assert row['capabilities'] == entry.capabilities.model_dump(mode='json')
    schema = ModelConfig.model_json_schema()
    if '$ref' in schema:
        schema = schema['$defs'][schema['$ref'].rsplit('/', 1)[-1]]
    assert result['controls']['max_tokens']['maximum'] == schema['properties']['max_tokens']['maximum']
    assert result['controls']['temperature'] == {'default': None, 'minimum': 0., 'maximum': 2.}


def test_nullable_capabilities_and_joint_sampling_follow_motoro():
    from motoro.services.model_capabilities import ModelCapabilities
    unknown = ModelCapabilities().model_dump(mode='json')
    assert catalog.validate_settings({'max_tokens': 4096}, unknown) == {'max_tokens': 4096}
    with pytest.raises(ValueError):
        catalog.validate_settings({'effort': 'high'}, unknown)
    caps = ModelCapabilities(supports_temperature=True, supports_effort=True,
                             effort_levels=['none', 'low', 'high'], default_effort='low',
                             temperature_effort_levels=['none']).model_dump(mode='json')
    assert catalog.validate_settings({'effort': 'none', 'temperature': .4}, caps)['temperature'] == .4
    assert catalog.validate_settings({'effort': 'high'}, caps) == {'effort': 'high'}
    with pytest.raises(ValueError):
        catalog.validate_settings({'effort': 'high', 'temperature': .4}, caps)
    caps.update(effort_levels=None, default_effort='high', temperature_effort_levels=None)
    assert catalog.validate_settings({'effort': 'high'}, caps) == {'effort': 'high'}
    with pytest.raises(ValueError):
        catalog.validate_settings({'effort': 'low'}, caps)


@pytest.mark.parametrize('model,settings', [
    ('gpt-5', {'temperature': .5}), ('gpt-5', {'effort': 'max'}),
    ('gpt-4o', {'effort': 'low'}), ('gpt-4o', {'temperature': float('nan')}),
    ('gpt-4o', {'temperature': True}), ('gpt-4o', {'temperature': 2.1}),
    ('gpt-5', {'max_tokens': 0}), ('gpt-5', {'max_tokens': 200001}),
    ('gpt-5', {'max_tokens': 1.1}), ('gpt-5', {'top_p': .5}),
])
def test_invalid_settings_rejected_before_probe(model, settings, monkeypatch):
    monkeypatch.setattr(connections, 'probe', lambda data: pytest.fail('Must not make a provider request'))
    with pytest.raises(ValueError):
        connections.check_and_save({'provider': 'openai', 'model': model, 'api_key': 'synthetic', 'settings': settings})


@pytest.mark.parametrize('provider,model,base,catalog_id,settings', [
    ('openai', 'gpt-5', '', 'openai:gpt-5', {'effort': 'high', 'max_tokens': 6000}),
    ('anthropic', 'claude-opus-4-7', '', 'anthropic:claude-opus-4-7', {'effort': 'max', 'max_tokens': 8000}),
    ('local', 'my-deployment', 'http://localhost:8080/v1', 'openai:gpt-4o', {'temperature': .2, 'max_tokens': 500}),
])
def test_checked_settings_survive_launch_and_resume(tmp_path, monkeypatch, provider, model, base, catalog_id, settings):
    from memstara.operational import model_profiles
    from memstara.stage_models import call_overrides, resolve_run_profiles, for_stage
    from motoro.schemas.agent import ModelConfig
    from motoro.services.llm_service import _sampling_kwargs
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.delenv('MOTORO_ENCRYPTION_KEY', raising=False)
    monkeypatch.setattr(connections, 'probe', lambda data: None)
    public = connections.check_and_save({'provider': provider, 'model': model, 'api_key': 'synthetic',
        'api_base': base, 'catalog_id': catalog_id, 'settings': settings})
    record = connections.load(public['id'])['connection']
    expected = connections.profiles(record)
    env = connections.environment(record, {})
    assert model_profiles(env) == expected
    frozen = resolve_run_profiles({}, recovering=True, frozen={'stage_models': expected})
    for role in frozen:
        actual = ModelConfig(**call_overrides(frozen, role))
        assert actual.model == model
        assert actual.max_tokens == settings['max_tokens']
        sampling = _sampling_kwargs(actual, model)
        assert sampling == ({'temperature': settings['temperature']} if 'temperature' in settings else {'reasoning_effort': settings['effort']})
        assert for_stage(frozen, role) == expected[role]
    # Changing the catalog later must not rewrite an already checked connection.
    monkeypatch.setattr(catalog, 'capabilities', lambda *args: pytest.fail('Stored capability metadata is frozen'))
    assert connections.load(public['id'])['connection'] == record
    assert 'synthetic' not in json.dumps(public)


def test_catalog_id_cannot_disguise_a_different_native_model():
    with pytest.raises(ValueError, match='differs'):
        catalog.capabilities('openai', 'gpt-5', 'openai:gpt-4o')
    with pytest.raises(ValueError, match='catalog'):
        catalog.capabilities('openai', 'gpt-5', 'anthropic:claude-opus-5')


def test_provider_discovery_paginates_and_does_not_return_credentials(monkeypatch):
    seen = []
    class Client:
        def open(self, request, timeout):
            seen.append(request)
            assert request.headers['X-api-key'] == 'synthetic-private'
            assert timeout <= 10
            return BytesIO(json.dumps({'data': [{'id': 'claude-sonnet-5'}, {'id': 'claude-haiku-4-5'}],
                'has_more': len(seen) == 1, 'last_id': 'page-end'}).encode())
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Client())
    result = catalog.list_provider_models({'provider': 'anthropic', 'api_key': 'synthetic-private'})
    assert len(seen) == 2 and 'after_id=page-end' in seen[1].full_url
    assert len(result['models']) == 2 and not result['truncated']
    assert 'synthetic-private' not in json.dumps(result)
    assert all('synthetic-private' not in request.full_url for request in seen)


def test_provider_errors_are_sanitized_and_redirects_refused(monkeypatch):
    def opener(handler):
        assert handler().redirect_request(None, None, None, None, None, 'https://other.test') is None
        class Client:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 401, 'synthetic-private', {}, None)
        return Client()
    monkeypatch.setattr('urllib.request.build_opener', opener)
    with pytest.raises(ValueError, match='access denied') as error:
        catalog.list_provider_models({'provider': 'openai', 'api_key': 'synthetic-private'})
    assert 'synthetic-private' not in str(error.value)
