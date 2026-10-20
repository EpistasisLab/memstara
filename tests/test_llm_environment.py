"""Verify environment-selected Azure routing without making model calls."""
import asyncio
from types import SimpleNamespace
import pytest
from memstara.env import configured_llm, configured_api_base


def test_environment_overrides_old_draft(monkeypatch):
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_MODEL', 'gpt-4o')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_MODEL', 'gpt-4o')
    assert configured_llm('azure_foundry', 'claude-sonnet-4-6') == ('openai', 'gpt-4o')


def test_missing_environment_rejects_saved_selection(monkeypatch):
    monkeypatch.delenv('MEMSTARA_HYPOTHESIS_PROVIDER', raising=False)
    monkeypatch.delenv('MEMSTARA_HYPOTHESIS_MODEL', raising=False)
    with pytest.raises(ValueError, match='MEMSTARA_HYPOTHESIS_PROVIDER'):
        configured_llm('anthropic', 'custom')


def test_motoro_native_resolver_keeps_azure_endpoint(monkeypatch):
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from motoro import config as core_config
    from motoro.schemas.agent import ModelConfig, LLMProvider
    from motoro.services.credentials import env_credential_resolver
    base = 'https://example-resource.services.ai.azure.com/openai/v1/'
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_MODEL', 'gpt-4o')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_API_BASE', base)
    monkeypatch.setattr(core_config, 'settings', SimpleNamespace(openai_api_key='test-only-key'))
    config = ModelConfig(provider=LLMProvider('openai'), model='gpt-4o', api_base=configured_api_base('openai'))
    conn = asyncio.run(env_credential_resolver(config))
    assert conn['api_base'] == base
    assert conn['api_key'] == 'test-only-key'
    assert config.model == 'gpt-4o'


@pytest.mark.parametrize('base', ['http://example.com', 'https://secret@example.com', 'https://example.com/?api-key=secret'])
def test_invalid_endpoint_rejected(monkeypatch, base):
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_MODEL', 'gpt-4o')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_API_BASE', base)
    with pytest.raises(ValueError):
        configured_api_base('openai')


@pytest.mark.parametrize('base', [
    'https://model.example:invalid', 'https://model.example:65536',
    'https://model.example:0', 'https://model example/v1',
    'https://model.example/\napi', 'https://model.example/\tapi',
    'https://model.example/\x00api',
])
def test_environment_endpoint_rejects_invalid_ports_and_control_characters(monkeypatch, base):
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_MODEL', 'gpt-4o')
    # NUL cannot be placed in an OS environment; emulate a supplied mapping value.
    monkeypatch.setattr('memstara.env.os.environ', {
        'MEMSTARA_HYPOTHESIS_PROVIDER': 'openai', 'MEMSTARA_HYPOTHESIS_MODEL': 'gpt-4o',
        'MEMSTARA_HYPOTHESIS_API_BASE': base,
    })
    with pytest.raises(ValueError, match='Model endpoints'):
        configured_api_base('openai')


@pytest.mark.parametrize('base', ['https://model.example:8443/v1', 'https://[::1]:443/v1'])
def test_environment_endpoint_preserves_valid_ports_and_provider_scope(monkeypatch, base):
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_MODEL', 'gpt-4o')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_API_BASE', ' ' + base + ' ')
    assert configured_api_base('openai') == base
    assert configured_api_base('anthropic') is None
