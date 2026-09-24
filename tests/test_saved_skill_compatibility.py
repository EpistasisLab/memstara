"""Saved configurations keep the original role and prompt after a skill rename."""

import json

from memstara.control.catalog import resolve
from memstara.control.workspace import PipelineWorkspace
from memstara.pipeline.prompts import load_prompt


def test_saved_ml_alias_keeps_role_and_workspace_loads(tmp_path, monkeypatch):
    aliases = tmp_path / "aliases.json"
    aliases.write_text(json.dumps({"legacy-model-summary": "ml_results_presenter"}))
    monkeypatch.setenv("MEMSTARA_SKILL_ALIASES_PATH", str(aliases))
    monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("MEMSTARA_RUN_CONFIG", raising=False)
    assert resolve("legacy-model-summary")["stage"] == "ml"
    assert load_prompt("board/ml", "legacy-model-summary") == load_prompt("board/ml", "ml_results_presenter")
    config = {
        "combination_skills": {
            "hypothesis": ["taxonomic"],
            "data": ["data_exact_features"],
            "ml": ["legacy-model-summary"],
            "interpreter": ["interpreter_factual_observations"],
            "report": ["report_clinical_explanations"],
        }
    }
    path = tmp_path / "workspace.json"
    path.write_text(json.dumps([{"id": "saved", "number": 1, "name": "Saved", "configuration": config}]))

    class Manager:
        def running(self):
            return None

        def finished(self):
            return []

    workspace = PipelineWorkspace(path, lambda _: Manager())
    row = workspace.list()[0]
    assert row["configuration"]["playbook_ml"] == "ml_results_presenter"
    assert row["configuration"]["combination_skills"]["ml"] == ["legacy-model-summary"]


def test_unavailable_saved_skill_does_not_hide_the_workspace(tmp_path):
    class Manager:
        def running(self):
            return None

        def finished(self):
            return []

    path = tmp_path / "workspace.json"
    saved = {"combination_skills": {"hypothesis": ["missing-skill"]}}
    path.write_text(json.dumps([{"id": "saved", "number": 1, "name": "Saved", "configuration": saved}]))
    workspace = PipelineWorkspace(path, lambda _: Manager())
    row = workspace.list()[0]
    assert row["configuration"] == saved
    assert row["configuration_error"]
    import pytest

    with pytest.raises(ValueError):
        workspace.start("saved", lambda *_: pytest.fail("Invalid configuration launched"))
    workspace.mutate({"action": "update", "id": "saved", "configuration": {}})
    assert workspace.list()[0]["configuration_error"] is None
