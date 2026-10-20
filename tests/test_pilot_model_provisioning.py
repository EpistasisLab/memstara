"""Verify routing reaches durable agent definitions without starting services."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip('motoro')
from memstara.pipeline import core
from motoro.schemas.agent import ModelConfig


@pytest.mark.parametrize('playbooks, count', [
    (None, 5),
    ({'hypothesis': ['guided', 'random'], 'interpreter': ['shap', 'lime']}, 7),
])
def test_provision_applies_stage_profiles_without_default_deployment(monkeypatch, playbooks, count):
    from memstara import env
    monkeypatch.setattr(env, 'configured_llm', lambda *_: pytest.fail('Explicit profiles must not use a fallback'))
    ensure = AsyncMock(return_value=SimpleNamespace(id='agent'))
    monkeypatch.setattr(core, '_ensure_agent_from_file', ensure)
    profiles = {'non_explanation_agents': {'provider': 'local', 'model': 'qwen-test', 'max_tokens': 2000},
                'explanation_agent': {'provider': 'azure_foundry', 'model': 'claude-sonnet-5', 'max_tokens': 3000}}
    asyncio.run(core.provision_board_agents(stage_models=profiles, namespace='fixture', playbooks=playbooks))
    assert ensure.await_count == count
    for call in ensure.call_args_list:
        expected = profiles['explanation_agent' if call.args[1] == 'board/report' else 'non_explanation_agents']
        assert call.kwargs['model_config'].model == expected['model']
        assert call.kwargs['model_config'].max_tokens == expected['max_tokens']


def test_same_model_refreshes_changed_endpoint_and_generation_settings(monkeypatch):
    current = ModelConfig(provider='local', model='qwen-test', max_tokens=1000)
    desired = current.model_copy(update={'max_tokens': 2000, 'api_base': 'http://localhost:1234/v1'})
    existing = SimpleNamespace(id='agent', model_config_data=current.model_dump(mode='json'))
    monkeypatch.setattr(core, 'get_agent_by_name', AsyncMock(return_value=existing))
    update = AsyncMock(return_value=existing)
    monkeypatch.setattr(core, 'update_agent', update)
    asyncio.run(core._ensure_agent('fixture', model_config=desired))
    update.assert_awaited_once_with('agent', model_config=desired)
    existing.model_config_data = desired.model_dump(mode='json')
    update.reset_mock()
    asyncio.run(core._ensure_agent('fixture', model_config=desired))
    update.assert_not_awaited()


def test_six_agent_profiles_reach_workers_and_question_run(monkeypatch):
    from memstara.stage_models import AGENT_ROLES, call_overrides
    profiles = {role: {'provider': 'openai', 'model': role + '-model', 'max_tokens': 2345}
                for role in AGENT_ROLES}
    ensure = AsyncMock(return_value=SimpleNamespace(id='agent'))
    monkeypatch.setattr(core, '_ensure_agent_from_file', ensure)
    asyncio.run(core.provision_board_agents(stage_models=profiles))
    expected = {'hypothesis': 'hypothesis', 'data': 'data', 'ml': 'ml',
                'interpreter': 'interpretation', 'report': 'explanation'}
    for call in ensure.call_args_list:
        role = expected[call.args[1].split('/')[1]]
        assert call.kwargs['model_config'].model == role + '-model'
    # Motoro shallow-merges saved per-run overrides onto the worker definition.
    worker = ModelConfig(**profiles['hypothesis']).model_dump(mode='json')
    effective = ModelConfig(**{**worker, **call_overrides(profiles, 'question0-1')})
    assert effective.model == 'question-model'
    assert effective.max_tokens == 2345
