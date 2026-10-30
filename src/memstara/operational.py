"""Project-owned operational configuration, separate from saved research designs.

File mode never fills missing project settings from the calling shell. Environment
mode is an explicit contract for CI and process supervision. Neither reads a
sibling checkout. Resolution is pure so callers can validate before initialization.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from memstara.paths import REPO_ROOT

SELECTORS = {"MEMSTARA_CONFIG_MODE", "MEMSTARA_ENV_FILE"}
PREFIXES = ("MEMSTARA_", "MOTORO_", "ANTHROPIC_", "OPENAI_", "OPENROUTER_", "AZURE_", "AGENTIC_", "AWS_", "LOCAL_LLM_")
EXTRA = {
    "COMPOSE_PROJECT_NAME",
    "AGENTIC_OKF_BUNDLE_DIR",
    "CORE_VIEWER_DSN",
    "VIEWER_CORS",
    "HF_HOME",
    "HF_HUB_CACHE",
    "HF_HUB_OFFLINE",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "TOKENIZERS_PARALLELISM",
    "POSTGRES_PASSWORD",
}
PORT_DEFAULTS = {"MEMSTARA_WEB_PORT": 5173, "MEMSTARA_API_PORT": 8071, "MEMSTARA_CONTROL_PORT": 8072}
PATH_DEFAULTS = {
    "MEMSTARA_OUTPUT_DIR": "outputs",
    "HF_HOME": "outputs/huggingface",
    "MEMSTARA_INPUTS_DIR": "user-inputs",
}
PATH_KEYS = {
    *PATH_DEFAULTS,
    "MEMSTARA_INPUTS_DIR",
    "MEMSTARA_PRICING_PATH",
    "HF_HUB_CACHE",
    "MEMSTARA_DATASET_PATH",
    "AGENTIC_OKF_BUNDLE_DIR",
    "MEMSTARA_USER_SKILLS_DIR",
    "MEMSTARA_SPECIALIST_SKILLS_DIR",
    "MEMSTARA_SHARED_SKILLS_DIR",
    "MEMSTARA_RESULTS_SKILL_PATH",
    "MEMSTARA_ML_REFERENCE_PATH",
    "MEMSTARA_SKILL_ALIASES_PATH",
    "MEMSTARA_LEAKAGE_RULES_PATH",
    "MEMSTARA_EXPLANATION_SOURCES",
}


def managed(name: str) -> bool:
    return name.startswith(PREFIXES) or name in EXTRA


def resolve(environ=None, *, file: Path | None = None):
    """Return validated values and safe provenance, without changing os.environ."""
    source = dict(os.environ if environ is None else environ)
    mode = source.get("MEMSTARA_CONFIG_MODE", "project")
    if mode not in ("project", "environment"):
        raise ValueError("MEMSTARA_CONFIG_MODE must be project or environment")
    path = Path(file or source.get("MEMSTARA_ENV_FILE") or REPO_ROOT / ".env").expanduser().resolve()
    if mode == "project":
        if not path.is_file():
            raise ValueError("Project .env is missing; copy .env.example and configure this installation")
        raw = dotenv_values(path, interpolate=False)
        from memstara.installation import read

        raw = {**read(path.parent), **{k: v for k, v in raw.items() if v is not None}}
        values = {k: v for k, v in raw.items() if v is not None and managed(k) and k not in SELECTORS}
        if any("${" in v for v in values.values()):
            raise ValueError("Project .env requires literal values; shell interpolation is not supported")
    else:
        values = {k: v for k, v in source.items() if managed(k) and k not in SELECTORS}
    # Research choices belong to saved UI profiles, not installation defaults.
    # Child execution environments still carry the frozen target for tool safety.
    if mode == "project":
        values.pop("MEMSTARA_OUTCOME_COLUMN", None)
        values.pop("MEMSTARA_ML_ENGINE", None)
    if (
        values.get("COMPOSE_PROJECT_NAME")
        and values.get("MEMSTARA_COMPOSE_PROJECT")
        and values["COMPOSE_PROJECT_NAME"] != values["MEMSTARA_COMPOSE_PROJECT"]
    ):
        raise ValueError("COMPOSE_PROJECT_NAME conflicts with legacy MEMSTARA_COMPOSE_PROJECT")
    import json

    for key, legacy in (
        ("MEMSTARA_PRICING_JSON", "MEMSTARA_PRICING_PATH"),
        ("MEMSTARA_EXPLANATION_SOURCES_JSON", "MEMSTARA_EXPLANATION_SOURCES"),
        ("MEMSTARA_AZURE_PRICING_METERS_JSON", None),
    ):
        if not values.get(key, "").strip():
            continue
        if legacy and values.get(legacy, "").strip():
            raise ValueError(f"{key} conflicts with {legacy}; choose one source")
        try:
            parsed = json.loads(values[key])
            if not isinstance(parsed, dict):
                raise ValueError()
            if key != "MEMSTARA_EXPLANATION_SOURCES_JSON" and not isinstance(parsed.get("profiles"), list):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(f"{key} must contain a valid JSON object with the documented schema") from None
    root = path.parent if mode == "project" else REPO_ROOT
    for name, default in PATH_DEFAULTS.items():
        values.setdefault(name, str(root / default))
    inputs = Path(values.get("MEMSTARA_INPUTS_DIR") or root / "user-inputs").expanduser()
    inputs = (inputs if inputs.is_absolute() else root / inputs).resolve()
    for name in PATH_KEYS:
        if values.get(name):
            p = Path(values[name]).expanduser()
            if name != "MEMSTARA_INPUTS_DIR" and not p.is_absolute() and p.parts[:1] == ("user-inputs",):
                p = inputs.joinpath(*p.parts[1:])
            values[name] = str((p if p.is_absolute() else root / p).resolve())
    for name, port_default in PORT_DEFAULTS.items():
        value = values.get(name, str(port_default))
        if not value.isdecimal() or not 1 <= int(value) <= 65535:
            raise ValueError(f"{name} must be an integer port from 1 to 65535")
        values[name] = str(int(value))
    if len({values[k] for k in PORT_DEFAULTS}) != len(PORT_DEFAULTS):
        raise ValueError("Web, API and control ports must be distinct")
    # Credentials are shared by provider, never selected through a common model.
    credential_keys = {
        "MEMSTARA_AZURE_FOUNDRY_API_KEY": "ANTHROPIC_FOUNDRY_API_KEY",
        "MEMSTARA_ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
        "MEMSTARA_OPENAI_API_KEY": "OPENAI_API_KEY",
        "MEMSTARA_OPENROUTER_API_KEY": "OPENROUTER_API_KEY",
        "MEMSTARA_LOCAL_API_KEY": "LOCAL_LLM_API_KEY",
    }
    for public, upstream in credential_keys.items():
        key = values.get(public, "").strip()
        if key:
            if values.get(upstream) and values[upstream] != key:
                raise ValueError(f"{public} conflicts with the legacy provider credential")
            values[upstream] = key
    values["MEMSTARA_CONFIG_MODE"] = mode
    values["MEMSTARA_ENV_FILE"] = str(path)
    return values, {
        "mode": mode,
        "file": str(path) if mode == "project" else None,
        "inherited_project_file": (source.get("MEMSTARA_CONFIG_ORIGIN_FILE") if mode == "environment" else None),
        "restart_required_after_change": True,
    }


def agent_profile(role, values=None):
    """Resolve an agent override against explicit common defaults."""
    from memstara.stage_models import AGENT_ROLES, validate_profiles

    role = {"interpreter": "interpretation", "report": "explanation"}.get(role, role)
    if role not in AGENT_ROLES:
        raise ValueError("Unknown model role")
    values = os.environ if values is None else values
    prefix = "MEMSTARA_" + role.upper() + "_"
    common_provider = values.get("MEMSTARA_LLM_PROVIDER", "").strip()
    provider = values.get(prefix + "PROVIDER", "").strip() or common_provider
    same_provider = not common_provider or provider == common_provider

    def setting(key):
        override = values.get(prefix + key.upper(), "").strip()
        # A different provider must supply its own model and endpoint; provider-
        # specific generation settings must not cross that boundary either.
        return override or (values.get("MEMSTARA_LLM_" + key.upper(), "").strip() if same_provider else "")

    profile = {"provider": provider, "model": setting("model"), "api_base": setting("api_base")}
    required = ["provider", "model"]
    if profile["provider"] in ("azure_foundry", "local"):
        required.append("api_base")
    for key in required:
        if not profile[key]:
            raise ValueError(
                f"{prefix}{key.upper()} is required (set this agent override or the matching MEMSTARA_LLM_ default)"
            )
    for key, cast in (("temperature", float), ("max_tokens", int)):
        raw = setting(key)
        if raw:
            try:
                profile[key] = cast(raw)
            except ValueError:
                raise ValueError(f"{prefix}{key.upper()} has an invalid numeric value") from None
    effort = setting("effort")
    if effort:
        profile["effort"] = effort
    capabilities_json = setting("capabilities_json")
    if capabilities_json:
        import json

        try:
            profile["resolved_capabilities"] = json.loads(capabilities_json)
        except ValueError:
            raise ValueError("Invalid model capability metadata") from None
    if not profile["api_base"]:
        profile.pop("api_base")
    # Reuse strict profile-value validation without reading other agents or secrets.
    return validate_profiles({r: profile for r in AGENT_ROLES})[role]


def model_profiles(values=None):
    """Expand common defaults and agent overrides into six frozen assignments."""
    from memstara.stage_models import AGENT_ROLES

    return {role: agent_profile(role, values) for role in AGENT_ROLES}


def save_source(directory: Path) -> None:
    """Record source metadata once, without copying configuration or secrets."""
    from memstara.env import configuration_source
    from memstara.pipeline.checkpoint import atomic_json

    path = directory / "operational_source.json"
    if not path.exists():
        atomic_json(path, configuration_source(), overwrite=False)


def database_errors(values: dict) -> list[str]:
    """Validate storage destinations before provisioning or schema mutations."""
    errors = []
    for name in ("MEMSTARA_DATABASE_URL", "MOTORO_DATABASE_URL", "MOTORO_REDIS_URL"):
        if not values.get(name):
            errors.append(f"{name} is required")
    identities = []
    for name in ("MEMSTARA_DATABASE_URL", "MOTORO_DATABASE_URL"):
        try:
            url = urlsplit(values.get(name, ""))
            if url.scheme not in ("postgresql", "postgresql+asyncpg") or not url.hostname or not url.path.strip("/"):
                raise ValueError()
            host = "127.0.0.1" if url.hostname == "localhost" else url.hostname
            identities.append((host, url.port or 5432, url.path))
        except ValueError:
            errors.append(f"{name} must identify a PostgreSQL database")
    if len(identities) == 2 and identities[0] == identities[1]:
        errors.append("Memstara and Motoro must use different databases")
    try:
        redis = urlsplit(values.get("MOTORO_REDIS_URL", ""))
        if redis.scheme not in ("redis", "rediss") or not redis.hostname:
            raise ValueError()
        _ = redis.port
    except ValueError:
        errors.append("MOTORO_REDIS_URL must identify a Redis service")
    return errors


def provider_errors(values, profiles):
    """Validate explicit Bedrock authentication without network or secret output."""
    if not any(p["provider"] == "bedrock" for p in profiles.values()):
        return []
    errors = []

    def present(key):
        value = values.get(key, "").strip()
        return bool(value) and not value.startswith(("YOUR_", "REPLACE_"))

    if not present("AWS_REGION"):
        errors.append("AWS_REGION is required for bedrock")
    bearer = present("AWS_BEARER_TOKEN_BEDROCK")
    access, secret = present("AWS_ACCESS_KEY_ID"), present("AWS_SECRET_ACCESS_KEY")
    session = present("AWS_SESSION_TOKEN")
    if bearer and (access or secret or session):
        errors.append("Choose AWS_BEARER_TOKEN_BEDROCK or AWS access credentials, not both")
    elif not bearer and not (access and secret):
        errors.append("Bedrock requires AWS_BEARER_TOKEN_BEDROCK or both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    return errors


def check(values: dict, *, require_models: bool = True) -> dict:
    """Check infrastructure at startup; require model readiness before execution."""
    errors = database_errors(values)
    for name in PATH_KEYS - set(PATH_DEFAULTS) - {"HF_HUB_CACHE", "MEMSTARA_USER_SKILLS_DIR", "MEMSTARA_INPUTS_DIR"}:
        if values.get(name) and not Path(values[name]).exists():
            errors.append(f"{name} does not exist; correct the selected project .env")
    if values.get("MEMSTARA_STAGE_MODELS_PATH"):
        errors.append("Set model fields in .env and remove unsupported MEMSTARA_STAGE_MODELS_PATH")
    profiles = {}
    if require_models:
        try:
            profiles = model_profiles(values)
        except ValueError as exc:
            errors.append(str(exc))
        errors.extend(provider_errors(values, profiles))
    keys = {
        "azure_foundry": "ANTHROPIC_FOUNDRY_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    for role, profile in profiles.items():
        key = keys.get(profile["provider"])
        if key and (not values.get(key) or values[key].startswith(("YOUR_", "REPLACE_"))):
            errors.append(
                f"{role}: configure the matching MEMSTARA_<PROVIDER>_API_KEY "
                "(or the role provider credential) in the selected source"
            )
    return {
        "configuration_valid": not errors,
        "errors": errors,
        "models": profiles,
        "ports": {k: values.get(k, str(v)) for k, v in PORT_DEFAULTS.items()},
        "database_connection": "not_tested",
        "model_call": "not_tested",
    }


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check",))
    parser.parse_args()
    try:
        values, source = resolve()
        result = check(values)
        print(json.dumps({"source": source, **result}, indent=2))
        return 0 if result["configuration_valid"] else 1
    except (ValueError, OSError):
        # Parser/IO details may contain credential-bearing input: keep this generic.
        print("Configuration unavailable. Check selected .env and values; no values logged.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
