#!/usr/bin/env python3
"""ML-tool MCP server — train on a sub-dataset, return AUC and feature importance.

**The engine is XGBoost, and it is the only one.** That was settled on 2026-09-08 as a
project requirement, and it is what the 2026-08-06 meeting had named all along — *"the
ML agent uses tools to do the XGBoost"*. It is also what the 2026-08-10 implementation

this file quietly shipped `sklearn_hgb` instead, to keep the install to one package, and
that is the divergence being closed rather than a new decision.

`MEMSTARA_ML_ENGINE` still exists and still reaches this process, so a stale `.env`
carrying `sklearn_hgb` fails loudly instead of being ignored. `xgboost` is the only value
it accepts.

    MEMSTARA_ML_ENGINE   xgboost — the only accepted value; unset means the same
    MEMSTARA_OUTPUT_DIR  the only directory inputs may come from (default: outputs/ beside this file)

**Measured before the switch**, on the four sub-datasets of run `merge_verify`, by
calling `train_and_score` directly with no pipeline and no model calls:

    dataset   sklearn_hgb   random_forest   xgboost
    t424           0.6463          0.6663    0.6226
    t425           0.6706          0.6302    0.6252
    t426           0.6713          0.6392    0.6229
    t427           0.6978          0.6745    0.6636

XGBoost was the lowest of the three on all four, by 0.024 to 0.048 of AUC. It is
faster — 0.4s against sklearn_hgb's 3.4-6.6s, because it carries
`feature_importances_` and never reaches the permutation route. Recorded here rather
than in a commit message because the next person to ask "why is the AUC lower than the
report says" needs it in the file, and the answer is that the engine changed.

**That table is the whole reason those numbers are still written down.** The two other
engines were removed on 2026-09-08, in the commit after the one that made XGBoost the
default, so nothing here can reproduce those two columns any more. Reinstating them is a
`git revert` away and is `A-26`'s business — lifting the engine to a tool argument, where
an agent could choose it, rather than an environment variable no agent can see.

**Results already on the board were not all produced by this engine.** 81 of them came
from `sklearn_hgb` and their `feature_importance` maps are permutation AUC drops on no
fixed scale, not gain. That is what the `model` column is for
(`src/memstara/blackboard.py:190-195`), and it is why the viewer still carries a scale
note for an engine this file no longer builds.

WARNING: env vars must be on the allowlist to reach this process — see
`mcp_allowed_env_vars` in `src/memstara/config.py`.


==============================================================================
 How to read this file
==============================================================================

 The ml agent's tool server. From the outside it exposes **only one** tool.

   train_and_score(path, y_column)   train a model on a small CSV and return AUC

 Two helpers are called from inside it:
   _make_model(engine, seed)   checks the name is "xgboost", returns the classifier
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

#: The engine a run uses when `MEMSTARA_ML_ENGINE` is unset — which is every run, since
#: nothing in the pipeline sets it. Named here rather than written into `train_and_score`
#: so that "what did this run actually use" is answerable by reading one line, and so a
#: test can assert it (`tests/test_ml_engines.py`). See the module docstring for why it is
#: XGBoost and what that cost in AUC.
_DEFAULT_ENGINE = "xgboost"


def _output_dir() -> Path:
    """The only directory that may be read from. resolve() flattens symlinks too,
    so this is the real path."""
    return Path(os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip() or _DEFAULT_OUT).resolve()


def _make_model(engine: str, seed: int) -> Any:
    """Build the XGBoost classifier, seeded from the caller's `seed`.

    **There is one engine, and `engine` is still a parameter.** It would be shorter to
    drop it and hard-code the classifier, and that would be the wrong shape: the value
    comes from `MEMSTARA_ML_ENGINE`, which is on the allowlist (`src/memstara/config.py:107`)
    and therefore still reaches this process. Somebody's `.env` says `sklearn_hgb`
    today. Ignoring it would run XGBoost while the operator believed otherwise and
    every number would look fine, which is the exact failure this file spent
    2026-09-08 closing at the other end. So the name is checked and a wrong one stops
    the call.

    The import is deferred rather than moved to the top of the file. That was originally
    so a missing optional engine could not prevent the server from starting; xgboost is a
    declared dependency now (`pyproject.toml:64`) so it is no longer optional, and the
    deferral is kept for the remaining half of the reason — an import at module scope runs
    when the *server* starts, and a failure there is a server that reports no tools rather


    **`seed` is the same one that splits the data**, and that is the point of the
    parameter. Until 2026-09-08 every engine carried a hard-coded ``random_state`` of 0
    while the split used the caller's 42, so a run had two different seeds in it and
    neither was controllable: `train_and_score` exposes `seed` as a tool parameter, and
    passing a different value moved the split and left the model exactly where it was.
    NFR-2b (`spec/Memstara_SRS_KR.md:949`) asks that the seed can *be fixed*, not that
    some seed is fixed somewhere.

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
    if engine != _DEFAULT_ENGINE:
        # Two different mistakes reach this line and the message has to tell them apart,
        # because the fix is different. `sklearn_hgb` and `random_forest` were real until
        # 2026-09-08 and were removed; a config that names one is out of date, not wrong,
        # and the numbers it used to produce are in this module's docstring. Anything else
        # is a typo.
        removed = {"sklearn_hgb", "random_forest"}
        if engine in removed:
            raise RuntimeError(
                f"MEMSTARA_ML_ENGINE={engine!r} was removed on 2026-09-08; XGBoost is the only "
                f"engine this server builds. Unset the variable, or set it to 'xgboost'."
            )
        raise RuntimeError(f"unknown MEMSTARA_ML_ENGINE: {engine!r} (the only accepted value is 'xgboost')")

    # The three hyperparameters are verbatim from

    # tuned; `eval_metric` is set only to silence a startup warning. `subsample` and
    # `colsample_*` are left at 1.0, which is why `seed` does not move this engine's
    # numbers — see the note above.
    #
    # **It handles missing values (NaN) as they are** — it does not blow up when 30% is
    # blank, as in NHANES. `sklearn_hgb` did too, which is why replacing it needed no
    # change to how the sub-datasets are cut.
    from xgboost import XGBClassifier

    return XGBClassifier(n_estimators=200, max_depth=4, eval_metric="logloss", random_state=seed)


