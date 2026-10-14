"""Project settings cannot silently inherit another installation's credentials."""
import json

import pytest

from memstara.operational import model_profiles, resolve


def test_project_file_replaces_shell_and_ignores_sibling(tmp_path, monkeypatch):
    file = tmp_path / '.env'
    file.write_text('MEMSTARA_LLM_PROVIDER=openai\nMEMSTARA_LLM_MODEL=project-model\n')
    (tmp_path / 'motoro').mkdir()
    (tmp_path / 'motoro/.env').write_text('OPENAI_API_KEY=SIBLING_SENTINEL\n')
    monkeypatch.chdir(tmp_path / 'motoro')
    values, provenance = resolve({'OPENAI_API_KEY': 'SHELL_SENTINEL', 'MEMSTARA_LLM_MODEL': 'wrong'}, file=file)
    assert values['MEMSTARA_LLM_MODEL'] == 'project-model'
    assert 'OPENAI_API_KEY' not in values
    assert values['MEMSTARA_OUTPUT_DIR'] == str(tmp_path / 'outputs')
    assert provenance['mode'] == 'project'


def test_environment_mode_is_explicit_and_does_not_read_file(tmp_path):
    file = tmp_path / '.env'
    file.write_text('OPENAI_API_KEY=FILE_SENTINEL\n')
    values, _ = resolve({'MEMSTARA_CONFIG_MODE': 'environment', 'MEMSTARA_LLM_MODEL': 'injected'}, file=file)
    assert values['MEMSTARA_LLM_MODEL'] == 'injected'
    assert 'OPENAI_API_KEY' not in values


def test_missing_file_does_not_fall_back_to_shell(tmp_path):
    with pytest.raises(ValueError, match='Project .env is missing'):
        resolve({'OPENAI_API_KEY': 'SENTINEL'}, file=tmp_path / '.env')


@pytest.mark.parametrize('extra', ['MEMSTARA_WEB_PORT=0', 'MEMSTARA_WEB_PORT=8071',
                                  'MEMSTARA_OUTPUT_DIR=${HOME}/data'])
def test_invalid_local_configuration_is_rejected(tmp_path, extra):
    file = tmp_path / '.env'
    file.write_text(extra + '\n')
    with pytest.raises(ValueError):
        resolve({}, file=file)


def test_foundry_resource_and_endpoint_agree(tmp_path):
    file = tmp_path / '.env'
    file.write_text('MEMSTARA_LLM_PROVIDER=azure_foundry\nMEMSTARA_LLM_MODEL=deployment\n'
                    'MEMSTARA_LLM_API_BASE=https://example.services.ai.azure.com\n')
    values, _ = resolve({}, file=file)
    assert values['ANTHROPIC_FOUNDRY_RESOURCE'] == 'example'
    file.write_text(file.read_text() + 'ANTHROPIC_FOUNDRY_RESOURCE=other\n')
    with pytest.raises(ValueError, match='conflict'):
        resolve({}, file=file)


def test_single_and_role_models_do_not_expose_credentials():
    values = {'MEMSTARA_LLM_PROVIDER': 'openai', 'MEMSTARA_LLM_MODEL': 'base',
              'OPENAI_API_KEY': 'KEY_SENTINEL', 'MEMSTARA_EXPLANATION_MODEL': 'report-model'}
    profiles = model_profiles(values)
    assert profiles['non_explanation_agents']['model'] == 'base'
    assert profiles['explanation_agent']['model'] == 'report-model'
    assert 'KEY_SENTINEL' not in json.dumps(profiles)


def test_design_saves_without_models_and_start_requires_models(tmp_path, monkeypatch):
    from memstara.control.workspace import PipelineWorkspace
    from memstara.control.request import build_argv
    monkeypatch.delenv('MEMSTARA_LLM_PROVIDER', raising=False)
    monkeypatch.delenv('MEMSTARA_LLM_MODEL', raising=False)
    workspace = PipelineWorkspace(tmp_path / 'workspace.json', lambda key: None)
    item = workspace.mutate({'action': 'add', 'name': 'Draft'})
    assert item['configuration']['stage_models'] == {}
    assert workspace.path.exists()
    with pytest.raises(ValueError, match='MEMSTARA_LLM_PROVIDER'):
        build_argv(item['configuration'], [])


def test_start_rejects_legacy_model_changes_but_resume_preserves_history(monkeypatch):
    from memstara.stage_models import resolve_run_profiles
    monkeypatch.delenv('MEMSTARA_STAGE_MODELS_PATH', raising=False)
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'current')
    old = {k: {'provider': 'openai', 'model': 'historical'}
           for k in ('non_explanation_agents', 'explanation_agent')}
    with pytest.raises(ValueError, match='Explicitly clear'):
        resolve_run_profiles(old)
    assert resolve_run_profiles({}, recovering=True, frozen={'stage_models': old}) == old


