# SOURCE: SANDBOX-ORIGINAL — cached matrix validation around the unchanged port.
"""Corrupt numeric caches must fail before encoding a query or ranking columns."""

import numpy as np
import pytest

from memstara.matcher.catalog import CatalogEntry, save_catalog
from memstara.matcher import embedder
from memstara.matcher.service import VerifiedMatcher


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(embedder, 'current_device', lambda: 'cpu')
    path = tmp_path / 'catalog.json'
    entry = CatalogEntry('age', 'demographic', 'age', 'wide_passthrough', 'age')
    save_catalog([entry], path)
    embedder.save_embeddings(np.array([[1., 0.]]), path, match_texts=[entry.match_text])
    return path


@pytest.mark.parametrize('matrix', [
    np.array([[np.nan, 0.]]), np.array([[np.inf, 0.]]),
    np.array([1.]), np.empty((1, 0)), np.ones((1, 2, 2)),
], ids=['nan', 'infinity', 'one-dimensional', 'empty-vectors', 'three-dimensional'])
def test_invalid_cached_matrix_rejected_before_query(catalog, matrix):
    np.save(embedder.embeddings_path(catalog), matrix)
    with pytest.raises(ValueError, match='Invalid matcher embedding matrix'):
        VerifiedMatcher.from_catalog(catalog, encoder=lambda texts: pytest.fail('Query must not encode'))


def test_valid_cached_matrix_retains_matching(catalog):
    matcher = VerifiedMatcher.from_catalog(catalog, encoder=lambda texts: np.array([[1., 0.]]))
    result = matcher.match('age')
    assert [m.feature_name for m in result.matches] == ['age']
    assert result.matches[0].similarity == pytest.approx(1.)
