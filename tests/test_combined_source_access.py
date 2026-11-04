"""Allow both saved HIV corpora without broadening access to other sources."""
import json

import pytest

from memstara.research_visibility import require_source_access, selection_policy


def test_combined_and_original_allowed_other_sources_blocked(tmp_path):
    dataset = str(tmp_path / "hiv.csv")
    old = str(tmp_path / "hiv")
    combined = str(tmp_path / "hiv-combined")
    (tmp_path / "app-selection.json").write_text(json.dumps({
        "allowed_sources": {"dataset_path": dataset, "knowledge_path": [old, combined]}
    }))
    for knowledge in (old, combined):
        require_source_access({"dataset_path": dataset, "knowledge_path": knowledge}, tmp_path)
    with pytest.raises(ValueError, match="not permitted"):
        require_source_access({"dataset_path": dataset, "knowledge_path": str(tmp_path / "heart-failure")}, tmp_path)
    require_source_access({"dataset_path": dataset, "knowledge_path": "", "knowledge_mode": "llm_only"}, tmp_path)
    with pytest.raises(ValueError, match="must not select"):
        require_source_access({"dataset_path": dataset, "knowledge_path": combined, "knowledge_mode": "llm_only"}, tmp_path)
    with pytest.raises(ValueError, match="not permitted"):
        require_source_access({"dataset_path": str(tmp_path / "other.csv"), "knowledge_path": combined}, tmp_path)


@pytest.mark.parametrize("paths", [[], ["relative"], [None], {"path": "/hiv"}])
def test_invalid_knowledge_allowlist_rejected(tmp_path, paths):
    (tmp_path / "app-selection.json").write_text(json.dumps({
        "allowed_sources": {"dataset_path": "/hiv.csv", "knowledge_path": paths}
    }))
    with pytest.raises(ValueError):
        selection_policy(tmp_path)