def test_web_and_api_environments_do_not_receive_provider_or_owner_credentials():
    from memstara.local_setup import child_environment
    from memstara.operational import PORT_DEFAULTS
    values = {k: str(v) for k, v in PORT_DEFAULTS.items()}
    values.update(ANTHROPIC_FOUNDRY_API_KEY='PROVIDER_SENTINEL',
                  MOTORO_DATABASE_URL='OWNER_SENTINEL', CORE_VIEWER_DSN='readonly')
    web = child_environment(values, 'web')
    api = child_environment(values, 'api')
    assert 'SENTINEL' not in json.dumps(web)
    assert 'SENTINEL' not in json.dumps(api)
    assert api['CORE_VIEWER_DSN'] == 'readonly'


def test_compose_uses_configured_ports_and_rejects_remote_database():
    from memstara.local_setup import compose_definition
    values = {'MEMSTARA_COMPOSE_PROJECT': 'isolated-example',
              'MEMSTARA_DATABASE_URL': 'postgresql://a:b@127.0.0.1:15501/board',
              'MOTORO_DATABASE_URL': 'postgresql+asyncpg://c:d@127.0.0.1:15502/runtime',
              'MOTORO_REDIS_URL': 'redis://127.0.0.1:16380/0'}
    config, ports = compose_definition(values)
    assert ports == [15501, 15502, 16380]
    assert config['name'] == 'isolated-example'
    assert config['services']['board']['ports'] == ['127.0.0.1:15501:5432']
    assert config['services']['runtime']['environment']['POSTGRES_DB'] == 'runtime'
    assert '$$POSTGRES_USER' in config['services']['board']['healthcheck']['test'][1]
    values['MEMSTARA_DATABASE_URL'] = 'postgresql://a:literal%24password@127.0.0.1:15501/board'
    escaped, _ = compose_definition(values)
    assert escaped['services']['board']['environment']['POSTGRES_PASSWORD'] == 'literal$$password'
    values['MOTORO_DATABASE_URL'] = 'postgresql://c:d@remote.example:15502/runtime'
    with pytest.raises(ValueError, match='local provisioning'):
        compose_definition(values)


def test_provider_override_does_not_reuse_default_endpoint():
    profiles = model_profiles({'MEMSTARA_LLM_PROVIDER': 'openai',
                               'MEMSTARA_LLM_MODEL': 'base',
                               'MEMSTARA_LLM_API_BASE': 'https://example.com/v1',
                               'MEMSTARA_EXPLANATION_PROVIDER': 'anthropic',
                               'MEMSTARA_EXPLANATION_MODEL': 'report'})
    assert 'api_base' not in profiles['explanation_agent']
    assert profiles['non_explanation_agents']['api_base'] == 'https://example.com/v1'


def test_migration_failure_preserves_original_and_restricted_backup(tmp_path, monkeypatch):
    from memstara.operational import migrate_models
    import dotenv
    env = tmp_path / '.env'
    original = 'OPENAI_API_KEY=PRIVATE_SENTINEL\nMEMSTARA_LLM_MODEL=original\n'
    env.write_text(original)
    (tmp_path / 'outputs').mkdir()
    legacy = tmp_path / 'profiles.json'
    legacy.write_text(json.dumps({key: {'provider': 'openai', 'model': 'replacement'}
                                 for key in ('non_explanation_agents', 'explanation_agent')}))
    def fail(*args, **kwargs):
        raise OSError('Simulated write failure')
    monkeypatch.setattr(dotenv, 'set_key', fail)
    with pytest.raises(OSError):
        migrate_models(legacy, env)
    assert env.read_text() == original
    backup = next((tmp_path / 'outputs').iterdir())
    assert backup.stat().st_mode & 0o777 == 0o700
    assert (backup / '.env').stat().st_mode & 0o777 == 0o600
    assert (backup / '.env').read_text() == original
    assert not list(tmp_path.glob('.env-migration-*'))


def test_provenance_does_not_include_credentials_or_overwrite_history(tmp_path, monkeypatch):
    from memstara import env
    from memstara.operational import save_source
    monkeypatch.setenv('OPENAI_API_KEY', 'SECRET_SENTINEL')
    monkeypatch.setattr(env, '_provenance', {'mode': 'project', 'file': '/example/.env'})
    save_source(tmp_path)
    before = (tmp_path / 'operational_source.json').read_text()
    assert 'SECRET_SENTINEL' not in before
    monkeypatch.setattr(env, '_provenance', {'mode': 'environment'})
    save_source(tmp_path)
    assert (tmp_path / 'operational_source.json').read_text() == before


def test_connection_probe_redacts_driver_errors(monkeypatch):
    import asyncio
    import asyncpg
    import redis.asyncio
    from memstara.local_setup import probe_connections
    async def fail(*args, **kwargs):
        raise RuntimeError('password=PRIVATE_DRIVER_SENTINEL')
    def fail_redis(*args, **kwargs):
        raise RuntimeError('redis://PRIVATE_DRIVER_SENTINEL')
    monkeypatch.setattr(asyncpg, 'connect', fail)
    monkeypatch.setattr(redis.asyncio, 'from_url', fail_redis)
    result = asyncio.run(probe_connections({'MEMSTARA_DATABASE_URL': 'postgresql://test/db'}))
    assert result['services']['MEMSTARA_DATABASE_URL'] == 'connection_failed'
    assert result['model_call'] == 'not_tested'
    assert 'PRIVATE_DRIVER_SENTINEL' not in json.dumps(result)


