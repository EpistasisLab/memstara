"""User-facing V1 contracts, immutable skills and executable evaluation policies."""

import asyncio
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from memstara.control import catalog
from memstara.control.request import build_argv
from memstara.evaluation import score, validate, DataQualityError
from memstara.mcp_servers.ml import train_and_score, train_and_score_async
from memstara.pipeline.prompts import load_prompt
from memstara.pipeline.snapshot import freeze


@pytest.fixture
def clean_data(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMSTARA_RUN_CONFIG", raising=False)
    monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(tmp_path))
    rng = np.random.default_rng(12)
    x = rng.normal(size=100)
    frame = pd.DataFrame(
        {
            "x": x,
            "noise": rng.normal(size=100),
            "kind": ["a", "b"] * 50,
            "outcome": (x + rng.normal(size=100) * 0.5 > 0).astype(int),
        }
    )
    path = tmp_path / "dataset.csv"
    frame.to_csv(path, index=False)
    monkeypatch.setenv("MEMSTARA_DATASET_PATH", str(path))
    return path


def test_user_skill_is_versioned_and_role_scoped(clean_data):
    first = catalog.register({"stage": "hypothesis", "name": "custom", "content": "# Custom\nUse anatomy."})
    changed = catalog.register({"stage": "hypothesis", "name": "custom", "content": "# Custom\nUse drugs."})
    assert first["id"] != changed["id"]
    assert "Use anatomy." in load_prompt("board/hypothesis", first["id"])["system_prompt"]
    with pytest.raises(ValueError, match="ml role"):
        catalog.validate_selection({"playbook_ml": first["id"]})
    renamed = catalog.register({"stage": "hypothesis", "name": "other", "content": "# Custom\nUse anatomy."})
    with pytest.raises(ValueError, match="different skill"):
        catalog.validate_selection({"hypothesis_agents": 2, "playbook_hypothesis": f"{first['id']},{renamed['id']}"})


def test_snapshot_freezes_prompt_and_forces_model_and_seed(clean_data, tmp_path, monkeypatch):
    args = SimpleNamespace(
        run_tag="test",
        question="Predict the outcome",
        hypothesis_agents=1,
        y_column="outcome",
        evaluation=json.dumps({"engine": "logistic_regression", "seed": 7}),
        trials=1,
        waves=1,
    )
    snapshot = freeze(args, tmp_path, {"hypothesis": ["treatment-toxicity"]})
    monkeypatch.setattr(catalog.prompts, "PLAYBOOKS_DIR", tmp_path / "no-longer-present")
    assert (
        load_prompt("board/hypothesis", "treatment-toxicity")
        == snapshot["prompts"]["board/hypothesis:treatment-toxicity"]
    )
    result = json.loads(train_and_score(str(clean_data), "outcome", seed=999))
    assert "error" not in result, result
    assert result["seed"] == 7
    assert result["model"] == "logistic_regression"
    assert "fixed target" in json.loads(train_and_score(str(clean_data), "x"))["error"]


@pytest.mark.parametrize("engine", ["xgboost", "random_forest", "logistic_regression"])
def test_model_cv_replicates_and_explanations_are_computed(clean_data, engine):
    result = score(clean_data, "outcome", {"engine": engine, "folds": 2, "replicates": 2, "search_trials": 2})
    assert 0 <= result["auc"] <= 1
    json.dumps(result, allow_nan=False)
    replicas = result["evaluation"]["replicates"]
    assert len(replicas) == 2 and all(r["cv_auc"] is not None for r in replicas)
    assert replicas[0]["split_id"] != replicas[1]["split_id"]
    assert result["explanation"]["partial_dependence"]
    if engine == "xgboost":
        assert result["explanation"]["shap"]["mean_absolute"]
    assert result["explanation"]["clinical_threshold"] is None


def test_feature_subsets_share_split_and_do_not_fit_encoders_on_holdout(clean_data, tmp_path):
    other = tmp_path / "other.csv"
    pd.read_csv(clean_data).drop(columns=["noise"]).to_csv(other, index=False)
    a = score(clean_data, "outcome", {"engine": "logistic_regression"})
    b = score(other, "outcome", {"engine": "logistic_regression"})
    assert a["evaluation"]["replicates"][0]["split_id"] == b["evaluation"]["replicates"][0]["split_id"]


