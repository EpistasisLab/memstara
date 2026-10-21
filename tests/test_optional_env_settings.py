"""Common defaults and independent overrides without secret serialization."""
import pytest
from memstara.operational import model_profiles, resolve
from memstara.stage_models import AGENT_ROLES


def explicit_values():
    return {f'MEMSTARA_{role.upper()}_{field}': value for role in AGENT_ROLES
            for field, value in [('PROVIDER', 'openai'), ('MODEL', role + '-model')]}


@pytest.mark.parametrize('role', AGENT_ROLES)
@pytest.mark.parametrize('suffix,value,expected', [
    ('PROVIDER', 'anthropic', 'anthropic'), ('MODEL', 'override-model', 'override-model'),
    ('API_BASE', 'https://example.com/v1', 'https://example.com/v1'),
    ('TEMPERATURE', '0.7', 0.7), ('MAX_TOKENS', '1234', 1234), ('EFFORT', 'high', 'high'),
])
def test_individual_setting_reaches_model_schema(tmp_path, role, suffix, value, expected):
    from motoro.schemas.agent import ModelConfig
    values = explicit_values()
    values[f'MEMSTARA_{role.upper()}_{suffix}'] = value
    path = tmp_path / '.env'
    path.write_text(''.join(f'{k}={v}\n' for k, v in values.items()))
    resolved, _ = resolve({}, file=path)
    profiles = model_profiles(resolved)
    assert getattr(ModelConfig(**profiles[role]), suffix.lower()) == expected
    assert all(p.get(suffix.lower()) != expected for r, p in profiles.items() if r != role)


@pytest.mark.parametrize('role', AGENT_ROLES)
@pytest.mark.parametrize('field', ['PROVIDER', 'MODEL'])
def test_missing_assignment_uses_shared_defaults(role, field):
    values = explicit_values()
    key = f'MEMSTARA_{role.upper()}_{field}'
    del values[key]
    values.update(MEMSTARA_LLM_PROVIDER='openai', MEMSTARA_LLM_MODEL='shared-model')
    assert model_profiles(values)[role][field.lower()] == values['MEMSTARA_LLM_' + field]


def test_shared_sampling_and_endpoint_values_are_inherited():
    values = explicit_values()
    values.update(MEMSTARA_LLM_TEMPERATURE='1.8', MEMSTARA_LLM_MAX_TOKENS='999',
                  MEMSTARA_LLM_EFFORT='high', MEMSTARA_LLM_API_BASE='https://ignored.example')
    assert all(p['temperature'] == 1.8 and p['max_tokens'] == 999
               and p['effort'] == 'high' and p['api_base'] == 'https://ignored.example'
               for p in model_profiles(values).values())


def test_provider_credentials_do_not_require_shared_model(tmp_path):
    path = tmp_path / '.env'
    path.write_text('MEMSTARA_AZURE_FOUNDRY_API_KEY=TEST_SENTINEL\n')
    values, _ = resolve({}, file=path)
    assert values['ANTHROPIC_FOUNDRY_API_KEY'] == 'TEST_SENTINEL'
    assert 'MEMSTARA_LLM_PROVIDER' not in values


@pytest.mark.parametrize('role', AGENT_ROLES)
def test_foundry_agent_requires_its_own_endpoint(role):
    values = explicit_values()
    values[f'MEMSTARA_{role.upper()}_PROVIDER'] = 'azure_foundry'
    with pytest.raises(ValueError, match=f'MEMSTARA_{role.upper()}_API_BASE'):
        model_profiles(values)


def test_compute_limits_are_allowed_in_tool_subprocesses():
    from memstara.config import Settings
    allowed = set(Settings.model_fields['mcp_allowed_env_vars'].default.split(','))
    assert {'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
            'TOKENIZERS_PARALLELISM', 'HF_HOME'} <= allowed


def test_common_only_reaches_actual_runtime_overrides():
    from memstara.stage_models import call_overrides
    profiles = model_profiles({'MEMSTARA_LLM_PROVIDER': 'openai', 'MEMSTARA_LLM_MODEL': 'shared'})
    for role in AGENT_ROLES:
        assert call_overrides(profiles, role)['model'] == 'shared'


def test_provider_change_does_not_inherit_endpoint_or_sampling():
    values = {'MEMSTARA_LLM_PROVIDER': 'azure_foundry', 'MEMSTARA_LLM_MODEL': 'common',
              'MEMSTARA_LLM_API_BASE': 'https://example.services.ai.azure.com',
              'MEMSTARA_LLM_TEMPERATURE': '1', 'MEMSTARA_LLM_EFFORT': 'high',
              'MEMSTARA_EXPLANATION_PROVIDER': 'openai', 'MEMSTARA_EXPLANATION_MODEL': 'other'}
    profiles = model_profiles(values)
    assert profiles['explanation'] == {'provider': 'openai', 'model': 'other'}
    del values['MEMSTARA_EXPLANATION_MODEL']
    with pytest.raises(ValueError, match='MEMSTARA_EXPLANATION_MODEL'):
        model_profiles(values)


def test_blank_override_inherits_and_zero_overrides():
    values = {'MEMSTARA_LLM_PROVIDER': 'openai', 'MEMSTARA_LLM_MODEL': 'common',
              'MEMSTARA_LLM_TEMPERATURE': '1', 'MEMSTARA_ML_MODEL': '  ',
              'MEMSTARA_ML_TEMPERATURE': '0'}
    profiles = model_profiles(values)
    assert profiles['ml']['model'] == 'common'
    assert profiles['ml']['temperature'] == 0
    assert profiles['question']['temperature'] == 1
