# SOURCE: MIXED. `bag_of_words_encoder` and `fake_encoder` are PORTED VERBATIM
#   from shared/afc-forge/tests/conftest.py:220-272 — the ported tests are
#   only evidence if they run against upstream's encoder stub, not a rewritten
#   one. Anything else in this file is sandbox-original.
"""Shared test fixtures.

`bag_of_words_encoder` and `fake_encoder` are ported verbatim from
`shared/afc-forge/tests/conftest.py:220-272`. The rest of that file builds a
mock cohort out of the descriptor system, which this sandbox does not carry.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# This import is load-bearing and its position is the whole point.
#
# xgboost and torch each ship their own copy of the OpenMP runtime, and on macOS
# whichever one loads first is the one both then use. torch's copy cannot run an
# xgboost fit: the process aborts inside `XGBClassifier.fit` with
#
#     OMP: Error #179: Function pthread_mutex_init failed
#     OMP: System error #22: Invalid argument
#
# which pytest reports as `Fatal Python error: Segmentation fault` and no test
# name, because the process is gone before the report is written. xgboost's copy
# runs both, so the fix is only to get there first.
#
# It could not be fixed inside `tests/test_ml_engines.py`. torch arrives during
# `tests/test_matcher.py`, which exercises the offline-flag path that imports it
# for its side effect (`src/memstara/matcher/embedder.py:154`) — and `matcher`
# sorts before `ml_engines`. A conftest is imported before any test module, which
# is what makes this the only position that works.
#
# **This is a test-suite problem and not a pipeline one.** Tool servers are child

# pandas, scikit-learn and xgboost and nothing that reaches torch — verified by
# importing it and finding `torch` absent from `sys.modules`. Only the test suite
# puts the two in one process.
# ---------------------------------------------------------------------------
import xgboost  # noqa: F401  — imported first for its OpenMP runtime; see above

# ---------------------------------------------------------------------------
# The deterministic encoder.
# ---------------------------------------------------------------------------
_TOKEN = re.compile(r"[a-z0-9]+")


def bag_of_words_encoder(dim: int = 1024):
    """A shared-token encoder: same interface as the real one, no download.

    The matcher takes its encoder as an argument precisely so this can exist
    (§6.7.1). Cosine here is the overlap of token *sets*, which is enough to
    reproduce every ranking property under test — a false friend outranking a
    real sibling, a family whose levels all clear the floor, a synonym scoring
    zero — while running in microseconds on a machine that has never loaded 1.3 GB
    of weights.

    Its geometry is NOT the real encoder's, so a test that uses it must state its
    own floor rather than inherit `matcher.sim_threshold`: 0.88 was calibrated on
    real embeddings and means nothing here.
    """
    index: dict[str, int] = {}

    def encode(texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in set(_TOKEN.findall(str(text).lower())):
                if token not in index:
                    if len(index) >= dim:
                        raise ValueError(
                            f"the fake encoder ran out of dimensions at {dim}; "
                            "the fixture vocabulary is larger than the test needs"
                        )
                    index[token] = len(index)
                out[row, index[token]] = 1.0
            norm = float(np.linalg.norm(out[row]))
            if norm:
                out[row] /= norm
        return out

    return encode


@pytest.fixture
def fake_encoder():
    """A fresh encoder per test — the token index is state, and sharing it hides
    a fixture that only ranks correctly because an earlier test seeded a token."""
    return bag_of_words_encoder()
