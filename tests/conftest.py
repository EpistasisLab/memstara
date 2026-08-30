# SOURCE: MIXED. `bag_of_words_encoder` and `fake_encoder` are PORTED VERBATIM
#   from shared/afc-forge/tests/conftest.py:220-272 — the ported tests are
#   only evidence if they run against upstream's encoder stub, not a rewritten
#   one. Anything else in this file is sandbox-original.
"""Shared test fixtures.

`bag_of_words_encoder` and `fake_encoder` are ported verbatim from afc-forge
`tests/conftest.py:220-272`. The rest of that file builds a mock cohort out of the
descriptor system, which this sandbox does not carry.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np
import pytest

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
