#!/usr/bin/env python3
"""The single place where the environment is set up.

Why this file exists
--------------------
"the environment differs depending on how you launched it" is the trap that caught
this project four times in one day.

    (1) sourcing only one file in the terminal — no LLM credentials, dead on the
        first call
    (2) VS Code's `envFile` accepting a single path — same symptom
    (3) `MEMSTARA_DEBUGPY` left out of the allowlist — the hook quietly did nothing
    (4) verifying along a path that was not the real one — fine from the terminal,
        broken under F5

All four share one root: **the code that set up the environment lived separately at
every entry point.** Separate copies always drift apart.

So it is gathered here. `02_mvp_pipeline.py`, `03_board_pipeline.py`,
`debug_harness.py` and `preflight.py` all call this file, and a new entry point
needs a single line: `load_env()`.

Why there are two `.env` files
------------------------------
    memstara/.env   MEMSTARA_* — this product's paths and settings
    motoro/.env           LLM credentials, MOTORO_DATABASE_URL — core's own

They are not merged. Merging would put secrets in two places, and the copy would
fall behind whenever the original changed. **Both are read instead.**
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent.resolve()

# Turn litellm's request logging on **at import time**, not inside `load_env()`.
#
# litellm reads `LITELLM_LOG` while it is being imported (`litellm/_logging.py:80`),
# and by the time `load_env()` runs inside `main()` litellm has long since been
# imported by `pipeline_core`. Setting it later leaves the request bodies unlogged —
# which is exactly how this first failed, silently.
#
# So every entry point must import `bootstrap` **before** anything that pulls in
# motoro / litellm. This has caught us twice.
#
# It is a setdefault, so a value given by the shell or by launch.json wins.
os.environ.setdefault("LITELLM_LOG", "DEBUG")

#: The `.env` files to read, **in priority order**.
#:
#: `load_dotenv` never overwrites a value that is already set (override=False is the
#: default), so whichever file is read first wins, and whatever the shell or
#: launch.json supplied beats both — which is what keeps "a different bundle for
#: this run only" working.
ENV_FILES = (
    HERE / ".env",                            # this product's first
    HERE / ".." / "motoro" / ".env",    # core fills the gaps
)

#: Required for any run, whichever entry point started it.
BASE_VARS = {
    "AGENTIC_OKF_BUNDLE_DIR": "the knowledge-source folder",
    "MEMSTARA_DATASET_PATH": "the data csv",
    "MEMSTARA_OUTPUT_DIR": "where the subsets go",
    "MOTORO_DATABASE_URL": "core's DB — the agents and the run history",
}

#: Extra keys each provider needs. Only the one picked with `--provider` is checked.
#:
#: Before this existed, empty credentials did not surface until the **first LLM
#: call** — by which point a seeding round had been spent and the board already
#: carried rows.
PROVIDER_KEYS = {
    "azure_foundry": ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


def load_env() -> list[Path]:
    """Read the `.env` files and return the ones that were actually read.

    Safe to call repeatedly — existing values are never overwritten.
    """
    read: list[Path] = []
    for path in ENV_FILES:
        if path.is_file():
            load_dotenv(path)
            read.append(path.resolve())
    return read


def missing_vars(provider: str = "") -> list[str]:
    """Return every missing environment variable **at once**. An empty list means ready.

    Reported together so that fixing one and re-running does not simply reveal the
    next one.
    """
    problems = [f"{name} is not set — {hint}"
                for name, hint in BASE_VARS.items()
                if not os.environ.get(name, "").strip()]
    problems += [f"{name} is not set — needed for --provider {provider}. Check motoro/.env."
                 for name in PROVIDER_KEYS.get(provider, ())
                 if not os.environ.get(name, "").strip()]
    return problems


def allowlist_gaps() -> list[str]:
    """Find environment variables the tool servers read that the allowlist omits.

    **This is the most valuable check in this file.**

    Core passes only the names listed in `mcp_allowed_env_vars` down to child
    processes. A name left off that list **never reaches the tool server, and
    nothing raises an error.** The tool simply falls back to a default, or quietly
    does nothing at all.

    That happened for real: `MEMSTARA_DEBUGPY` was missing from the list, so the
    debugger hook never opened its port, and the logs said nothing. Tracking down
    the cause took a long time.

    A hand-maintained list is guaranteed to drift, so **the sources are scanned and
    compared** instead.
    """
    from settings import Settings

    allowed = {v.strip() for v in Settings().mcp_allowed_env_vars.split(",") if v.strip()}

    # Scrape the names the tool servers actually read straight out of the sources.
    # Catches both `os.environ.get("X")` and `os.environ["X"]`.
    pattern = re.compile(r'os\.environ(?:\.get)?[\[(]\s*"([A-Z_][A-Z0-9_]*)"')
    read: set[str] = set()
    for path in sorted(HERE.glob("tools_*.py")) + [HERE / "debug_hook.py"]:
        if path.is_file():
            read |= set(pattern.findall(path.read_text(encoding="utf-8")))

    # Names core forwards by default — they arrive even when the list omits them.
    #
    # PYDEVD_* is set by debug_hook **inside its own process**, so it need not come
    # from the parent. PATH and friends are already on core's default list.
    always = {"AGENTIC_OKF_BUNDLE_DIR", "PATH", "HOME", "PYDEVD_DISABLE_FILE_VALIDATION"}

    return sorted(name for name in read - allowed - always)
