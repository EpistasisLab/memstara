"""Offline design preview for the temporary agent-combinations pilot.

This module never provisions agents, connects to a database or starts a run.
Unresolved design choices remain explicit; a requested total is not a schedule.
"""

from __future__ import annotations

import argparse
from itertools import product
import json
from pathlib import Path


def draft() -> dict:
    return {
        "version": 1,
        "study_id": "agent-combinations-pilot",
        "requested_combinations": 64,
        "repetitions": 1,
        "feature_bounds": [4, 20],
        "feature_policy": None,
        "data_variants": None,
        "ml_layout": None,
        "hypothesis_variants": ["guided", "random"],
        "interpretation_variants": ["shap", "lime"],
        "explanation_variants": ["addiction", "hiv"],
        "llm": {
            "hypothesis": "non_explanation_agents",
            "data": "non_explanation_agents",
            "ml": "non_explanation_agents",
            "interpreter": "non_explanation_agents",
            "report": "explanation_agent",
        },
        "model_deployments": {"non_explanation_agents": None, "explanation_agent": None},
        "required_skills": {"shap": None, "lime": None, "addiction": None, "hiv": None},
        "knowledge_bindings": {"addiction": None, "hiv": None},
        "ml_configuration_owner": "llm",
        "interpretation_requires_both_models": True,
        "isolation": {
            "output_root": "outputs/experiments/agent-combinations-pilot",
            "memory_namespace": None,
            "seed": None,
        },
    }


def preview(plan: dict) -> dict:
    """Count actual factors; never manufacture a sixth binary factor to reach 64."""
    if plan.get("version") != 1 or plan.get("feature_bounds") != [4, 20]:
        raise ValueError("Expected version 1 with feature bounds [4, 20]")
    if plan.get("repetitions") != 1:
        raise ValueError("This pilot requires exactly one repetition")
    feature = plan.get("feature_policy")
    if feature not in (None, "range", "endpoints"):
        raise ValueError("feature_policy must be range or endpoints")
    data = plan.get("data_variants")
    if data not in (None, ["training_heavy", "balanced_stratified"], ["training_heavy", "balanced", "stratified"]):
        raise ValueError("Resolve the two-skill or three-skill data design")
    layout = plan.get("ml_layout")
    if layout not in (None, "paired", "separate"):
        raise ValueError("ml_layout must be paired or separate")
    blockers = [key for key in ("feature_policy", "data_variants", "ml_layout") if plan.get(key) is None]
    for group in ("model_deployments", "required_skills", "knowledge_bindings"):
        blockers.extend(f"{group}.{key}" for key, value in plan[group].items() if not value)
    blockers.extend(f"isolation.{key}" for key in ("memory_namespace", "seed") if plan["isolation"].get(key) is None)
    rows = []
    if feature and data and layout:
        sizes = ["range_4_20"] if feature == "range" else [4, 20]
        models = [["logistic_regression", "xgboost"]] if layout == "paired" else [["logistic_regression"], ["xgboost"]]
        for index, (hyp, size, split, estimators, interpretation, explanation) in enumerate(
            product(
                plan["hypothesis_variants"],
                sizes,
                data,
                models,
                plan["interpretation_variants"],
                plan["explanation_variants"],
            ),
            1,
        ):
            rows.append(
                {
                    "combination": index,
                    "hypothesis": hyp,
                    "feature_size": size,
                    "data_skill": split,
                    "estimators": estimators,
                    "interpretation": interpretation,
                    "explanation": explanation,
                    "repetition": 1,
                }
            )
        if len(rows) != plan["requested_combinations"]:
            blockers.append("requested_combination_count_mismatch")
        if layout == "separate" and plan["interpretation_requires_both_models"]:
            blockers.append("cross_model_interpretation_join_not_defined")
    # This is a design calculator, not an execution adapter. Never imply otherwise.
    blockers.append("specialist_execution_config_required")
    return {
        "status": "design_only",
        "execution_ready": False,
        "actual_combinations": len(rows) if rows else None,
        "blockers": blockers,
        "candidate_schedule": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, help="Read an existing JSON draft")
    parser.add_argument("--output", type=Path, required=True, help="New local design artifact; never overwrites")
    args = parser.parse_args()
    loaded = json.loads(args.plan.read_text()) if args.plan else draft()
    plan = loaded.get("plan", loaded)
    result = {"plan": plan, "preview": preview(plan)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                "artifact": str(args.output),
                "status": result["preview"]["status"],
                "actual_combinations": result["preview"]["actual_combinations"],
                "blockers": result["preview"]["blockers"],
            }
        )
    )


if __name__ == "__main__":
    main()
