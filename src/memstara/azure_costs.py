"""Legacy offline public-meter inspection; direct account billing is disabled.

Run `python -m memstara.azure_costs --help`. No model inference is performed.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

RETAIL = "https://prices.azure.com/api/retail/prices"


def fetch_meters(query, fetch=None):
    def get(url):
        with urlopen(url, timeout=30) as response:
            return json.load(response)

    fetch = fetch or get
    url = RETAIL + "?" + urlencode({"$filter": query, "currencyCode": "USD"})
    items = []
    seen: set[str] = set()
    while url:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "prices.azure.com" or parsed.path != "/api/retail/prices":
            raise ValueError("Unexpected retail API pagination destination")
        if url in seen or len(seen) >= 100:
            raise ValueError("Retail API pagination did not complete")
        seen.add(url)
        page = fetch(url)
        items.extend(page["Items"])
        url = page.get("NextPageLink")
    return items


def normalize_meter(items, meter_id, region, now=None):
    now = now or datetime.now(UTC)
    matches = [
        x
        for x in items
        if x.get("meterId") == meter_id
        and x.get("armRegionName") == region
        and x.get("currencyCode") == "USD"
        and x.get("type") == "Consumption"
        and x.get("tierMinimumUnits") == 0
        and datetime.fromisoformat(x["effectiveStartDate"].replace("Z", "+00:00")) <= now
    ]
    if not matches:
        raise ValueError("No current exact meter/region match; no guessed price saved")
    latest = max(x["effectiveStartDate"] for x in matches)
    matches = [x for x in matches if x["effectiveStartDate"] == latest]
    if len(matches) != 1:
        raise ValueError("Ambiguous meter price; review deployment and meter mapping")
    item = matches[0]
    factor = {"1K": 1000, "1M": 1}.get(item["unitOfMeasure"])
    if factor is None:
        raise ValueError("Meter is not a supported token unit; hourly compute is not a token rate")
    import math

    rate = item["retailPrice"] * factor
    if not math.isfinite(rate) or rate < 0:
        raise ValueError("Invalid meter price")
    return rate, item


def refresh(mapping=None):
    from memstara.cost_accounting import catalog_path
    from datetime import timedelta

    import os

    data = json.loads(
        Path(mapping).read_text() if mapping else os.environ.get("MEMSTARA_AZURE_PRICING_METERS_JSON", "{}")
    )
    if not isinstance(data, dict) or not data.get("profiles"):
        raise ValueError("Configure MEMSTARA_AZURE_PRICING_METERS_JSON")
    if catalog_path() is None:
        raise ValueError("Set MEMSTARA_PRICING_PATH to an output catalog path before refresh")
    profiles = []
    for profile in data["profiles"]:
        rates, evidence = {}, {}
        if not {"input", "output"} <= profile["meters"].keys():
            raise ValueError("Input and output meters are required")
        for kind, meter_id in profile["meters"].items():
            if kind not in ("input", "output", "cache_read"):
                raise ValueError("Unsupported token category")
            import uuid

            uuid.UUID(meter_id)
            items = fetch_meters("meterId eq '" + meter_id + "'")
            rates[kind], evidence[kind] = normalize_meter(items, meter_id, profile["region"])
        now = datetime.now(UTC)
        profiles.append(
            {
                **{k: profile[k] for k in ("provider", "model", "api_base")},
                "billing": "tokens",
                "currency": "USD",
                "usd_per_million_tokens": rates,
                "source": RETAIL,
                "retrieved_at": now.isoformat(),
                "valid_from": now.isoformat(),
                "valid_until": (now + timedelta(days=7)).isoformat(),
                "meter_evidence": evidence,
            }
        )
    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    identities = {(p["provider"], p["model"], p["api_base"]) for p in profiles}
    previous = json.loads(path.read_text())["profiles"] if path.exists() else []
    profiles = [p for p in previous if (p["provider"], p["model"], p["api_base"]) not in identities] + profiles
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "profiles": profiles}, indent=2))
    temporary.replace(path)
    return {"profiles": len(profiles), "catalog": str(path), "basis": "Undiscounted Azure retail estimate"}


def query_costs(scope, start, end, destination):
    """Retired entry point; never contact Azure or replace historical receipts."""
    raise RuntimeError("Direct Azure billing queries are disabled. Cost information must come from Motoro.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("meters")
    find.add_argument("--filter", required=True)
    find.add_argument("--output", required=True)
    update = commands.add_parser("refresh")
    update.add_argument("--mapping", help="Optional legacy mapping file; otherwise read project .env")
    actual = commands.add_parser("actual")
    actual.add_argument("--scope", required=True)
    actual.add_argument("--start", required=True)
    actual.add_argument("--end", required=True)
    actual.add_argument("--output", default="outputs/runs/azure_costs.json")
    args = parser.parse_args()
    from memstara.env import load_env

    load_env()
    if args.command == "meters":
        items = fetch_meters(args.filter)
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"source": RETAIL, "retrieved_at": datetime.now(UTC).isoformat(), "items": items}, indent=2)
        )
        print(json.dumps({"meters": len(items), "output": str(path)}))
    elif args.command == "refresh":
        print(json.dumps(refresh(args.mapping)))
    else:
        print(json.dumps(query_costs(args.scope, args.start, args.end, args.output)))


if __name__ == "__main__":
    main()
