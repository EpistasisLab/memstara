"""Deterministic pre-training feasibility critic; never judges biological truth."""

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, UTC

VERSION = "deterministic_feasibility_v1"


def assess(columns, plan):
    reasons = []
    if not columns:
        reasons.append("no_predictors")
    if len(columns) != len(set(columns)):
        reasons.append("duplicate_predictors")
    if plan.get("y_column") in columns:
        reasons.append("target_as_predictor")
    context = plan.get("feature_context", {}).get("features")
    if context is not None:
        allowed = {r["column"] for r in context}
        if set(columns) - allowed:
            reasons.append("unknown_predictors")
    baseline = set(plan.get("comparison_policy", {}).get("baseline_columns", []))
    if columns and baseline and set(columns) <= baseline:
        reasons.append("no_incremental_predictors_beyond_fixed_baseline")
    return {
        "version": VERSION,
        "verdict": "rejected" if reasons else "accepted",
        "reason_codes": reasons,
        "predictor_count": len(columns),
        "scope": "Structural feasibility for incremental discovery; not clinical or causal validation",
    }


def review(columns, plan, question_id, trial):
    if (plan or {}).get("critic_policy", {}).get("version") != VERSION:
        return None
    decision = assess(columns, plan)
    config = os.environ.get("MEMSTARA_RUN_CONFIG")
    if not config:
        raise ValueError("Critic requires a run audit location")
    event = {
        **decision,
        "run_tag": plan["run_tag"],
        "config_hash": plan["config_hash"],
        "question_id": question_id,
        "trial": trial,
        "time": datetime.now(UTC).isoformat(),
        "predictor_sha256": hashlib.sha256(json.dumps(columns).encode()).hexdigest(),
    }
    payload = (json.dumps(event) + "\n").encode()
    fd = os.open(Path(config).parent / "critic_decisions.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError("Incomplete critic audit")
    finally:
        os.close(fd)
    return decision
