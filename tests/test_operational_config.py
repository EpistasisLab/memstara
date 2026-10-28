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


def test_relative_file_settings_survive_relocation_and_foreign_launch_directory(tmp_path, monkeypatch):
    from memstara.operational import PATH_KEYS
    original = tmp_path / 'first installation'
    relocated = tmp_path / 'another installation'
    elsewhere = tmp_path / 'unrelated terminal'
    for directory in (original, relocated, elsewhere):
        directory.mkdir()
    content = ''.join(f'{key}=resources/{key.lower()}\n' for key in sorted(PATH_KEYS))
    content += 'MEMSTARA_LLM_API_BASE=https://example.services.ai.azure.com\n'
    content += 'MEMSTARA_DATABASE_URL=postgresql://example:example@127.0.0.1:55641/example\n'
    for directory in (original, relocated):
        (directory / '.env').write_text(content)
    monkeypatch.chdir(elsewhere)
    before, _ = resolve({}, file=original / '.env')
    after, _ = resolve({}, file=relocated / '.env')
    for key in PATH_KEYS:
        expected = 'resources/' + key.lower()
        assert before[key] == str(original / expected)
        assert after[key] == str(relocated / expected)
    for key in ('MEMSTARA_LLM_API_BASE', 'MEMSTARA_DATABASE_URL'):
        assert before[key] == after[key]


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


def test_foundry_explicit_endpoint_does_not_require_shared_resource(tmp_path):
    from memstara.operational import agent_profile
    file = tmp_path / '.env'
    file.write_text('MEMSTARA_QUESTION_PROVIDER=azure_foundry\nMEMSTARA_QUESTION_MODEL=deployment\n'
                    'MEMSTARA_QUESTION_API_BASE=https://example.services.ai.azure.com\n')
    values, _ = resolve({}, file=file)
    assert agent_profile('question', values)['api_base'] == 'https://example.services.ai.azure.com'
    assert 'ANTHROPIC_FOUNDRY_RESOURCE' not in values


def test_single_and_role_models_do_not_expose_credentials():
    values = {'MEMSTARA_LLM_PROVIDER': 'openai', 'MEMSTARA_LLM_MODEL': 'base',
              'OPENAI_API_KEY': 'KEY_SENTINEL', 'MEMSTARA_EXPLANATION_MODEL': 'report-model'}
    profiles = model_profiles({**explicit_models(), **values})
    assert profiles['hypothesis']['model'] == 'base'
    assert profiles['explanation']['model'] == 'report-model'
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
    with pytest.raises(ValueError, match='MEMSTARA_HYPOTHESIS_PROVIDER'):
        build_argv(item['configuration'], [])


def test_start_rejects_legacy_model_changes_but_resume_preserves_history(monkeypatch):
    from memstara.stage_models import resolve_run_profiles
    monkeypatch.delenv('MEMSTARA_STAGE_MODELS_PATH', raising=False)
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    for key, value in explicit_models('current').items():
        monkeypatch.setenv(key, value)
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
    profiles = model_profiles({**explicit_models(), 'MEMSTARA_HYPOTHESIS_API_BASE': 'https://example.com/v1',
                               'MEMSTARA_LLM_PROVIDER': 'openai',
                               'MEMSTARA_LLM_MODEL': 'base',
                               'MEMSTARA_LLM_API_BASE': 'https://example.com/v1',
                               'MEMSTARA_EXPLANATION_PROVIDER': 'anthropic',
                               'MEMSTARA_EXPLANATION_MODEL': 'report'})
    assert 'api_base' not in profiles['explanation']
    assert profiles['hypothesis']['api_base'] == 'https://example.com/v1'


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
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'azure_foundry')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'fixture-model')
    monkeypatch.setenv('MEMSTARA_LLM_API_BASE', 'https://fixture.services.ai.azure.com')
    monkeypatch.setenv('ANTHROPIC_FOUNDRY_API_KEY', 'fixture-key')
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


def test_unconfigured_default_sources_explain_how_to_select_research(monkeypatch):
    from unittest.mock import Mock
    from memstara.control import service
    monkeypatch.delenv('AGENTIC_OKF_BUNDLE_DIR', raising=False)
    h = object.__new__(service.Handler)
    sent = []
    h._send = lambda code, body: sent.append((code, body))
    manager = Mock()
    h._launch({'knowledge_mode': 'okf'}, manager)
    assert sent[0][0] == 422
    assert 'Select a saved research input' in sent[0][1]['error']
    manager.start.assert_not_called()


