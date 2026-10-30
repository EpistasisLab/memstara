"""Central paths for package resources, dependencies and generated artifacts."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PACKAGE_ROOT = Path(__file__).resolve().parent

PROMPTS_DIR = PACKAGE_ROOT / "prompts"

PLAYBOOKS_DIR = PACKAGE_ROOT / "playbooks"

WORKSPACE_ROOT = REPO_ROOT.parent

MOTORO_ROOT = WORKSPACE_ROOT / "motoro"

DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"

LOG_DIR = DEFAULT_OUTPUT_DIR / "logs"
RUNS_DIR = DEFAULT_OUTPUT_DIR / "runs"

ENV_FILES = (
    REPO_ROOT / ".env",
    MOTORO_ROOT / ".env",
)


def output_dir() -> Path:
    """Resolve the configured directory for generated artifacts at call time."""
    return Path(os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip() or DEFAULT_OUTPUT_DIR).resolve()
