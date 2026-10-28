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
    from memstara.preprocessing_policy import VERSION, TYPED, requires_numeric
    previous = None
    if getattr(args, 'resume', False) and (run_dir / 'config.json').exists():
        previous = json.loads((run_dir / 'config.json').read_text())
    from memstara.data_allocation import TWO_WAY_VERSION
    # Historical resumes and explicitly frozen comparison protocols retain their
    # original partition contract. New ordinary MVP runs use the entire cohort.
    two_way = (previous.get('partition_policy') == TWO_WAY_VERSION if previous is not None
               else not bool(json.loads(getattr(args, 'controlled_comparison', '{}') or '{}')))
    research_config = (getattr(args, "research_profile", None) or {}).get("configuration", {})
    preprocessing = previous.get('preprocessing_policy', 'legacy_encoding_v1') if previous is not None else TYPED if 'predictor_types' in research_config else VERSION
    prepared_input = requires_numeric({'preprocessing_policy': preprocessing})
    missing_policy = research_config.get("missing_policy", "reject")
    if missing_policy not in ("reject", "impute_train_v1"):
        raise ValueError("Unsupported missing-value policy")
    combination_plan = json.loads(getattr(args, "combination_plan", "") or "null")
    if combination_plan:
        books = {stage: [s['id'] for s in entries] for stage, entries in combination_plan['skills'].items()}
    from memstara.pipeline.runtime import provider_policy
    resolved = {}
    for stage in ("hypothesis", "data", "ml", "interpreter", "report"):
        for book in books.get(stage) or [""]:
            key = f"board/{stage}:{book}"
            stored = (previous or {}).get('prompts', {}).get(key)
            resolved[key] = dict(stored) if stored else load_prompt(f"board/{stage}", book)
    if two_way and previous is None:
        from memstara.paths import PROMPTS_DIR
        contract = (PROMPTS_DIR / 'board/_two_way_data.md').read_text()
        for key, prompt in resolved.items():
            if key.startswith('board/data:'):
                prompt['system_prompt'] += '\n\n' + contract
    if getattr(args, "report_only", False) and not os.environ.get("MEMSTARA_DATASET_PATH"):
        return {}
    dataset = Path(os.environ["MEMSTARA_DATASET_PATH"])
    from memstara.control.catalog import resolve
    ml_books = books.get("ml") or []
    skill_policy = resolve(ml_books[0]).get("evaluation", {}) if ml_books else {}
    # Skills supply model defaults; registered consent controls imputation.
    evaluation = validate({**skill_policy, **json.loads(args.evaluation)})
    allow_missing = False
    if not getattr(args, "report_only", False):
        preflight(dataset, args.y_column, evaluation,
                  allow_missing=allow_missing, missing_policy=missing_policy,
                  require_numeric=prepared_input)
    partition = None
    if not getattr(args, "report_only", False):
        from memstara.evaluation import validate_clean_dataset, discovery_partition, evaluation_splits
        frame = validate_clean_dataset(dataset, args.y_column,
                                       allow_missing=allow_missing, missing_policy=missing_policy,
                                       require_numeric=prepared_input)
        if not two_way:
            partition = discovery_partition(frame[args.y_column], evaluation['seed'])
        evaluation_splits(frame[args.y_column], evaluation, partition=partition)
        if two_way:
            import math
            from memstara.evaluation import DataQualityError
            # Check the most restrictive requested allocation before paid calls.
            for skill in books.get('data') or ['data_training_heavy']:
                fraction = .5 if skill == 'data_balanced_stratified' else .3
                splits = evaluation_splits(frame[args.y_column], {**evaluation, 'test_size': fraction,
                                                                  'replicates': 1}, partition={})
                if any(len(test) != math.ceil(len(frame) * fraction) for _, _, test in splits):
                    raise DataQualityError('Too few rows for the selected Data skill train/test ratio')
    from memstara.study_comparison import resolve_comparison
    comparison_policy = resolve_comparison(json.loads(getattr(args, "baseline_columns", "[]")), args.y_column, dataset)
    ablate_okf = bool(getattr(args, "ablate_okf", False))
    if ablate_okf:
        from memstara.pipeline.ablation import INSTRUCTIONS
        for key, prompt in resolved.items():
            if not key.startswith(('board/interpreter:', 'board/report:')):
                prompt['system_prompt'] = INSTRUCTIONS + '\n\n' + prompt['system_prompt']
    digest = hashlib.sha256()
    with dataset.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    from memstara.pipeline.feature_context import freeze_feature_context
    from memstara.stage_models import for_stage
    state = {
        "preprocessing_policy": preprocessing,
        "classifier_seed_policy": "split_seed_v1",
        "pause_policy": "fresh_model_request_v1",
        "schema_version": 1,
        "critic_policy": {"version": "deterministic_feasibility_v1", "extra_llm_calls": 0},
        "knowledge_policy": {"mode": "no_okf" if ablate_okf else "okf", "retrieval_enabled": not ablate_okf},
        "agent_labels": dict(AGENT_LABELS),
        "combination_plan": combination_plan,
        "recovery_policy": {"version": "artifact_checked_v1", "question_attempts": 2, "hypothesis_attempts": 2},
        "llm_api_base": (for_stage(args.stage_models, "hypothesis").get("api_base")
                         if getattr(args, "stage_models", None) else None),
        "validation_partition": partition,
        "hypothesis_policy": {} if getattr(args, "report_only", False) else {
            "version": "knowledge_only_v1" if combination_plan else "iterative_discovery_v1",
            "kind": "independent_combination" if combination_plan else "iterative_discovery",
            **({"combination_questions": "independent_combination_questions_v1"} if combination_plan else {}),
            "question_contract": "fixed_target_v1",
            "prior_ml_feedback": not bool(combination_plan),
            "validation_status": "exploratory_not_independently_validated",
            "refinement": "none" if combination_plan else "prior_iteration_evidence_with_explicit_lineage",
        },
        "data_mode": "dataset",
        "knowledge_mode": "llm_only" if ablate_okf else "okf",
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
        "missing_value_policy": missing_policy,
        "explainability_review": "Review required; provisional specification",
        "dataset_sha256": digest.hexdigest(),
        **({"feature_context": freeze_feature_context(
            dataset, args.y_column,
            require_complete=True, missing_policy=missing_policy, require_numeric=prepared_input)}
           if not getattr(args, "report_only", False) else {}),
        "knowledge_path": None if ablate_okf else os.environ.get("AGENTIC_OKF_BUNDLE_DIR"),
        "trials": args.trials,
        "waves": args.waves,
        "continuous": getattr(args, "continuous", False),
    }
    if getattr(args, 'research_profile', None):
        state['research_profile'] = args.research_profile
        state['missing_value_policy'] = missing_policy
    # New records include partition-specific metrics; saved runs keep their contract.
    from memstara.performance_metrics import VERSION as metrics_version
    if previous is None:
        state['metrics_policy'] = metrics_version
    elif 'metrics_policy' in previous:
        state['metrics_policy'] = previous['metrics_policy']
    from memstara.ml_configuration import validate_overrides
    ml_skills = ([item['id'] for item in combination_plan['skills']['ml']]
                 if combination_plan else books.get('ml', []))
    overrides = validate_overrides(
        json.loads(getattr(args, 'ml_overrides', '{}')), ml_skills, replicates=evaluation['replicates'])
    if prepared_input and any(
            settings.get('scale_numeric') for settings in overrides.get('models', {}).values()):
        raise ValueError('Automatic scaling is disabled for new runs; remove scale_numeric overrides')
    if overrides:
        state['ml_overrides'] = overrides
    if combination_plan and not getattr(args, "report_only", False):
        from memstara.pipeline.feature_selection import freeze as freeze_selection
        state["feature_selection_policy"] = freeze_selection(state)
        state["feature_reproduction"] = {"version": 1, "directory": "feature_reproduction"}
        from memstara.ml_configuration import policy
        state["ml_configuration_policy"] = policy()
    if getattr(args, "stage_models", None):
        from memstara.stage_models import snapshot_profiles
        prior_path = run_dir / "config.json"
        prior_profiles = json.loads(prior_path.read_text()).get("stage_models") if prior_path.exists() else None
        state["stage_models"] = snapshot_profiles(args.stage_models, prior_profiles)
    configurable_models = ('ml_logistic_regression', 'ml_xgboost', 'ml_default_logistic_regression')
    if any(book in configurable_models for book in books.get('ml', [])):
        from memstara.ml_configuration import policy
        state['ml_configuration_policy'] = policy()
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
    if two_way:
        state['partition_policy'] = TWO_WAY_VERSION
        allocation_version = TWO_WAY_VERSION
    if two_way or any(book in SKILLS for book in books.get("data", [])):
        state["data_allocation_policy"] = {"version": allocation_version}
    if not getattr(args, "report_only", False):
        from memstara.specialist_xai import freeze as freeze_xai
        specialist = freeze_xai(books, resolved)
        if specialist:
            state["specialist_xai_policy"] = specialist
            from memstara.ml_configuration import policy
            state.setdefault("ml_configuration_policy", policy())
    if getattr(args, 'model_connection_id', ''):
        state['model_connection_id'] = args.model_connection_id
    from memstara.specialist_explanation import freeze as freeze_explanation
    from memstara.corpus_skills import corpus_profile
    # A specialist's writing skill must not switch a Heart Failure/general
    # dataset to an unrelated expert corpus. Explicit source bindings remain opt-in.
    has_expert_sources = bool(os.environ.get('MEMSTARA_EXPLANATION_SOURCES')
                              or os.environ.get('MEMSTARA_EXPLANATION_SOURCES_JSON'))
    scoped_expert = has_expert_sources or corpus_profile(getattr(args, 'research_profile', None)) == 'hiv'
    from memstara.specialist_explanation import SKILLS as bound_expert_skills
    # A mixed perspective plan uses the same per-result handoff for every report;
    # it must not force unrelated perspectives into a specialty database binding.
    bound_only = bool(books.get('report')) and set(books['report']).issubset(bound_expert_skills)
    explanation = freeze_explanation(books, resolved) if not ablate_okf and scoped_expert and bound_only else None
    if explanation:
        state["specialist_explanation_policy"] = explanation
    from memstara.controlled_comparison import freeze as freeze_controls
    controls = freeze_controls(getattr(args, 'controlled_comparison', '{}'), state)
    if controls:
        if prepared_input and any(
                settings.get('scale_numeric') for settings in controls['ml_plan'].get('models', {}).values()):
            raise ValueError('Automatic scaling is disabled for new runs; update the comparison plan')
        if overrides:
            raise ValueError('Controlled comparisons cannot also use advanced ML overrides')
        state['controlled_comparison'] = controls
    if state.get("data_allocation_policy") and not controls and not two_way:
        # A normal run lets the first Data Agent seed the independent reserve.
        # Controlled comparisons retain their precommitted server split.
        state["validation_partition_policy"] = "data_agent_seed_v1"
        state["validation_partition"] = None
    # Resume retains the original scientific/configuration identity. Resource-only
    # recovery changes are separately validated and recorded by active_plan().
    if getattr(args, 'resume', False) and (run_dir / 'config.json').exists():
        original = json.loads((run_dir / 'config.json').read_text())
        state['preprocessing_policy'] = original.get('preprocessing_policy', 'legacy_encoding_v1')
        if 'preprocessing_policy' not in original:
            state.pop('preprocessing_policy', None)
        if 'classifier_seed_policy' in original:
            state['classifier_seed_policy'] = original['classifier_seed_policy']
        else:
            state.pop('classifier_seed_policy', None)
        if 'pause_policy' in original:
            state['pause_policy'] = original['pause_policy']
        else:
            state.pop('pause_policy', None)
        if 'ml_configuration_policy' in original:
            state['ml_configuration_policy'] = original['ml_configuration_policy']
        for key in ('partition_policy', 'data_allocation_policy',
                    'validation_partition_policy', 'validation_partition'):
            if key in original:
                state[key] = original[key]
            else:
                state.pop(key, None)
    from memstara.pipeline.experiment_policy import freeze as freeze_experiment
    freeze_experiment(state, args, previous)
    from memstara.seed_schedule import freeze as freeze_seeds
    freeze_seeds(state, args, previous)
    if state.get('seed_schedule') and not getattr(args, 'report_only', False):
        from memstara.data_allocation import request as allocation_request
        from memstara.seed_schedule import task_seed
        total = combination_plan['total_loops'] if combination_plan else args.waves * args.trials
        checked = set()
        for trial in range(total):
            allocation = allocation_request(state, trial)
            if not allocation or not allocation.get('required_data_plan'):
                raise ValueError('The selected Data skill must support the recorded split contract')
            fraction, seed = allocation['minimum_test_size'], task_seed(state, trial)
            if (fraction, seed) not in checked:
                evaluation_splits(frame[args.y_column], {**evaluation, 'test_size': fraction,
                                                        'seed': seed, 'replicates': 1}, partition={})
                checked.add((fraction, seed))
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
        from memstara.operational import save_source
        save_source(run_dir)
    if state.get("feature_selection_policy"):
        from memstara.feature_reproduction import archive
        archive(state, dataset, knowledge, run_dir)
    os.environ["MEMSTARA_RUN_CONFIG"] = str(location.resolve())
    os.environ["MEMSTARA_OUTCOME_COLUMN"] = args.y_column
    return state
