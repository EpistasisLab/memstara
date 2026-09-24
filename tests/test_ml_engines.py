# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. afc-forge has no ML tool
#   server, so there is no counterpart upstream.
"""`_make_model` — one engine, and one seed that reaches it.

**Until 2026-09-08 this file did not exist and neither did any test of the ml tool
server.** That is what let the following stand unnoticed: `train_and_score` exposed
`seed` as a tool parameter and used it to split the data, while all three engines
carried a hard-coded `random_state=0`. Passing a different seed moved the split and
left the model exactly where it was, so the seed the caller chose was never the seed
the run used. NFR-2b asks that the seed *can be fixed*
(`spec/Memstara_SRS_KR.md:949`); half of it could not be reached at all.

**Three engines became one, later the same day.** XGBoost was made the default, and then
`sklearn_hgb` and `random_forest` were removed outright. So this file now guards two
things that look similar and are not: that the one engine takes its seed, and that the
two that no longer exist are *refused by name* rather than quietly ignored.

These tests are offline and take milliseconds. `_make_model` is a pure function — it
builds an estimator and returns it, fitting nothing — so no CSV, no Postgres, no model
call and no pipeline run is involved. That is why the gap was cheap to leave open and
is cheap to close.

`test_no_seed_is_written_into_this_module` is the one that keeps it closed. The other
tests check the parameter arrives; that one checks nobody adds a fourth engine, or a
second `permutation_importance` call, with a literal seed beside it — which is exactly
how the original divergence appeared, one plausible line at a time.
"""

from __future__ import annotations

import inspect
import json
import re

import pytest

from memstara.mcp_servers import ml as tools_ml

#: The two engines that existed until 2026-09-08 and do not any more. Named here rather
#: than inline because three separate tests are about them, and because the list is the
#: thing that has to change if `A-26` ever brings a second engine back.
REMOVED_ENGINES = ["sklearn_hgb", "random_forest"]


@pytest.mark.parametrize("seed", [0, 7, 42])
def test_xgboost_takes_the_seed_it_is_given(seed: int) -> None:
    """The seed argument reaches the estimator, whatever its value.

    Three seeds rather than one: with a single value a test passes just as well against a
    hard-coded constant that happens to equal it, which is the state this module was in
    when the constant was 0. There used to be two more engines parametrised alongside
    this one; they were removed on 2026-09-08 and so was the parametrisation over them.

    This test spent its first day skipped. xgboost was undeclared then, so it ran only
    where somebody had installed it by hand, and it was worth writing anyway because the
    xgboost branch is the one that cannot be checked by reading: `XGBClassifier` accepts
    unknown keyword arguments without complaint, so a misspelled `random_state` would
    look correct in the source and do nothing. It is a declared dependency as of
    2026-09-08 (`pyproject.toml:64`), so the skip below no longer fires.

    Note what this does *not* claim. `random_state` only changes an XGBoost fit when
    `subsample` or `colsample_*` is below 1.0, and `_make_model` sets neither, so two
    seeds are expected to produce the same numbers. The test is that the value is
    carried, not that it changes anything — which is exactly what makes it worth keeping
    now that this is the only engine: the day somebody adds subsampling, the seed has to
    already be arriving.
    """
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
    """42 is the documented value and the default must stay it.


    for reproducibility and sets it to 42. Every result on the board was produced by a
    call that did not pass one, so moving the default silently re-bases the whole
    record against numbers nobody can reproduce.
    """
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
    """`seed` and `test_size` are in the return, at whatever value was passed.

    They are tool parameters, so an agent can pass something other than the default.
    Before 2026-09-08 doing so left no trace: the return carried the AUC and not the
    conditions that produced it, which made the docstring's promise — that a result can
    be re-scored by hand and checked against the board — true only of calls that passed
    neither.

    A non-default seed rather than 42, for the reason the parametrised tests above take
    three values: against a hard-coded default, echoing the default proves nothing.
    """
    out = json.loads(tools_ml.train_and_score(str(subset), "outcome", test_size=0.4, seed=7))

    assert "error" not in out, out
    assert out["seed"] == 7
    assert out["test_size"] == 0.4
    # The engine is still reported too — the three together are the whole condition.
    assert out["model"] == tools_ml._DEFAULT_ENGINE


def test_the_default_engine_is_xgboost() -> None:
    """A run that sets nothing is an XGBoost run.

    This is a project requirement as of 2026-09-08, not a preference: XGBoost is the
    engine the 2026-08-06 meeting named and the one the 2026-08-10 implementation guide
    wrote as the default. This file shipped `sklearn_hgb` for two months instead, to
    keep the install to one package, and nothing failed — which is exactly why the
    divergence lasted. A test is what stops it recurring the next time somebody weighs
    a dependency against a default.

    Asserted twice on purpose. `_DEFAULT_ENGINE` is the constant, and the second
    assertion is that `train_and_score` actually *reaches* it with the environment
    unset — a constant nothing reads would satisfy the first line alone.
    """
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
    (`src/memstara/mcp_servers/ml.py (at commit 0990ec5, lines 242-249)`), and that check deliberately runs *above*
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
