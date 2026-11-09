"""Durable per-agent records; legacy aggregate files remain readable snapshots."""

import json
from pathlib import Path
from uuid import UUID


def save_call(root, call):
    from memstara.pipeline.checkpoint import atomic_json

    directory = Path(root) / "call_records"
    directory.mkdir(mode=0o700, exist_ok=True)
    identifier = str(UUID(call["run_id"]))
    atomic_json(directory / f"{identifier}.json", call)


def load_calls(root):
    root = Path(root)
    baseline = root / "calls_checkpoint.json"
    if not baseline.exists():
        baseline = root / "runs.json"
    calls = json.loads(baseline.read_text()) if baseline.exists() else []
    records = {call.get("run_id", f"legacy-{index}"): call for index, call in enumerate(calls)}
    for path in sorted((root / "call_records").glob("*.json")):
        call = json.loads(path.read_text())
        if str(UUID(call["run_id"])) != path.stem:
            raise ValueError("Call journal identity changed")
        records[call["run_id"]] = call
    return sorted(records.values(), key=lambda c: (c.get("started_at") or 0, c.get("seq") or 0, c.get("run_id", "")))
