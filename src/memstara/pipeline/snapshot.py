"""Freeze a run before provisioning agents; the MCP children read the same policy."""

import hashlib
import json
import os
from pathlib import Path

from memstara.evaluation import validate, preflight
from memstara.pipeline.prompts import load_prompt


def freeze(args, run_dir: Path, books: dict) -> dict:
    os.environ.pop("MEMSTARA_RUN_CONFIG", None)
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
    digest = hashlib.sha256()
    with dataset.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    state = {
        "schema_version": 1,
        "hypothesis_policy": {} if getattr(args, "report_only", False) else {
            "version": "knowledge_only_v1",
            "kind": "primary_knowledge_driven",
            "prior_ml_feedback": False,
            "validation_status": "exploratory_not_independently_validated",
            "refinement": "requires_separate_preregistered_comparison",
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
        "hypotheses": args.hypothesis_agents,
        "interpreters": getattr(args, "interpret_agents", 1),
        "interpretation_mode": "all_per_hypothesis",
        "books": books,
        "prompts": resolved,
        "evaluation": evaluation,
        "input_contract": "clean single dataset; column selection only; fixed binary target",
        "missing_value_policy": "native_xgboost" if evaluation["engine"] == "xgboost" else "reject",
        "explainability_review": "reviewer original required; provisional specification",
        "dataset_sha256": digest.hexdigest(),
        "knowledge_path": os.environ.get("AGENTIC_OKF_BUNDLE_DIR"),
        "trials": args.trials,
        "waves": args.waves,
        "continuous": getattr(args, "continuous", False),
    }
    knowledge = Path(os.environ.get("AGENTIC_OKF_BUNDLE_DIR", "/nonexistent"))
    state["knowledge_hashes"] = (
        {
            str(p.relative_to(knowledge)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(knowledge.rglob("*.md"))
            if p.is_file()
        }
        if knowledge.is_dir()
        else {}
    )
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
    os.environ["MEMSTARA_RUN_CONFIG"] = str(location.resolve())
    os.environ["MEMSTARA_OUTCOME_COLUMN"] = args.y_column
    return state
