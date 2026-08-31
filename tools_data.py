#!/usr/bin/env python3
"""Data-tool MCP server — inspect the columns, slice a subset.

Core launches this file as a stdio subprocess. Same FastMCP shape as
`examples/mcp_server.py`.

**Configuration arrives only through the environment.** Same convention as core's
own OKF server (`AGENTIC_OKF_BUNDLE_DIR`): an agent never supplies a path.

    MEMSTARA_DATASET_PATH   source dataset CSV (required)
    MEMSTARA_OUTPUT_DIR     where sub-datasets are written (default: outputs/ beside this file)

WARNING: these must be on core's MCP subprocess env allowlist to reach this
process — see `mcp_allowed_env_vars` in `sandbox/settings.py`. Without them the
tools below return `{"error": ...}`.

Reading the environment inside the functions rather than at module scope is
deliberate. `os.environ[...]` at import time kills the server during startup, and
the caller sees only "failed to connect" with no indication of why.


==============================================================================
 How to read this file
==============================================================================

 The data agent's tool server. It has **only two** tools.

   describe_dataset()   what columns this dataset has, and how empty each one is
   slice_columns(...)   cut out only the chosen columns and save a small CSV

 This file runs as a **separate process**, started with `python tools_data.py`.
 The pipeline launches it as a child and talks to it over stdin/stdout. That is
 why attaching a debugger to the pipeline will not hit breakpoints in here.

 To call it by hand: `python debug_harness.py data`
"""

from __future__ import annotations

import hashlib     # builds the short fingerprint (hash) that goes into filenames
import json        # a tool must return a **string**, so results are wrapped in JSON
import os          # environment variables
from pathlib import Path

import pandas as pd                      # the library for working with tabular data
from mcp.server.fastmcp import FastMCP    # the toolkit for building an MCP server

# This server's name. The pipeline looks it up as "memstara-data".
# It is a child process, so the parent's debugger cannot reach it. It waits for a
# debugger only when MEMSTARA_DEBUGPY contains this server's name — otherwise it
# does nothing at all. See debug_hook.py.
from debug_hook import quiet_child, wait_for_debugger

quiet_child()          # silences the three startup messages a child prints
wait_for_debugger('memstara-data')

mcp = FastMCP("memstara-data")

# Fallback used when the output directory is not given in the environment —
# outputs/ beside this file.
_DEFAULT_OUT = Path(__file__).parent / "outputs"


def _dataset_path() -> Path:
    """Path to the source CSV. Raises a human-readable error when it is absent."""
    raw = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    if not raw:
        # Rather than a bare KeyError, say **which file to fix**. This error is
        # almost always caused by a missing entry in the allowlist.
        raise RuntimeError(
            "MEMSTARA_DATASET_PATH is not set. Check that you exported it, and that it "
            "appears in mcp_allowed_env_vars in sandbox/settings.py."
        )
    path = Path(raw)
    if not path.is_file():
        raise RuntimeError(f"dataset file not found: {path}")
    return path


def _output_dir() -> Path:
    """Directory the sliced CSVs go into. Created if it does not exist."""
    out = Path(os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip() or _DEFAULT_OUT)
    out.mkdir(parents=True, exist_ok=True)   # no error if it is already there
    return out


@mcp.tool()
def describe_dataset() -> str:
    """Return the dataset's actual column names, row count, and how empty each column is.

    Call this FIRST, before choosing any columns. Concept names in the knowledge
    source and column names in the dataset are not the same thing (for example
    "body mass index" versus "bmi"). Choosing a column that does not exist wastes
    the trial.

    ``missing_pct`` lists only the columns that have gaps. A column can exist and
    still be nearly empty — the shared HIV cohort has a BMI column that is 90%
    blank — and a name alone cannot say so. Choosing such a column is close to
    choosing nothing, so check this before selecting.
    """
    try:
        df = pd.read_csv(_dataset_path())
    except Exception as e:
        # A tool returns {"error": ...} instead of raising, so that the agent can
        # read it and decide what to do — an exception only ever reads to the
        # agent as "the tool is broken".
        return json.dumps({"error": str(e)})

    # The outcome column is never exposed to the agent.
    # Selecting it as a feature would put the answer into the input — data leakage.
    # Same blocking-at-the-source approach as reviewer's build_catalog.py.
    outcome_col = os.environ.get("MEMSTARA_OUTCOME_COLUMN", "").strip()
    feature_cols = [c for c in df.columns if c != outcome_col] if outcome_col else list(df.columns)

    # Missing rate per column. isna() gives a True/False table, and mean() gives
    # the average of that = the proportion.
    missing = df[feature_cols].isna().mean()

    return json.dumps(
        {
            "n_rows": int(len(df)),
            "n_columns": len(feature_cols),
            "columns": feature_cols,
            # Only the columns that **have** gaps are listed. Carrying the 0%
            # ones as well would make the list long, and that length is then
            # reloaded into the conversation on every round that follows.
            "missing_pct": {c: round(float(v) * 100, 1) for c, v in missing.items() if v > 0},
        }
    )


