"""Legacy import compatibility; pricing is owned exclusively by Motoro."""
from motoro.services import pricing_service


def calculate_cost(model, prompt_tokens, completion_tokens, completion_response=None):
    """Delegate without local rates, fallback calculations or provider substitutions."""
    return pricing_service.calculate_cost(model, prompt_tokens, completion_tokens, completion_response)


def install():
    """Deprecated no-op. Never replace Motoro's pricing function."""
