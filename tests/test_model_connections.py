"""Experiment model choices persist without leaking keys or changing other runs."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from memstara import model_connections as connections


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.delenv('MOTORO_ENCRYPTION_KEY', raising=False)
    monkeypatch.setattr(connections, 'probe', lambda data: None)
    return tmp_path


def save(provider='openai', **extra):
    return connections.check_and_save({'provider': provider, 'model': 'chosen-model',
                                       'api_key': 'synthetic-private-key', **extra})


def test_encrypted_persistence_and_restart(store):
    public = save()
    assert 'synthetic-private-key' not in json.dumps(public)
    directory = store / 'private-model-connections'
    encrypted = directory / (public['id'] + '.enc')
    assert b'synthetic-private-key' not in encrypted.read_bytes()
    assert encrypted.stat().st_mode & 0o777 == 0o600
    assert (directory / 'encryption.key').stat().st_mode & 0o777 == 0o600
    assert connections.load(public['id'])['connection']['api_key'] == 'synthetic-private-key'
    # The key is read from disk again, not retained only in process memory.
    assert connections.public(connections.load(public['id'])) == public


def test_connection_change_does_not_rewrite_existing_runs(store):
    first = save()
    second = save(model='another-model', api_key='another-synthetic-key')
    assert first['id'] != second['id']
    assert connections.load(first['id'])['connection']['model'] == 'chosen-model'
    assert connections.load(second['id'])['connection']['model'] == 'another-model'


@pytest.mark.parametrize('provider,extra', [
    ('openai', {}), ('anthropic', {}), ('openrouter', {}),
    ('azure_foundry', {'api_base': 'https://example.services.ai.azure.com/anthropic'}),
    ('local', {'api_base': 'http://localhost:8000/v1', 'api_key': ''}),
    ('bedrock', {'region': 'us-east-1', 'auth_type': 'api_key'}),
    ('bedrock', {'region': 'us-east-1', 'auth_type': 'aws_credentials', 'api_key': '',
                 'access_key_id': 'synthetic-id', 'secret_access_key': 'synthetic-secret', 'session_token': 'temporary'})])
def test_provider_reaches_motoro_without_other_experiment_settings(store, monkeypatch, provider, extra):
    record = connections.load(save(provider, **extra)['id'])
    parent = {'MEMSTARA_LLM_PROVIDER': 'azure_foundry', 'MEMSTARA_EXPLANATION_MODEL': 'old-model',
              'MEMSTARA_EXPLANATION_PROVIDER': 'azure_foundry', 'MEMSTARA_LLM_API_BASE': 'https://old.test',
              'OPENAI_API_KEY': 'other-experiment-secret', 'AWS_BEARER_TOKEN_BEDROCK': 'old-key'}
    untouched = dict(parent)
    child = connections.environment(record['connection'], parent)
    assert parent == untouched
    assert 'other-experiment-secret' not in json.dumps(child)
    assert child['MEMSTARA_LLM_MODEL'] == 'chosen-model'
    assert 'MEMSTARA_EXPLANATION_MODEL' not in child
    from memstara.operational import model_profiles, provider_errors
    models = model_profiles(child)
    assert all(row['provider'] == provider and row['model'] == 'chosen-model' for row in models.values())
    assert provider_errors(child, models) == []
    for key, value in child.items():
        monkeypatch.setenv(key, value)
    from memstara.config import Settings
    from motoro import config
    from motoro.schemas.agent import ModelConfig
    from motoro.services.llm_service import _resolve_connection_for_principal
    monkeypatch.setattr(config, 'settings', Settings())
    resolved = asyncio.run(_resolve_connection_for_principal(ModelConfig(**models['hypothesis'])))
    if provider in ('local', 'azure_foundry'):
        assert resolved['api_base'] == models['hypothesis']['api_base']
    if provider not in ('bedrock', 'local'):
        assert resolved['api_key'] == 'synthetic-private-key'
    if provider == 'bedrock':
        assert resolved['aws_region_name'] == 'us-east-1'


def test_failed_probe_is_not_saved(store, monkeypatch):
    def fail(data):
        raise ValueError('Authentication failed')
    monkeypatch.setattr(connections, 'probe', fail)
    with pytest.raises(ValueError, match='Authentication failed'):
        save()
    assert not list(store.rglob('*.enc'))


@pytest.mark.parametrize('patch', [
    {'provider': 'unsupported'}, {'model': ''}, {'api_key': ''},
    {'api_base': 'https://unwanted.test'}, {'api_key': 'bad\nkey'},
    {'provider': 'azure_foundry', 'api_base': 'https://user:secret@example.test'},
    {'provider': 'local', 'api_base': 'http://example.test/?key=secret'},
    {'provider': 'bedrock', 'region': '', 'auth_type': 'api_key'},
    {'provider': 'bedrock', 'region': 'us-east-1', 'auth_type': 'aws_credentials'},
])
def test_invalid_input_never_reaches_provider(store, monkeypatch, patch):
    monkeypatch.setattr(connections, 'probe', lambda data: pytest.fail('No provider call'))
    with pytest.raises(ValueError):
        connections.check_and_save({'provider': 'openai', 'model': 'test', 'api_key': 'test', **patch})


def test_probe_diagnostics_never_return_credentials(monkeypatch):
    monkeypatch.setattr(connections.subprocess, 'run', lambda *a, **kw: SimpleNamespace(
        returncode=1, stdout=b'provider echoed synthetic-private-key\nauth\n', stderr=b'private exception'))
    with pytest.raises(ValueError) as error:
        connections.probe(connections.validate({'provider': 'openai', 'model': 'test', 'api_key': 'synthetic-private-key'}))
    assert 'synthetic-private-key' not in str(error.value)
    assert 'Authentication failed' in str(error.value)


def test_design_launch_and_worker_use_same_checked_connection(store, monkeypatch):
    from memstara.control.workspace import PipelineWorkspace
    from memstara.control.request import build_argv
    public = save()
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'anthropic')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'server-default')
    workspace = PipelineWorkspace(store / 'pipelines.json', lambda key: None)
    item = workspace.mutate({'action': 'add', 'name': 'Own model', 'configuration': {'model_connection_id': public['id']}})
    config = item['configuration']
    assert config['model_connection_id'] == public['id']
    argv = build_argv(config, [], playbooks=[v for k, v in config.items() if k.startswith('playbook_') and v],
                      playbook_stages=('hypothesis', 'data', 'ml', 'interpreter', 'report'))
    assert argv[argv.index('--model') + 1] == 'chosen-model'
    assert argv[argv.index('--model-connection-id') + 1] == public['id']
    assert 'synthetic-private-key' not in json.dumps(argv)
    assert 'synthetic-private-key' not in (store / 'pipelines.json').read_text()
    child = connections.execution_environment(public['id'])
    from memstara.stage_models import resolve_run_profiles
    for key, value in child.items():
        monkeypatch.setenv(key, value)
    assert resolve_run_profiles(config['stage_models']) == config['stage_models']
    assert resolve_run_profiles({}, recovering=True, frozen={'stage_models': config['stage_models']}) == config['stage_models']


def test_missing_or_modified_connection_never_falls_back(store):
    with pytest.raises(ValueError):
        connections.execution_environment('../not-a-connection')
    public = save()
    path = store / 'private-model-connections' / (public['id'] + '.enc')
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='unavailable'):
        connections.execution_environment(public['id'])


def test_current_connection_keeps_existing_environment():
    source = {'MEMSTARA_LLM_MODEL': 'current', 'OPENAI_API_KEY': 'current-key'}
    assert connections.execution_environment('', source) == {**source, 'MEMSTARA_CONFIG_MODE': 'environment'}
