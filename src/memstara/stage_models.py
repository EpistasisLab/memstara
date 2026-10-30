"""Explicit model routing shared by board provisioning and the pilot final stages."""

from copy import deepcopy

AGENT_ROLES = ("question", "hypothesis", "data", "ml", "interpretation", "explanation")


def deployment_profiles() -> dict:
    """Build profiles from the authoritative process settings, never a JSON file."""
    import os

    if os.environ.get("MEMSTARA_STAGE_MODELS_PATH", "").strip():
        raise ValueError("Legacy model JSON must be migrated into project .env; unset MEMSTARA_STAGE_MODELS_PATH")
    from memstara.operational import model_profiles

    return model_profiles()


def public_profiles(profiles):
    """Only model identities belong in connection summaries; never endpoint credentials."""
    return (
        {
            family: {key: profile[key] for key in ("provider", "model")}
            for family, profile in validate_profiles(profiles).items()
        }
        if profiles
        else {}
    )


def resolve_run_profiles(raw, *, recovering=False, frozen=None):
    """New launches require all agent settings; recovery keeps its frozen assignment."""
    import json

    profiles = json.loads(raw) if isinstance(raw, str) else raw
    if profiles is None:
        profiles = {}
    if profiles != {}:
        profiles = validate_profiles(profiles)
    if recovering:
        expected = (frozen or {}).get("stage_models", {})
        if profiles and profiles != (validate_profiles(expected) if expected else {}):
            raise ValueError("Recovery model profiles differ from the frozen execution")
        return validate_profiles(expected) if expected else {}
    current = deployment_profiles()
    if profiles and expanded_profiles(profiles) != expanded_profiles(current):
        raise ValueError(
            "Saved model profiles differ from project .env. Explicitly clear stage_models "
            "on the saved design to adopt project models, or use historical resume."
        )
    return current


def validate_call(config, stage, snapshot):
    """Refuse stale agent models before a provider request, including transport retries."""
    import re

    profiles = (snapshot or {}).get("stage_models")
    if not profiles:
        return
    match = re.match(r"^(question|hypothesis|data|ml|interpret(?:er)?|report)(?:[#0-9-].*)?$", stage)
    if not match:
        raise ValueError("Unknown stage for frozen model routing")
    role = {"interpret": "interpreter"}.get(match[1], match[1])
    expected = for_stage(profiles, role)
    provider = getattr(config.provider, "value", config.provider)
    if (provider, config.model) != (expected["provider"], expected["model"]):
        raise ValueError("Agent provider/model differs from the frozen stage assignment")
    if expected.get("api_base") and config.api_base != expected["api_base"]:
        raise ValueError("Agent endpoint differs from the frozen stage assignment")


def snapshot_profiles(profiles, recorded=None):
    """Keep the exact historical key representation when the assignment is unchanged."""
    normalized = validate_profiles(profiles)
    if recorded and validate_profiles(recorded) == normalized:
        return deepcopy(recorded)
    return normalized


def validate_profiles(profiles: dict) -> dict:
    if isinstance(profiles, dict) and set(profiles) == {"analysis", "explanation"}:
        profiles = {"non_explanation_agents": profiles["analysis"], "explanation_agent": profiles["explanation"]}
    if isinstance(profiles, dict) and set(profiles) == {"qwen", "sonnet"}:
        profiles = {"non_explanation_agents": profiles["qwen"], "explanation_agent": profiles["sonnet"]}
    if not isinstance(profiles, dict) or set(profiles) not in (
        set(AGENT_ROLES),
        {"non_explanation_agents", "explanation_agent"},
    ):
        raise ValueError(
            "Provide explicit non_explanation_agents and explanation_agent model profiles "
            "(or all six agent profiles; do not mix legacy keys)"
        )
    for family, profile in profiles.items():
        if not isinstance(profile, dict) or not profile.get("provider") or not profile.get("model"):
            raise ValueError(f"Explicit {family} provider and deployment name are required")
        # Historical profile keys identify stage groups, not a model vendor.
        # Azure deployment names are user-defined and need not contain a family name.
        if not isinstance(profile["model"], str) or not profile["model"].strip():
            raise ValueError(f"{family} deployment must have a nonempty model name")
        if profile["provider"] not in ("anthropic", "azure_foundry", "openai", "bedrock", "local", "openrouter"):
            raise ValueError("Unsupported model provider")
        if set(profile) - {
            "provider",
            "model",
            "api_base",
            "temperature",
            "max_tokens",
            "effort",
            "resolved_capabilities",
        }:
            raise ValueError("Profiles cannot contain credentials or implicit fallback models")
        if profile.get("resolved_capabilities") is not None:
            from motoro.services.model_capabilities import ModelCapabilities

            try:
                caps = ModelCapabilities.model_validate(profile["resolved_capabilities"])
            except Exception:
                raise ValueError("Invalid frozen model capabilities") from None
            from memstara.model_catalog import validate_settings

            validate_settings(
                {k: profile[k] for k in ("temperature", "effort", "max_tokens") if k in profile},
                caps.model_dump(mode="json"),
            )
        if "max_tokens" in profile and (
            type(profile["max_tokens"]) is not int or not 0 < profile["max_tokens"] <= 200000
        ):
            raise ValueError("max_tokens must be an integer between 1 and 200000")
        if profile.get("resolved_capabilities") is None and profile.get("effort") not in (
            None,
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        ):
            raise ValueError("Unsupported reasoning effort")
        if profile.get("api_base") is not None and not isinstance(profile["api_base"], str):
            raise ValueError("api_base must be a URL string")
        if "temperature" in profile and (
            type(profile["temperature"]) not in (int, float) or not 0 <= profile["temperature"] <= 2
        ):
            raise ValueError("temperature must be between 0 and 2")
    for profile in profiles.values():
        if profile.get("api_base"):
            validate_endpoint(profile["api_base"], allow_http=profile["provider"] == "local")
    return deepcopy(profiles)


