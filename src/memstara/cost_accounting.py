"""Auditable local estimates; no remote requests in the inference path."""

import hashlib
import json
import math
import os
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

request_profile = ContextVar("pricing_request_profile", default=None)
price_receipt = ContextVar("pricing_receipt", default=None)


def catalog_path():
    return Path(
        os.environ.get("MEMSTARA_PRICING_PATH", str(Path(__file__).resolve().parents[2] / "config/pricing.local.json"))
    )


def estimate(profile, prompt, output, cached=0, written=0):
    """Normalized LiteLLM prompt count includes cached input. Never guess TTL prices."""
    path = catalog_path()
    try:
        raw = path.read_bytes()
        catalog = json.loads(raw)
        matches = [
            p for p in catalog["profiles"] if all(p.get(k) == profile.get(k) for k in ("provider", "model", "api_base"))
        ]
        if len(matches) != 1:
            return None
        rate = matches[0]
        if rate.get("billing") != "tokens" or rate.get("currency") != "USD":
            return None
        if not rate.get("source") or not rate.get("retrieved_at"):
            return None
        now = datetime.now(UTC)
        if not datetime.fromisoformat(rate["valid_from"]) <= now < datetime.fromisoformat(rate["valid_until"]):
            return None
        if any(type(n) is not int or n < 0 for n in (prompt, output, cached, written)):
            return None
        # Cache writes may have 5-minute or 1-hour rates. Aggregate counts lack TTL.
        if written or cached > prompt:
            return None
        units = {"input": prompt - cached, "output": output, "cache_read": cached}
        rates = rate["usd_per_million_tokens"]
        parts = {}
        for kind, count in units.items():
            if not count:
                parts[kind] = 0.0
                continue
            price = rates[kind]
            if type(price) not in (float, int) or not math.isfinite(price) or price < 0:
                return None
            parts[kind] = count * price / 1_000_000
        return {
            "usd": sum(parts.values()),
            "components_usd": parts,
            "rates": rates,
            "source": rate["source"],
            "retrieved_at": rate["retrieved_at"],
            "valid_from": rate["valid_from"],
            "valid_until": rate["valid_until"],
            "catalog_sha256": hashlib.sha256(raw).hexdigest(),
            "basis": "configured deployment rates",
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None


def record_attempt(context, loop, config, record=None, error=False):
    from memstara.pipeline.diagnostics import request_id
    if not context:
        return
    receipt = price_receipt.get()
    source = getattr(record, "pricing_source", "unavailable")
    amount = getattr(record, "cost_estimate", None)
    known = (
        record is not None
        and source != "unavailable"
        and isinstance(amount, (int, float))
        and math.isfinite(amount)
        and amount >= 0
    )
    # Generic catalogs are estimates, not verified Azure contract prices.
    if amount == 0 and not receipt:
        known = False
    row = {
        "id": str(uuid4()),
        "request_id": request_id.get(),
        "at": datetime.now(UTC).isoformat(),
        "agent_run_id": str(context[1]),
        "stage": context[2],
        "loop": loop,
        "provider": getattr(getattr(config, "provider", None), "value", getattr(config, "provider", None)),
        "model": config.model,
        "response_model": getattr(record, "model", None),
        "status": "unknown" if not known else "estimated",
        "usd": amount if known else None,
        "currency": "USD",
        "source": source,
        "price_receipt": receipt,
        "reason": "Request failed; provider may still bill usage"
        if error
        else ("Price or complete usage unavailable" if not known else None),
        "prompt_tokens": getattr(record, "prompt_tokens", None),
        "completion_tokens": getattr(record, "completion_tokens", None),
        "cache_read_input_tokens": getattr(record, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(record, "cache_creation_input_tokens", None),
    }
    # No prompts, credentials, endpoint URLs or patient data in this ledger.
    try:
        with (Path(context[0]) / "cost_ledger.jsonl").open("a") as stream:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
    except (OSError, ValueError, TypeError):
        import logging

        logging.getLogger(__name__).warning("Cost ledger write failed; cost coverage is incomplete")
