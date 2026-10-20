import json
from types import SimpleNamespace
import pytest
from memstara import cost_accounting as accounting
from memstara.azure_costs import normalize_meter, fetch_meters


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    from memstara import pricing_compat  # noqa: F401

    monkeypatch.delenv("MEMSTARA_PRICING_JSON", raising=False)
    profile = {"provider": "openai", "model": "deployment", "api_base": "https://example.test/v1"}
    rate = {
        **profile,
        "billing": "tokens",
        "currency": "USD",
        "source": "https://prices.azure.com/api/retail/prices",
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "valid_from": "2020-01-01T00:00:00+00:00",
        "valid_until": "2099-01-01T00:00:00+00:00",
        "usd_per_million_tokens": {"input": 2, "output": 8, "cache_read": 1},
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"profiles": [rate]}))
    monkeypatch.setenv("MEMSTARA_PRICING_PATH", str(path))
    return profile, rate, path


def test_cached_tokens_are_not_charged_twice(catalog):
    p, _, _ = catalog
    r = accounting.estimate(p, 1000000, 100000, 200000)
    assert r["usd"] == pytest.approx(2.6)
    assert r["components_usd"] == {"input": 1.6, "output": 0.8, "cache_read": 0.2}
    assert len(r["catalog_sha256"]) == 64


def test_wrong_endpoint_expired_price_and_unknown_cache_ttl_are_unpriced(catalog):
    p, r, path = catalog
    assert accounting.estimate({**p, "api_base": "https://other.test"}, 100, 10) is None
    assert accounting.estimate(p, 100, 10, 0, 10) is None
    assert accounting.estimate(p, 100, 10, 101) is None
    r["valid_until"] = "2021-01-01T00:00:00+00:00"
    path.write_text(json.dumps({"profiles": [r]}))
    assert accounting.estimate(p, 100, 10) is None


def test_unknown_failure_is_preserved_without_sensitive_data(tmp_path):
    cfg = SimpleNamespace(provider="openai", model="deployment", api_base="https://secret.example")
    accounting.record_attempt((tmp_path, "agent", "hypothesis0"), 1, cfg, error=True)
    raw = (tmp_path / "cost_ledger.jsonl").read_text()
    r = json.loads(raw)
    assert r["usd"] is None and r["status"] == "unknown"
    assert "secret.example" not in raw


def test_meter_unit_conversion_and_rejection():
    item = {
        "meterId": "id",
        "armRegionName": "eastus",
        "currencyCode": "USD",
        "type": "Consumption",
        "tierMinimumUnits": 0,
        "effectiveStartDate": "2020-01-01T00:00:00Z",
        "unitOfMeasure": "1K",
        "retailPrice": 0.0025,
    }
    assert normalize_meter([item], "id", "eastus")[0] == 2.5
    with pytest.raises(ValueError):
        normalize_meter([item], "id", "westus")
    with pytest.raises(ValueError):
        normalize_meter([item, item], "id", "eastus")
    with pytest.raises(ValueError):
        normalize_meter([{**item, "unitOfMeasure": "1 Hour"}], "id", "eastus")


def test_retail_pagination_is_complete_and_rejects_foreign_hosts():
    pages = iter([{"Items": [1], "NextPageLink": "https://prices.azure.com/api/retail/prices?page=2"}, {"Items": [2]}])
    assert fetch_meters("fixture", lambda _: next(pages)) == [1, 2]
    with pytest.raises(ValueError):
        fetch_meters("fixture", lambda _: {"Items": [], "NextPageLink": "https://evil.test/"})


