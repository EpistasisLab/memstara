"""Bounded long-context execution policy, frozen with each research run."""

TRANSPORT_RETRY_DELAYS = (2, 4, 8, 16, 32)


def runtime_timeouts(model):
    if model.lower().rsplit('/', 1)[-1].startswith(('qwen', 'claude')):
        retry_budget = 1800 * len(TRANSPORT_RETRY_DELAYS) + sum(TRANSPORT_RETRY_DELAYS)
        return {'llm_call_timeout_seconds': 1800, 'hook_timeout_seconds': 1860 + retry_budget,
                'agent_timeout_seconds': 10800 + retry_budget}
    return {}


def provider_policy(model):
    if model.lower().rsplit('/', 1)[-1].startswith('qwen'):
        return {'max_tokens': 8192, 'extra_body': {'reasoning_effort': 'none'},
                'stage_reasoning_effort': {'report': 'low'}, 'transport_attempts': 6,
                'transport_retry_delays_seconds': list(TRANSPORT_RETRY_DELAYS)}
    return {'transport_attempts': 6, 'transport_retry_delays_seconds': list(TRANSPORT_RETRY_DELAYS)}