def test_port_probe_rejects_listener_and_allows_closed_connection_restart():
    import socket
    from memstara.local_setup import assert_free
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.listen(1)
        with pytest.raises(ValueError, match='unavailable'):
            assert_free([port])
        with socket.create_connection(('127.0.0.1', port)) as client:
            accepted, _ = listener.accept()
            accepted.close()
            assert client.recv(1) == b''
    assert_free([port])


def test_absent_deployment_corpus_has_empty_knowledge_menu(monkeypatch):
    from memstara.control import service
    monkeypatch.delenv('AGENTIC_OKF_BUNDLE_DIR', raising=False)
    h = object.__new__(service.Handler)
    h.path = '/control/skills'
    h._refuse_stranger = lambda: False
    sent = []
    h._send = lambda code, body: sent.append((code, body))
    h.do_GET()
    assert sent[0][0] == 200
    assert sent[0][1]['skills'] == []
    assert sent[0][1]['configured'] is False


@pytest.mark.parametrize('provider,upstream', [
    ('azure_foundry', 'ANTHROPIC_FOUNDRY_API_KEY'),
    ('anthropic', 'ANTHROPIC_API_KEY'), ('openai', 'OPENAI_API_KEY'),
    ('openrouter', 'OPENROUTER_API_KEY'),
])
def test_generic_credential_adapts_only_to_selected_provider(tmp_path, provider, upstream):
    file = tmp_path / '.env'
    file.write_text(f'MEMSTARA_{provider.upper()}_API_KEY=SECRET_SENTINEL\n')
    values, provenance = resolve({}, file=file)
    assert values[upstream] == 'SECRET_SENTINEL'
    assert 'SECRET_SENTINEL' not in json.dumps(provenance)
    assert 'SECRET_SENTINEL' not in json.dumps(model_profiles({**explicit_models(), **values}))
    again, _ = resolve({**values, 'MEMSTARA_CONFIG_MODE': 'environment'}, file=file)
    assert again[upstream] == values[upstream]


def test_provider_credential_conflicts_fail_without_secret_values(tmp_path):
    file = tmp_path / '.env'
    file.write_text('MEMSTARA_AZURE_FOUNDRY_API_KEY=SECRET_ONE\n')
    values, _ = resolve({}, file=file)
    assert values['ANTHROPIC_FOUNDRY_API_KEY'] == 'SECRET_ONE'
    file.write_text(file.read_text() + 'ANTHROPIC_FOUNDRY_API_KEY=SECRET_TWO\n')
    with pytest.raises(ValueError, match='conflicts') as error:
        resolve({}, file=file)
    assert 'SECRET' not in str(error.value)


def test_generic_key_not_forwarded_to_viewer(tmp_path):
    from memstara.local_setup import child_environment
    file = tmp_path / '.env'
    file.write_text('MEMSTARA_OPENAI_API_KEY=SECRET_SENTINEL\n')
    values, _ = resolve({}, file=file)
    for service in ('api', 'web'):
        assert 'SECRET_SENTINEL' not in json.dumps(child_environment(values, service))


def test_project_defaults_cannot_choose_target_or_predictive_model(tmp_path):
    file = tmp_path / '.env'
    file.write_text('MEMSTARA_OUTCOME_COLUMN=private_label\nMEMSTARA_ML_ENGINE=sklearn_hgb\n')
    values, _ = resolve({}, file=file)
    assert 'MEMSTARA_OUTCOME_COLUMN' not in values
    assert 'MEMSTARA_ML_ENGINE' not in values
    # Frozen child settings retain the target to prevent target leakage into features.
    values, _ = resolve({'MEMSTARA_CONFIG_MODE': 'environment',
                         'MEMSTARA_OUTCOME_COLUMN': 'chosen_label'}, file=file)
    assert values['MEMSTARA_OUTCOME_COLUMN'] == 'chosen_label'


def test_dataset_execution_requires_explicit_ui_target():
    from memstara.control.request import build_argv
    with pytest.raises(ValueError, match='Select a target column'):
        build_argv({'data_mode': 'dataset', 'y_column': ''}, [])


def explicit_models(model='base'):
    from memstara.stage_models import AGENT_ROLES
    return {f'MEMSTARA_{role.upper()}_{field}': value for role in AGENT_ROLES
            for field, value in [('PROVIDER', 'openai'), ('MODEL', model)]}
