# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. afc-forge has no ML tool
#   server, so there is no counterpart upstream.
"""`_make_model` — one seed reaches every engine.

**Until 2026-09-08 this file did not exist and neither did any test of the ml tool
server.** That is what let the following stand unnoticed: `train_and_score` exposed
`seed` as a tool parameter and used it to split the data, while all three engines
carried a hard-coded `random_state=0`. Passing a different seed moved the split and
left the model exactly where it was, so the seed the caller chose was never the seed
the run used. NFR-2b asks that the seed *can be fixed*
(`spec/Memstara_SRS_KR.md:949`); half of it could not be reached at all.

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
import re

import pytest

from memstara.mcp_servers import ml as tools_ml

#: The two engines scikit-learn provides. xgboost is optional and is tested separately,
#: because a skip that silently swallows the other two would be worse than no test.
SKLEARN_ENGINES = ["sklearn_hgb", "random_forest"]


@pytest.mark.parametrize("engine", SKLEARN_ENGINES)
@pytest.mark.parametrize("seed", [0, 7, 42])
def test_each_engine_takes_the_seed_it_is_given(engine: str, seed: int) -> None:
    """The seed argument reaches the estimator, whatever its value.

    Three seeds rather than one: with a single value a test passes just as well
    against a hard-coded constant that happens to equal it, which is the state this
    module was in when the constant was 0.
    """
    model = tools_ml._make_model(engine, seed)
    assert model.random_state == seed


@pytest.mark.parametrize("seed", [0, 7, 42])
def test_xgboost_takes_the_seed_it_is_given(seed: int) -> None:
    """Same check for the optional engine.

    xgboost is deliberately undeclared (`pyproject.toml:41`), so this skips here and on
    CI and only runs where somebody installed it. Worth having anyway: the xgboost
    branch is the one that cannot be checked by reading, because `XGBClassifier`
    accepts unknown keyword arguments without complaint.

    Note what this does *not* claim. `random_state` only changes an XGBoost fit when
    `subsample` or `colsample_*` is below 1.0, and `_make_model` sets neither, so two
    seeds are expected to produce the same numbers. The test is that the value is
    carried, not that it changes anything.
    """
    pytest.importorskip("xgboost")
    model = tools_ml._make_model("xgboost", seed)
    assert model.random_state == seed


def test_an_unknown_engine_names_the_ones_that_exist() -> None:
    """A typo fails loudly and the message is the answer.

    `.env.example` shipped `MEMSTARA_ML_ENGINE=logistic` — a value that exists nowhere.
    Uncommenting it lands here, and what makes that recoverable in one read rather than
    one search is that the exception lists the three real names.
    """
    with pytest.raises(RuntimeError) as caught:
        tools_ml._make_model("logistic", 42)

    message = str(caught.value)
    assert "logistic" in message
    for engine in ("sklearn_hgb", "random_forest", "xgboost"):
        assert engine in message


def test_the_default_seed_is_42() -> None:
    """42 is the documented value and the default must stay it.


    for reproducibility and sets it to 42. Every result on the board was produced by a
    call that did not pass one, so moving the default silently re-bases the whole
    record against numbers nobody can reproduce.
    """
    default = inspect.signature(tools_ml.train_and_score).parameters["seed"].default
    assert default == 42


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
