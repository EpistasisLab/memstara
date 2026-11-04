"""Temporary execution ban preserves source files and historical display."""
import json

import pytest

from memstara.control import catalog
from memstara.corpus_skills import PROFILES
from memstara.pipeline import prompts


def test_frailty_hidden_and_rejected_including_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMSTARA_USER_SKILLS_DIR", str(tmp_path / "skills"))
    alias = tmp_path / "aliases.json"
    alias.write_text(json.dumps({"old-frailty": "hiv-clinical-frailty"}))
    monkeypatch.setenv("MEMSTARA_SKILL_ALIASES_PATH", str(alias))
    source = prompts.PLAYBOOKS_DIR / "hiv-clinical-frailty.md"
    original = source.read_bytes()
    assert "hiv-clinical-frailty" not in prompts.playbook_names()
    assert "hiv-clinical-frailty" not in {item["id"] for item in catalog.catalog()}
    assert "hiv-clinical-frailty" not in PROFILES["hiv"]["hypothesis"]
    assert catalog.resolve("hiv-clinical-frailty")["content"]
    for name in ("hiv-clinical-frailty", "old-frailty"):
        with pytest.raises(ValueError, match="disabled for execution"):
            catalog.ensure_hypothesis_enabled([name])
    assert source.read_bytes() == original
