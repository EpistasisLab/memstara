"""Manual rates are optional, deployment-bound estimates with explicit provenance."""
from copy import deepcopy

import pytest

from memstara import cost_accounting, manual_pricing, stage_models


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.delenv('MEMSTARA_PRICING_JSON', raising=False)
    monkeypatch.delenv('MEMSTARA_PRICING_PATH', raising=False)
    profile = {'provider': 'openai', 'model': 'test-model', 'api_base': 'https://example.test/v1'}
    monkeypatch.setattr(stage_models, 'deployment_profiles', lambda: {
        'non_explanation_agents': profile, 'explanation_agent': profile})
    row = manual_pricing.view()['models'][0]
    row.update(enabled=True, rates={'input': 2, 'output': 8, 'cache_read': 1},
               source='https://example.test/prices', valid_until='2099-01-01T00:00:00+00:00')
    return profile, {'models': [row]}


def test_optional_save_estimate_and_disable(setup):
    profile, body = setup
    assert cost_accounting.estimate(profile, 100, 10) is None
    view = manual_pricing.save(body)
    assert len(view['models']) == 1
    assert len(view['models'][0]['roles']) == 2
    receipt = cost_accounting.estimate(profile, 1000000, 100000, 200000)
    assert receipt['usd'] == pytest.approx(2.6)
    assert cost_accounting.estimate(profile, 100, 10, written=1) is None
    assert 'api_base' not in view['models'][0]
    body['models'][0]['enabled'] = False
    manual_pricing.save(body)
    assert cost_accounting.estimate(profile, 100, 10) is None


@pytest.mark.parametrize('field,value', [('rates', {'input': -1, 'output': 1}),
    ('rates', {'input': float('nan'), 'output': 1}), ('rates', {'input': True, 'output': 1}),
    ('source', 'unverified'), ('valid_until', '2020-01-01T00:00:00+00:00'),
    ('valid_until', '2099-01-01'), ('id', 'stale-model')])
def test_invalid_save_preserves_existing_rates(setup, field, value):
    _, body = setup
    manual_pricing.save(body)
    original = manual_pricing.path().read_bytes()
    changed = deepcopy(body)
    changed['models'][0][field] = value
    with pytest.raises((ValueError, TypeError)):
        manual_pricing.save(changed)
    assert manual_pricing.path().read_bytes() == original


def test_missing_cache_price_is_unknown_not_zero(setup):
    profile, body = setup
    body['models'][0]['rates'].pop('cache_read')
    manual_pricing.save(body)
    assert cost_accounting.estimate(profile, 100, 10, cached=20) is None
    assert cost_accounting.estimate(profile, 100, 10) is not None


def test_legacy_override_cannot_be_silently_overwritten(setup, monkeypatch):
    _, body = setup
    monkeypatch.setenv('MEMSTARA_PRICING_JSON', '{"profiles":[]}')
    assert manual_pricing.view()['read_only']
    with pytest.raises(ValueError, match='Legacy pricing'):
        manual_pricing.save(body)
    assert not manual_pricing.path().exists()