def _importance(model: Any, X: pd.DataFrame, y: pd.Series, seed: int) -> dict[str, float]:
    """Per-column importance, straight off the fitted model.

    **One engine means one route.** `XGBClassifier` carries `feature_importances_`, so
    the numbers are gain: non-negative, and summing to exactly 1.0000 on all four
    `merge_verify` sub-datasets. There is nothing here to choose between any more, and
    the `y` and `seed` parameters are now unused by the body — kept in the signature
    because the second route is a revert away, and a caller that has to be edited back is
    a caller that will not be.

    **The second route is gone, and rows produced by it are not.** Until 2026-09-08 an
    engine without `feature_importances_` fell back to permutation importance: shuffle
    one column and measure how far AUC drops. That drop **is** the number — a different
    unit, on no fixed scale, negative for a column whose shuffling made the model look
    better. `sklearn_hgb` was the only engine that reached it, `sklearn_hgb` was the
    default for two months, and **81 results on the board are in those units**. They
    cannot be compared column-by-column with anything produced after that date; ranking
    one against the other is reading an AUC delta against a fraction of gain. The `model`
    field stored beside each row is the only thing that says which is which
    (`src/memstara/blackboard.py:190-195`).

    Two things that were true of that route, recorded because nothing in this file can
    demonstrate them any more. It was expensive: permutation was most of `sklearn_hgb`'s
    2.9-6.3s per call, against 0.4-0.5s for an engine that skipped it, and the four
    sub-datasets have 22, 18, 17 and 11 columns after one-hot encoding rather than the
    "fewer than ten" an earlier version of this docstring assumed. And it was worth
    paying anyway, for the engine that needed it: a model with no importance at all is a
    result nobody can read.

    That earlier version also claimed permutation "yields a comparable quantity across
    engines". It did not and could not — only one engine ever reached the branch, so the
    two routes never produced comparable numbers for the same engine, only incomparable
    ones for different engines.
    """
    if not hasattr(model, "feature_importances_"):
        # Unreachable while XGBoost is the only engine, and kept as a guard rather than
        # deleted. It fires if a future xgboost stops exposing the attribute, or if a
        # second engine is added without its importance route — and an empty importance
        # map is the kind of failure that reads as "this column mattered least" rather
        # than as a bug.
        raise RuntimeError(
            f"{type(model).__name__} has no feature_importances_, and the permutation "
            f"fallback was removed on 2026-09-08 when XGBoost became the only engine."
        )

    # strict=True: one score per column, or the model was not fitted on this X. Without
    # it zip() truncates to the shorter side and the caller gets a short, plausible,
    # wrong importance table.
    return {c: float(v) for c, v in zip(X.columns, model.feature_importances_, strict=True)}


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
            different experimental condition. Whichever value is used comes back in
            the return, so the condition travels with the numbers.

    Returns:
        JSON with auc, features, feature_importance, n_train, n_test, model, seed and
        test_size. Report the returned numbers as they stand; do not restate them
        approximately.

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
    engine = os.environ.get("MEMSTARA_ML_ENGINE", "").strip() or _DEFAULT_ENGINE

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
            # The two conditions the caller could have changed, returned for the same
            # reason `model` is: a number is only reproducible alongside what produced
            # it. Both are tool parameters, so an agent may pass something other than
            # the default — and until now, doing so left no trace anywhere. The
            # docstring's promise that a result can be re-scored by hand and checked
            # against the board was therefore true only of calls that passed neither.
            #
            # This reaches the run trace, not the board: `submit_result` has no
            # parameter for either (`src/memstara/mcp_servers/blackboard.py:289-293`)
            # and `memstara_results` has no column
            # (`src/memstara/blackboard.py:247-277`). Storing them is a schema change
            # and its own piece of work; returning them costs nothing and is what makes
            # that work possible to do later against real values.
            "seed": int(seed),
            "test_size": float(test_size),
        }
    )


if __name__ == "__main__":
    mcp.run()