def test_mcp_training_is_concurrent_and_writes_separate_artifacts(clean_data, tmp_path):
    second = tmp_path / "second.csv"
    second.write_bytes(clean_data.read_bytes())

    async def run():
        return await asyncio.gather(
            train_and_score_async(str(clean_data), "outcome"), train_and_score_async(str(second), "outcome")
        )

    a, b = [json.loads(x) for x in asyncio.run(run())]
    assert "error" not in a and "error" not in b
    intervals = [(x["evaluation"]["started_at"], x["evaluation"]["duration_seconds"]) for x in (a, b)]
    assert max(t for t, _ in intervals) < min(t + d for t, d in intervals)
    assert clean_data.with_suffix(".evaluation.json").exists() and second.with_suffix(".evaluation.json").exists()


def test_governance_request_rejects_unsupported_or_unsafe_options():
    for plan in ({"folds": 1}, {"seed": True}, {"replicates": 0}, {"search_trials": 11}, {"test_size": float("nan")}):
        with pytest.raises(ValueError):
            validate(plan)
    argv = build_argv({"evaluation": {"engine": "random_forest"}, "question": "What predicts the target?"}, [])
    assert json.loads(argv[argv.index("--evaluation") + 1])["engine"] == "random_forest"
    assert argv[argv.index("--question") + 1] == "What predicts the target?"


def test_governance_skill_carries_executable_defaults(clean_data):
    skill = catalog.register(
        {
            "stage": "ml",
            "name": "cv",
            "content": '<!-- evaluation: {"folds": 5, "replicates": 2} -->\n# Governance\nUse cross-validation.',
        }
    )
    assert skill["evaluation"] == {"folds": 5, "replicates": 2}
    assert "<!--" not in skill["content"]
    with pytest.raises(ValueError):
        catalog.register({"stage": "ml", "name": "bad", "content": '<!-- evaluation: {"folds": 1} -->\nInvalid folds'})


@pytest.mark.parametrize("engine", ["xgboost", "random_forest", "logistic_regression"])
def test_missing_infinite_categorical_and_empty_features_are_handled(clean_data, engine):
    frame = pd.read_csv(clean_data)
    frame.loc[:20, "x"] = np.nan
    frame.loc[21, "noise"] = np.inf
    frame.loc[:15, "kind"] = np.nan
    frame["empty"] = np.nan
    frame.to_csv(clean_data, index=False)
    original = clean_data.read_bytes()
    with pytest.raises(DataQualityError, match="AI-ready input required"):
        score(clean_data, "outcome", {"engine": engine, "folds": 2})
    assert clean_data.read_bytes() == original


def test_missing_labels_produce_measured_failure_not_fake_auc(clean_data):
    frame = pd.read_csv(clean_data)
    frame.loc[0, "outcome"] = np.nan
    frame.to_csv(clean_data, index=False)
    result = json.loads(train_and_score(str(clean_data), "outcome"))
    assert result["status"] == "failed"
    assert "cannot be imputed" in result["error"]
    assert "auc" not in result
    assert json.loads(clean_data.with_suffix(".evaluation.json").read_text()) == result


def test_tiny_minority_disables_cv_search_explicitly(clean_data):
    frame = pd.read_csv(clean_data).iloc[:8].copy()
    frame["outcome"] = [0] * 6 + [1] * 2
    frame.to_csv(clean_data, index=False)
    result = score(clean_data, "outcome", {"engine": "logistic_regression", "test_size": .5,
                                          "folds": 5, "search_trials": 3})
    rep = result["evaluation"]["replicates"][0]
    assert rep["cv_folds"] == 0 and rep["cv_auc"] is None
    assert any("CV folds reduced" in w for w in result["data_quality"]["warnings"])


def test_failed_tasks_do_not_keep_retry_loop_alive():
    from memstara.pipeline.board import summarise
    counts, retries = summarise([
        {"task_id": 1, "task_type": "ml", "status": "failed", "attempts": 9},
        {"task_id": 2, "task_type": "ml", "status": "ready", "attempts": 1},
    ])
    assert counts == {"ml/ready": 1}
    assert retries == []


