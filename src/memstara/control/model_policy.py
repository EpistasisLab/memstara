"""Provider restriction for user-facing model setup and new web executions."""

PROVIDER = "azure_foundry"
MESSAGE = "Only Azure Foundry is available. Configure an Azure Foundry model to continue."


def require_provider(provider):
    if provider != PROVIDER:
        raise ValueError(MESSAGE)


def defaults_view(body):
    profiles = body["profiles"]
    ready = bool(profiles) and all(p["provider"] == PROVIDER and p.get("credentials_available", True) for p in profiles)
    return {
        **body,
        "profiles": [p for p in profiles if p["provider"] == PROVIDER],
        "current_allowed": ready,
        "setup_required": not ready,
        "allowed_provider": PROVIDER,
    }


def require_selection(body, *, use_defaults=False):
    """Check explicit, stored and environment-based assignments before side effects.

    Historical artifacts and recovery keep their recorded provider identities;
    this policy does not rewrite the underlying Motoro provider implementation.
    """
    if body.get("provider"):
        require_provider(body["provider"])
    profiles = body.get("stage_models") or {}
    if not isinstance(profiles, dict):
        raise ValueError(MESSAGE)
    for profile in profiles.values():
        if not isinstance(profile, dict):
            raise ValueError(MESSAGE)
        require_provider(profile.get("provider"))
    if body.get("model_connection_id"):
        from memstara.model_connections import load

        require_provider(load(body["model_connection_id"])["connection"]["provider"])
    elif use_defaults:
        from memstara.stage_models import deployment_profiles

        profiles = deployment_profiles()
        if not profiles:
            raise ValueError(MESSAGE)
        for profile in profiles.values():
            require_provider(profile.get("provider"))
