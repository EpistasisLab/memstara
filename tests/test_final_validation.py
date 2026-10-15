"""Every completed hypothesis task gets its own one-time reserve score; no LLM calls."""
import json
from pathlib import Path

import pytest

import numpy as np
import pandas as pd

from memstara.evaluation import discovery_partition
from memstara.final_validation import eligible_tasks, evaluate_candidate, run


def fixture_run(tmp_path, monkeypatch, engine="logistic_regression", replicates=1):
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
    if engine == "xgboost":
        from xgboost import XGBClassifier
        model = XGBClassifier(n_estimators=8, max_depth=2, n_jobs=1, random_state=73)
    params = json.loads(json.dumps(model.get_params()), parse_constant=str)
    settings = {"parameters": params, "scale_numeric": True, "threshold": .45}
    effective = {"primary_model": engine, "folds": 0,
                 "models": {engine: settings}, "rationale": "synthetic test"}
    plan = {"engine": engine, "seed": 41, "test_size": .25,
            "folds": 0, "replicates": replicates, "search_trials": 1}
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


@pytest.mark.parametrize("engine", ["logistic_regression", "xgboost"])
@pytest.mark.parametrize("replicates", [1, 3])
def test_final_refit_uses_all_development_rows_and_saved_model_replays(tmp_path, monkeypatch, engine, replicates):
    import joblib
    from sklearn.pipeline import Pipeline
    from sklearn.metrics import roc_auc_score
    path, partition, task, config = fixture_run(tmp_path, monkeypatch, engine, replicates)
    original_fit = Pipeline.fit
    fit_rows = []
    def checked_fit(self, x, y, **kwargs):
        fit_rows.append(x.index.tolist())
        assert sorted(x.index) == sorted(partition["exploration_rows"])
        assert not kwargs  # no reserve eval_set, callbacks, or tuning
        return original_fit(self, x, y, **kwargs)
    monkeypatch.setattr(Pipeline, "fit", checked_fit)
    result = evaluate_candidate(task, config, tmp_path)
    assert len(fit_rows) == 1
    assert result["status"] == "completed"
    assert result["n_fit"] == len(partition["exploration_rows"])
    assert result["n_fit"] > task["evaluation"]["evaluation"]["replicates"][0]["n_train"]
    assert result["n_validation"] == partition["reserved_count"]
    assert sum(result["metrics"]["confusion_matrix"][key] for key in ("tn", "fp", "fn", "tp")) == result["n_validation"]
    bundle = Path(result["final_model_artifact"]["bundle_path"])
    model = joblib.load(bundle / "model.joblib")
    frame = pd.read_csv(path)
    with np.load(bundle / "split.npz") as split, np.load(bundle / "predictions.npz") as predictions:
        assert set(split["development"]).isdisjoint(split["reserve"])
        assert len(split["development"]) + len(split["reserve"]) == len(frame)
        probabilities = model.predict_proba(frame[["signal", "noise"]].iloc[split["reserve"]])[:, 1]
        np.testing.assert_array_equal(probabilities, predictions["probability"])
        assert roc_auc_score(predictions["labels"], probabilities) == result["metrics"]["auroc"]
    assert result["final_fit_seed"] == model.named_steps["model"].random_state
    if engine == "logistic_regression":
        np.testing.assert_allclose(model.named_steps["encode"].named_transformers_["numeric"].mean_,
                                   frame[["signal", "noise"]].iloc[partition["exploration_rows"]].mean())
    from memstara.reproducibility import digest
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert all(digest(bundle / name) == value for name, value in manifest["files"].items())
    assert digest(bundle / "manifest.json") == result["final_model_artifact"]["manifest_sha256"]


def test_refit_budget_rejects_before_fitting(tmp_path, monkeypatch):
    _, _, task, config = fixture_run(tmp_path, monkeypatch)
    config["ml_configuration_policy"]["max_dense_cells"] = 1
    from sklearn.pipeline import Pipeline
    monkeypatch.setattr(Pipeline, "fit", lambda *args, **kwargs: pytest.fail("must reject before fit"))
    with pytest.raises(ValueError, match="design-matrix budget"):
        evaluate_candidate(task, config, tmp_path)


def test_old_scoring_policy_is_preserved_without_refitting(tmp_path, monkeypatch):
    _, _, task, config = fixture_run(tmp_path, monkeypatch)
    artifact = tmp_path / "final_validation.json"
    old = {"schema_version": 2, "policy": "every_completed_hypothesis_task_once_v1", "status": "completed"}
    artifact.write_text(json.dumps(old))
    monkeypatch.setattr("memstara.final_validation._evaluate_with_budget", lambda *args: pytest.fail("must not refit"))
    assert run(tmp_path, config, [task])["status"] == "failed"
    assert json.loads(artifact.read_text()) == old


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


def test_reserve_values_cannot_change_final_fitted_model(tmp_path, monkeypatch):
    import joblib
    import memstara.evaluation as evaluation
    _, partition, task, config = fixture_run(tmp_path, monkeypatch)
    first = evaluate_candidate(task, config, tmp_path)
    original = evaluation.validate_clean_dataset
    def changed_reserve(*args, **kwargs):
        frame = original(*args, **kwargs)
        reserve = sorted(set(range(len(frame))) - set(partition["exploration_rows"]))
        frame.loc[reserve, "signal"] += 10000
        frame.loc[reserve, "Y"] = 1 - frame.loc[reserve, "Y"]
        return frame
    monkeypatch.setattr(evaluation, "validate_clean_dataset", changed_reserve)
    second = evaluate_candidate(task, config, tmp_path)
    a, b = [joblib.load(Path(result["final_model_artifact"]["bundle_path"]) / "model.joblib")
            for result in (first, second)]
    np.testing.assert_array_equal(a.named_steps["model"].coef_, b.named_steps["model"].coef_)
    np.testing.assert_array_equal(a.named_steps["encode"].named_transformers_["numeric"].mean_,
                                  b.named_steps["encode"].named_transformers_["numeric"].mean_)


def test_tampered_reserve_is_rejected_before_refit(tmp_path, monkeypatch):
    _, partition, task, config = fixture_run(tmp_path, monkeypatch)
    partition["reserved_split_id"] = "tampered"
    from sklearn.pipeline import Pipeline
    monkeypatch.setattr(Pipeline, "fit", lambda *args, **kwargs: pytest.fail("must reject before fit"))
    with pytest.raises(ValueError, match="integrity check"):
        evaluate_candidate(task, config, tmp_path)


def test_tampered_model_is_rejected_before_refit(tmp_path, monkeypatch):
    _, _, task, config = fixture_run(tmp_path, monkeypatch)
    bundle = Path(task["evaluation"]["evaluation"]["reproducibility"]["bundle_path"])
    (bundle / "model-0.joblib").write_bytes(b"invalid")
    with pytest.raises(ValueError, match="integrity check"):
        evaluate_candidate(task, config, tmp_path)
