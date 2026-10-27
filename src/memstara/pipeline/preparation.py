"""Prepare empirical executions before the driver provisions agents or tools.

This boundary owns budgets, runtime/model recovery and input/configuration
preflight. The board driver retains execution gates, checkpoints and cleanup.
Proposal execution has its own preparation path and does not call this module.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from motoro import configure

from memstara.config import Settings


@dataclass(frozen=True)
class PreparedExecution:
    combination_plan: dict[str, Any] | None
    stage_models: dict[str, Any]


def normalize_random_selection(args: argparse.Namespace, books: dict[str, list[str]]) -> None:
    """A random skill must use the server-sampled contract even outside the wizard."""
    if (getattr(args, 'combination_plan', '') or args.report_only
            or 'random_features' not in books.get('hypothesis', [])):
        return
    if args.resume:
        raise ValueError('Legacy random execution has no frozen sampling policy; start a new execution')
    from memstara.combinations import STAGES, build_plan
    if (any(len(books.get(stage, [])) != 1 for stage in STAGES)
            or args.trials != 1 or args.hypothesis_agents != 1 or args.interpret_agents != 1):
        raise ValueError('Standalone random selection requires one skill per stage and one trial per Loop; '
                         'use an explicit combination plan for multiple skills')
    normalize_budget(args)
    args.combination_plan = json.dumps(build_plan(books, max_loops=args.waves))


def normalize_budget(args: argparse.Namespace) -> dict[str, Any] | None:
    """Apply the existing frozen combination and ordinary pipeline loop limits."""
    plan = json.loads(getattr(args, "combination_plan", "") or "null")
    if plan:
        limit = plan.get('total_loops')
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError('Invalid frozen combination Loop limit')
        args.waves = limit
        args.continuous = False
        args.trials = args.hypothesis_agents = args.interpret_agents = 1
    if args.pipeline_id and not plan:
        if args.continuous:
            args.waves = 10
        if not 1 <= args.waves <= 10:
            raise ValueError("Maximum Loops per pipeline must be between 1 and 10")
        args.continuous = False
    return plan


def frozen_model_source(args: argparse.Namespace, run_dir: Path) -> dict[str, Any] | None:
    """Recover the original settings; ambiguous report sources remain an error."""
    if args.resume:
        return json.loads((run_dir / "config.json").read_text())
    if args.report_only:
        from memstara.paths import RUNS_DIR

        originals = [json.loads(path.read_text()) for path in RUNS_DIR.glob("*/config.json")]
        originals = [item for item in originals if item.get("run_tag") == args.run_tag
                     and item.get("mode") != "report_only"]
        if len(originals) != 1:
            raise ValueError("Report recovery requires one unambiguous frozen source execution")
        return originals[0]
    return None


async def prepare_execution(
    args: argparse.Namespace, run_dir: Path, books: dict[str, list[str]],
) -> PreparedExecution:
    """Preserve preflight ordering and let errors stop the driver before execution."""
    from memstara.pipeline.runtime import runtime_timeouts
    from memstara.pipeline.snapshot import freeze

    normalize_random_selection(args, books)
    plan = normalize_budget(args)
    args.runtime_timeouts = runtime_timeouts(args.model)
    settings = Settings()
    if args.runtime_timeouts:
        settings = settings.model_copy(update={
            key: value for key, value in args.runtime_timeouts.items()
            if key != 'agent_timeout_seconds'})
    configure(settings)
    from memstara.pipeline.diagnostics import install

    install()
    from memstara.stage_models import resolve_run_profiles

    models = resolve_run_profiles(
        getattr(args, "stage_models", {}),
        recovering=bool(args.resume or args.report_only),
        frozen=frozen_model_source(args, run_dir),
    )
    args.stage_models = models
    if getattr(args, 'research_profile', None):
        from memstara.research_inputs import ensure_matcher, verify_materialized
        from memstara.evaluation import preflight as data_preflight, validate as validate_evaluation

        verify_materialized(args.research_profile)
        data_preflight(Path(os.environ['MEMSTARA_DATASET_PATH']), args.y_column,
                       validate_evaluation(json.loads(args.evaluation)), reserve_validation=True,
                       missing_policy=args.research_profile.get("configuration", {}).get("missing_policy", "reject"),
                       require_numeric="predictor_types" not in args.research_profile.get("configuration", {}))
        ensure_matcher(args.research_profile)
    if models:
        from memstara.stage_models import preflight_profiles

        await preflight_profiles(models)
    configuration = freeze(args, run_dir, books)
    from memstara.specialist_explanation import preflight as explanation_preflight

    await explanation_preflight(configuration, run_dir)
    return PreparedExecution(plan, models)
