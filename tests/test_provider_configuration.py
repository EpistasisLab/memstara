"""Provider settings survive project loading and Docker without entering public profiles."""
import asyncio
import json

import pytest

from memstara.operational import model_profiles, provider_errors, resolve
from memstara.stage_models import AGENT_ROLES


@pytest.mark.parametrize('provider,key,base', [
    ('openai', 'MEMSTARA_OPENAI_API_KEY', ''),
    ('anthropic', 'MEMSTARA_ANTHROPIC_API_KEY', ''),
    ('openrouter', 'MEMSTARA_OPENROUTER_API_KEY', ''),
    ('azure_foundry', 'MEMSTARA_AZURE_FOUNDRY_API_KEY', 'https://example.services.ai.azure.com'),
    ('local', 'MEMSTARA_LOCAL_API_KEY', 'http://host.docker.internal:8000/v1'),
    ('bedrock', 'AWS_BEARER_TOKEN_BEDROCK', ''),
])
def test_project_to_motoro_connection(tmp_path, monkeypatch, provider, key, base):
    from memstara.config import Settings
    from motoro import config
    from motoro.schemas.agent import ModelConfig
    from motoro.services.llm_service import _resolve_connection_for_principal
    path = tmp_path / '.env'
    path.write_text(f'MEMSTARA_LLM_PROVIDER={provider}\nMEMSTARA_LLM_MODEL=test-model\n'
                    f'MEMSTARA_LLM_API_BASE={base}\n{key}=synthetic-secret\nAWS_REGION=us-east-1\n')
    values, _ = resolve({}, file=path)
    for k,v in values.items():
        monkeypatch.setenv(k,v)
    monkeypatch.setattr(config, 'settings', Settings())
    profiles = model_profiles(values)
    assert provider_errors(values, profiles) == []
    assert 'synthetic-secret' not in json.dumps(profiles)
    for role in AGENT_ROLES:
        conn = asyncio.run(_resolve_connection_for_principal(ModelConfig(**profiles[role])))
        if provider == 'bedrock':
            assert conn['aws_region_name'] == 'us-east-1'
            # LiteLLM reads this bearer token from the generated process environment.
            import os
            assert os.environ['AWS_BEARER_TOKEN_BEDROCK'] == 'synthetic-secret'
        else:
            assert conn['api_key'] == 'synthetic-secret'
        assert conn['api_base'] == (base or None)


@pytest.mark.parametrize('values,valid', [
    ({}, False),
    ({'AWS_REGION':'us-east-1'}, False),
    ({'AWS_REGION':'us-east-1','AWS_ACCESS_KEY_ID':'test'}, False),
    ({'AWS_REGION':'us-east-1','AWS_ACCESS_KEY_ID':'test','AWS_SECRET_ACCESS_KEY':'secret'}, True),
    ({'AWS_REGION':'us-east-1','AWS_ACCESS_KEY_ID':'test','AWS_SECRET_ACCESS_KEY':'secret','AWS_SESSION_TOKEN':'session'}, True),
    ({'AWS_REGION':'us-east-1','AWS_BEARER_TOKEN_BEDROCK':'token'}, True),
    ({'AWS_REGION':'us-east-1','AWS_BEARER_TOKEN_BEDROCK':'token','AWS_ACCESS_KEY_ID':'test'}, False),
])
def test_bedrock_authentication_requirements(values, valid):
    assert (not provider_errors(values, {'ml':{'provider':'bedrock'}})) == valid


def test_project_does_not_borrow_shell_credentials(tmp_path):
    path=tmp_path/'.env'
    path.write_text('MEMSTARA_LLM_PROVIDER=bedrock\nMEMSTARA_LLM_MODEL=test\n')
    values,_=resolve({'AWS_REGION':'other','AWS_ACCESS_KEY_ID':'shell','LOCAL_LLM_API_KEY':'shell'},file=path)
    assert 'AWS_REGION' not in values
    assert 'AWS_ACCESS_KEY_ID' not in values
    assert 'LOCAL_LLM_API_KEY' not in values


def test_local_http_is_provider_scoped():
    for provider in ('openai','azure_foundry','anthropic','openrouter','bedrock'):
        with pytest.raises(ValueError,match='Model endpoints'):
            model_profiles({'MEMSTARA_LLM_PROVIDER':provider,'MEMSTARA_LLM_MODEL':'test',
                            'MEMSTARA_LLM_API_BASE':'http://localhost:8000/v1'})


def test_provider_secrets_remain_in_control_only(tmp_path):
    from test_container_config import configuration
    from memstara.container_config import derive
    values=configuration(tmp_path)
    values.update(AWS_REGION='us-east-1', AWS_BEARER_TOKEN_BEDROCK='synthetic-secret',
                  MEMSTARA_LOCAL_API_KEY='local-secret', LOCAL_LLM_API_KEY='local-secret')
    groups=derive(values,root=tmp_path)
    assert groups['control']['AWS_BEARER_TOKEN_BEDROCK']=='synthetic-secret'
    assert groups['control']['LOCAL_LLM_API_KEY']=='local-secret'
    for group in ('api','board','runtime'):
        assert 'synthetic-secret' not in json.dumps(groups[group])
        assert 'local-secret' not in json.dumps(groups[group])


def test_provider_credentials_not_exposed_to_mcp_tools():
    from memstara.config import Settings
    allowed = set(Settings.model_fields['mcp_allowed_env_vars'].default.split(','))
    assert not {'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_BEARER_TOKEN_BEDROCK',
                'MEMSTARA_LOCAL_API_KEY', 'LOCAL_LLM_API_KEY'} & allowed


def test_profile_preflight_rejects_missing_bedrock_auth(monkeypatch):
    from memstara.stage_models import preflight_profiles
    for key in ('AWS_REGION','AWS_BEARER_TOKEN_BEDROCK','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    profiles = model_profiles({'MEMSTARA_LLM_PROVIDER':'bedrock','MEMSTARA_LLM_MODEL':'test'})
    with pytest.raises(ValueError, match='AWS_REGION'):
        asyncio.run(preflight_profiles(profiles))
