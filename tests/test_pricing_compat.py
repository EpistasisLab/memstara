"""Unknown deployment prices cannot crash accounting or become a fabricated zero."""
from decimal import Decimal
from collections import OrderedDict
from unittest.mock import Mock
import pytest

pytest.importorskip('motoro', reason='Pricing adapter requires the optional Motoro runtime')
from memstara import pricing_compat as pricing


@pytest.fixture(autouse=True)
def empty_overrides(monkeypatch):
    monkeypatch.setattr(pricing.pricing_service, '_cache', OrderedDict())


def test_fallback_uses_token_api(monkeypatch):
    response = Mock(side_effect=ValueError('Unknown response deployment'))
    tokens = Mock(return_value=(.03, .04))
    monkeypatch.setattr(pricing.litellm, 'completion_cost', response)
    monkeypatch.setattr(pricing.litellm, 'cost_per_token', tokens)
    assert pricing.calculate_cost('known-model', 10, 20, object()) == (.07, 'litellm')
    assert set(response.call_args.kwargs) == {'completion_response'}
    tokens.assert_called_once_with(model='known-model', prompt_tokens=10, completion_tokens=20)


def test_unknown_price_is_not_zero(monkeypatch):
    monkeypatch.setattr(pricing.litellm, 'cost_per_token', Mock(side_effect=ValueError('Unknown model')))
    assert pricing.calculate_cost('private-deployment', 10, 20) == (None, 'unavailable')


def test_cache_accounting_from_response_preserved(monkeypatch):
    response = object()
    monkeypatch.setattr(pricing.litellm, 'completion_cost', Mock(return_value=.0123))
    fallback = Mock(side_effect=AssertionError('Must preserve response cache accounting'))
    monkeypatch.setattr(pricing.litellm, 'cost_per_token', fallback)
    assert pricing.calculate_cost('known', 10, 20, response) == (.0123, 'litellm')
    fallback.assert_not_called()


def test_explicit_override_keeps_precedence(monkeypatch):
    pricing.pricing_service._cache['deployment'] = (Decimal('2'), Decimal('4'))
    monkeypatch.setattr(pricing.litellm, 'completion_cost', Mock(side_effect=AssertionError('Override wins')))
    assert pricing.calculate_cost('openai/deployment', 1000000, 2000000, object()) == (10., 'override')


def test_worker_installs_adapter_without_changing_other_workers(monkeypatch):
    from memstara.pipeline.llm import PipelineLLMService
    original = pricing.pricing_service.calculate_cost
    monkeypatch.setattr(pricing.pricing_service, 'calculate_cost', original)
    PipelineLLMService()
    assert pricing.pricing_service.calculate_cost is pricing.calculate_cost
    PipelineLLMService()
    assert pricing.pricing_service.calculate_cost is pricing.calculate_cost
