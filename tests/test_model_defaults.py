"""Environment defaults reach the GUI and frozen connections without exposing keys."""
import json

import pytest

from memstara import model_connections, model_defaults, operational
from memstara.stage_models import AGENT_ROLES


@pytest.fixture
def configured(tmp_path, monkeypatch):
    source = tmp_path / '.env'
    source.write_text('\n'.join([
        'MEMSTARA_LLM_PROVIDER=openai', 'MEMSTARA_LLM_MODEL=gpt-4o',
        'MEMSTARA_LLM_TEMPERATURE=0.2', 'MEMSTARA_LLM_MAX_TOKENS=7000',
        'MEMSTARA_OPENAI_API_KEY=synthetic-configured-key',
        'MEMSTARA_EXPLANATION_PROVIDER=azure_foundry',
        'MEMSTARA_EXPLANATION_MODEL=clinical-deployment',
        'MEMSTARA_EXPLANATION_API_BASE=https://clinical.example/anthropic',
        'MEMSTARA_EXPLANATION_MAX_TOKENS=11000',
        'MEMSTARA_AZURE_FOUNDRY_API_KEY=synthetic-explanation-key',
    ]))
    values, _ = operational.resolve({'MEMSTARA_CONFIG_MODE': 'project',
                                     'OPENAI_API_KEY': 'foreign-shell-key'}, file=source)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path / 'outputs'))
    return source


def test_env_defaults_keep_role_overrides_and_hide_credentials(configured):
    body = model_defaults.public_defaults()
    assert body['source'] == 'project_env'
    first, explanation = body['profiles']
    assert first['roles'] == list(AGENT_ROLES[:-1])
    assert first['provider'] == 'openai' and first['model'] == 'gpt-4o'
    assert first['settings'] == {'temperature': .2, 'max_tokens': 7000}
    assert explanation['roles'] == ['explanation']
    assert explanation['api_base'] == 'https://clinical.example'
    assert explanation['settings'] == {'max_tokens': 11000}
    assert all(row['credentials_available'] for row in body['profiles'])
    public = json.dumps(body)
    for secret in ('synthetic-configured-key', 'synthetic-explanation-key', 'foreign-shell-key'):
        assert secret not in public
    assert all(not set(model_defaults.SECRET_FIELDS) & row.keys() for row in body['profiles'])
    # The preview and runtime both use the settings loaded at server startup.
    configured.write_text('MEMSTARA_LLM_MODEL=changed-on-disk\n')
    assert model_defaults.public_defaults() == body


def test_reused_key_is_server_only_and_frozen_for_execution(configured, monkeypatch):
    seen = []
    monkeypatch.setattr(model_connections, 'probe', lambda data: seen.append(data))
    public = model_connections.check_and_save({
        'default_role': 'question', 'provider': 'openai', 'model': 'gpt-4o',
        'settings': {'temperature': .2, 'max_tokens': 7000},
    })
    assert seen[0]['api_key'] == 'synthetic-configured-key'
    assert 'synthetic-configured-key' not in json.dumps(public)
    monkeypatch.setenv('OPENAI_API_KEY', 'new-server-key')
    record = model_connections.load(public['id'])
    assert record['connection']['api_key'] == 'synthetic-configured-key'
    assert model_connections.execution_environment(public['id'])['OPENAI_API_KEY'] == 'synthetic-configured-key'
    assert all(p['max_tokens'] == 7000 and p['temperature'] == .2
               for p in model_connections.profiles(record['connection']).values())


@pytest.mark.parametrize('changes', [
    {'provider': 'local'}, {'api_base': 'https://other.example'},
    {'api_base': 'https://clinical.example/other-path'},
    {'api_base': 'https://clinical.example?token=anything'},
    {'api_base': 'https://clinical.example.attacker.test'},
    {'region': 'us-east-1'}, {'api_key': 'supplied-key'}, {'default_role': 'invalid'},
])
def test_configured_key_cannot_follow_changed_destination(configured, monkeypatch, changes):
    monkeypatch.setattr(model_connections, 'probe', lambda data: pytest.fail('Must reject before a provider call'))
    with pytest.raises(ValueError):
        model_connections.check_and_save({
            'default_role': 'explanation', 'provider': 'azure_foundry', 'model': 'another-deployment',
            'api_base': 'https://clinical.example', **changes,
        })


def test_configured_key_allows_model_change_on_same_azure_endpoint(configured):
    data = model_connections.validate({
        'default_role': 'explanation', 'provider': 'azure_foundry', 'model': 'another-deployment',
        'api_base': 'https://clinical.example/anthropic/',
    })
    assert data['api_key'] == 'synthetic-explanation-key'
    assert data['api_base'] == 'https://clinical.example'


@pytest.mark.parametrize('auth', ['api_key', 'aws_credentials'])
def test_bedrock_defaults_and_server_credential_reuse(monkeypatch, auth):
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'bedrock')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'deployment-id')
    monkeypatch.setenv('AWS_REGION', 'us-east-1')
    if auth == 'api_key':
        monkeypatch.setenv('AWS_BEARER_TOKEN_BEDROCK', 'synthetic-bearer')
    else:
        monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'synthetic-access')
        monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'synthetic-secret')
        monkeypatch.setenv('AWS_SESSION_TOKEN', 'synthetic-session')
    body = model_defaults.public_defaults()
    assert len(body['profiles']) == 1
    profile = body['profiles'][0]
    assert profile['region'] == 'us-east-1' and profile['auth_type'] == auth
    assert 'synthetic-' not in json.dumps(body)
    submitted = {'default_role': profile['role'], 'provider': 'bedrock', 'model': 'deployment-id',
                 'auth_type': auth, 'region': 'us-east-1'}
    data = model_connections.validate(submitted)
    assert data['api_key'] == ('synthetic-bearer' if auth == 'api_key' else '')
    if auth == 'aws_credentials':
        assert data['secret_access_key'] == 'synthetic-secret' and data['session_token'] == 'synthetic-session'
    with pytest.raises(ValueError, match='original provider'):
        model_connections.validate({**submitted, 'region': 'us-west-2'})


def test_missing_key_is_not_a_configured_credential(configured, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', '')
    assert not model_defaults.public_defaults()['profiles'][0]['credentials_available']
    with pytest.raises(ValueError, match='No credentials'):
        model_connections.validate({'default_role': 'question', 'provider': 'openai', 'model': 'gpt-4o'})


def test_defaults_http_uses_safe_preview_and_safe_errors(configured, monkeypatch):
    from test_control_query_routes import request
    from memstara.control import service
    status, body = request(service, '/control/model-defaults')
    assert status == 200 and body == model_defaults.public_defaults()
    def broken():
        raise ValueError('synthetic-private-error')
    monkeypatch.setattr(model_defaults, 'public_defaults', broken)
    status, body = request(service, '/control/model-defaults')
    assert status == 503 and 'synthetic-private-error' not in json.dumps(body)
