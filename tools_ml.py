#!/usr/bin/env python3
"""ML-tool MCP server — train on a sub-dataset, return AUC and feature importance.

The meeting never settled on an engine — *"XGBoost, whatever we decide to do"*. So
the engine is swappable through `MEMSTARA_ML_ENGINE`. Changing it touches neither the
agent definitions nor the pipeline.

    MEMSTARA_ML_ENGINE   sklearn_hgb (default) | random_forest | xgboost
    MEMSTARA_OUTPUT_DIR  the only directory inputs may come from (default: outputs/ beside this file)

The default is scikit-learn to keep the install small — one package and it runs.
xgboost is optional and only fails if you select that engine.

WARNING: env vars must be on the allowlist to reach this process — see
`mcp_allowed_env_vars` in `sandbox/settings.py`.


==============================================================================
 How to read this file
==============================================================================

 The ml agent's tool server. From the outside it exposes **only one** tool.

   train_and_score(path, y_column)   train a model on a small CSV and return AUC

 Two helpers are called from inside it:
   _make_model(engine)      engine name -> the actual model object
   _importance(model, ...)  which column contributed how much

 The flow:
   (1) is the path inside the allowed directory (security check)
   (2) read the CSV
   (3) expand string columns into numbers (one-hot)
   (4) split into train and test
   (5) fit and measure AUC
   (6) pull out the importances

 For AUC, 0.5 is a coin flip and 1.0 is perfect. 0.64 means roughly "there is
 some signal here".

 To call it by hand: `python debug_harness.py ml`
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from mcp.server.fastmcp import FastMCP

# This is a child process, so the parent's debugger cannot reach it. It waits for
# a debugger only when MEMSTARA_DEBUGPY contains this server's name — otherwise it
# does nothing at all. See debug_hook.py.
from debug_hook import quiet_child, wait_for_debugger

quiet_child()          # silences the three startup messages a child prints
wait_for_debugger('memstara-ml')

mcp = FastMCP("memstara-ml")

_DEFAULT_OUT = Path(__file__).parent / "outputs"


def _output_dir() -> Path:
    """The only directory that may be read from. resolve() flattens symlinks too,
    so this is the real path."""
    return Path(os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip() or _DEFAULT_OUT).resolve()


def _make_model(engine: str) -> Any:
    """Build a model for the named engine.

    Imports are deferred so that a missing optional engine does not prevent the
    server from starting. Put at the top of the file instead, anyone who never
    uses xgboost would still have to install it.
    """
    if engine == "sklearn_hgb":
        # The default. Histogram-based gradient boosting.
        # **It handles missing values (NaN) as they are** — it does not blow up
        # when 30% is blank, as in NHANES.
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(max_iter=200, max_depth=4, random_state=0)
    if engine == "random_forest":
        from sklearn.ensemble import RandomForestClassifier

        return RandomForestClassifier(n_estimators=300, random_state=0, n_jobs=-1)
    if engine == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(n_estimators=200, max_depth=4, eval_metric="logloss", random_state=0)

    # A typo is not let through silently. The message also names what is available.
    raise RuntimeError(f"unknown MEMSTARA_ML_ENGINE: {engine!r} (sklearn_hgb | random_forest | xgboost)")


def _importance(model: Any, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    """Extract per-column importance, whichever engine produced the model.

    HistGradientBoosting has no ``feature_importances_``, so fall back to
    permutation importance. Slower, but there are fewer than ten columns here, and
    it yields a comparable quantity across engines. Permutation importance works
    by shuffling one column's values and measuring how far performance drops.
    """
    if hasattr(model, "feature_importances_"):
        # If the model already carries them, use them as they are.
        return {c: float(v) for c, v in zip(X.columns, model.feature_importances_)}

    from sklearn.inspection import permutation_importance

    # n_repeats=5 — shuffle five times and average. A single shuffle is swayed by chance.
    r = permutation_importance(model, X, y, n_repeats=5, random_state=0, scoring="roc_auc")
    return {c: float(v) for c, v in zip(X.columns, r.importances_mean)}


@mcp.tool()
def train_and_score(path: str, y_column: str, test_size: float = 0.25, seed: int = 42) -> str:
    """Train a binary classifier on a sub-dataset and return AUC and feature importance.

    Args:
        path: sub-dataset CSV produced by slice_columns.
        y_column: name of the outcome column.
        test_size: test split fraction (default 0.25).
        seed: random seed. It is fixed, so the same input always yields the same
            number and a result can be re-scored by hand later and checked
            against what the board recorded.

    Returns:
        JSON with auc, feature_importance, n_train, n_test and model. Report the
        returned numbers as they stand; do not restate them approximately.
    """
    # The path check comes FIRST. Putting a security check behind an optional
    # dependency means it is skipped entirely wherever that package is absent,
    # hidden behind an "install scikit-learn" message.
    out_dir = _output_dir()
    try:
        p = Path(path).resolve()
        # relative_to raises unless p sits under out_dir. This is what blocks a
        # path such as "../../etc/passwd".
        p.relative_to(out_dir)
    except (ValueError, OSError):
        return json.dumps({"error": f"path is outside the allowed directory: {path}", "allowed_dir": str(out_dir)})
    if not p.is_file():
        return json.dumps({"error": f"file not found: {p}"})

    try:
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import train_test_split
    except ImportError:
        return json.dumps({"error": "scikit-learn is not installed. `pip install scikit-learn`"})

    # If the environment variable is unset or empty, use the default engine.
    engine = os.environ.get("MEMSTARA_ML_ENGINE", "").strip() or "sklearn_hgb"

    try:
        df = pd.read_csv(p)
        if y_column not in df.columns:
            return json.dumps({"error": f"y_column '{y_column}' not found"})

        y = df[y_column]                      # the value to predict (0 or 1)
        if y.nunique() < 2:
            # All 0 or all 1 means there is nothing to learn.
            return json.dumps({"error": "the outcome has only one class; nothing to train"})

        # One-hot so the engine tolerates categorical columns. A single column such
        # as Race1 splits into Race1_White, Race1_Hispanic and so on. drop_first=True
        # **holds one category out as the baseline**, which means the importances of
        # the ones that remain read as "the difference against the dropped category",
        # not as "this value contributes". That makes interpretation confusing — it
        # is a spot that has not been fixed yet.
        X = pd.get_dummies(df.drop(columns=[y_column]), drop_first=True)
        if X.empty or X.shape[1] == 0:
            return json.dumps({"error": "no feature columns"})

        # Split into train and test. stratify=y keeps the positive rate the same on
        # both sides — without it, data with only 10% positives can end up with
        # almost no positives on the test side.
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=test_size, random_state=seed, stratify=y)
        model = _make_model(engine)
        model.fit(X_tr, y_tr)                 # fit

        # predict_proba gives [P(0), P(1)]. [:, 1] takes only the probability of 1.
        auc = float(roc_auc_score(y_te, model.predict_proba(X_te)[:, 1]))

        # Importance is measured on the **test data**. Measured on the training data,
        # whatever the model memorised would look important too.
        importance = _importance(model, X_te, y_te)
    except Exception as e:
        # Return the kind of failure as well as the message, so the agent can read
        # it and decide what to do.
        return json.dumps({"error": f"{type(e).__name__}: {e}"})

    return json.dumps(
        {
            "auc": round(auc, 4),
            # The columns this actually trained on, as the sub-dataset spells them —
            # BEFORE one-hot. Two things need it. First, it is the only place a result
            # can be checked against the hypothesis it is filed under: without it the
            # board records what the data stage said it cut, never what the ml stage
            # read, and a sub-dataset that was overwritten between the two stages scores
            # silently under the wrong row. Second, `feature_importance` is keyed by
            # post-one-hot names (`Race1_White`), which match no column and no knowledge
            # source concept; this keeps the original names in the record beside them.
            "features": [c for c in df.columns if c != y_column],
            # Sorted with the largest importance first, so it reads top-down.
            "feature_importance": {k: round(v, 5) for k, v in sorted(importance.items(), key=lambda kv: -kv[1])},
            "n_train": int(len(X_tr)),
            "n_test": int(len(X_te)),
            "model": engine,      # record which engine produced these numbers
        }
    )


if __name__ == "__main__":
    mcp.run()
