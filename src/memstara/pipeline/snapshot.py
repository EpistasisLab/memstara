"""Freeze a run before provisioning agents; the MCP children read the same policy."""

import hashlib
import json
import os
from pathlib import Path

from memstara.evaluation import validate, preflight
from memstara.agent_labels import AGENT_LABELS
from memstara.pipeline.prompts import load_prompt


def freeze(args, run_dir: Path, books: dict) -> dict:
    os.environ.pop("MEMSTARA_RUN_CONFIG", None)
    combination_plan = json.loads(getattr(args, "combination_plan", "") or "null")
    if combination_plan:
        books = {stage: [s['id'] for s in entries] for stage, entries in combination_plan['skills'].items()}
    from memstara.pipeline.runtime import provider_policy
    resolved = {}
    for stage in ("hypothesis", "data", "ml", "interpreter", "report"):
        for book in books.get(stage) or [""]:
            resolved[f"board/{stage}:{book}"] = load_prompt(f"board/{stage}", book)
    if getattr(args, "report_only", False) and not os.environ.get("MEMSTARA_DATASET_PATH"):
        return {}
    dataset = Path(os.environ["MEMSTARA_DATASET_PATH"])
    from memstara.control.catalog import resolve
    ml_books = books.get("ml") or []
    skill_policy = resolve(ml_books[0]).get("evaluation", {}) if ml_books else {}
    # A skill supplies defaults; only explicitly supplied controls override them.
    evaluation = validate({**skill_policy, **json.loads(args.evaluation)})
    if not getattr(args, "report_only", False):
        preflight(dataset, args.y_column, evaluation)
    partition = None
    if not getattr(args, "report_only", False):
        from memstara.evaluation import validate_clean_dataset, discovery_partition, evaluation_splits
        frame = validate_clean_dataset(dataset, args.y_column, allow_missing=evaluation['engine'] == 'xgboost')
        partition = discovery_partition(frame[args.y_column], evaluation['seed'])
        evaluation_splits(frame[args.y_column], evaluation, partition=partition)
    from memstara.study_comparison import resolve_comparison
    comparison_policy = resolve_comparison(json.loads(getattr(args, "baseline_columns", "[]")), args.y_column, dataset)
    ablate_okf = bool(getattr(args, "ablate_okf", False))
    if ablate_okf:
        from memstara.pipeline.ablation import INSTRUCTIONS
        for prompt in resolved.values():
            prompt['system_prompt'] = INSTRUCTIONS + '\n\n' + prompt['system_prompt']
    digest = hashlib.sha256()
    with dataset.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    from memstara.pipeline.feature_context import freeze_feature_context
    from memstara.env import configured_api_base
    state = {
        "schema_version": 1,
        "critic_policy": {"version": "deterministic_feasibility_v1", "extra_llm_calls": 0},
        "knowledge_policy": {"mode": "no_okf" if ablate_okf else "okf", "retrieval_enabled": not ablate_okf},
        "agent_labels": dict(AGENT_LABELS),
        "combination_plan": combination_plan,
        "recovery_policy": {"version": "artifact_checked_v1", "question_attempts": 2, "hypothesis_attempts": 2},
        "llm_api_base": configured_api_base(getattr(args, "provider", "")),
        "validation_partition": partition,
        "hypothesis_policy": {} if getattr(args, "report_only", False) else {
            "version": "iterative_discovery_v1",
            "kind": "iterative_discovery",
            "question_contract": "fixed_target_v1",
            "prior_ml_feedback": True,
            "validation_status": "exploratory_not_independently_validated",
            "refinement": "prior_iteration_evidence_with_explicit_lineage",
        },
        "mode": "report_only" if getattr(args, "report_only", False) else "pipeline",
        "run_tag": args.run_tag,
        "pipeline_id": getattr(args, "pipeline_id", ""),
        "pipeline_name": getattr(args, "pipeline_name", ""),
        "y_column": args.y_column,
        "question": args.question,
        "skill": getattr(args, "skill", ""),
        "provider": getattr(args, "provider", None),
        "model": getattr(args, "model", None),
        "runtime_timeouts": getattr(args, "runtime_timeouts", {}),
        "provider_request_policy": provider_policy(getattr(args, "model", "") or ""),
        "hypotheses": args.hypothesis_agents,
        "interpreters": getattr(args, "interpret_agents", 1),
        "interpretation_mode": "all_per_hypothesis",
        "books": books,
        "prompts": resolved,
        "evaluation": evaluation,
        "comparison_policy": comparison_policy,
        "input_contract": "clean single dataset; column selection only; fixed binary target",
        "missing_value_policy": "native_xgboost" if evaluation["engine"] == "xgboost" else "reject",
        "explainability_review": "Review required; provisional specification",
        "dataset_sha256": digest.hexdigest(),
        **({"feature_context": freeze_feature_context(dataset, args.y_column)}
           if not getattr(args, "report_only", False) else {}),
        "knowledge_path": None if ablate_okf else os.environ.get("AGENTIC_OKF_BUNDLE_DIR"),
        "trials": args.trials,
        "waves": args.waves,
        "continuous": getattr(args, "continuous", False),
    }
    if combination_plan and not getattr(args, "report_only", False):
        from memstara.pipeline.feature_selection import freeze as freeze_selection
        state["feature_selection_policy"] = freeze_selection(state)
        state["feature_reproduction"] = {"version": 1, "directory": "feature_reproduction"}
        from memstara.ml_configuration import policy
        state["ml_configuration_policy"] = policy()
    knowledge = Path(os.environ.get("AGENTIC_OKF_BUNDLE_DIR", "/nonexistent"))
    state["knowledge_hashes"] = (
        {
            str(p.relative_to(knowledge)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(knowledge.rglob("*.md"))
            if p.is_file()
        }
        if knowledge.is_dir() and not ablate_okf
        else {}
    )
    from memstara.data_allocation import SKILLS, VERSION as allocation_version
    if any(book in SKILLS for book in books.get("data", [])):
        state["data_allocation_policy"] = {"version": allocation_version}
    if not getattr(args, "report_only", False):
        from memstara.specialist_xai import freeze as freeze_xai
        specialist = freeze_xai(books, resolved)
        if specialist:
            state["specialist_xai_policy"] = specialist
            from memstara.ml_configuration import policy
            state.setdefault("ml_configuration_policy", policy())
    state["config_hash"] = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    location = run_dir / "config.json"
    if location.exists():
        if json.loads(location.read_text()) != state:
            raise ValueError(
                "This run directory already contains a different configuration; choose a new run directory"
            )
    else:
        with location.open("x", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2)
    if state.get("feature_selection_policy"):
        from memstara.feature_reproduction import archive
        archive(state, dataset, knowledge, run_dir)
    os.environ["MEMSTARA_RUN_CONFIG"] = str(location.resolve())
    os.environ["MEMSTARA_OUTCOME_COLUMN"] = args.y_column
    return state
