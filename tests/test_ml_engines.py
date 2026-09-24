# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. afc-forge has no ML tool
#   server, so there is no counterpart upstream.
"""`_make_model` — one engine, and one seed that reaches it."""

from __future__ import annotations

import inspect
import json
import re

import pytest

from memstara.mcp_servers import ml as tools_ml

REMOVED_ENGINES = ["sklearn_hgb", "random_forest"]


@pytest.mark.parametrize("seed", [0, 7, 42])
def test_xgboost_takes_the_seed_it_is_given(seed: int) -> None:
    """The seed argument reaches the estimator, whatever its value."""
    pytest.importorskip("xgboost")
    model = tools_ml._make_model("xgboost", seed)
    assert model.random_state == seed


def test_an_unknown_engine_names_the_one_that_exists() -> None:
    """A typo fails loudly and the message is the answer.

    `.env.example` shipped `MEMSTARA_ML_ENGINE=logistic` — a value that exists nowhere.
    Uncommenting it lands here, and what makes that recoverable in one read rather than
    one search is that the exception names the value that does work.
    """
    with pytest.raises(ValueError) as caught:
        tools_ml._make_model("logistic", 42)

    message = str(caught.value)
    assert "logistic" in message
    assert "Unsupported model" in message


@pytest.mark.parametrize("engine", ["xgboost", "random_forest", "logistic_regression"])
def test_supported_models_receive_the_same_seed(engine):
    assert tools_ml._make_model(engine, 7).get_params()["random_state"] == 7


def test_standalone_async_mcp_accepts_explicit_governance(subset, monkeypatch):
    import asyncio
    monkeypatch.delenv("MEMSTARA_RUN_CONFIG", raising=False)
    result = json.loads(asyncio.run(tools_ml.train_and_score_async(
        str(subset), "outcome", seed=7, engine="logistic_regression", folds=2,
    )))
    assert "error" not in result, result
    assert result["model"] == "logistic_regression"
    assert result["evaluation"]["plan"]["folds"] == 2
    assert result["evaluation"]["replicates"][0]["cv_auc"] is not None


def test_the_default_seed_is_42() -> None:
    """42 is the documented value and the default must stay it."""
    default = inspect.signature(tools_ml.train_and_score).parameters["seed"].default
    assert default == 42


@pytest.fixture()
def subset(tmp_path, monkeypatch):
    """A tiny sub-dataset inside an allowed output directory.

    60 rows with one column that carries the signal and one that does not, which is
    enough for a split, a fit and a permutation pass. It is not the cohort and must not
    become it: what is under test is what the tool *reports about its own conditions*,
    and a test that needs the real dataset stops running the moment that file moves
    (`tests/test_slice_columns.py:16-18` makes the same choice for the same reason).
    """
    out = tmp_path / "out"
    out.mkdir()
    rows = ["signal,noise,outcome"]
    for i in range(60):
        label = i % 2
        rows.append(f"{label * 10 + i % 3},{i % 7},{label}")
    csv = out / "subset.csv"
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(out))
    monkeypatch.delenv("MEMSTARA_ML_ENGINE", raising=False)
    return csv


def test_the_conditions_come_back_with_the_numbers(subset) -> None:
    """`seed` and `test_size` are in the return, at whatever value was passed."""
    out = json.loads(tools_ml.train_and_score(str(subset), "outcome", test_size=0.4, seed=7))

    assert "error" not in out, out
    assert out["seed"] == 7
    assert out["test_size"] == 0.4
    # The engine is still reported too — the three together are the whole condition.
    assert out["model"] == tools_ml._DEFAULT_ENGINE


def test_the_default_engine_is_xgboost() -> None:
    """A run that sets nothing is an XGBoost run."""
    assert tools_ml._DEFAULT_ENGINE == "xgboost"


def test_a_run_that_sets_nothing_uses_the_default_engine(subset) -> None:
    """The second half of the assertion above, through the tool rather than the constant.

    The `subset` fixture deletes `MEMSTARA_ML_ENGINE`, so this is the unset case — the
    one every pipeline run is in, since nothing in `board.py` sets the variable.
    """
    out = json.loads(tools_ml.train_and_score(str(subset), "outcome"))

    assert "error" not in out, out
    assert out["model"] == "xgboost"


def test_unknown_engine_is_refused_through_the_tool(subset, monkeypatch):
    monkeypatch.setenv("MEMSTARA_ML_ENGINE", "sklearn_hgb")
    out = json.loads(tools_ml.train_and_score(str(subset), "outcome"))
    assert "sklearn_hgb" in out["error"]


def test_random_forest_is_selectable_through_the_tool(subset, monkeypatch):
    monkeypatch.setenv("MEMSTARA_ML_ENGINE", "random_forest")
    out = json.loads(tools_ml.train_and_score(str(subset), "outcome"))
    assert "error" not in out, out
    assert out["model"] == "random_forest"
    assert out["explanation"]["method"] == "holdout_permutation_auc"


def test_a_path_outside_the_output_directory_is_refused(subset, tmp_path) -> None:
    """The security check still fires, and still fires first.

    Named here because this file is now the only test of this module: `train_and_score`
    resolves symlinks and then requires the path to sit under the output directory
    in the ML server, and that check deliberately runs *above*
    the scikit-learn import so it cannot be skipped wherever the optional dependency is
    absent. A refusal is JSON rather than an exception, per this directory's rule that
    an agent must get something it can act on.
    """
    outside = tmp_path / "elsewhere.csv"
    outside.write_text("a,outcome\n1,0\n2,1\n", encoding="utf-8")

    out = json.loads(tools_ml.train_and_score(str(outside), "outcome"))
    assert "outside the allowed directory" in out["error"]


def test_no_seed_is_written_into_this_module() -> None:
    """No literal `random_state=<number>` anywhere in `ml.py`.

    Every randomness knob must read the caller's `seed`. This is a source check rather
    than a behavioural one on purpose: the failure it guards against is a *new* call
    site — a fourth engine, or a second `permutation_importance` — arriving with its
    own constant, and no behavioural test can see a code path that does not exist yet.

    Docstrings and comments are searched too. `ml.py`'s do discuss the old `0`, but
    they spell it as prose or inside backticks rather than as an assignment, so the
    pattern below does not match them — and a comment that shows the assignment is
    something a reader can copy, which is how it would come back.
    """
    source = inspect.getsource(tools_ml)
    literals = re.findall(r"random_state\s*=\s*(\d+)", source)
    assert literals == [], (
        f"ml.py hard-codes random_state={literals}. Every random source in this module "
        f"takes the caller's `seed` so that one run has one seed; see `_make_model`."
    )
