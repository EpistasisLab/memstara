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


def train_and_score(path: str, y_column: str, test_size: float = 0.25, seed: int = 42) -> str:
    """Evaluate a subset with the immutable run policy, saving the measured artifact."""
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
            "engine": os.environ.get("MEMSTARA_ML_ENGINE", "").strip() or _DEFAULT_ENGINE,
            "seed": seed, "test_size": test_size,
        }
        plan = validate(plan)
        try:
            result = score(p, y_column, plan)
        except Exception as exc:
            # Never send data values embedded in library exception messages to an LLM.
            detail = str(exc) if isinstance(exc, DataQualityError) else f"Evaluation failed ({type(exc).__name__})"
            result = {"status": "failed", "error": detail,
                      "evaluation": {"dataset_sha256": hashlib.sha256(p.read_bytes()).hexdigest()}}

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
async def train_and_score_async(path: str, y_column: str, test_size: float = 0.25, seed: int = 42) -> str:
    """Train the chosen model under the saved run plan; concurrent jobs do not block MCP."""
    import asyncio
    return await asyncio.to_thread(train_and_score, path, y_column, test_size, seed)


if __name__ == "__main__":
    mcp.run()