def test_cost_ui_keeps_unknown_calls_partial(tmp_path, monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewer/api"))
    import cost_details

    monkeypatch.setattr(cost_details.run_artifacts, "directory_for", lambda tag: tmp_path)
    monkeypatch.setattr(cost_details.run_artifacts, "lookup", lambda tag: {"calls": [{"llm_requests": 2}]})
    (tmp_path / "pipeline_status.json").write_text('{"status":"completed"}')
    rows = [
        {"id": "a", "status": "estimated", "usd": 0.4, "stage": "ml", "model": "x"},
        {"id": "b", "status": "unknown", "usd": 0, "stage": "ml", "model": "x"},
    ]
    (tmp_path / "cost_ledger.jsonl").write_text("\n".join(map(json.dumps, rows + rows)))
    r = cost_details.details("run")
    assert r["usd"] == 0.4 and r["status"] == "partial" and r["recorded_calls"] == 2
    assert r["unpriced_calls"] == 1
    (tmp_path / "cost_ledger.jsonl").unlink()
    assert cost_details.details("run")["status"] == "unavailable"


def test_azure_query_preserves_currency_and_existing_snapshot_on_failure(tmp_path, monkeypatch):
    import subprocess
    from memstara import azure_costs

    page = {
        "properties": {
            "columns": [{"name": "Cost"}, {"name": "Currency"}, {"name": "ServiceName"}],
            "rows": [[1.25, "USD", "Foundry"], [2.0, "EUR", "Marketplace"]],
        }
    }
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(page)))
    dest = tmp_path / "azure.json"
    azure_costs.query_costs("/subscriptions/1234", "2026-10-07T00:00:00Z", "2026-10-08T00:00:00Z", dest)
    before = dest.read_bytes()
    assert json.loads(before)["totals"] == {"USD": 1.25, "EUR": 2.0}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=""))
    with pytest.raises(RuntimeError):
        azure_costs.query_costs("/subscriptions/1234", "2026-10-07T00:00:00Z", "2026-10-08T00:00:00Z", dest)
    assert dest.read_bytes() == before


@pytest.mark.parametrize("amount,status", [(None,"unknown"),(0.0,"unknown"),(.125,"estimated")])
def test_runtime_records_motoro_amount_without_local_receipts(tmp_path, amount, status):
    token = accounting.price_receipt.set({"usd": 999, "source": "stale-local-rate"})
    try:
        config = SimpleNamespace(provider="openai", model="model")
        record = SimpleNamespace(cost_estimate=amount, pricing_source="litellm")
        accounting.record_attempt((tmp_path,"agent","ml"), 1, config, record)
        row = json.loads((tmp_path / "cost_ledger.jsonl").read_text())
        assert row["usd"] == (amount if status == "estimated" else None)
        assert row["reported_cost_estimate"] == amount
        assert row["status"] == status
        assert row["price_receipt"] is None
        assert row["calculated_by"] == "motoro"
    finally:
        accounting.price_receipt.reset(token)


def test_custom_pricing_requires_explicit_configuration(monkeypatch, tmp_path):
    from memstara.cost_accounting import catalog_path, estimate

    monkeypatch.delenv("MEMSTARA_PRICING_PATH", raising=False)
    monkeypatch.delenv("MEMSTARA_PRICING_JSON", raising=False)
    monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(tmp_path))
    assert catalog_path() is None
    assert estimate({"provider": "openai", "model": "example"}, 100, 10) is None


def test_inline_rates_work_after_source_file_removed(catalog, monkeypatch):
    profile, _, path = catalog
    monkeypatch.setenv("MEMSTARA_PRICING_JSON", path.read_text())
    monkeypatch.delenv("MEMSTARA_PRICING_PATH")
    path.unlink()
    result = accounting.estimate(profile, 1000000, 100000, 200000)
    assert result["usd"] == pytest.approx(2.6)
    assert len(result["catalog_sha256"]) == 64


def test_meter_refresh_reads_env_mapping_and_writes_generated_catalog(tmp_path, monkeypatch):
    from memstara import azure_costs

    mapping = {
        "profiles": [
            {
                "provider": "openai",
                "model": "deployment",
                "api_base": "https://example.test/v1",
                "region": "eastus",
                "meters": {
                    "input": "00000000-0000-0000-0000-000000000001",
                    "output": "00000000-0000-0000-0000-000000000002",
                },
            }
        ]
    }
    monkeypatch.setenv("MEMSTARA_AZURE_PRICING_METERS_JSON", json.dumps(mapping))
    monkeypatch.setenv("MEMSTARA_PRICING_PATH", str(tmp_path / "outputs/pricing/catalog.json"))
    monkeypatch.setattr(azure_costs, "fetch_meters", lambda query: [])
    monkeypatch.setattr(azure_costs, "normalize_meter", lambda items, meter, region: (2.0, {"meterId": meter}))
    result = azure_costs.refresh()
    assert result["profiles"] == 1
    assert not (tmp_path / "config").exists()
    assert accounting.estimate(mapping["profiles"][0], 1000000, 0)["usd"] == 2.0
