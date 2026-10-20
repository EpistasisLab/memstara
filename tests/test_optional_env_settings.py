"""Independent agent settings: no shared model fallback or secret serialization."""
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
def test_missing_assignment_never_uses_shared_defaults(role, field):
    values = explicit_values()
    key = f'MEMSTARA_{role.upper()}_{field}'
    del values[key]
    values.update(MEMSTARA_LLM_PROVIDER='openai', MEMSTARA_LLM_MODEL='forbidden-fallback')
    with pytest.raises(ValueError, match=key):
        model_profiles(values)


def test_shared_sampling_and_endpoint_values_are_ignored():
    values = explicit_values()
    values.update(MEMSTARA_LLM_TEMPERATURE='1.8', MEMSTARA_LLM_MAX_TOKENS='999',
                  MEMSTARA_LLM_EFFORT='high', MEMSTARA_LLM_API_BASE='https://ignored.example')
    assert all(set(p) == {'provider', 'model'} for p in model_profiles(values).values())


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
