"""MCP model evaluation with run-scoped policy and concurrent native ML jobs.

The synchronous function is also used by offline callers. The registered asynchronous
wrapper keeps the MCP event loop available while scikit-learn/XGBoost perform the fit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from memstara.mcp_servers.debug_hook import quiet_child, wait_for_debugger
from memstara.paths import DEFAULT_OUTPUT_DIR

quiet_child()
wait_for_debugger("memstara-ml")
mcp = FastMCP("memstara-ml")
_DEFAULT_ENGINE = "xgboost"


@mcp.tool(name="list_models")
async def list_models() -> str:
    """List predictive models available through the ML MCP server."""
    return json.dumps([
        {"id": "xgboost", "label": "XGBoost", "library": "xgboost", "explainability": "TreeSHAP"},
        {"id": "random_forest", "label": "Random forest", "library": "scikit-learn",
         "explainability": "permutation importance"},
        {"id": "logistic_regression", "label": "Logistic regression", "library": "scikit-learn",
         "explainability": "permutation importance"},
    ])


def _output_dir() -> Path:
    return Path(os.environ.get("MEMSTARA_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR).resolve()


def _make_model(engine: str, seed: int):
    from memstara.evaluation import model_for
    return model_for(engine, seed)


@mcp.tool()
async def get_ml_configuration(path: str, y_column: str) -> str:
    """Get complete LR/XGBoost parameters and permitted choices before proposing ml_plan.

    The server owns predictor/split identity and resource limits. The ML Agent chooses
    the exposed model parameters, scaling, cutoff, training CV and primary perspective.
    """
    from memstara.evaluation import active_plan
    from memstara.data_allocation import load_effective
    from memstara.ml_configuration import context, enabled, for_dataset
    try:
        p = Path(path).resolve()
        p.relative_to(_output_dir())
        snapshot = active_plan()
        if snapshot is None or not enabled(snapshot):
            return json.dumps({"required": False, "instruction": "Use the frozen single-model run policy."})
        if snapshot['y_column'] != y_column:
            raise ValueError('Target differs from the run target')
        plan, _ = load_effective(p, snapshot, snapshot['evaluation'])
        return json.dumps(context(for_dataset(snapshot, p), plan))
    except Exception as exc:
        return json.dumps({'error': str(exc) if isinstance(exc, ValueError) else type(exc).__name__})


def train_and_score(
    path: str, y_column: str, test_size: float = 0.25, seed: int = 42,
    engine: str = "", folds: int = 0, replicates: int = 1, search_trials: int = 1,
    ml_plan: dict | None = None,
) -> str:
    """Evaluate with the frozen run policy, or explicit options for standalone calls.

    Frozen UI/CLI run settings take precedence over agent-provided options. CV and
    candidate selection use training folds; the hold-out is reserved for evaluation.
    """
    from memstara.evaluation import DataQualityError, active_plan, score, validate
    import hashlib
    import tempfile
    try:
        p = Path(path).resolve()
        try:
            p.relative_to(_output_dir())
        except ValueError:
            return json.dumps({"error": "path is outside the allowed directory"})
        snapshot = active_plan()
        if snapshot and y_column != snapshot["y_column"]:
            raise ValueError("Target differs from the run's fixed target")
        plan = snapshot["evaluation"] if snapshot else {
            "engine": engine or os.environ.get("MEMSTARA_ML_ENGINE", "").strip() or _DEFAULT_ENGINE,
            "seed": seed, "test_size": test_size,
            "folds": folds, "replicates": replicates, "search_trials": search_trials,
        }
        plan = validate(plan)
        from memstara.data_allocation import load_effective
        plan, allocation = load_effective(p, snapshot, plan)
        from memstara.ml_configuration import enabled, resolve as resolve_ml, for_dataset
        plan_resolution = None
        if enabled(snapshot):
            snapshot = for_dataset(snapshot, p)
            # Proposal errors are repairable and cannot start training or freeze a plan.
            ml_plan, plan_resolution = resolve_ml(ml_plan, snapshot, plan)
        elif ml_plan is not None:
            raise ValueError('This frozen run does not support agent-configured paired ML')
        try:
            if enabled(snapshot):
                from memstara.paired_ml import execute
                result = execute(p, y_column, plan, snapshot, ml_plan)
                if result.get('retryable'):
                    return json.dumps(result)
            elif (snapshot or {}).get("comparison_policy"):
                from memstara.comparisons import score_comparisons
                result = score_comparisons(p, y_column, plan, snapshot)
            else:
                result = score(p, y_column, plan)
        except Exception as exc:
            if enabled(snapshot) and isinstance(exc, ValueError):
                raise
            # Never send data values embedded in library exception messages to an LLM.
            detail = str(exc) if isinstance(exc, DataQualityError) else f"Evaluation failed ({type(exc).__name__})"
            result = {"status": "failed", "error": detail,
                      "evaluation": {"dataset_sha256": hashlib.sha256(p.read_bytes()).hexdigest()}}

        if allocation:
            result["data_allocation"] = allocation
        if plan_resolution:
            result['ml_plan_resolution'] = plan_resolution
        result["config_hash"] = snapshot.get("config_hash") if snapshot else None
        result["y_column"] = y_column
        destination = p.with_suffix(".evaluation.json")
        with tempfile.NamedTemporaryFile(mode="w", dir=p.parent, suffix=".json", delete=False) as f:
            json.dump(result, f, allow_nan=False)
            temporary = Path(f.name)
        temporary.replace(destination)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


@mcp.tool(name="train_and_score")
async def train_and_score_async(
    path: str, y_column: str, test_size: float = 0.25, seed: int = 42,
    engine: str = "", folds: int = 0, replicates: int = 1, search_trials: int = 1,
    ml_plan: dict | None = None,
) -> str:
    """Evaluate a model without blocking MCP. Frozen run settings override these options.

    ml_plan: omit when get_ml_configuration returns plan_source=server_frozen.
    Otherwise submit the complete proposal for new paired-model runs.
    Legacy engine: xgboost, random_forest or logistic_regression; empty uses the default.
    folds: training-only stratified CV (0 off, 2-10 enabled).
    replicates: 1-10 seeded splits. search_trials: 1-10 training-CV candidates.
    test_size: reserved hold-out fraction. No cleaning or imputation is performed.
    """
    import asyncio
    return await asyncio.to_thread(
        train_and_score, path, y_column, test_size, seed, engine, folds, replicates, search_trials, ml_plan,
    )


if __name__ == "__main__":
    mcp.run()
