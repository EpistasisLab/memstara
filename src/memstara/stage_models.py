"""Explicit model routing shared by board provisioning and the pilot final stages."""

from copy import deepcopy


def deployment_profiles() -> dict:
    """Read deployment defaults; an explicitly configured missing file is an error."""
    import json
    import os
    from pathlib import Path

    configured = os.environ.get("MEMSTARA_STAGE_MODELS_PATH", "").strip()
    path = Path(configured) if configured else (
        Path(__file__).resolve().parents[2] / "config" / "stage-models.local.json"
    )
    if not configured and not path.exists():
        return {}
    try:
        return validate_profiles(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise ValueError("Deployment stage model profiles are missing or invalid") from exc


def public_profiles(profiles):
    """Only model identities belong in connection summaries; never endpoint credentials."""
    return {family: {key: profile[key] for key in ('provider', 'model')}
            for family, profile in validate_profiles(profiles).items()} if profiles else {}


def resolve_run_profiles(raw, *, recovering=False, frozen=None):
    """New launches inherit defaults; recovery cannot change a frozen assignment."""
    import json
    profiles = json.loads(raw) if isinstance(raw, str) else raw
    if profiles is None:
        profiles = {}
    if profiles != {}:
        profiles = validate_profiles(profiles)
    if recovering:
        expected = (frozen or {}).get('stage_models', {})
        if profiles and profiles != expected:
            raise ValueError('Recovery model profiles differ from the frozen execution')
        return validate_profiles(expected) if expected else {}
    return profiles or deployment_profiles()


def validate_call(config, stage, snapshot):
    """Refuse stale agent models before a provider request, including transport retries."""
    import re
    profiles = (snapshot or {}).get('stage_models')
    if not profiles:
        return
    match = re.match(r'^(question|hypothesis|data|ml|interpret(?:er)?|report)(?:[#0-9-].*)?$', stage)
    if not match:
        raise ValueError('Unknown stage for frozen model routing')
    role = {'question': 'hypothesis', 'interpret': 'interpreter'}.get(match[1], match[1])
    expected = for_stage(profiles, role)
    provider = getattr(config.provider, 'value', config.provider)
    if (provider, config.model) != (expected['provider'], expected['model']):
        raise ValueError('Agent provider/model differs from the frozen stage assignment')
    if expected.get('api_base') and config.api_base != expected['api_base']:
        raise ValueError('Agent endpoint differs from the frozen stage assignment')


def validate_profiles(profiles: dict) -> dict:
    if not isinstance(profiles, dict) or set(profiles) != {"qwen", "sonnet"}:
        raise ValueError("Provide explicit qwen and sonnet model profiles")
    for family, profile in profiles.items():
        if not isinstance(profile, dict) or not profile.get("provider") or not profile.get("model"):
            raise ValueError(f"Explicit {family} provider and deployment name are required")
        if not isinstance(profile["model"], str) or family not in profile["model"].lower():
            raise ValueError(f"{family} deployment must identify its requested model family")
        if profile["provider"] not in ("anthropic", "azure_foundry", "openai", "bedrock", "local", "openrouter"):
            raise ValueError("Unsupported model provider")
        if set(profile) - {"provider", "model", "api_base", "temperature", "max_tokens", "effort"}:
            raise ValueError("Profiles cannot contain credentials or implicit fallback models")
        if "max_tokens" in profile and (
            type(profile["max_tokens"]) is not int or not 0 < profile["max_tokens"] <= 200000
        ):
            raise ValueError("max_tokens must be an integer between 1 and 200000")
        if profile.get("effort") not in (None, "low", "medium", "high", "xhigh", "max"):
            raise ValueError("Unsupported reasoning effort")
        if profile.get("api_base") is not None and not isinstance(profile["api_base"], str):
            raise ValueError("api_base must be a URL string")
        if "temperature" in profile and (
            type(profile["temperature"]) not in (int, float) or not 0 <= profile["temperature"] <= 2
        ):
            raise ValueError("temperature must be between 0 and 2")
    from urllib.parse import urlsplit

    for profile in profiles.values():
        if profile.get("api_base"):
            url = urlsplit(profile["api_base"])
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("Model endpoints require HTTPS without embedded credentials or query parameters")
    return deepcopy(profiles)


def for_stage(profiles: dict, stage: str) -> dict:
    base = stage.split("#", 1)[0]
    if base not in ("hypothesis", "data", "ml", "interpreter", "report"):
        raise ValueError("Unknown pipeline stage")
    return validate_profiles(profiles)["sonnet" if base == "report" else "qwen"]


async def preflight_profiles(profiles):
    """Resolve both runtime connections without sending inference or exposing secrets."""
    from motoro.schemas.agent import ModelConfig
    from motoro.services.credentials import resolve
    for family, profile in validate_profiles(profiles).items():
        config = ModelConfig(**profile)
        default = {'model': None, 'api_key': None, 'api_base': config.api_base,
                   'api_version': None, 'aws_region_name': None}
        try:
            connection = await resolve(default, config, None)
        except Exception:
            raise ValueError(f'{family}: runtime connection could not be resolved') from None
        if profile['provider'] not in ('local', 'bedrock') and not connection.get('api_key'):
            raise ValueError(f'{family}: runtime credential is not configured')
        if profile['provider'] in ('azure_foundry', 'local') and not connection.get('api_base'):
            raise ValueError(f'{family}: runtime endpoint is not configured')
        if profile.get('api_base') and connection.get('api_base') != profile['api_base']:
            raise ValueError(f'{family}: resolved endpoint differs from its frozen profile')
        override = connection.get('model')
        if override and override not in (profile['model'], 'azure_ai/' + profile['model'],
                                         'openai/' + profile['model'], 'bedrock/' + profile['model']):
            raise ValueError(f'{family}: resolver changed the requested model')
