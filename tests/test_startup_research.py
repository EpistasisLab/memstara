"""Automatic research registration preserves sources and existing registrations."""
import json
from pathlib import Path

import pytest

from memstara import research_inputs, startup_research
from memstara.corpus_skills import corpus_profile

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_startup_is_repeatable_and_uses_heart_failure_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMSTARA_RESEARCH_INPUTS_DIR", str(tmp_path / "registry"))
    kwargs = dict(root=ROOT, inputs=tmp_path / "inputs", destination=tmp_path / "prepared")
    first = startup_research.bootstrap(**kwargs)
    second = startup_research.bootstrap(**kwargs)
    assert first == second
    records = research_inputs.list_inputs()
    assert len(records) == 1
    assert records[0]["dataset"]["rows"] == 1671
    assert records[0]["configuration"]["target"]["column"] == "chronic_heart_failure"
    assert "heart" in str(corpus_profile(records[0])).lower()
    assert not first["execution_started"]
    data = Path(records[0]["configuration"]["dataset_path"])
    data.write_text(data.read_text() + "\n")
    with pytest.raises(ValueError, match="data changed"):
        startup_research.bootstrap(**kwargs)


def test_relative_paths_deduplication_and_new_version(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMSTARA_RESEARCH_INPUTS_DIR", str(tmp_path / "registry"))
    study = tmp_path / "inputs" / "my-study"
    study.mkdir(parents=True)
    example = ROOT / "examples/research-inputs"
    (study / "dataset.csv").write_bytes((example / "dataset.csv").read_bytes())
    value = json.loads((example / "research.json").read_text())
    value.update(dataset_path="dataset.csv", knowledge_path=str(example / "okf"))
    manifest = study / "research.json"
    manifest.write_text(json.dumps(value))
    first = startup_research.register_file(manifest)
    assert startup_research.register_file(manifest) == first
    value["target"]["description"] += " Updated study definition."
    manifest.write_text(json.dumps(value))
    assert startup_research.register_file(manifest) != first
    assert len(research_inputs.list_inputs()) == 2


@pytest.mark.parametrize("content", ['{"name": "Incomplete"}', '[]', '{broken'])
def test_invalid_user_study_does_not_hide_bundled_study(tmp_path, monkeypatch, content):
    monkeypatch.setenv("MEMSTARA_RESEARCH_INPUTS_DIR", str(tmp_path / "registry"))
    study = tmp_path / "inputs" / "broken"
    study.mkdir(parents=True)
    (study / "research.json").write_text(content)
    result = startup_research.bootstrap(ROOT, tmp_path / "inputs", tmp_path / "prepared")
    assert result["bundled"]
    assert result["user_inputs"][0]["status"] == "invalid"
    assert len(research_inputs.list_inputs()) == 1