def validate_endpoint(endpoint: str, *, allow_http: bool = False) -> None:
    """Apply the same endpoint contract to profiles and environment defaults."""
    from urllib.parse import urlsplit

    message = (
        "Model endpoints require a valid HTTPS URL (HTTP allowed for local only) and port (1-65535), "
        "without whitespace, control characters, embedded credentials or query parameters"
    )
    # urlsplit silently removes some control characters and defers port validation.
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in endpoint):
        raise ValueError(message)
    try:
        url = urlsplit(endpoint)
        port = url.port
    except ValueError:
        raise ValueError(message) from None
    if (
        url.scheme not in (("https", "http") if allow_http else ("https",))
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or port == 0
    ):
        raise ValueError(message)


def for_stage(profiles: dict, stage: str) -> dict:
    import re

    match = re.fullmatch(
        r"(question|hypothesis|data|ml|interpretation|interpreter|interpret|explanation|report)(?:[#0-9-].*)?", stage
    )
    if not match:
        raise ValueError("Unknown pipeline stage")
    aliases = {"interpreter": "interpretation", "interpret": "interpretation", "report": "explanation"}
    role = aliases.get(match[1], match[1])
    checked = validate_profiles(profiles)
    if set(checked) == set(AGENT_ROLES):
        return checked[role]
    return checked["explanation_agent" if role == "explanation" else "non_explanation_agents"]


def expanded_profiles(profiles):
    return {role: for_stage(profiles, role) for role in AGENT_ROLES}


def call_overrides(profiles, stage, temperature=None):
    """Freeze each new call's full model settings, including the question writer.

    Legacy executions retain their original per-call overrides on resume.
    """
    if profiles and set(profiles) == set(AGENT_ROLES):
        from motoro.schemas.agent import ModelConfig

        profile = ModelConfig(**for_stage(profiles, stage)).model_dump(mode="json")
        keys = ["provider", "model", "api_base", "temperature", "max_tokens", "effort"]
        if profile.get("resolved_capabilities") is not None:
            keys.append("resolved_capabilities")
        return {key: profile[key] for key in keys}
    overrides = {"temperature": temperature} if temperature is not None else {}
    if stage == "report":
        overrides["max_tokens"] = 8192
    return overrides or None


async def preflight_profiles(profiles):
    """Resolve all runtime connections without sending inference or exposing secrets."""
    import os
    from memstara.operational import provider_errors

    errors = provider_errors(os.environ, profiles)
    if errors:
        raise ValueError("; ".join(errors))
    from motoro.schemas.agent import ModelConfig
    from motoro.services.credentials import resolve

    for family, profile in validate_profiles(profiles).items():
        config = ModelConfig(**profile)
        default = {
            "model": None,
            "api_key": None,
            "api_base": config.api_base,
            "api_version": None,
            "aws_region_name": None,
        }
        try:
            connection = await resolve(default, config, None)
        except Exception:
            raise ValueError(f"{family}: runtime connection could not be resolved") from None
        if profile["provider"] not in ("local", "bedrock") and not connection.get("api_key"):
            raise ValueError(f"{family}: runtime credential is not configured")
        if profile["provider"] in ("azure_foundry", "local") and not connection.get("api_base"):
            raise ValueError(f"{family}: runtime endpoint is not configured")
        if profile.get("api_base") and connection.get("api_base") != profile["api_base"]:
            raise ValueError(f"{family}: resolved endpoint differs from its frozen profile")
        override = connection.get("model")
        if override and override not in (
            profile["model"],
            "azure_ai/" + profile["model"],
            "openai/" + profile["model"],
            "bedrock/" + profile["model"],
        ):
            raise ValueError(f"{family}: resolver changed the requested model")
