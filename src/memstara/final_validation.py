"""Final development-set refitting and one-time reserve scoring per hypothesis."""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
from typing import Any


POLICY = "every_completed_hypothesis_development_refit_v2"


def eligible_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every completed hypothesis/ML task with a frozen model and input."""
    candidates: list[dict[str, Any]] = []
    for task in tasks:
        evaluation = task.get("evaluation") or {}
        ml = evaluation.get("ml_configuration") or {}
        effective = ml.get("effective") or {}
        score = evaluation.get("auc")
        if (task.get("status") != "done" or not isinstance(score, (float, int))
                or not effective.get("primary_model") or not task.get("subset_path")
                or not task.get("columns_used") or not task.get("y_column")):
            continue
        candidates.append(task)
    return sorted(candidates, key=lambda task: (int(task.get("trial", 0)), int(task.get("task_id", 0))))


def _task_key(task: dict[str, Any]) -> str:
    return f"{int(task.get('trial', 0))}:{int(task['task_id'])}"


def _task_identity(task: dict[str, Any]) -> dict[str, Any]:
    return {"key": _task_key(task), "task_id": task["task_id"], "trial": task.get("trial"),
            "hypothesis_id": task.get("hypothesis_id"), "hypothesis": task.get("hypothesis"),
            "status": "pending"}


def _partition(run_dir: Path, config: dict, row_count: int) -> dict:
    path = run_dir / "validation_partition.json"
    partition = json.loads(path.read_text()) if path.is_file() else config.get("validation_partition")
    if not isinstance(partition, dict):
        raise ValueError("The run did not save its independent validation partition")
    exploration = partition.get("exploration_rows")
    if (partition.get("row_count") != row_count or not isinstance(exploration, list)
            or not exploration or len(set(exploration)) != len(exploration)
            or any(type(row) is not int or row < 0 or row >= row_count for row in exploration)):
        raise ValueError("Saved validation partition does not match the selected task rows")
    reserve = sorted(set(range(row_count)) - set(exploration))
    if len(reserve) != partition.get("reserved_count") or not reserve:
        raise ValueError("Saved validation reserve is empty or inconsistent")
    import numpy as np
    if hashlib.sha256(np.asarray(reserve, dtype=int).tobytes()).hexdigest() != partition.get("reserved_split_id"):
        raise ValueError("Saved validation reserve indices failed their integrity check")
    return {**partition, "exploration_rows": sorted(exploration), "reserved_rows": reserve}


def evaluate_candidate(candidate: dict[str, Any], config: dict, run_dir: Path) -> dict:
    """Refit the frozen configuration on all development rows, then score the reserve."""
    began = time.perf_counter()
    import numpy as np
    from sklearn.base import clone
    from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score,
                                 auc, brier_score_loss, cohen_kappa_score, confusion_matrix,
                                 f1_score, log_loss, matthews_corrcoef, precision_recall_curve,
                                 precision_score, recall_score, roc_auc_score)
    from threadpoolctl import threadpool_limits

    task_evaluation = candidate["evaluation"]
    ml_record = task_evaluation["ml_configuration"]
    effective = ml_record["effective"]
    model_name = effective["primary_model"]
    settings = effective["models"][model_name]
    target = candidate["y_column"]
    path = Path(candidate["subset_path"]).resolve()
    source_bytes = path.read_bytes()
    measured_input_hash = (task_evaluation.get("evaluation") or {}).get("dataset_sha256")
    if measured_input_hash and hashlib.sha256(source_bytes).hexdigest() != measured_input_hash:
        raise ValueError("Hypothesis task input differs from its ML evaluation artifact")
    allocation = task_evaluation.get("data_allocation") or {}
    expected_subset = allocation.get("subset_sha256")
    if expected_subset and hashlib.sha256(source_bytes).hexdigest() != expected_subset:
        raise ValueError("Hypothesis task input changed after exploratory evaluation")
    limits = config.get("ml_configuration_policy", {})
    from memstara.paired_ml import exceeds_limit
    if exceeds_limit(limits, "max_csv_bytes", len(source_bytes)):
        raise ValueError("Final validation input exceeds the configured CSV size budget")
    from memstara.evaluation import validate_clean_dataset
    from memstara.missing_values import resolve_policy, imputation_record
    from memstara.preprocessing_policy import analysis_ready
    frame = validate_clean_dataset(path, target, allow_missing=model_name == "xgboost",
                                   missing_policy=resolve_policy(config), require_numeric=analysis_ready(config))
    features = [name for name in candidate["columns_used"] if name != target]
    if not features or any(name not in frame for name in features):
        raise ValueError("Hypothesis task feature list does not match its saved input")
    frame = frame[features + [target]]
    partition = _partition(run_dir, config, len(frame))
    if allocation.get("reserved_rows") and sorted(allocation["reserved_rows"]) != partition["reserved_rows"]:
        raise ValueError("Hypothesis task allocation disagrees with the run's frozen reserve")

    template, _, manifest_hash = _load_fitted_model(candidate, config, features, model_name, settings,
                                                        source_bytes, partition)
    y = frame[target]
    if y.isna().any() or set(y.unique()) != {0, 1}:
        raise ValueError("Final validation requires the original complete binary target")
    reserve = np.asarray(partition["reserved_rows"], dtype=int)
    y_test = y.iloc[reserve]
    if y_test.nunique() != 2:
        raise ValueError("Both target classes must be present in the independent validation reserve")
    x = frame[features]
    development = np.asarray(partition["exploration_rows"], dtype=int)
    if y.iloc[development].nunique() != 2:
        raise ValueError("Both target classes must be present in the final training population")
    # clone discards ALL learned preprocessing and estimator state. The verified
    # template supplies structure only; parameters come from the immutable plan.
    model = clone(template)
    parameters = dict(settings["parameters"])
    if parameters.get("missing") == "NaN":
        parameters["missing"] = float("nan")
    if parameters.get("early_stopping_rounds") is not None or parameters.get("callbacks"):
        raise ValueError("Final refit requires a frozen training length without early-stopping callbacks")
    model.named_steps["model"].set_params(**parameters)
    # Bound dense allocation BEFORE fitting, including categories unseen in the
    # original replicate. Only development rows determine preprocessing dimensions.
    width = 0
    for name, _, columns in model.named_steps["encode"].transformers:
        if name == "numeric":
            width += len(columns)
        elif name == "categorical":
            width += sum(x.iloc[development][column].nunique(dropna=False) for column in columns)
        else:
            raise ValueError("Unsupported preprocessing structure for final refit")
    if exceeds_limit(limits, "max_encoded_columns", width):
        raise ValueError("Final validation input exceeds the configured encoded-column budget")
    if exceeds_limit(limits, "max_dense_cells", width * max(len(development), len(reserve))):
        raise ValueError("Final validation input exceeds the configured design-matrix budget")
    fit_started = time.perf_counter()
    with threadpool_limits(limits=1):
        model.fit(x.iloc[development], y.iloc[development])
    fit_seconds = time.perf_counter() - fit_started
    # Persist the final model before exposing any reserve predictions.
    bundle = _save_final_model(run_dir, candidate, model, source_bytes, settings,
                               features, target, development, reserve, manifest_hash)
    score_started = time.perf_counter()
    with threadpool_limits(limits=1):
        probability = model.predict_proba(x.iloc[reserve])[:, 1]
    score_seconds = time.perf_counter() - score_started
    threshold = settings["threshold"]
    predicted = probability >= threshold
    matrix = confusion_matrix(y_test, predicted, labels=[0, 1])
    tn, fp, fn, tp = (int(value) for value in matrix.ravel())
    precision_curve, recall_curve, _ = precision_recall_curve(y_test, probability)
    metrics = {
        "auroc": float(roc_auc_score(y_test, probability)),
        "pr_auc_trapezoidal": float(auc(recall_curve, precision_curve)),
        "average_precision": float(average_precision_score(y_test, probability)),
        "brier_score": float(brier_score_loss(y_test, probability)),
        "log_loss": float(log_loss(y_test, probability, labels=[0, 1])),
        "accuracy": float(accuracy_score(y_test, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(y_test, predicted)),
        "f1": float(f1_score(y_test, predicted, zero_division=0)),
        "confusion_matrix": {"labels": [0, 1], "tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "sensitivity": float(recall_score(y_test, predicted, zero_division=0)),
        "specificity": tn / (tn + fp) if tn + fp else None,
        "precision": float(precision_score(y_test, predicted, zero_division=0)),
        "negative_predictive_value": tn / (tn + fn) if tn + fn else None,
        "matthews_correlation_coefficient": float(matthews_corrcoef(y_test, predicted)),
        "cohen_kappa": float(cohen_kappa_score(y_test, predicted)),
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "false_negative_rate": fn / (fn + tp) if fn + tp else None,
        "false_discovery_rate": fp / (fp + tp) if fp + tp else None,
        "false_omission_rate": fn / (fn + tn) if fn + tn else None,
        "youden_j": (tp / (tp + fn) + tn / (tn + fp) - 1)
                    if tp + fn and tn + fp else None,
    }
    np.savez_compressed(bundle / "predictions.npz", rows=reserve,
                        labels=y_test.to_numpy(), probability=probability, predicted=predicted)
    from memstara.pipeline.checkpoint import atomic_json
    from memstara.reproducibility import digest
    atomic_json(bundle / "metrics.json", metrics)
    final_manifest_path = bundle / "manifest.json"
    final_manifest = json.loads(final_manifest_path.read_text())
    final_manifest["files"].update({name: digest(bundle / name)
                                    for name in ("predictions.npz", "metrics.json")})
    final_manifest["status"] = "evaluated"
    atomic_json(final_manifest_path, final_manifest)
    for file in bundle.iterdir():
        file.chmod(0o600)
    return {
        "schema_version": 2, "status": "completed",
        "scope": "one_time_per_hypothesis_same_dataset_validation_reserve",
        "selection_policy": POLICY,
        "hypothesis_id": candidate.get("hypothesis_id"),
        "hypothesis": candidate.get("hypothesis"),
        "task_id": candidate["task_id"], "trial": candidate["trial"],
        "exploratory_auc": float(task_evaluation["auc"]),
        "model": model_name, "parameters": settings["parameters"],
        "numeric_scaling": settings["scale_numeric"], "probability_threshold": threshold,
        "target": target, "features": features,
        "fit_scope": "all non-reserve development rows; frozen settings; fresh preprocessing and model fit",
        "training_split_id": hashlib.sha256(development.tobytes()).hexdigest(),
        "imputation": imputation_record(model, resolve_policy(config), fit_scope="development_partition"),
        "n_fit": int(len(development)),
        "n_validation": int(len(reserve)),
        "fit_class_counts": {str(k): int(v) for k, v in y.iloc[development].value_counts().items()},
        "validation_class_counts": {str(k): int(v) for k, v in y_test.value_counts().items()},
        "validation_partition": {"seed": partition.get("seed"), "fraction": partition.get("fraction"),
                                 "split_id": partition.get("reserved_split_id"),
                                 "status": "scored_once_after_exploration"},
        "selected_task_input_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_model_bundle_manifest_sha256": manifest_hash,
        "final_model_artifact": {"bundle_path": str(bundle.resolve()),
                                 "model_sha256": final_manifest["files"]["model.joblib"],
                                 "manifest_sha256": digest(final_manifest_path)},
        "final_fit_seconds": fit_seconds, "reserve_prediction_seconds": score_seconds,
        "final_fit_seed": parameters.get("random_state"),
        "metrics": metrics, "duration_seconds": time.perf_counter() - began,
        "interpretation": "This is the one-time reserve estimate for this hypothesis task. "
                          "The same reserve is scored separately for each completed hypothesis task; "
                          "do not use reserve outcomes to tune settings or choose hypotheses.",
    }


def _save_final_model(run_dir, candidate, model, source, settings, features, target,
                      development, reserve, source_manifest_hash):
    """Keep final-fit evidence separate from immutable exploratory artifacts."""
    import joblib
    import numpy as np
    from memstara.pipeline.checkpoint import atomic_json
    from memstara.reproducibility import digest, environment

    root = run_dir / "final_models"
    root.mkdir(parents=True, exist_ok=True)
    bundle = Path(tempfile.mkdtemp(prefix=f"task-{int(candidate['task_id'])}-", dir=root))
    joblib.dump(model, bundle / "model.joblib")
    (bundle / "input.csv").write_bytes(source)
    np.savez_compressed(bundle / "split.npz", development=development, reserve=reserve)
    atomic_json(bundle / "environment.json", environment())
    (bundle / "final_validation.py").write_bytes(Path(__file__).read_bytes())
    atomic_json(bundle / "manifest.json", {
        "schema_version": 1, "policy": POLICY, "status": "fitted_before_reserve_prediction",
        "task_id": candidate["task_id"], "trial": candidate["trial"],
        "target": target, "features": features, "configuration": settings,
        "source_manifest_sha256": source_manifest_hash,
        "training_scope": "all non-reserve development rows",
        "n_fit": len(development), "n_validation": len(reserve),
        "files": {file.name: digest(file) for file in bundle.iterdir()},
    })
    for file in bundle.iterdir():
        file.chmod(0o600)
    return bundle


def _load_fitted_model(candidate: dict[str, Any], config: dict, features: list[str], model_name: str,
                       settings: dict, source_bytes: bytes, partition: dict):
    """Verify the local ML bundle before loading its fitted estimator for prediction."""
    import joblib
    import numpy as np
    from memstara.paths import DEFAULT_OUTPUT_DIR

    task_evaluation = candidate["evaluation"]
    artifact = (task_evaluation.get("evaluation") or {}).get("reproducibility") or {}
    bundle = Path(artifact.get("bundle_path", "")).resolve()
    root = (Path(os.environ.get("MEMSTARA_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR) / "reproducibility").resolve()
    try:
        bundle.relative_to(root)
    except ValueError:
        raise ValueError("Saved model bundle is outside the configured reproducibility directory") from None
    if artifact.get("status") != "verified":
        raise ValueError("The selected ML artifact has no verified fitted model bundle")
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("The selected model bundle has no manifest")
    manifest_bytes = manifest_path.read_bytes()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_hash != artifact.get("manifest_sha256"):
        raise ValueError("The selected model bundle manifest changed after ML evaluation")
    manifest = json.loads(manifest_bytes)
    if (manifest.get("version") != 1 or manifest.get("target") != candidate["y_column"]
            or manifest.get("predictors") != features or manifest.get("plan", {}).get("engine") != model_name
            or manifest.get("configuration") != settings):
        raise ValueError("The fitted model bundle does not match the selected task and frozen ML settings")
    expected_input = hashlib.sha256(source_bytes).hexdigest()
    files = manifest.get("files") or {}
    if files.get("input.csv") != expected_input:
        raise ValueError("The fitted model bundle input differs from the selected task input")
    split_path = bundle / "split-0.npz"
    if not split_path.is_file() or hashlib.sha256(split_path.read_bytes()).hexdigest() != files.get("split-0.npz"):
        raise ValueError("The fitted model's training-split record is missing or failed integrity validation")
    split_record = task_evaluation["evaluation"]["replicates"][0]
    with np.load(split_path, allow_pickle=False) as saved_split:
        train_rows = saved_split["train"]
        exploratory_test_rows = saved_split["test"]
    if (hashlib.sha256(train_rows.tobytes()).hexdigest() != split_record.get("train_split_id")
            or hashlib.sha256(exploratory_test_rows.tobytes()).hexdigest() != split_record.get("split_id")):
        raise ValueError("The saved fitted model does not match the selected task's recorded split")
    exploration_rows = set(partition["exploration_rows"])
    reserved_rows = set(partition["reserved_rows"])
    if (not set(train_rows.tolist()).issubset(exploration_rows)
            or not set(exploratory_test_rows.tolist()).issubset(exploration_rows)
            or set(train_rows.tolist()) & reserved_rows
            or set(exploratory_test_rows.tolist()) & reserved_rows):
        raise ValueError("The fitted model's train/test rows overlap the final validation reserve")
    model_name_in_bundle = "model-0.joblib"
    model_path = bundle / model_name_in_bundle
    if (Path(model_name_in_bundle).name != model_name_in_bundle or not model_path.is_file()
            or hashlib.sha256(model_path.read_bytes()).hexdigest() != files.get(model_name_in_bundle)):
        raise ValueError("The saved fitted model is missing or its integrity check failed")
    if (not manifest.get("verification") or manifest["verification"][0].get("status") != "verified"
            or manifest["verification"][0].get("replicate") != 1):
        raise ValueError("The saved model did not pass the ML artifact's refit-integrity check")
    if not task_evaluation.get("evaluation", {}).get("replicates"):
        raise ValueError("The selected ML result has no recorded fitted training split")
    return joblib.load(model_path), manifest, manifest_hash


def run(run_dir: Path, config: dict, tasks: list[dict]) -> dict:
    """Score every eligible hypothesis task once and persist each outcome as it finishes."""
    if config.get('partition_policy') == 'two_way_stratified_v1':
        return {'status': 'not_applicable', 'policy': 'two_way_stratified_v1', 'results': [],
                'reason': 'Use each task train/test evaluation. No reserve scoring or final refit.'}
    from memstara.pipeline.checkpoint import atomic_json

    artifact = run_dir / "final_validation.json"
    candidates = eligible_tasks(tasks)
    if artifact.is_file():
        previous = json.loads(artifact.read_text())
        if previous.get("schema_version") != 2 or previous.get("policy") != POLICY:
            return {"schema_version": 2, "status": "failed", "policy": POLICY,
                    "reason": "An incompatible prior final-validation record exists; the reserve will not be rescored."}
        if previous.get("status") in ("completed", "failed", "not_run"):
            return previous
        stored = previous.get("results", [])
        expected = [_task_identity(task) for task in candidates]
        if [row.get("key") for row in stored] != [row["key"] for row in expected]:
            return {**previous, "status": "failed",
                    "reason": "The completed-task set changed after reserve scoring began; no task was rescored."}
        results = stored
        for row in results:
            if row.get("status") == "in_progress":
                row.update(status="interrupted", reason=(
                    "Scoring began but did not finish; this task will not be rescored."
                ))
        result = previous
    elif not candidates:
        result = {"schema_version": 2, "status": "not_run", "policy": POLICY, "results": [],
                  "reason": "No completed hypothesis task contains a frozen ML plan and saved input."}
        atomic_json(artifact, result)
        return result
    else:
        results = [_task_identity(task) for task in candidates]
        result = {"schema_version": 2, "status": "in_progress", "policy": POLICY,
                  "reserve_scope": "same run-time split, withheld from all exploration Loops",
                  "candidate_count": len(candidates), "results": results, "started_at": time.time()}
        atomic_json(artifact, result)

    tasks_by_key = {_task_key(task): task for task in candidates}
    for row in results:
        if row.get("status") != "pending":
            continue
        candidate = tasks_by_key[row["key"]]
        row.update(status="in_progress", started_at=time.time())
        result.update(status="in_progress", results=results)
        atomic_json(artifact, result)
        try:
            outcome = _evaluate_with_budget(candidate, config, run_dir)
            row.update(outcome)
        except Exception as exc:
            row.update(status="failed", error_type=type(exc).__name__, reason=str(exc))
        row["finished_at"] = time.time()
        result.update(results=results)
        atomic_json(artifact, result)

    failed = [row for row in results if row.get("status") in ("failed", "interrupted")]
    pending = [row for row in results if row.get("status") == "pending"]
    result.update(status="failed" if failed else "interrupted" if pending else "completed",
                  completed_count=sum(row.get("status") == "completed" for row in results),
                  failed_count=len(failed), results=results, finished_at=time.time())
    if failed:
        result["reason"] = "One or more per-hypothesis reserve evaluations failed or were interrupted; " \
                            "successful task results are preserved and failures are not automatically retried."
    atomic_json(artifact, result)
    return result


def _evaluate_with_budget(candidate: dict[str, Any], config: dict, run_dir: Path) -> dict:
    """Run final fitting and prediction under the normal process-level limits."""
    from memstara.paired_ml import atomic, supervise
    from memstara.paths import DEFAULT_OUTPUT_DIR

    root = Path(os.environ.get("MEMSTARA_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR)
    root.mkdir(parents=True, exist_ok=True)
    limits = config.get("ml_configuration_policy")
    if not limits:
        from memstara.ml_configuration import policy
        limits = policy()
    # Only pass the frozen ML plan and the row-allocation provenance the child needs.
    evaluation = candidate["evaluation"]
    minimal_candidate = {
        key: candidate[key] for key in
        ("task_id", "trial", "status", "subset_path", "columns_used", "y_column")
    }
    for key in ("hypothesis_id", "hypothesis", "question_id"):
        if key in candidate:
            minimal_candidate[key] = candidate[key]
    minimal_candidate["evaluation"] = {
        "auc": evaluation["auc"],
        "ml_configuration": evaluation["ml_configuration"],
        # Preserve only the model artifact and fit/split provenance required by
        # the child. Its verified template is cloned and refitted on development
        # rows; no reserve-guided model selection or tuning is performed.
        "evaluation": {
            "dataset_sha256": (evaluation.get("evaluation") or {}).get("dataset_sha256"),
            "reproducibility": (evaluation.get("evaluation") or {}).get("reproducibility"),
            "replicates": (evaluation.get("evaluation") or {}).get("replicates"),
        },
        "data_allocation": {key: (evaluation.get("data_allocation") or {}).get(key)
                             for key in ("reserved_rows", "subset_sha256")},
    }
    minimal_config = {key: config.get(key) for key in
                      ("evaluation", "validation_partition", "ml_configuration_policy")}
    with tempfile.TemporaryDirectory(prefix="final-validation-", dir=root) as folder:
        temporary_root = Path(folder)
        request_path, result_path = temporary_root / "request.json", temporary_root / "result.json"
        atomic(request_path, {"candidate": minimal_candidate, "config": minimal_config,
                              "run_dir": str(run_dir.resolve())})
        env = {**os.environ, **{name: "1" for name in (
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")}}
        # Final refits obey the same global ML concurrency limit as exploration.
        with (root / ".paired-ml.lock").open("a") as lock:
            wait_started = time.monotonic()
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if (limits.get("wall_seconds") is not None
                            and time.monotonic() - wait_started >= limits["wall_seconds"]):
                        raise RuntimeError(
                            "Final refit could not acquire the ML resource lock within its wait budget"
                        ) from None
                    time.sleep(.2)
            usage = supervise([sys.executable, "-m", "memstara.final_validation",
                               str(request_path), str(result_path)], env=env, limits=limits)
            usage["lock_wait_seconds"] = time.monotonic() - wait_started - usage["duration_seconds"]
        result = json.loads(result_path.read_text())
    if result.get("status") != "completed":
        frames = result.get("failure_trace", [])
        location = f" at {frames[-1]['file']}:{frames[-1]['line']}" if frames else ""
        raise RuntimeError(f"Final validation worker failed ({result.get('error_type', 'unknown')}){location}")
    result["resource_usage"] = usage
    return result


def _worker(request_path: Path, result_path: Path) -> None:
    """Isolated worker entry point; the parent supervisor also enforces the deadline."""
    request = json.loads(request_path.read_text())
    policy = request["config"].get("ml_configuration_policy") or {}
    deadline = policy.get("wall_seconds")
    if isinstance(deadline, int) and deadline > 0:
        signal.alarm(deadline)
    from memstara.paired_ml import atomic
    try:
        result = evaluate_candidate(request["candidate"], request["config"], Path(request["run_dir"]))
    except Exception as exc:
        import traceback
        result = {"schema_version": 1, "status": "failed", "error_type": type(exc).__name__,
                  "failure_trace": [{"file": Path(frame.filename).name, "line": frame.lineno,
                                     "function": frame.name}
                                    for frame in traceback.extract_tb(exc.__traceback__)]}
    atomic(result_path, result)


if __name__ == "__main__":
    _worker(Path(sys.argv[1]), Path(sys.argv[2]))
