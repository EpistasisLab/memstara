"""Read Azure public meters and account costs; never create or modify resources.

Run `python -m memstara.azure_costs --help`. No model inference is performed.
"""

import argparse
import json
import subprocess
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
    items, seen = [], set()
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


def refresh(mapping):
    from memstara.cost_accounting import catalog_path
    from datetime import timedelta

    data = json.loads(Path(mapping).read_text())
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
    import re

    if not re.fullmatch(r"/subscriptions/[0-9a-fA-F-]+(?:/resourceGroups/[\w.()\-]+)?", scope):
        raise ValueError("Use a subscription or resource-group scope")
    a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if a >= b:
        raise ValueError("End must be after start")
    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {"from": start, "to": end},
        "dataset": {
            "granularity": "Daily",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "ServiceName"}],
        },
    }
    url = "https://management.azure.com" + scope + "/providers/Microsoft.CostManagement/query?api-version=2025-03-01"
    pages = []
    seen = set()
    while url:
        if url in seen or len(seen) >= 100 or urlsplit(url).hostname != "management.azure.com":
            raise ValueError("Invalid cost API pagination")
        seen.add(url)
        result = subprocess.run(
            ["az", "rest", "--method", "post", "--url", url, "--body", json.dumps(body), "--output", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode:
            raise RuntimeError(
                "Azure cost query failed. Check az login and Cost Management read access; no zero assumed."
            )
        page = json.loads(result.stdout)["properties"]
        pages.append(page)
        url = page.get("nextLink")
    totals = {}
    for page in pages:
        names = [c["name"] for c in page["columns"]]
        for row in page["rows"]:
            value = dict(zip(names, row, strict=True))
            currency = value["Currency"]
            totals[currency] = totals.get(currency, 0) + float(value["Cost"])
    output = {
        "status": "retrieved",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "period": {"from": start, "to": end},
        "scope_type": "resource group" if "/resourceGroups/" in scope else "subscription",
        "totals": totals,
        "pages": pages,
        "basis": (
            "Azure reported actual cost for the selected scope and period; "
            "not a final invoice or per-run attribution"
        ),
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(output, indent=2, allow_nan=False))
    temp.replace(path)
    return {"status": "retrieved", "output": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("meters")
    find.add_argument("--filter", required=True)
    find.add_argument("--output", required=True)
    update = commands.add_parser("refresh")
    update.add_argument("--mapping", required=True)
    actual = commands.add_parser("actual")
    actual.add_argument("--scope", required=True)
    actual.add_argument("--start", required=True)
    actual.add_argument("--end", required=True)
    actual.add_argument("--output", default="outputs/runs/azure_costs.json")
    args = parser.parse_args()
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
