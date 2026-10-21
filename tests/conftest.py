# SOURCE: MIXED. `bag_of_words_encoder` and `fake_encoder` are PORTED VERBATIM
#   from afc-forge/tests/conftest.py:220-272 — the ported tests are
#   only evidence if they run against upstream's encoder stub, not a rewritten
#   one. Anything else in this file is sandbox-original.
"""Shared test fixtures.

`bag_of_words_encoder` and `fake_encoder` are ported verbatim from
`afc-forge/tests/conftest.py:220-272`. The rest of that file builds a
mock cohort out of the descriptor system, which this sandbox does not carry.
"""

from __future__ import annotations

import os
import re

from collections.abc import Sequence

import numpy as np
import pytest

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


@pytest.fixture(autouse=True)
def isolated_operational_environment(request):
    """A direct load_env call must not leak project settings into the next test."""
    if request.config.getoption('--run-live'):
        yield
        return
    from memstara.operational import managed
    from memstara import env
    saved = {key: value for key, value in os.environ.items() if managed(key)}
    source, provenance = env._loaded_source, env._provenance
    for key in list(os.environ):
        if managed(key) and not key.startswith('MEMSTARA_TEST_'):
            os.environ.pop(key, None)
    os.environ['MEMSTARA_CONFIG_MODE'] = 'environment'
    env._loaded_source, env._provenance = None, {}
    try:
        yield
    finally:
        for key in list(os.environ):
            if managed(key):
                os.environ.pop(key, None)
        os.environ.update(saved)
        env._loaded_source, env._provenance = source, provenance


def pytest_addoption(parser):
    parser.addoption("--run-docker", action="store_true", help="Run isolated container restart fault tests")
    parser.addoption("--run-integration", action="store_true", help="Run tests against an explicit test database")
    parser.addoption("--run-live", action="store_true", help="Run paid Haiku 5.5 pipeline acceptance tests")
    parser.addoption("--live-pause-resume", action="store_true",
                     help="Require cooperative pause/resume evidence during fresh paid execution")
    parser.addoption("--live-batch", default="",
                     help="Audit completed cases and run remaining cases in this live batch")
    parser.addoption("--live-retry-failed", action="store_true",
                     help="Keep failed evidence and run a fresh attempt after investigating the failure")
    parser.addoption("--live-loops", type=int, choices=(1, 2), default=1,
                     help="Paid Haiku Loops per selected case (default one; two for audit acceptance)")
    parser.addoption("--live-audit-io", action="store_true",
                     help="Require verified request payload and stage export evidence in live cases")
    parser.addoption("--live-private-research", default="",
                     help="Explicit private HIV research JSON/registration for opt-in acceptance")
    parser.addoption("--live-installed-python", default="",
                     help="Run the paid worker with an isolated, non-editable installed-wheel Python")


def pytest_collection_modifyitems(config, items):
    selected, deselected = [], []
    for item in items:
        excluded = (
            item.get_closest_marker("integration") and not config.getoption("--run-integration")
        ) or (item.get_closest_marker("live") and not config.getoption("--run-live")) or (
            item.get_closest_marker("docker") and not config.getoption("--run-docker"))
        (deselected if excluded else selected).append(item)
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)


def pytest_configure(config):
    """Offline tests cannot accidentally borrow deployment credentials/defaults."""
    config.addinivalue_line('markers', 'docker: isolated Docker restart tests; require --run-docker')
    if config.getoption('--run-live'):
        return
    from memstara.operational import PREFIXES
    for key in list(os.environ):
        if (key.startswith(PREFIXES) and not key.startswith('MEMSTARA_TEST_')) or key == 'CORE_VIEWER_DSN':
            os.environ.pop(key, None)
    os.environ['MEMSTARA_CONFIG_MODE'] = 'environment'
