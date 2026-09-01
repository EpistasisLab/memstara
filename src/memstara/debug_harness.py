#!/usr/bin/env python3
"""A debugging harness — call the tools directly, in one process.

Why this is needed
------------------
In a normal run `tools_okf.py`, `tools_data.py`, `tools_ml.py` and
`tools_blackboard.py` are **child processes** started by
`03_board_pipeline.py:119 setup_tools()`. Attaching a debugger to the pipeline
therefore **never** hits a breakpoint in the tool code.

This file pulls the same functions **into this process** and calls them. Breakpoints
then fire the ordinary way, and since no LLM is ever called it costs neither money
nor time. It is exactly the method used for today's verification.

`@mcp.tool()` returns the function unchanged rather than wrapping it, so a registered
tool can be called as a plain Python function — no adapter, no JSON-RPC.

Usage
-----
    uv run --no-sync --project ../motoro python debug_harness.py okf
    uv run --no-sync --project ../motoro python debug_harness.py data
    uv run --no-sync --project ../motoro python debug_harness.py ml
    uv run --no-sync --project ../motoro python debug_harness.py board

Without `--no-sync`, uv tries to rebuild litellm from source and fails.

In VS Code, press F5 on the "1. tool harness" configuration.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
from pathlib import Path

# **Both** `.env` files have to be read. The sandbox's holds the dataset and bundle
# paths, core's holds MOTORO_DATABASE_URL. Read only one and the pipeline cannot
# even start — it stops at "Environment is not ready".
#
# This used to read core's file first, which is the opposite of the order every other
# entry point used — a real difference in which file wins, hidden in a copy of two
# lines. `load_env()` is now the one reader. (Measured before switching: the two files
# share no key names at all, so nothing actually changed hands.)
from memstara.env import load_env  # noqa: E402

from memstara.paths import DEFAULT_OUTPUT_DIR, SHARED_ROOT  # noqa: E402

load_env()

# Which bundle and which data to look at — overridden for this run only, without
# touching `.env`.
BUNDLE = SHARED_ROOT / "hiv-suppression" / "okf"
DATASET = DEFAULT_OUTPUT_DIR / "hiv_cohort.csv"
Y = "HIV_DETECTABLE"

if BUNDLE.is_dir():
    os.environ["AGENTIC_OKF_BUNDLE_DIR"] = str(BUNDLE.resolve())
if DATASET.is_file():
    os.environ["MEMSTARA_DATASET_PATH"] = str(DATASET.resolve())
os.environ.setdefault("MEMSTARA_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))


def load(name: str):
    """Load a module such as `tools_okf` into this process.

    `import_module` registers it in sys.modules *before* executing it, which matters
    here: a dataclass looks its own module back up in sys.modules while being defined,
    so executing first would die there with an AttributeError. Loading it from a file
    path did that by hand, and tied this file to being the servers' neighbour.
    """
    return importlib.import_module(name)


def show(label: str, payload: str, limit: int = 900) -> None:
    """Pretty-print a tool's JSON string under a heading, clipped to *limit* chars."""
    print(f"\n── {label} " + "─" * max(0, 60 - len(label)))
    text = json.dumps(json.loads(payload), ensure_ascii=False, indent=2)
    print(text[:limit] + (" …" if len(text) > limit else ""))


def do_okf() -> None:
    """Knowledge source. Put breakpoints in tools_okf.py: _load, scoring, section extraction."""
    okf = load("tools_okf")

    show("okf_list_domains", okf.okf_list_domains())
    show("okf_search('adherence')", okf.okf_search("adherence", k=3))
    show("okf_search('art')  ← this used to match 132 papers", okf.okf_search("art", k=3))

    first = json.loads(okf.okf_search("adherence", k=1))["results"][0]["hits"][0]["id"]
    whole = json.loads(okf.okf_read(first))["documents"][0]
    part = json.loads(okf.okf_read(first, section="Bottom line"))["documents"][0]
    print(f"\n── reading a section ──────────────────────────────────")
    print(f"   {first}")
    print(f"   whole {len(whole['text']):,} chars  vs  Bottom line {len(part['text']):,} chars")
    print(f"   sections: {whole['sections']}")


def do_data() -> None:
    """Data. Put a breakpoint on the hash computation at tools_data.py:149."""
    data = load("tools_data")

    show("describe_dataset", data.describe_dataset(), limit=600)

    a = "CURRENT_AGE,SEX,TOBACCO_LAST_STATUS,n_diagnoses"
    b = "CURRENT_AGE,SEX,RACE_1,MARITAL_STATUS"
    # Same tag, different columns — this used to overwrite a single file twice.
    show("slice_columns(A, tag='dbg')", data.slice_columns(a, Y, "dbg"))
    show("slice_columns(B, tag='dbg')  ← same tag", data.slice_columns(b, Y, "dbg"))
    made = sorted(p.name for p in DEFAULT_OUTPUT_DIR.glob("sub_dbg_*.csv"))
    print(f"\n   {len(made)} files made: {made}")
    print("   two means there is no collision. One means it was overwritten.")


def do_ml() -> None:
    """Training. Put breakpoints on get_dummies at tools_ml.py:118 and features at :141."""
    data, ml = load("tools_data"), load("tools_ml")

    cols = "CURRENT_AGE,SEX,RACE_1,MARITAL_STATUS,n_diagnoses"
    sliced = json.loads(data.slice_columns(cols, Y, "dbgml"))
    print(f"\n   subset: {Path(sliced['path']).name}")

    result = json.loads(ml.train_and_score(sliced["path"], Y))
    print(f"   AUC {result['auc']}   train {result['n_train']} / test {result['n_test']}")
    print(f"   {len(result['features'])} features (before one-hot): {result['features']}")
    print(f"   {len(result['feature_importance'])} feature_importance keys — more, because this is after one-hot:")
    for k, v in list(result["feature_importance"].items())[:6]:
        print(f"      {k:<28} {v}")


def do_board() -> None:
    """Board. Read-only — this harness never writes anything to the board."""
    board = load("tools_blackboard")

    async def go() -> None:
        show("read_board(run_tag='example')", await board.read_board("example"), limit=1200)
        show("read_results(run_tag='example')", await board.read_results("example"), limit=800)

    asyncio.run(go())


MODES = {"okf": do_okf, "data": do_data, "ml": do_ml, "board": do_board}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "okf"
    if mode not in MODES:
        sys.exit(f"the mode must be one of {' / '.join(MODES)}. Got: {mode!r}")
    print(f"bundle {os.environ.get('AGENTIC_OKF_BUNDLE_DIR', '(none)')}")
    print(f"data   {os.environ.get('MEMSTARA_DATASET_PATH', '(none)')}")
    MODES[mode]()
