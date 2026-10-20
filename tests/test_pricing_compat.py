"""Memstara must never replace or independently calculate Motoro pricing."""
from unittest.mock import Mock
import pytest
pytest.importorskip('motoro')
from memstara import pricing_compat as pricing


def test_worker_leaves_motoro_calculator_untouched():
    from memstara.pipeline.llm import PipelineLLMService
    original = pricing.pricing_service.calculate_cost
    pricing.install()
    PipelineLLMService()
    PipelineLLMService()
    assert pricing.pricing_service.calculate_cost is original
    assert original.__module__ == 'motoro.services.pricing_service'


@pytest.mark.parametrize('result', [(None, 'litellm'), (0.0, 'override'), (.123, 'litellm')])
def test_legacy_entrypoint_only_delegates_even_with_local_rates(monkeypatch, result):
    from memstara import cost_accounting
    monkeypatch.setenv('MEMSTARA_PRICING_JSON', '{"profiles":[{"model":"anything"}]}')
    local = Mock(side_effect=AssertionError('Local estimates must not run'))
    monkeypatch.setattr(cost_accounting, 'estimate', local)
    native = Mock(return_value=result)
    monkeypatch.setattr(pricing.pricing_service, 'calculate_cost', native)
    response = object()
    assert pricing.calculate_cost('deployment', 10, 20, response) == result
    native.assert_called_once_with('deployment', 10, 20, response)
    local.assert_not_called()


def test_motoro_usage_callback_keeps_ownership(monkeypatch):
    from types import SimpleNamespace
    from motoro.services import llm_service
    from memstara.pipeline.llm import PipelineLLMService
    from memstara import cost_accounting
    PipelineLLMService()
    local = Mock(side_effect=AssertionError('No Memstara calculation'))
    monkeypatch.setattr(cost_accounting, 'estimate', local)
    native = Mock(return_value=(.42, 'litellm'))
    monkeypatch.setattr(pricing.pricing_service, 'calculate_cost', native)
    response = SimpleNamespace(model='deployment', usage=SimpleNamespace(prompt_tokens=100,completion_tokens=10))
    token = llm_service._last_usage.set(None)
    try:
        llm_service._capture_usage_callback({}, response)
        assert llm_service._last_usage.get()['cost'] == .42
        native.assert_called_once_with(model='deployment', prompt_tokens=100,completion_tokens=10,completion_response=response)
        local.assert_not_called()
    finally:
        llm_service._last_usage.reset(token)
