"""Read frozen agent instructions without substituting today's skill library."""
import hashlib
import json
from pathlib import Path


def recorded_instructions(run_dir, run_tag, stage, skill, expected_hash=""):
    if stage not in {"hypothesis", "data", "ml", "interpreter", "report"} or not skill:
        raise ValueError("Choose an agent role and skill")
    root = Path(run_dir).resolve()
    path = root / "config.json"
    if path.is_symlink():
        raise ValueError("Recorded configuration must belong to this execution")
    state = json.loads(path.read_text())
    if state.get("run_tag") != run_tag:
        raise ValueError("Recorded configuration belongs to a different execution")
    entries = (state.get("combination_plan") or {}).get("skills", {}).get(stage, [])
    entry = next((item for item in entries if item.get("id") == skill), {})
    if expected_hash and entry.get("hash") != expected_hash:
        raise ValueError("Requested skill version does not match this execution")
    prompt = state.get("prompts", {}).get(f"board/{stage}:{skill}", {})
    content = prompt.get("system_prompt")
    if not isinstance(content, str) or not content.strip():
        raise FileNotFoundError("This execution has no saved instructions for this skill")
    return {
        "run_tag": run_tag, "stage": stage, "id": skill,
        "title": entry.get("title", skill), "hash": entry.get("hash"),
        "content": content, "goal": prompt.get("goal", ""),
        "prompt_hash": hashlib.sha256(content.encode()).hexdigest(),
        "source": "Recorded execution configuration",
    }
