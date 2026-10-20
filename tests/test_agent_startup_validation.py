"""Exercise the launch gate and early-failure API, not only server readiness."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from memstara import env
from memstara.stage_models import AGENT_ROLES


@pytest.fixture
def explicit_agents(monkeypatch, tmp_path):
    for key in tuple(env.os.environ):
        if key.startswith(('MEMSTARA_LLM_', 'ANTHROPIC_FOUNDRY_')):
            monkeypatch.delenv(key)
    for role in AGENT_ROLES:
        monkeypatch.setenv(f'MEMSTARA_{role.upper()}_PROVIDER', 'azure_foundry')
        monkeypatch.setenv(f'MEMSTARA_{role.upper()}_MODEL', role + '-fixture')
        monkeypatch.setenv(f'MEMSTARA_{role.upper()}_API_BASE', 'https://fixture.services.ai.azure.com')
    monkeypatch.setenv('ANTHROPIC_FOUNDRY_API_KEY', 'synthetic-not-a-real-key')
    for key in env.BASE_VARS:
        monkeypatch.setenv(key, str(tmp_path))
    return tmp_path


def test_real_board_launch_gate_accepts_explicit_endpoints_without_resource(explicit_agents, monkeypatch):
    from memstara.pipeline import board
    from memstara.stage_models import deployment_profiles
    connection = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(board.asyncpg, 'connect', AsyncMock(return_value=connection))
    problems = asyncio.run(board.check_environment(
        provider='azure_foundry', stage_models=deployment_profiles(), use_data=False, use_okf=False))
    assert problems == []
    assert env.missing_vars('azure_foundry') == []
    assert 'ANTHROPIC_FOUNDRY_RESOURCE' not in env.os.environ


@pytest.mark.parametrize('role', AGENT_ROLES)
def test_each_agent_endpoint_is_required_by_startup_gate(explicit_agents, monkeypatch, role):
    key = f'MEMSTARA_{role.upper()}_API_BASE'
    monkeypatch.delenv(key)
    assert any(key in error for error in env.model_environment_errors('azure_foundry'))


def test_all_selected_providers_checked_not_only_hypothesis(explicit_agents, monkeypatch):
    monkeypatch.setenv('MEMSTARA_EXPLANATION_PROVIDER', 'openai')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert any('OPENAI_API_KEY is not set' in p for p in env.model_environment_errors('azure_foundry'))


def test_frozen_profiles_are_not_replaced_by_current_env(explicit_agents, monkeypatch):
    frozen = {role: {'provider': 'openai', 'model': 'historical'} for role in AGENT_ROLES}
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic')
    monkeypatch.delenv('MEMSTARA_QUESTION_MODEL')
    monkeypatch.delenv('ANTHROPIC_FOUNDRY_API_KEY')
    assert env.model_environment_errors('azure_foundry', frozen) == []


def test_early_failure_records_safe_cause_without_inventing_config(tmp_path):
    from memstara.pipeline.failures import record_startup_failure, visible_failure
    record_startup_failure(tmp_path, ['MEMSTARA_ML_API_BASE is required',
                                     'private-path secret-value'])
    assert not (tmp_path / 'config.json').exists()
    failure = visible_failure(tmp_path)
    assert 'MEMSTARA_ML_API_BASE' in failure['message']
    assert 'secret-value' not in json.dumps(failure)
    assert json.loads((tmp_path / 'pipeline_status.json').read_text())['status'] == 'failed'


@pytest.mark.parametrize('recorded', [False, True])
def test_completed_startup_failure_has_readable_combination_response(tmp_path, monkeypatch, recorded):
    from memstara.control import service
    from memstara.pipeline.failures import record_startup_failure
    original = 'Environment is not ready:\n  - ANTHROPIC_FOUNDRY_RESOURCE is not set\n'
    (tmp_path / 'control.log').write_text(original)
    if recorded:
        record_startup_failure(tmp_path, ['MEMSTARA_ML_API_BASE is required'])
    manager = SimpleNamespace(running=lambda: None, finished=lambda: [
        {'run_tag': 'failed-start', 'run_dir': str(tmp_path), 'exit_code': 1}])
    monkeypatch.setattr(service, 'WORKSPACE', SimpleNamespace(manager=lambda key: manager))
    handler = object.__new__(service.Handler)
    handler.headers = {'Host': 'localhost'}
    handler.path = '/control/pipelines/p/combinations?loop=1'
    handler._send = Mock()
    handler.do_GET()
    code, data = handler._send.call_args.args
    assert code == 200
    assert not data['preparing'] and data['planned'] is None and data['calls'] == []
    assert data['failure']['code'] == 'startup_environment_rejected'
    assert (tmp_path / 'control.log').read_text() == original
    assert not (tmp_path / 'config.json').exists()
