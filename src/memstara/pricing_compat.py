"""Process-local Motoro pricing adapter for installed LiteLLM token accounting.

Unknown deployment pricing stays unknown. Never infer a price from another model.
"""
from decimal import Decimal
import math

import litellm
from motoro.services import pricing_service


def calculate_cost(model, prompt_tokens, completion_tokens, completion_response=None):
    from memstara.cost_accounting import estimate, request_profile, price_receipt
    usage = getattr(completion_response, 'usage', None)
    cached = getattr(usage, 'cache_read_input_tokens', 0) or 0
    details = getattr(usage, 'prompt_tokens_details', None)
    cached = cached or getattr(details, 'cached_tokens', 0) or 0
    written = getattr(usage, 'cache_creation_input_tokens', 0) or 0
    profile = request_profile.get()
    if profile:
        receipt = estimate(profile, prompt_tokens, completion_tokens, cached, written)
        if receipt:
            price_receipt.set(receipt)
            return receipt['usd'], 'deployment_catalog'
    # Preserve Motoro's explicit, database-backed per-million-token overrides.
    for key in (model, model.rsplit('/', 1)[-1]):
        if key in pricing_service._cache and not cached and not written:
            incoming, outgoing = pricing_service._cache[key]
            pricing_service._cache.move_to_end(key)
            return float((incoming * prompt_tokens + outgoing * completion_tokens) / Decimal(1_000_000)), 'override'
    if completion_response is not None:
        try:
            cost = float(litellm.completion_cost(completion_response=completion_response))
            if math.isfinite(cost) and cost >= 0:
                return cost, 'litellm'
        except Exception:
            # Deployment aliases may not exist in the pricing catalog. Try the
            # requested identifier, without assuming an alias or fabricating rates.
            pass
    if cached or written:
        return None, 'unavailable'
    try:
        incoming, outgoing = litellm.cost_per_token(
            model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        cost = float(incoming + outgoing)
        if math.isfinite(cost) and cost >= 0:
            return cost, 'litellm'
    except Exception:
        pass
    return None, 'unavailable'


def install():
    """Install only in the Memstara worker; do not modify Motoro source or pricing data."""
    pricing_service.calculate_cost = calculate_cost
