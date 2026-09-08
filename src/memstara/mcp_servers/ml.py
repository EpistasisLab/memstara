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
`mcp_allowed_env_vars` in `src/memstara/config.py`.


==============================================================================
 How to read this file
==============================================================================

 The ml agent's tool server. From the outside it exposes **only one** tool.

   train_and_score(path, y_column)   train a model on a small CSV and return AUC

 Two helpers are called from inside it:
   _make_model(engine, seed)   engine name -> the actual model object
   _importance(model, ...)     which column contributed how much

 The flow:
   (1) is the path inside the allowed directory (security check)
   (2) read the CSV
   (3) expand string columns into numbers (one-hot)
   (4) split into train and test
   (5) fit and measure AUC
   (6) pull out the importances

 For AUC, 0.5 is a coin flip and 1.0 is perfect. 0.64 means roughly "there is
 some signal here".

 To call it by hand: `python -m memstara.debug_harness ml`
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
# does nothing at all. See src/memstara/mcp_servers/debug_hook.py.
from memstara.mcp_servers.debug_hook import quiet_child, wait_for_debugger

from memstara.paths import DEFAULT_OUTPUT_DIR

quiet_child()          # silences the three startup messages a child prints
wait_for_debugger('memstara-ml')

mcp = FastMCP("memstara-ml")

_DEFAULT_OUT = DEFAULT_OUTPUT_DIR


def _output_dir() -> Path:
    """The only directory that may be read from. resolve() flattens symlinks too,
    so this is the real path."""
    return Path(os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip() or _DEFAULT_OUT).resolve()


def _make_model(engine: str, seed: int) -> Any:
    """Build a model for the named engine, seeded from the caller's `seed`.

    Imports are deferred so that a missing optional engine does not prevent the
    server from starting. Put at the top of the file instead, anyone who never
    uses xgboost would still have to install it.

    **`seed` is the same one that splits the data**, and that is the point of the
    parameter. Until 2026-09-08 all three engines carried a hard-coded
    ``random_state`` of 0 while the split used the caller's 42, so a run had two
    different seeds in it and neither was controllable: `train_and_score` exposes
    `seed` as a tool parameter, and passing a different value moved the split and
    left the model exactly where it was. NFR-2b (`spec/Memstara_SRS_KR.md:949`) asks
    that the seed can *be fixed*, not that some seed is fixed somewhere.

    42 rather than 0 because it is the value with a documented origin —

    seed for reproducibility and sets it to 42. A seed of 0 appears in no
    meeting note and no design document; it entered during implementation, and
    since the whole repository arrived in one commit (`b4fd613`) git cannot say
    whose judgement it was.

    Note for whoever reads an unchanged xgboost number afterwards: `XGBClassifier`'s
    `random_state` only bites when `subsample` or `colsample_*` is below 1.0, and
    neither is set here, so training is deterministic and the AUC is expected not to
    move. That is not a failure of this change — the change buys controllability and
    a single seed per run, not different numbers.
    """
    if engine == "sklearn_hgb":
        # The default. Histogram-based gradient boosting.
        # **It handles missing values (NaN) as they are** — it does not blow up
        # when 30% is blank, as in NHANES.
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(max_iter=200, max_depth=4, random_state=seed)
    if engine == "random_forest":
        from sklearn.ensemble import RandomForestClassifier

        return RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=-1)
    if engine == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(n_estimators=200, max_depth=4, eval_metric="logloss", random_state=seed)

    # A typo is not let through silently. The message also names what is available.
    raise RuntimeError(f"unknown MEMSTARA_ML_ENGINE: {engine!r} (sklearn_hgb | random_forest | xgboost)")