@mcp.tool()
def slice_columns(columns: list[str], y_column: str, tag: str) -> str:
    """Extract the named columns plus the outcome into a sub-dataset CSV.

    Args:
        columns: a LIST of column names, one name per element, e.g.
            ["BMI", "LAB__HDL CHOLESTEROL, DIRECT", "CURRENT_AGE"]. Pass them
            exactly as `describe_dataset` or the matcher spelled them, commas
            and all — this is a list, not a comma-separated string.
        y_column: name of the outcome column.
        tag: identifier used in the output filename, e.g. "t03"

    Returns:
        JSON with path, n_rows, columns_used and columns_missing. A non-empty
        columns_missing means those names are not in the dataset — check the
        spelling against describe_dataset and report what stays missing.

    A LIST rather than a comma-separated string, because 158 of this cohort's
    1,393 columns carry a comma inside the name (`DX__E78.5__Hyperlipidemia,
    unspecified`, `LAB__HDL CHOLESTEROL, DIRECT`). Splitting on commas cut each
    of those into two names that exist nowhere, and the old docstring told the
    agent to read that as "the knowledge source's names diverged from the
    dataset's" — a wrong diagnosis of a bug in this function. `match_concepts`
    already takes a list; the two tools now agree.
    """
    try:
        df = pd.read_csv(_dataset_path())
        out_dir = _output_dir()
    except Exception as e:
        return json.dumps({"error": str(e)})

    # The outcome column — the same line of defence as in describe_dataset.
    # Even if the y_column name is wrong (say "outcome" versus "HIV_DETECTABLE"),
    # the environment variable blocks it a second time.
    outcome_col = os.environ.get("MEMSTARA_OUTCOME_COLUMN", "").strip()

    # A bare string is refused rather than iterated. Python would iterate it
    # character by character and hand back 30 single-letter names in
    # columns_missing — a failure that reads like a naming problem and is not one.
    if isinstance(columns, str):
        return json.dumps(
            {
                "error": "columns must be a list of column names, not a string",
                "hint": 'Pass ["BMI", "LAB__HDL CHOLESTEROL, DIRECT"], not '
                '"BMI, LAB__HDL CHOLESTEROL, DIRECT". Column names contain commas, '
                "so a comma-separated string cannot be split back apart.",
            }
        )

    # Surrounding whitespace is stripped and empty entries dropped; the name
    # itself, commas included, is left exactly as given.
    wanted = [str(c).strip() for c in columns if str(c).strip()]
    # If the outcome column is mixed into the feature list, drop it silently
    # (blocking leakage at the source).
    if outcome_col:
        wanted = [c for c in wanted if c != outcome_col]
    if not wanted:
        return json.dumps({"error": "columns is empty"})

    if y_column not in df.columns:
        # Without the outcome column nothing can be done at all.
        # The outcome is hidden from the column list in the error message too — if
        # the agent learns that name it could use it as a feature on the next call,
        # which would be leakage.
        safe_cols = [c for c in df.columns if c != outcome_col] if outcome_col else list(df.columns)
        return json.dumps(
            {"error": f"y_column '{y_column}' is not in the dataset", "columns": safe_cols}
        )

    # Feeding the outcome back in as a feature is leakage. Drop it if requested.
    # It amounts to reading the answer off the answer, so the AUC comes out close
    # to 1.0 and means nothing at all.
    present = [c for c in wanted if c in df.columns and c != y_column]   # the ones that exist
    missing = [c for c in wanted if c not in df.columns]                 # the ones that do not

    if not present:
        return json.dumps(
            {
                "error": "none of the requested columns exist in the dataset",
                "columns_missing": missing,
                "hint": "Call describe_dataset to see the real column names.",
            }
        )

    # The tag reaches the filesystem, so strip anything that could traverse it.
    # The tag is a string the agent chose and it becomes the filename directly.
    # Something like "../../etc/passwd" must not get through, so only alphanumerics
    # and -_ are kept, cut to 40 characters.
    safe_tag = "".join(ch for ch in tag if ch.isalnum() or ch in "-_")[:40] or "untagged"

    # The filename carries a digest of the request, not the tag alone. The tag is chosen
    # by an agent, and on a board run three data agents pick it independently — nothing
    # makes them differ. On run `example` all three chose the run tag, so all three wrote
    # `sub_example.csv` in turn and each ml stage trained on whichever slice happened to
    # be on disk at that moment. Every AUC on the board belonged to a different
    # hypothesis than the row it sat in:
    #
    #     task 90 (8 cols) recorded 0.6443, its own columns score 0.6175
    #     task 91 (7 cols) recorded 0.6169, its own columns score 0.6443
    #     task 92 (5 cols) recorded 0.6169  — the only one that was its own
    #
    # Nothing failed and nothing warned. The earlier NHANES run survived only because
    # its agents happened to pick t86/t87/t88.
    #
    # Hashed in the order given, not sorted: the CSV is written in that order too, so
    # sorting would map two genuinely different files onto one name and reopen the same
    # silent overwrite. Identical requests still land on one file with one content,
    # which is what makes a repeat idempotent rather than a collision.
    #
    # In short: different columns produce a different name, so one slice can never
    # overwrite another; the same request produces the same name and the same
    # content, so repeating it is safe.
    digest = hashlib.sha1("|".join(present + [y_column]).encode("utf-8")).hexdigest()[:8]
    out_path = out_dir / f"sub_{safe_tag}_{digest}.csv"

    # The chosen columns plus the outcome. Putting the outcome **last** is this
    # project's convention.
    subset = df[present + [y_column]]
    subset.to_csv(out_path, index=False)   # index=False — do not add a row-number column

    return json.dumps(
        {
            "path": str(out_path),          # the next stage (ml) trains from this path
            "n_rows": int(len(subset)),
            "columns_used": present + [y_column],
            "columns_missing": missing,     # non-empty means a name did not match
        }
    )


if __name__ == "__main__":
    # It only starts as a server when this file is run directly, never on import —
    # which is what lets debug_harness.py borrow the functions on their own.
    mcp.run()
