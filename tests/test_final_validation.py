"""Every completed hypothesis task gets its own one-time reserve score; no LLM calls."""
import json

import numpy as np
import pandas as pd

from memstara.evaluation import discovery_partition
from memstara.final_validation import eligible_tasks, evaluate_candidate, run


def fixture_run(tmp_path, monkeypatch):
    rng = np.random.default_rng(120)
    n = 240
    signal = rng.normal(size=n)
    frame = pd.DataFrame({"signal": signal, "noise": rng.normal(size=n),
                          "Y": (signal + rng.normal(size=n) * .6 > 0).astype(int)})
    path = tmp_path / "subset.csv"
    frame.to_csv(path, index=False)
    partition = discovery_partition(frame["Y"], seed=41, fraction=.2)
    monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(tmp_path))
    from memstara.evaluation import score
    from sklearn.linear_model import LogisticRegression
    model = LogisticRegression(C=.7, max_iter=400, random_state=41)
    params = model.get_params()
    settings = {"parameters": params, "scale_numeric": True, "threshold": .45}
    effective = {"primary_model": "logistic_regression", "folds": 0,
                 "models": {"logistic_regression": settings}, "rationale": "synthetic test"}
    plan = {"engine": "logistic_regression", "seed": 41, "test_size": .25,
            "folds": 0, "replicates": 1, "search_trials": 1}
    measured = score(path, "Y", plan, predictors=["signal", "noise"], partition=partition,
                     configuration=settings, explain=False, persist=True)
    task = {"task_id": 15, "trial": 2, "hypothesis_id": "hyp-15", "hypothesis": "Signal predicts Y",
            "status": "done", "subset_path": str(path),
            "columns_used": ["signal", "noise", "Y"], "y_column": "Y",
            "evaluation": {"auc": measured["auc"], "ml_configuration": {"effective": effective},
                           "evaluation": measured["evaluation"]}}
    config = {"evaluation": {"seed": 41}, "validation_partition": partition,
              "ml_configuration_policy": {"max_encoded_columns": 100, "max_dense_cells": 100_000}}
    return path, partition, task, config


def test_final_validation_uses_saved_fit_without_refitting(tmp_path, monkeypatch):
    path, partition, task, config = fixture_run(tmp_path, monkeypatch)
    from sklearn.pipeline import Pipeline
    monkeypatch.setattr(Pipeline, "fit", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("final validation must not retrain the selected model")))
    result = evaluate_candidate(task, config, tmp_path)
    assert result["status"] == "completed"
    assert result["scope"] == "one_time_per_hypothesis_same_dataset_validation_reserve"
    assert result["fit_scope"] == "already-fitted exploration training split; reserve excluded; no refit"
    assert result["n_fit"] == task["evaluation"]["evaluation"]["replicates"][0]["n_train"]
    assert result["n_validation"] == partition["reserved_count"]
    assert sum(result["metrics"]["confusion_matrix"][key] for key in ("tn", "fp", "fn", "tp")) == result["n_validation"]
    assert 0 <= result["metrics"]["auroc"] <= 1
    assert result["selected_task_input_sha256"]
    assert "do not use reserve outcomes to tune" in result["interpretation"]


def test_final_validation_worker_uses_the_bounded_subprocess(tmp_path, monkeypatch):
    from memstara.final_validation import _evaluate_with_budget
    from memstara.ml_configuration import policy
    _, _, task, config = fixture_run(tmp_path, monkeypatch)
    config["ml_configuration_policy"] = policy()
    monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(tmp_path))
    result = _evaluate_with_budget(task, config, tmp_path)
    assert result["status"] == "completed"
    assert result["resource_usage"]["threads"] == 1
    assert result["resource_usage"]["peak_rss_bytes"] > 0


def test_all_completed_hypothesis_tasks_are_scored_regardless_of_exploratory_rank():
    base = {"status": "done", "subset_path": "/unused", "columns_used": ["x", "Y"],
            "evaluation": {"ml_configuration": {"effective": {"primary_model": "xgboost"}}}}
    tasks = [{**base, "task_id": 4, "trial": 1, "y_column": "Y",
              "evaluation": {**base["evaluation"], "auc": .8}},
             {**base, "task_id": 5, "trial": 0, "y_column": "Y",
              "evaluation": {**base["evaluation"], "auc": .7}},
             {**base, "task_id": 1, "trial": 0, "status": "failed", "y_column": "Y",
              "evaluation": {**base["evaluation"], "auc": .99}}]
    assert [task["task_id"] for task in eligible_tasks(tasks)] == [5, 4]


def test_every_hypothesis_has_a_saved_reserve_result(tmp_path, monkeypatch):
    _, _, task, config = fixture_run(tmp_path, monkeypatch)
    second = {**task, "task_id": 16, "trial": 3, "hypothesis_id": "hyp-16",
              "hypothesis": "Noise predicts Y"}
    import memstara.final_validation as final_validation
    monkeypatch.setattr(final_validation, "_evaluate_with_budget",
                        lambda candidate, frozen, run_dir: evaluate_candidate(candidate, frozen, run_dir))
    result = run(tmp_path, config, [task, second])
    saved = json.loads((tmp_path / "final_validation.json").read_text())
    assert saved == result
    assert saved["status"] == "completed"
    assert saved["candidate_count"] == 2
    assert [row["task_id"] for row in saved["results"]] == [15, 16]
    assert [row["hypothesis_id"] for row in saved["results"]] == ["hyp-15", "hyp-16"]
    monkeypatch.setattr(final_validation, "_evaluate_with_budget", lambda *args: (_ for _ in ()).throw(
        AssertionError("completed reserve evaluations must be reused, not repeated")))
    assert run(tmp_path, config, [task, second]) == saved


def test_no_eligible_hypothesis_is_explicitly_recorded(tmp_path):
    result = run(tmp_path, {}, [{"task_id": 1, "trial": 0, "status": "failed"}])
    assert result["status"] == "not_run"
    assert json.loads((tmp_path / "final_validation.json").read_text())["status"] == "not_run"


def test_interrupted_task_is_not_replayed_but_unstarted_hypotheses_continue(tmp_path, monkeypatch):
    _, _, task, config = fixture_run(tmp_path, monkeypatch)
    second = {**task, "task_id": 16, "trial": 3, "hypothesis_id": "hyp-16",
              "hypothesis": "Noise predicts Y"}
    artifact = tmp_path / "final_validation.json"
    from memstara.final_validation import POLICY
    artifact.write_text(json.dumps({"schema_version": 2, "policy": POLICY, "status": "in_progress",
        "results": [{"key": "2:15", "task_id": 15, "trial": 2, "status": "interrupted",
                     "reason": "already started"},
                    {"key": "3:16", "task_id": 16, "trial": 3, "status": "pending"}]}))
    scored = []
    monkeypatch.setattr("memstara.final_validation._evaluate_with_budget",
                        lambda candidate, frozen, run_dir: scored.append(candidate["task_id"]) or
                        {"status": "completed", "task_id": candidate["task_id"]})
    result = run(tmp_path, config, [task, second])
    assert result["status"] == "failed"
    assert scored == [16]
    assert [row["status"] for row in result["results"]] == ["interrupted", "completed"]