def _importance(model: Any, X: pd.DataFrame, y: pd.Series, seed: int) -> dict[str, float]:
    """Extract per-column importance, by whichever route the engine allows.

    **The two routes do not return the same quantity, and this function cannot make
    them.** Which one ran is therefore part of the answer, not an implementation
    detail — `train_and_score` returns the engine name alongside the numbers, and the
    caller is expected to store it (`src/memstara/blackboard.py:305`).

    The figures below come from calling `train_and_score` directly on the four
    sub-datasets of run `merge_verify`, once per engine — no pipeline run, no model
    call.

    - ``feature_importances_`` — random_forest and xgboost carry it. Impurity decrease
      or gain: non-negative, and summing to about 1 across the columns. random_forest
      sums to exactly 1.0000 on all four.
    - permutation importance — HistGradientBoosting has no ``feature_importances_``,
      so shuffle one column's values and measure how far AUC drops. That drop **is**
      the number: a different unit, on no fixed scale, and negative for a column
      whose shuffling made the model look better. sklearn_hgb's maps sum to 0.0819
      and 0.2572 on two of the four, with a minimum entry of -0.0131.

    So two rows can only be compared column-by-column when they were produced by
    engines on the same route. Ranking one engine's map against another's is reading
    an AUC delta against a fraction of impurity.

    Until 2026-09-08 this docstring claimed permutation "yields a comparable quantity
    across engines". It does not, and could not: only HistGradientBoosting reaches
    that branch, so the two routes never produce comparable numbers for the same
    engine — they produce incomparable numbers for different ones. The same passage
    called the permutation cost acceptable because "there are fewer than ten columns
    here"; the four sub-datasets have 22, 18, 17 and 11 after one-hot encoding, and
    permutation is most of sklearn_hgb's 2.9-6.3s per call against random_forest's
    0.4-0.5s. It is still worth paying — a HistGradientBoosting model with no
    importance at all is a result nobody can read — but it is not free and it is not
    the same measurement.
    """
    if hasattr(model, "feature_importances_"):
        # If the model already carries them, use them as they are.
        # strict=True: one score per column, or the model was not fitted on this X.
        # Without it zip() truncates to the shorter side and the caller gets a
        # short, plausible, wrong importance table.
        return {c: float(v) for c, v in zip(X.columns, model.feature_importances_, strict=True)}

    from sklearn.inspection import permutation_importance

    # n_repeats=5 — shuffle five times and average. A single shuffle is swayed by chance.
    # `seed` is the caller's, the same one that split the data and built the model. This
    # branch is the one the default engine takes, so leaving a hard-coded 0 here would
    # have made the seed controllable everywhere except the place sklearn_hgb's numbers
    # actually come from — which is most of a run's randomness, not a corner of it.
    r = permutation_importance(model, X, y, n_repeats=5, random_state=seed, scoring="roc_auc")
    return {c: float(v) for c, v in zip(X.columns, r.importances_mean, strict=True)}


@mcp.tool()
def train_and_score(path: str, y_column: str, test_size: float = 0.25, seed: int = 42) -> str:
    """Train a binary classifier on a sub-dataset and return AUC and feature importance.

    Args:
        path: sub-dataset CSV produced by slice_columns.
        y_column: name of the outcome column.
        test_size: test split fraction (default 0.25).
        seed: random seed. **It is the only one** — it splits the data, builds the
            model and drives the permutation shuffle, so the same input yields the
            same number and a result can be re-scored by hand later and checked
            against what the board recorded. Leave it at 42 unless you are
            deliberately testing how much of a result is the split; changing it is a
            different experimental condition, and nothing yet records which value
            was used.

    Returns:
        JSON with auc, feature_importance, n_train, n_test and model. Report the
        returned numbers as they stand; do not restate them approximately.

        ``model`` is which engine ran, and it belongs with the numbers rather than
        beside them: it is what says whether feature_importance is impurity/gain or a
        drop in AUC. See ``_importance`` above. Pass it on unchanged — you did not
        choose it and cannot, it is read from the environment here.
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
        model = _make_model(engine, seed)
        model.fit(X_tr, y_tr)                 # fit

        # predict_proba gives [P(0), P(1)]. [:, 1] takes only the probability of 1.
        auc = float(roc_auc_score(y_te, model.predict_proba(X_te)[:, 1]))

        # Importance is measured on the **test data**. Measured on the training data,
        # whatever the model memorised would look important too.
        importance = _importance(model, X_te, y_te, seed)
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
