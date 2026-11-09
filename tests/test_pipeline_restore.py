import json

import pytest

from memstara.control.restore import definition
from memstara.control.workspace import PipelineWorkspace


def archived(root, tag="old", key="deleted-id", name="Saved study"):
    folder = root / tag
    folder.mkdir()
    config = {"run_tag": tag, "pipeline_id": key, "pipeline_name": name,
              "combination_plan": {"skills": {"hypothesis": [{"id": "retired-skill"}]},
                                   "repetitions": 15, "execution_order": "pipeline_replicates_first",
                                   "start_index": 0, "max_loops": None}}
    saved = {"run_tag": tag, "pipeline_id": key, "provider": "azure_foundry", "model": "saved-model",
             "evaluation": '{"replicates": 2}', "baseline_columns": '["age"]',
             "ml_overrides": '{}', "controlled_comparison": '{}', "research_input_id": "saved-input"}
    (folder / "config.json").write_text(json.dumps(config))
    (folder / "resume_arguments.json").write_text(json.dumps(saved))
    return folder


def test_restore_keeps_identity_settings_and_live_manager_without_starting(tmp_path):
    folder = archived(tmp_path)
    evidence = {p.name: p.read_bytes() for p in folder.iterdir()}
    workspace = PipelineWorkspace(tmp_path / "pipeline_workspace.json", lambda key: pytest.fail("No manager should start"))
    current = {"id": "active", "number": 3, "name": "Running study", "configuration": {}}
    workspace.items = [current]
    marker = object()
    workspace.managers["active"] = marker
    workspace._save()
    result = workspace.mutate({"action": "restore", "run_tag": "old", "number": 1})
    assert result["id"] == "deleted-id"
    assert result["configuration"]["provider"] == "azure_foundry"
    assert result["configuration"]["evaluation"] == {"replicates": 2}
    assert result["configuration"]["baseline_columns"] == ["age"]
    assert result["configuration"]["combination_repetitions"] == 15
    assert result["configuration"]["combination_execution_order"] == "pipeline_replicates_first"
    assert result["configuration"]["combination_skills"] == {"hypothesis": ["retired-skill"]}
    assert workspace.managers == {"active": marker}
    assert workspace.items[1] == current
    assert json.loads((tmp_path / result["restoration_backup"]).read_text()) == [current]
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == evidence
    workspace.mutate({"action": "restore", "run_tag": "old", "number": 1})
    assert len(workspace.items) == 2
    assert len(list(tmp_path.glob("workspace-before-restore-*.json"))) == 1


def test_restore_rejects_number_collision_and_mismatched_evidence(tmp_path):
    folder = archived(tmp_path)
    workspace = PipelineWorkspace(tmp_path / "pipeline_workspace.json", lambda key: None)
    workspace.items = [{"id": "other", "number": 1}]
    with pytest.raises(ValueError, match="already in use"):
        workspace.mutate({"action": "restore", "run_tag": "old", "number": 1})
    saved = json.loads((folder / "resume_arguments.json").read_text())
    saved["pipeline_id"] = "wrong"
    (folder / "resume_arguments.json").write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="do not belong"):
        definition(tmp_path, "old", 2)
    assert workspace.items == [{"id": "other", "number": 1}]


def test_restore_does_not_accept_arbitrary_paths(tmp_path):
    archived(tmp_path)
    with pytest.raises(ValueError, match="missing or ambiguous"):
        definition(tmp_path, "../old", 1)


def test_failed_restore_save_keeps_memory_and_existing_file(tmp_path, monkeypatch):
    archived(tmp_path)
    workspace = PipelineWorkspace(tmp_path / "pipeline_workspace.json", lambda key: None)
    workspace._save()
    before = workspace.path.read_bytes()
    def fail():
        raise OSError("Disk unavailable")
    monkeypatch.setattr(workspace, "_save", fail)
    with pytest.raises(OSError, match="Disk unavailable"):
        workspace.mutate({"action": "restore", "run_tag": "old", "number": 1})
    assert workspace.items == []
    assert workspace.path.read_bytes() == before
