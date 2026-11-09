"""Installation-specific research visibility; stored studies remain unchanged."""

import json
import os
import re
from pathlib import Path

from memstara.paths import REPO_ROOT


def selection_policy(inputs=None):
    root = Path(inputs or os.environ.get("MEMSTARA_INPUTS_DIR") or REPO_ROOT / "user-inputs")
    path = root / "app-selection.json"
    if not path.exists():
        return {"register_bundled_demo": True, "hidden_research_ids": []}
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) - {"register_bundled_demo", "hidden_research_ids", "allowed_sources"}:
        raise ValueError("Invalid app research selection configuration")
    enabled = value.get("register_bundled_demo", True)
    hidden = value.get("hidden_research_ids", [])
    if (
        not isinstance(enabled, bool)
        or not isinstance(hidden, list)
        or any(not isinstance(item, str) or not re.fullmatch(r"[a-f0-9]{32}", item) for item in hidden)
    ):
        raise ValueError("Invalid app research selection configuration")
    sources = value.get("allowed_sources")
    if sources is not None and (
        not isinstance(sources, dict)
        or set(sources) != {"dataset_path", "knowledge_path"}
        or not isinstance(sources["dataset_path"], str)
        or not Path(sources["dataset_path"]).is_absolute()
    ):
        raise ValueError("Invalid allowed research sources")
    if sources is not None:
        knowledge = sources["knowledge_path"]
        choices = knowledge if isinstance(knowledge, list) else [knowledge]
        if not choices or any(not isinstance(path, str) or not Path(path).is_absolute() for path in choices):
            raise ValueError("Invalid allowed research sources")
    return {"register_bundled_demo": enabled, "hidden_research_ids": hidden, "allowed_sources": sources}


def visible_records(records, inputs=None):
    policy = selection_policy(inputs)
    hidden = set(policy["hidden_research_ids"])
    visible = []
    for record in records:
        if record.get("id") in hidden:
            continue
        try:
            require_source_access(record.get("configuration", {}), inputs)
        except ValueError:
            continue
        visible.append(record)
    return visible


def require_source_access(configuration, inputs=None):
    sources = selection_policy(inputs).get("allowed_sources")
    if sources is None:
        return
    for key, expected in sources.items():
        if key == "knowledge_path" and configuration.get("knowledge_mode") == "llm_only":
            if configuration.get(key):
                raise ValueError("Knowledge-free research must not select a knowledge source")
            continue
        actual = configuration.get(key)
        choices = expected if isinstance(expected, list) else [expected]
        if not actual or Path(actual).resolve() not in {Path(path).resolve() for path in choices}:
            raise ValueError("Research source is not permitted in this installation")
