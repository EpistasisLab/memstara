"""Expose Motoro's provider/schema/catalog metadata, without a second model registry."""

from __future__ import annotations

from typing import Any

LABELS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "azure_foundry": "Azure Foundry",
    "openrouter": "OpenRouter",
    "local": "Local / self-hosted",
    "bedrock": "Amazon Bedrock",
}
ALIASES = {"azure_foundry", "local", "bedrock"}


def choices(provider):
    from motoro.services.model_capabilities import CATALOG

    rows = []
    for entry in CATALOG:
        if provider not in ALIASES | {"openrouter", entry.provider}:
            continue
        rows.append(
            {
                "id": f"{entry.provider}:{entry.model}",
                "label": entry.label,
                "model": f"{entry.provider}/{entry.model}" if provider == "openrouter" else entry.model,
                "capabilities": entry.capabilities.model_dump(mode="json"),
            }
        )
    return rows


def catalog():
    from importlib.metadata import version
    from motoro.schemas.agent import LLMProvider, ModelConfig
    from motoro.services.model_capabilities import DEFAULT_CAPABILITIES

    schema = ModelConfig.model_json_schema()
    if "$ref" in schema:
        schema = schema["$defs"][schema["$ref"].rsplit("/", 1)[-1]]
    schema = schema["properties"]
    controls = {}
    for key in ("temperature", "max_tokens"):
        # Nullable controls keep their numeric bounds inside anyOf in Motoro 0.13.
        numeric: dict[str, Any] = next(
            (part for part in schema[key].get("anyOf", []) if part.get("type") in ("number", "integer")), {}
        )
        fields = {**schema[key], **numeric}
        controls[key] = {
            field: fields[field] for field in ("default", "minimum", "maximum", "exclusiveMinimum") if field in fields
        }
    return {
        "source": "motoro",
        "version": version("motoro"),
        "controls": controls,
        "default_capabilities": DEFAULT_CAPABILITIES.model_dump(mode="json"),
        "providers": [
            {
                "id": p.value,
                "label": LABELS.get(p.value, p.value),
                "custom_model_name": p.value in ALIASES,
                "can_list_models": p.value in ("openai", "anthropic", "openrouter", "local"),
                "models": choices(p.value),
            }
            for p in LLMProvider
        ],
    }


def capabilities(provider, model, catalog_id=""):
    from motoro.services.model_capabilities import get_capabilities

    if catalog_id:
        entry = next((row for row in choices(provider) if row["id"] == catalog_id), None)
        if entry is None:
            raise ValueError("Choose a model from the current Motoro catalog")
        if provider not in ALIASES and model != entry["model"]:
            raise ValueError("The selected model differs from its Motoro catalog entry")
        return entry["capabilities"]
    return get_capabilities(model).model_dump(mode="json")


def validate_settings(settings, caps):
    import math
    from motoro.schemas.agent import ModelConfig
    from motoro.services.sampling import resolve_sampling

    if not isinstance(settings, dict) or set(settings) - {"temperature", "effort", "max_tokens"}:
        raise ValueError("Unsupported advanced model settings")
    if "temperature" in settings:
        if not caps["supports_temperature"]:
            raise ValueError("Temperature support is not confirmed for this model")
        if type(settings["temperature"]) not in (float, int) or not math.isfinite(settings["temperature"]):
            raise ValueError("Temperature must be a finite number")
    if "max_tokens" in settings and type(settings["max_tokens"]) is not int:
        raise ValueError("Maximum output tokens must be a whole number")
    try:
        ModelConfig(**settings, resolved_capabilities=caps)
        resolve_sampling(caps, temperature=settings.get("temperature"), effort=settings.get("effort"))
    except Exception:
        raise ValueError("Advanced model settings are outside the Motoro limits") from None
    return dict(settings)


def list_provider_models(value):
    """Read a provider's model list, not inference. Keys never enter URLs or responses.

    Azure deployment discovery needs a management/project identity beyond the
    inference key; Bedrock model discovery also needs distinct AWS permissions.
    Those providers use explicit deployment/profile IDs with Motoro family choices.
    """
    import json
    import re
    import time
    from urllib.error import HTTPError
    from urllib.parse import urlencode
    from urllib.request import Request, HTTPRedirectHandler, build_opener
    from memstara.model_connections import validate

    data = validate({**value, "model": "catalog-list"})
    provider = data["provider"]
    urls = {
        "openai": "https://api.openai.com/v1/models",
        "anthropic": "https://api.anthropic.com/v1/models",
        "openrouter": "https://openrouter.ai/api/v1/models",
        "local": data["api_base"].rstrip("/") + "/models",
    }
    if provider not in urls:
        raise ValueError("Enter the deployment or inference-profile ID for this provider")
    headers = (
        {"x-api-key": data["api_key"], "anthropic-version": "2023-06-01"}
        if provider == "anthropic"
        else {"Authorization": "Bearer " + data["api_key"]}
        if data["api_key"]
        else {}
    )

    class NoRedirects(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None  # Never forward a credential to a redirected host.

    client = build_opener(NoRedirects)
    models, seen, cursor = [], set(), ""
    deadline = time.monotonic() + 25
    truncated = False
    for _ in range(20):
        query = (
            "?" + urlencode({"limit": 100, **({"after_id": cursor} if cursor else {})})
            if provider == "anthropic"
            else ""
        )
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                truncated = True
                break
            with client.open(Request(urls[provider] + query, headers=headers), timeout=min(10, remaining)) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError()
            body = json.loads(raw)
            rows = body["data"]
            if not isinstance(rows, list):
                raise ValueError()
        except HTTPError as error:
            message = (
                "Model list access denied. Check the API key and provider permissions."
                if error.code in (401, 403)
                else "The provider could not return its model list. You can still enter a model ID."
            )
            raise ValueError(message) from None
        except Exception:
            raise ValueError("Could not load models. Check the connection, or enter a model ID.") from None
        for row in rows:
            model = row.get("id", "") if isinstance(row, dict) else ""
            if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,200}", model) or model in seen:
                continue
            seen.add(model)
            models.append({"model": model, "label": model, "capabilities": capabilities(provider, model)})
        truncated = bool(body.get("has_more"))
        next_cursor = body.get("last_id")
        if provider != "anthropic" or not truncated or not isinstance(next_cursor, str) or next_cursor == cursor:
            break
        cursor = next_cursor
    return {
        "source": "provider",
        "models": sorted(models, key=lambda row: row["model"]),
        "truncated": truncated,
        "note": "Listed by your provider. Check & use model confirms that it works with Motoro.",
    }
