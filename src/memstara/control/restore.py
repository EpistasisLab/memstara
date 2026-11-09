"""Recover a deleted workspace definition from its immutable execution settings."""

import copy
import json

from memstara.agent_labels import AGENT_LABELS
from memstara.control.request import DEFAULTS, normalize_agent_configuration


def definition(runs_root, run_tag, number):
    """Resolve an existing tag, never a caller-supplied path or replacement ID."""
    if not isinstance(run_tag, str) or not run_tag or type(number) is not int or number < 1:
        raise ValueError("Choose a saved execution and a positive experiment number")
    matches = []
    for directory in runs_root.iterdir():
        if not directory.is_dir() or directory.is_symlink():
            continue
        path = directory / "config.json"
        if not path.is_file() or path.is_symlink():
            continue
        try:
            config = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(config, dict) and config.get("run_tag") == run_tag and config.get("mode") != "report_only":
            matches.append((directory, config))
    if len(matches) != 1:
        raise ValueError("Saved execution is missing or ambiguous")
    directory, config = matches[0]
    source = directory / "resume_arguments.json"
    if source.is_symlink():
        raise ValueError("Saved settings must not be a symbolic link")
    saved = normalize_agent_configuration(json.loads(source.read_text()))
    key = config.get("pipeline_id")
    if not key or saved.get("pipeline_id") != key or saved.get("run_tag") != run_tag:
        raise ValueError("Saved settings do not belong to this experiment")
    settings = {k: copy.deepcopy(saved.get(k, value)) for k, value in DEFAULTS.items()}
    for field in ("evaluation", "ml_overrides", "baseline_columns", "stage_models", "controlled_comparison"):
        if isinstance(settings[field], str):
            settings[field] = json.loads(settings[field]) if settings[field].strip() else copy.deepcopy(DEFAULTS[field])
        if not isinstance(settings[field], type(DEFAULTS[field])):
            raise ValueError(f"Invalid saved {field}")
    plan = config.get("combination_plan")
    if plan:
        settings.update(
            combination_skills={stage: [item["id"] for item in entries] for stage, entries in plan["skills"].items()},
            combination_repetitions=plan["repetitions"],
            combination_execution_order=plan.get("execution_order", "all_pipelines_first"),
            combination_random_start=bool(plan.get("start_index", 0)),
            combination_max_loops=plan.get("max_loops"),
        )
    return {
        "id": key,
        "number": number,
        "name": config.get("pipeline_name") or saved.get("pipeline_name") or f"Experiment {number}",
        "agent_labels": copy.deepcopy(config.get("agent_labels") or AGENT_LABELS),
        "configuration": settings,
        "restored_from_run_tag": run_tag,
    }
