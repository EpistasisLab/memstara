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

So it is gathered here. `src/memstara/pipeline/mvp.py`, `src/memstara/pipeline/board.py`,
`debug_harness.py` and `preflight.py` all call this file, and a new entry point
needs a single line: `load_env()`.

Configuration sources and precedence
------------------------------------
Local execution reads the selected project's .env as the authoritative source.
Shell values for managed keys and sibling files cannot fill omissions. Explicit
MEMSTARA_CONFIG_MODE=environment supports CI and supervised child processes.
The first load freezes process settings; restart to adopt later file changes.

"""

from __future__ import annotations

import os
import re
from pathlib import Path


from memstara.paths import ENV_FILES
from memstara.servers import SCANNED_MODULES, source_of

# `LITELLM_LOG` used to be set here, by an `os.environ.setdefault` at import time.
#
# litellm reads it *while it is being imported* (`litellm/_logging.py:80`), so setting
# it any later than that leaves every request body unlogged — silently, which is how
# it first failed. The rule that came out of it was "every entry point must import
# this module before anything that pulls in motoro / litellm", and that rule caught
# us
# twice more.
#
# It now lives in `src/memstara/__init__.py`, which the import above cannot avoid
# running. A rule every entry point has to remember became a thing the interpreter
# does on the way in.

#: Required for any run, whichever entry point started it.
BASE_VARS = {
    "AGENTIC_OKF_BUNDLE_DIR": "the knowledge-source folder",
    "MEMSTARA_DATASET_PATH": "the data csv",
    "MEMSTARA_OUTPUT_DIR": "where the subsets go",
    "MOTORO_DATABASE_URL": "core's DB — the agents and the run history",
}

#: Credentials required by each provider used in the selected agent profiles.
#:
#: Before this existed, empty credentials did not surface until the **first LLM
#: call** — by which point a seeding round had been spent and the board already
#: carried rows.
PROVIDER_KEYS = {
    "azure_foundry": ("ANTHROPIC_FOUNDRY_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
}


_loaded_source = None
_provenance: dict = {}


def load_env() -> list[Path]:
    """Load one explicit source once, before clients are initialized."""
    global _loaded_source, _provenance
    from memstara.operational import managed, resolve
    mode = os.environ.get('MEMSTARA_CONFIG_MODE', 'project')
    path = Path(os.environ.get('MEMSTARA_ENV_FILE') or ENV_FILES[0]).expanduser().resolve()
    identity = (mode, str(path))
    if identity == _loaded_source:
        return [path] if mode == 'project' else []
    values, provenance = resolve(file=path)
    if mode == 'project':
        for name in list(os.environ):
            if managed(name):
                os.environ.pop(name, None)
    os.environ.update(values)
    _loaded_source, _provenance = identity, provenance
    return [path] if mode == 'project' else []


def configuration_source() -> dict:
    """Safe source metadata, never values or credentials."""
    return dict(_provenance)


def missing_vars(provider: str = "", *, knowledge_mode: str = "okf", data_mode: str = "dataset") -> list[str]:
    """Return every missing environment variable **at once**. An empty list means ready.

    Reported together so that fixing one and re-running does not simply reveal the
    next one.
    """
    if knowledge_mode not in ('okf', 'llm_only') or data_mode not in ('dataset', 'proposal'):
        raise ValueError('Select supported knowledge and data modes')
    omitted = set()
    if knowledge_mode == 'llm_only':
        omitted.add('AGENTIC_OKF_BUNDLE_DIR')
    if data_mode == 'proposal':
        omitted.add('MEMSTARA_DATASET_PATH')
    problems = [f"{name} is not set — {hint}"
                for name, hint in BASE_VARS.items()
                if name not in omitted and not os.environ.get(name, "").strip()]
    if provider:
        problems += model_environment_errors(provider)
    return problems


def model_environment_errors(provider: str = "", profiles=None) -> list[str]:
    """Validate explicit agent identities/endpoints and provider credentials together.

    Resource-name aliases are unnecessary when an agent supplies its API_BASE.
    Supplied frozen profiles take precedence over today's deployment on recovery.
    """
    from memstara.stage_models import deployment_profiles, validate_profiles
    problems = []
    try:
        selected = deployment_profiles() if profiles is None else validate_profiles(profiles)
    except ValueError as exc:
        selected = {}
        problems.append(str(exc))
    providers = {p['provider'] for p in selected.values()} or ({provider} if provider else set())
    for name in sorted({key for p in providers for key in PROVIDER_KEYS.get(p, ())}):
        if not os.environ.get(name, '').strip():
            problems.append(f'{name} is not set — configure the matching provider credential in .env')
    for role, profile in selected.items():
        if profile['provider'] in ('azure_foundry', 'local') and not profile.get('api_base'):
            problems.append(f'{role}: an explicit model API_BASE is required')
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

    Raises:
        FileNotFoundError: if any module in `servers.SCANNED_MODULES` is not where it
            is expected. Skipping it quietly would leave this function returning `[]`,
            which reads as "everything is fine".
    """
    from memstara.config import Settings

    allowed = {v.strip() for v in Settings().mcp_allowed_env_vars.split(",") if v.strip()}

    # Scrape the names the tool servers actually read straight out of the sources.
    # Catches both `os.environ.get("X")` and `os.environ["X"]`.
    pattern = re.compile(r'os\.environ(?:\.get)?[\[(]\s*"([A-Z_][A-Z0-9_]*)"')
    read: set[str] = set()
    for module in SCANNED_MODULES:
        path = source_of(module)
        if not path.is_file():
            raise FileNotFoundError(
                f"{path} is missing, so the allowlist check cannot be trusted. "
                "Update SCANNED_MODULES in memstara/servers.py if the file was moved "
                "or renamed — skipping it would turn this check into a permanent pass."
            )
        read |= set(pattern.findall(path.read_text(encoding="utf-8")))

    # Names core forwards by default — they arrive even when the list omits them.
    #
    # PYDEVD_* is set by `mcp_servers/debug_hook.py` **inside its own process**, so it need not come
    # from the parent. PATH and friends are already on core's default list.
    always = {"AGENTIC_OKF_BUNDLE_DIR", "PATH", "HOME", "PYDEVD_DISABLE_FILE_VALIDATION"}

    return sorted(name for name in read - allowed - always)


def configured_llm(provider: str, model: str) -> tuple[str, str]:
    """Explicit hypothesis selection for legacy scalar metadata; never a shared default."""
    from memstara.control.request import configured_llm as deployment_llm
    return deployment_llm()


def configured_api_base(provider: str, stage: str = 'hypothesis') -> str | None:
    """Read an explicit role endpoint; never consult a common endpoint."""
    from memstara.operational import agent_profile
    profile = agent_profile(stage)
    return profile.get('api_base') if profile['provider'] == provider else None