def test_connection_probe_rejects_viewer_with_write_privileges(monkeypatch):
    import asyncio
    import asyncpg
    from memstara.local_setup import probe_connections
    class Connection:
        async def fetchval(self, query):
            return True
        async def close(self):
            pass
    async def connect(*args, **kwargs):
        return Connection()
    monkeypatch.setattr(asyncpg, 'connect', connect)
    result = asyncio.run(probe_connections({'MEMSTARA_VIEWER_DSN': 'postgresql://test/db'}))
    assert result['services']['MEMSTARA_VIEWER_DSN'] == 'unsafe_write_privileges'


@pytest.mark.parametrize('same', [True, False])
def test_migration_preserves_profiles_without_pinning_redundant_overrides(tmp_path, same):
    from dotenv import dotenv_values
    from memstara.operational import migrate_models
    (tmp_path / 'outputs').mkdir()
    env = tmp_path / '.env'
    env.write_text('OPENAI_API_KEY=PRIVATE_SENTINEL\n')
    profiles = {'non_explanation_agents': {'provider': 'openai', 'model': 'base', 'temperature': 1},
                'explanation_agent': {'provider': 'openai', 'model': 'base', 'temperature': 1}
                if same else {'provider': 'openai', 'model': 'other'}}
    source = tmp_path / 'models.json'
    source.write_text(json.dumps(profiles))
    migrate_models(source, env)
    values = dotenv_values(env, interpolate=False)
    assert model_profiles(values) == profiles
    if same:
        assert not any(k.startswith(('MEMSTARA_NON_EXPLANATION_', 'MEMSTARA_EXPLANATION_')) for k in values)
        values['MEMSTARA_LLM_MODEL'] = 'changed'
        assert {p['model'] for p in model_profiles(values).values()} == {'changed'}


@pytest.mark.parametrize('command', ['init', 'services'])
def test_storage_commands_reject_same_database_before_subprocess(tmp_path, monkeypatch, capsys, command):
    from unittest.mock import Mock
    from memstara import local_setup
    file = tmp_path / '.env'
    file.write_text(
        'MEMSTARA_DATABASE_URL=postgresql://owner:SECRET_SENTINEL@localhost:15501/shared\n'
        'MOTORO_DATABASE_URL=postgresql+asyncpg://other:SECRET_SENTINEL@127.0.0.1:15501/shared\n'
        'MOTORO_REDIS_URL=redis://127.0.0.1:16380/0\n')
    monkeypatch.setenv('MEMSTARA_CONFIG_MODE', 'project')
    monkeypatch.setenv('MEMSTARA_ENV_FILE', str(file))
    monkeypatch.setattr('sys.argv', ['local_setup', command])
    run = Mock(side_effect=AssertionError('No subprocess may start'))
    monkeypatch.setattr(local_setup.subprocess, 'run', run)
    monkeypatch.setattr(local_setup.subprocess, 'call', run)
    monkeypatch.setattr(local_setup.subprocess, 'check_output', run)
    assert local_setup.main() == 1
    output = capsys.readouterr().out
    assert 'different databases' in output
    assert 'SECRET_SENTINEL' not in output
    run.assert_not_called()


def test_control_refuses_invalid_storage_before_creating_worker(monkeypatch):
    from unittest.mock import Mock
    from memstara.control import service
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'fixture-model')
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    monkeypatch.setenv('MEMSTARA_DATABASE_URL', 'postgresql://test:SECRET_SENTINEL@localhost/shared')
    monkeypatch.setenv('MOTORO_DATABASE_URL', 'postgresql://test:SECRET_SENTINEL@localhost/shared')
    monkeypatch.setenv('MOTORO_REDIS_URL', 'redis://localhost:6379/0')
    monkeypatch.setattr(service, 'playbooks', lambda: {'playbooks': [], 'stages': []})
    monkeypatch.setattr(service, 'build_argv', lambda *args: [])
    monkeypatch.setattr(service, 'validate_selection', lambda *args: None)
    create = Mock(side_effect=AssertionError('No run directory may be created'))
    monkeypatch.setattr(service, 'new_run_dir', create)
    handler = object.__new__(service.Handler)
    responses = []
    handler._send = lambda status, payload: responses.append((status, payload))
    manager = Mock()
    handler._launch({'knowledge_mode': 'llm_only', 'data_mode': 'proposal'}, manager)
    assert responses[0][0] == 422
    assert responses[0][1]['code'] == 'configuration_invalid'
    assert 'different databases' in responses[0][1]['error']
    assert 'SECRET_SENTINEL' not in json.dumps(responses)
    create.assert_not_called()
    manager.start.assert_not_called()
