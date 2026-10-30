"""Paired feature-group comparisons, derived from the persisted question mapping.

Only the blackboard data handoff writes the context. The ML tool cannot choose
baseline columns or reinterpret the question's concept groups. No patient rows
are included in the artifact returned to agents.
"""

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def validate_baseline(columns, target, dataset=None):
    if not isinstance(columns, list) or any(not isinstance(c, str) for c in columns):
        raise ValueError("Baseline columns must be an array of nonempty exact column names")
    columns = list(dict.fromkeys(c.strip() for c in columns if c.strip()))
    if target in columns:
        raise ValueError("The prediction target cannot be a baseline predictor")
    if dataset is not None:
        with Path(dataset).open(newline="", encoding="utf-8-sig") as stream:
            header = next(csv.reader(stream), [])
        if any(c not in header for c in columns):
            raise ValueError("A baseline predictor is not present in the configured dataset")
    return columns


def write_context(subset_path, task, snapshot, *, data_allocation=None):
    from memstara.paths import DEFAULT_OUTPUT_DIR

    path = Path(subset_path).resolve()
    path.relative_to(Path(os.environ.get("MEMSTARA_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR).resolve())
    evaluation = task.get("evaluation") or {}
    if isinstance(evaluation, str):
        evaluation = json.loads(evaluation)
    columns = task["columns"]
    if isinstance(columns, str):
        columns = json.loads(columns)
    from memstara.pipeline.feature_selection import validate as validate_selection

    selected = validate_selection(columns, snapshot, task.get("trial"))
    if selected and evaluation.get("feature_selection") != selected:
        raise ValueError("Task feature selection provenance changed before training")
    baseline = validate_baseline(snapshot["comparison_policy"]["baseline_columns"], task["y_column"])
    groups: dict[str, list[str]] = {}
    for row in evaluation.get("feature_mapping", []):
        if row.get("column") in columns:
            groups.setdefault(row["concept"], []).append(row["column"])
    # Older contracts without mappings are explicit single-column groups.
    for column in columns:
        if not any(column in members for members in groups.values()):
            groups[f"Column: {column}"] = [column]
    with path.open(newline="", encoding="utf-8-sig") as stream:
        header = next(csv.reader(stream), [])
    if set(header) != set(columns + baseline + [task["y_column"]]) or len(header) != len(set(header)):
        raise ValueError("Extract exactly the hypothesis predictors, fixed baseline and target")
    existing = path.with_suffix(".comparison.json")
    if existing.exists():
        recorded = json.loads(existing.read_text()).get("data_allocation")
        if recorded is not None and recorded != data_allocation:
            raise ValueError("Accepted Data allocation cannot be changed on retry")
    selection_record = None
    if selected:
        from memstara.feature_reproduction import record_extraction

        selection_record = record_extraction(task, snapshot, selected)
    payload = {
        "trial": task.get("trial", 0),
        "data_allocation": data_allocation,
        "feature_selection": selection_record,
        "version": "paired_groups_v1",
        "config_hash": snapshot["config_hash"],
        "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "target": task["y_column"],
        "baseline_columns": baseline,
        "hypothesis_columns": columns,
        "groups": groups,
    }
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, suffix=".json", delete=False) as f:
        json.dump(payload, f, allow_nan=False)
        temporary = Path(f.name)
    temporary.replace(path.with_suffix(".comparison.json"))


def score_comparisons(path, target, plan, snapshot, *, configuration=None, xai_request=None):
    from memstara.evaluation import score, evaluation_splits, validate_clean_dataset

    context = json.loads(path.with_suffix(".comparison.json").read_text())
    if (
        context.get("config_hash") != snapshot["config_hash"]
        or context.get("target") != target
        or context.get("dataset_sha256") != hashlib.sha256(path.read_bytes()).hexdigest()
        or context.get("baseline_columns") != snapshot["comparison_policy"]["baseline_columns"]
    ):
        raise ValueError("Comparison context does not match the frozen task")
    baseline = context["baseline_columns"]
    full = list(dict.fromkeys(baseline + context["hypothesis_columns"]))
    # Choose HP on full-model training folds, then freeze them for every variant.
    # The test split is never used for candidate selection.
    result = score(path, target, plan, predictors=full, configuration=configuration, xai_request=xai_request)
    reference = result["evaluation"]["replicates"]
    trials = [r["selected_trial"] for r in reference]
    variants = []
    cache = {tuple(sorted(full)): result}

    def evaluate(key, label, columns, removed=None):
        item = {"id": key, "label": label, "features": columns, "removed_features": removed or []}
        measured: dict[str, Any]
        try:
            signature = tuple(sorted(columns))
            if not columns:
                # An empty clinical baseline is explicitly an intercept reference.
                # Constant training prevalence yields ROC AUC .5 on binary test sets.
                frame = validate_clean_dataset(path, target, allow_missing=plan["engine"] == "xgboost")
                runs = [
                    {
                        "seed": seed,
                        "split_id": hashlib.sha256(test.tobytes()).hexdigest(),
                        "auc": 0.5,
                        "training_prevalence": float(frame[target].iloc[train].mean()),
                        "n_train": len(train),
                        "n_test": len(test),
                    }
                    for seed, train, test in evaluation_splits(frame[target], plan)
                ]
                measured = {"auc": 0.5, "evaluation": {"replicates": runs}}
                item["method"] = "training_prevalence_only"
            else:
                if signature not in cache:
                    cache[signature] = score(
                        path,
                        target,
                        plan,
                        predictors=columns,
                        fixed_trials=trials,
                        explain=False,
                        configuration=configuration,
                    )
                measured = cache[signature]
                item["method"] = plan["engine"]
            runs = measured["evaluation"]["replicates"]
            if [(r["seed"], r["split_id"]) for r in runs] != [(r["seed"], r["split_id"]) for r in reference]:
                raise ValueError("Unpaired comparison splits")
            item.update(
                status="completed",
                auc=measured["auc"],
                replicates=runs,
                delta_from_full=measured["auc"] - result["auc"],
            )
        except Exception as exc:
            # Keep the completed main evaluation when an auxiliary fit fails.
            item.update(status="failed", error_type=type(exc).__name__)
        variants.append(item)
        return item

    label = "Clinical baseline" if baseline else "Prevalence reference (no clinical baseline)"
    base = evaluate("baseline", label, baseline)
    expanded = evaluate("expanded", "Baseline + hypothesis predictors", full)
    if base["status"] == "completed":
        expanded["delta_from_baseline"] = expanded["auc"] - base["auc"]
        expanded["paired_deltas"] = [r["auc"] - b["auc"] for r, b in zip(reference, base["replicates"], strict=True)]
    for index, (concept, columns) in enumerate(context["groups"].items()):
        removable = [c for c in dict.fromkeys(columns) if c not in baseline]
        if not removable:
            variants.append(
                {
                    "id": f"ablation_{index}",
                    "label": f"Without {concept}",
                    "status": "not_applicable",
                    "features": full,
                    "removed_features": [],
                    "reason": "Group is already in the fixed baseline",
                }
            )
            continue
        evaluate(f"ablation_{index}", f"Without {concept}", [c for c in full if c not in removable], removable)
    result["comparison"] = {
        "version": "paired_groups_v1",
        "status": "partial" if any(v["status"] == "failed" for v in variants) else "completed",
        "baseline_configured": bool(baseline),
        "baseline_columns": baseline,
        "groups": context["groups"],
        "variants": variants,
        "parameters_policy": "Full-model training-CV selection, then frozen across variants per replicate",
        "scope": "Adaptive exploratory comparison; not independent validation or evidence of causality",
        "timing_status": snapshot["comparison_policy"].get("timing_status", "unverified"),
        "interpretation_limit": snapshot["comparison_policy"].get(
            "interpretation_limit", "Predictor timing has not been verified. Not validated prospective prediction."
        ),
        "baseline_source": snapshot["comparison_policy"].get("baseline_source", "historical_configuration"),
        "study_policy_sha256": snapshot["comparison_policy"].get("study_policy_sha256"),
        "group_policy": "Remove all mapped non-baseline columns for each concept, including shared columns; "
        "effects are not additive",
        "validation_reserve": result["evaluation"].get("validation_reserve"),
    }
    return result
