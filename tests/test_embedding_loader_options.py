"""Memstara loader options preserve revision and cache-recovery behavior offline."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from memstara.matcher import embedder
from memstara.matcher.config import EmbeddingConfig


@pytest.mark.parametrize("revision", [None, "pinned-revision"])
@pytest.mark.parametrize("cached_failure", [False, True])
def test_loader_preserves_exact_options_on_cache_retry(monkeypatch, revision, cached_failure):
    loaded = object()
    constructor = Mock(side_effect=[RuntimeError("cache incomplete"), loaded] if cached_failure else [loaded])
    restore = Mock()
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor))
    monkeypatch.setattr(embedder, "current_device", lambda: "cpu")
    monkeypatch.setattr(embedder, "_prefer_cached_model", lambda model: cached_failure)
    monkeypatch.setattr(embedder, "_restore_online", restore)
    config = EmbeddingConfig(model="synthetic-model", revision=revision)

    assert embedder.load_sentence_transformer(config) is loaded
    expected = {"device": "cpu"}
    if revision is not None:
        expected["revision"] = revision
    assert constructor.call_count == (2 if cached_failure else 1)
    for call in constructor.call_args_list:
        assert call.args == ("synthetic-model",)
        assert call.kwargs == expected
    assert restore.call_count == int(cached_failure)


def test_online_load_failure_is_not_retried(monkeypatch):
    constructor = Mock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor))
    monkeypatch.setattr(embedder, "current_device", lambda: "cpu")
    monkeypatch.setattr(embedder, "_prefer_cached_model", lambda model: False)
    with pytest.raises(RuntimeError, match="unavailable"):
        embedder.load_sentence_transformer(EmbeddingConfig())
    assert constructor.call_count == 1