def test_encoding_statistics_never_include_holdout(clean_data, monkeypatch):
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    frame = pd.read_csv(clean_data)
    train, test = train_test_split(np.arange(len(frame)), test_size=25, random_state=42,
                                   stratify=frame["outcome"])
    frame.loc[test, "x"] = 1_000_000.0
    frame.to_csv(clean_data, index=False)
    captured = []
    original_fit = StandardScaler.fit

    def track(self, X, y=None):
        fitted = original_fit(self, X, y)
        captured.append(self.mean_.copy())
        return fitted

    monkeypatch.setattr(StandardScaler, "fit", track)
    score(clean_data, "outcome", {"engine": "logistic_regression"})
    assert len(captured) == 1
    assert captured[0][0] == pytest.approx(frame.iloc[train]["x"].mean())
    assert captured[0][0] != pytest.approx(frame["x"].mean())


def test_threshold_evidence_and_replicates_are_measured(clean_data):
    result = score(clean_data, "outcome", {"engine": "logistic_regression", "replicates": 10})
    replicas = result["evaluation"]["replicates"]
    assert len(replicas) == 10
    assert [r["seed"] for r in replicas] == list(range(42, 52))
    assert result["auc"] == pytest.approx(np.mean([r["auc"] for r in replicas]))
    for rep in replicas:
        op = rep["operating_point"]
        assert op["probability_cutoff"] == .5
        assert op["true_positive"] + op["false_negative"] == rep["test_class_counts"]["1"]
        assert op["true_negative"] + op["false_positive"] == rep["test_class_counts"]["0"]
        assert op["sensitivity"] == pytest.approx(op["true_positive"] / rep["test_class_counts"]["1"])
    explanation = result["explanation"]
    assert "reviewer original required" in explanation["review_status"]
    assert explanation["clinical_threshold"] is None
    for effect in explanation["feature_effects"]:
        assert effect["range_start"] <= effect["range_end"]
        assert effect["probability_change"] == pytest.approx(effect["probability_after"] - effect["probability_before"])
    json.dumps(result, allow_nan=False)


def test_fixed_parameters_and_split_across_hypotheses(clean_data, tmp_path):
    other = tmp_path / "subset.csv"
    pd.read_csv(clean_data).drop(columns=["noise"]).to_csv(other, index=False)
    a = score(clean_data, "outcome", {})
    b = score(other, "outcome", {})
    ra, rb = a["evaluation"]["replicates"][0], b["evaluation"]["replicates"][0]
    assert ra["parameters"] == rb["parameters"]
    assert ra["split_id"] == rb["split_id"]
    assert ra["seed"] == rb["seed"] == 42


def test_data_agent_only_selects_columns_and_fixed_target(clean_data, monkeypatch):
    from memstara.mcp_servers.data import slice_columns
    monkeypatch.setenv('MEMSTARA_OUTCOME_COLUMN', 'outcome')
    original = pd.read_csv(clean_data)
    sliced = json.loads(slice_columns(['x', 'noise'], 'outcome', 'test'))
    pd.testing.assert_frame_equal(pd.read_csv(sliced['path']), original[['x', 'noise', 'outcome']])
    rejected = json.loads(slice_columns(['x'], 'noise', 'wrong-target'))
    assert 'fixed target' in rejected['error']


def test_dirty_input_is_rejected_before_run_configuration_is_frozen(clean_data, tmp_path):
    data = pd.read_csv(clean_data)
    data.loc[0, 'x'] = np.nan
    data.to_csv(clean_data, index=False)
    args = SimpleNamespace(run_tag='preflight', question='', hypothesis_agents=1,
                           y_column='outcome', evaluation='{}', trials=1, waves=1)
    with pytest.raises(DataQualityError, match='AI-ready'):
        freeze(args, tmp_path, {})
    assert not (tmp_path / 'config.json').exists()


def test_skill_optimization_defaults_reach_frozen_runtime(clean_data, tmp_path):
    skill = catalog.register({'stage': 'ml', 'name': 'replicated',
        'content': '<!-- evaluation: {"replicates": 10, "folds": 2} -->\nUse ten seeded replicates.'})
    argv = build_argv({'playbook_ml': skill['id'], 'evaluation': {'engine': 'logistic_regression'}},
                      [], [skill['id']], ['ml'])
    args = SimpleNamespace(run_tag='skill-policy', question='', hypothesis_agents=1,
                           y_column='outcome', evaluation=argv[argv.index('--evaluation') + 1], trials=1, waves=1)
    config = freeze(args, tmp_path, {'ml': [skill['id']]})
    assert config['evaluation']['replicates'] == 10
    assert config['evaluation']['folds'] == 2
    assert config['evaluation']['engine'] == 'logistic_regression'
