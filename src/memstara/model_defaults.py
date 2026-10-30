"""Public model defaults and destination-bound reuse of server credentials."""

from __future__ import annotations

import os
from typing import Any

from memstara.stage_models import AGENT_ROLES, deployment_profiles, expanded_profiles

SECRET_FIELDS = ("api_key", "access_key_id", "secret_access_key", "session_token")


def connection(role):
    """Private connection material from the same process settings used by launches."""
    if role not in AGENT_ROLES:
        raise ValueError("Choose a configured agent model")
    profile = expanded_profiles(deployment_profiles())[role]
    from memstara.config import Settings

    settings = Settings()
    provider = profile["provider"]
    data = {
        "provider": provider,
        "model": profile["model"],
        "api_base": profile.get("api_base", ""),
        "region": "",
        "auth_type": "",
        **dict.fromkeys(SECRET_FIELDS, ""),
    }
    if provider == "azure_foundry":
        from motoro.services.credentials import foundry_api_base

        data["api_base"] = foundry_api_base(data["api_base"])
    attributes = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "azure_foundry": "anthropic_foundry_api_key",
        "openrouter": "openrouter_api_key",
        "local": "local_api_key",
    }
    if provider in attributes:
        data["api_key"] = getattr(settings, attributes[provider])
    elif provider == "bedrock":
        data["region"] = settings.bedrock_region
        bearer = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "").strip()
        data["auth_type"] = "api_key" if bearer else "aws_credentials"
        data.update(
            api_key=bearer,
            access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "").strip(),
            secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip(),
            session_token=os.environ.get("AWS_SESSION_TOKEN", "").strip(),
        )
    return data, profile


def credentials_available(data):
    def present(key):
        value = data.get(key, "").strip()
        return bool(value) and not value.startswith(("YOUR_", "REPLACE_"))

    if data["provider"] == "bedrock" and data["auth_type"] == "aws_credentials":
        return present("access_key_id") and present("secret_access_key")
    return present("api_key")


def public_defaults():
    """Group identical role assignments without exposing keys or loading sibling .env files."""
    from memstara.model_catalog import capabilities

    groups: list[dict[str, Any]] = []
    for role in AGENT_ROLES:
        data, profile = connection(role)
        safe = {key: data[key] for key in ("provider", "model", "api_base", "region", "auth_type")}
        safe["settings"] = {key: profile[key] for key in ("temperature", "effort", "max_tokens") if key in profile}
        safe["capabilities"] = profile.get("resolved_capabilities") or capabilities(data["provider"], data["model"])
        safe["credentials_available"] = credentials_available(data)
        existing = next((group for group in groups if {k: group[k] for k in safe} == safe), None)
        if existing:
            existing["roles"].append(role)
        else:
            groups.append({**safe, "role": role, "roles": [role]})
    return {"source": "project_env", "restart_required_after_edit": True, "profiles": groups}


def experiment_defaults():
    """A checked GUI choice takes precedence for new experiment wizards only."""
    from memstara.control.model_policy import defaults_view
    from memstara.model_connections import current_default

    try:
        body = defaults_view(public_defaults())
    except ValueError:
        body = defaults_view({"source": "project_env", "profiles": [], "restart_required_after_edit": True})
    try:
        connection = current_default()
    except (ValueError, OSError):
        # Do not silently switch to another model if a remembered record is lost.
        return {
            **body,
            "current_allowed": False,
            "setup_required": True,
            "current_error": "Saved current model is unavailable. Set up and check a model again.",
        }
    if connection:
        return {
            **body,
            "source": "saved_connection",
            "connection": connection,
            "current_allowed": True,
            "setup_required": False,
        }
    return body


def resolve_credentials(value):
    """Never send a deployment-owned credential to an edited provider or endpoint."""
    if not isinstance(value, dict) or "default_role" not in value:
        return value
    if any(value.get(key) for key in SECRET_FIELDS):
        raise ValueError("Use configured credentials or enter your own, not both")
    try:
        data, _ = connection(value["default_role"])
    except ValueError:
        raise ValueError("Configured model is unavailable. Reload the settings or enter your own connection.") from None
    base = value.get("api_base", "")
    if not isinstance(base, str):
        raise ValueError("Invalid model endpoint")
    if value.get("provider") == "azure_foundry" and base.strip():
        from motoro.services.credentials import foundry_api_base

        base = foundry_api_base(base)
    if (
        value.get("provider") != data["provider"]
        or base.strip().rstrip("/") != data["api_base"].rstrip("/")
        or value.get("region", "") != data["region"]
        or value.get("auth_type", "") != data["auth_type"]
    ):
        raise ValueError(
            "Configured credentials can only be used with their original provider, endpoint and region. "
            "Enter your own credentials for this connection."
        )
    if not credentials_available(data):
        raise ValueError("No credentials are configured for this model. Enter your own credentials.")
    result = {key: item for key, item in value.items() if key != "default_role"}
    result.update({key: data[key] for key in SECRET_FIELDS})
    return result
