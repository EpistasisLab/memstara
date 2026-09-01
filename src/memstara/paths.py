"""Every path this repository knows about, resolved in one place.

Why this file exists
--------------------
Before it, fourteen modules each worked out where they were with
`Path(__file__).parent` and built the repository's layout back up from there.

.. repair-citations: off

**The paths below are the pre-restructure ones** — they are the record of what was
consolidated, not somewhere to go and look now. Read them at `2ff414d`, the commit
before the move; every one of these files lives under `src/memstara/` today and none
of them still computes its own paths::

    logging_setup.py:35-36   outputs/logs, outputs/runs
    tools_data.py:61         outputs/
    tools_ml.py:64           outputs/
    make_sample_data.py:78   outputs/
    matcher_impl/config.py:87  outputs/
    prep_nhanes.py:74        outputs/
    prep_hiv_dataset.py:70-71  ../shared/..., outputs/
    trace_run.py:78          outputs/todo_rows.json
    bootstrap.py:61-64       .env and ../motoro/.env
    02_mvp_pipeline.py:419-420, 03_board_pipeline.py:1548-1549,
    debug_harness.py:46-47, preflight.py:68   the same two `.env` files again

.. repair-citations: on

Each of those is correct only while the file stays exactly where it is. That is a
fragile thing to have written down fourteen times, and it fails **quietly**: a
module one directory deeper does not raise, it writes to a different `outputs/`
that nobody is watching.

`.gitignore:21` makes the quiet failure worse than untidy. The pattern is
`outputs/*` — it contains a slash, so git anchors it to the repository root. An
`outputs/` produced anywhere else is **not ignored**, and run records from the HIV
cohort would sit untracked inside the source tree waiting to be committed by


So the layout is asserted once, here, and every other module asks.

The one assumption
------------------
`REPO_ROOT` is the only line in this repository that depends on how deep a file
sits. It is `parents[2]` because this file is `<root>/src/memstara/paths.py`. If
that ever changes, this is the single line to change — which is the entire point.
"""

from __future__ import annotations

import os
from pathlib import Path

#: `<root>/src/memstara/paths.py` → parents[0] = memstara, [1] = src, [2] = the root.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: The folder holding this checkout and its siblings. `motoro` and `shared`
#: are checked out beside this repository, not inside it, and several paths are
#: relative to that arrangement. `environment.yml:37`'s `-e ../motoro` assumes it
#: too — renaming the sibling folder still breaks that, and this file cannot help.
WORKSPACE_ROOT = REPO_ROOT.parent

MOTORO_ROOT = WORKSPACE_ROOT / "motoro"
SHARED_ROOT = WORKSPACE_ROOT / "shared"

#: Where run artifacts go when the environment does not say otherwise.
#:
#: Pinned to the repository root deliberately, and **not** to this package. It is
#: the directory `.gitignore` covers and the directory every existing run wrote
#: into; moving the code must not move the data.
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"

# repair-citations: off
#: Logs and run records. Unconditional, matching what `logging_setup.py:35-36` did
#: before this file absorbed it — a pre-move line, read it at `2ff414d`. These two are
#: **not** redirected by `MEMSTARA_OUTPUT_DIR`, because a run that sends its subsets
#: elsewhere still belongs in the one run history.
# repair-citations: on
LOG_DIR = DEFAULT_OUTPUT_DIR / "logs"
RUNS_DIR = DEFAULT_OUTPUT_DIR / "runs"

#: The `.env` files to read, **in priority order**.
#:
#:     memstara/.env   MEMSTARA_* — this product's paths and settings
#:     motoro/.env                 LLM credentials, MOTORO_DATABASE_URL — core's own
#:
#: They are not merged. Merging would put secrets in two places, and the copy would
#: fall behind whenever the original changed. Both are read instead, and the reader
#: is `memstara.env.load_env()` — the only one.
ENV_FILES = (
    REPO_ROOT / ".env",
    MOTORO_ROOT / ".env",
)


def output_dir() -> Path:
    """Where subsets and catalogs are written, honouring `MEMSTARA_OUTPUT_DIR`.

    A function rather than a constant because the tool servers are child processes:
    core hands them the variable at spawn time, and `src/memstara/mcp_servers/ml.py:69-72` has always
    read it per call. Freezing it at import would be a behaviour change disguised as
    a tidy-up.

    Returns:
        The resolved output directory. `resolve()` flattens symlinks, so callers
        comparing this against a user-supplied path compare real paths.
    """
    return Path(os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip() or DEFAULT_OUTPUT_DIR).resolve()
