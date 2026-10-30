#!/usr/bin/env python3
"""A debugging harness — call the tools directly, in one process."""

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

from memstara.paths import DEFAULT_OUTPUT_DIR  # noqa: E402
from memstara.servers import BY_NAME  # noqa: E402

load_env()

# Explicit environment values take precedence over the synthetic sample defaults.
os.environ.setdefault("AGENTIC_OKF_BUNDLE_DIR", str(DEFAULT_OUTPUT_DIR / "okf_synthetic_sample"))
os.environ.setdefault("MEMSTARA_DATASET_PATH", str(DEFAULT_OUTPUT_DIR / "dataset.csv"))
os.environ.setdefault("MEMSTARA_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))
Y = os.environ.get("MEMSTARA_TARGET_COLUMN", "Y")


def feature_columns() -> list[str]:
    """Read sample feature columns from the configured dataset header."""
    import csv

    with Path(os.environ["MEMSTARA_DATASET_PATH"]).open(newline="") as stream:
        return [name for name in next(csv.reader(stream)) if name != Y][:5]


def load(name: str):
    """Load a module such as `memstara.mcp_servers.okf` into this process.

    `import_module` registers it in sys.modules *before* executing it, which matters
    here: a dataclass looks its own module back up in sys.modules while being defined,
    so executing first would die there with an AttributeError. Loading it from a file
    path did that by hand, and tied this file to being the servers' neighbour.
    """
    return importlib.import_module(name)


def load_server(name: str):
    """Load a tool server by its **registered** name, e.g. "okf" or "memstara-data".

    Goes through `servers.BY_NAME` rather than naming the module here. The module
    names used to be written out in this file as well, which is how it came to still
    say `tools_okf` after the modules had moved into the package — a stale string that
    no import rewrite could see and no import error could catch, because it is only
    read when the function runs.
    """
    return load(BY_NAME[name].module)


def show(label: str, payload: str, limit: int = 900) -> None:
    """Pretty-print a tool's JSON string under a heading, clipped to *limit* chars."""
    print(f"\n── {label} " + "─" * max(0, 60 - len(label)))
    text = json.dumps(json.loads(payload), ensure_ascii=False, indent=2)
    print(text[:limit] + (" …" if len(text) > limit else ""))


def do_okf() -> None:
    """Knowledge source. Put breakpoints in src/memstara/mcp_servers/okf.py: _load, scoring, section extraction."""
    okf = load_server("okf")

    show("okf_list_domains", okf.okf_list_domains())
    show("okf_search('adherence')", okf.okf_search("adherence", k=3))
    show("okf_search('glucose')", okf.okf_search("glucose", k=3))

    results = json.loads(okf.okf_search("glucose", k=1))["results"]
    hits = results[0].get("hits", []) if results else []
    if not hits:
        return
    first = hits[0]["id"]
    whole = json.loads(okf.okf_read(first))["documents"][0]
    part = json.loads(okf.okf_read(first, section="Bottom line"))["documents"][0]
    print("\n── reading a section ──────────────────────────────────")
    print(f"   {first}")
    print(f"   whole {len(whole['text']):,} chars  vs  Bottom line {len(part['text']):,} chars")
    print(f"   sections: {whole['sections']}")


def do_data() -> None:
    """Data. Put a breakpoint on the hash computation at src/memstara/mcp_servers/data.py:152."""
    data = load_server("memstara-data")

    show("describe_dataset", data.describe_dataset(), limit=600)

    # A list, not a comma-separated string. `slice_columns` refuses a bare string
    # outright (see its docstring: 158 of this cohort's columns have a comma inside
    # the name), so this mode had been returning an error payload and reporting
    # "0 files made" ever since the signature changed under it.
    a = feature_columns()[:3]
    b = feature_columns()
    # Same tag, different columns — this used to overwrite a single file twice.
    show("slice_columns(A, tag='dbg')", data.slice_columns(a, Y, "dbg"))
    show("slice_columns(B, tag='dbg')  ← same tag", data.slice_columns(b, Y, "dbg"))
    made = sorted(p.name for p in DEFAULT_OUTPUT_DIR.glob("sub_dbg_*.csv"))
    print(f"\n   {len(made)} files made: {made}")
    print("   two means there is no collision. One means it was overwritten.")


def do_ml() -> None:
    """Training. Put breakpoints on get_dummies at src/memstara/mcp_servers/ml.py"""
    data, ml = load_server("memstara-data"), load_server("memstara-ml")

    cols = feature_columns()
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
    board = load_server("memstara-blackboard")

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
