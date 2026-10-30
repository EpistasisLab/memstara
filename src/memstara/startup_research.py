"""Register bundled and mounted research inputs without executing experiments."""

import fcntl
import json
import os
import tempfile
from pathlib import Path

from memstara import research_inputs
from memstara.heart_failure_demo import prepare
from memstara.paths import REPO_ROOT, output_dir


def register_file(path):
    """Resolve paths relative to the manifest and reuse unchanged registrations."""
    path = Path(path).resolve()
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Research manifest must be a JSON object")
    for key in ("dataset_path", "knowledge_path"):
        if value.get(key):
            candidate = Path(value[key])
            value[key] = str((path.parent / candidate).resolve())
    checked = research_inputs.inspect(value)
    if not checked["input_checks_passed"]:
        raise ValueError("Research input validation failed; inspect this manifest before registering")
    for record in research_inputs.list_inputs():
        if (
            record.get("input_checks_passed")
            and record.get("fingerprint") == checked["fingerprint"]
            and record.get("configuration") == checked["configuration"]
        ):
            return record["id"]
    record = research_inputs.register(value)
    if not record["input_checks_passed"]:
        raise ValueError("Inputs changed during registration")
    return record["id"]


def bootstrap(root=REPO_ROOT, inputs=None, destination=None):
    root = Path(root)
    inputs = Path(inputs or os.environ.get("MEMSTARA_INPUTS_DIR") or root / "user-inputs")
    destination = Path(destination or output_dir() / "bundled-research")
    destination.mkdir(parents=True, exist_ok=True)
    # The lock also prevents duplicate registrations when initializers overlap.
    with (destination / ".registration.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        source = root / "examples/heart-failure/dataset.csv"
        corpus = root / "examples/heart-failure/okf"
        prepared = destination / ("heart-failure-v1-" + research_inputs.digest(source))
        if not prepared.exists():
            with tempfile.TemporaryDirectory(dir=destination) as temporary:
                staging = Path(temporary) / "prepared"
                prepare(source, corpus, staging)
                value = json.loads((staging / "research.json").read_text())
                value["dataset_path"] = "dataset.csv"
                (staging / "research.json").write_text(json.dumps(value, indent=2) + "\n")
                staging.rename(prepared)
        evidence = json.loads((prepared / "preparation.json").read_text())
        if research_inputs.digest(prepared / "dataset.csv") != evidence["derived_sha256"]:
            raise ValueError("Prepared HeartFailure data changed; restore it before startup")
        result = {"bundled": register_file(prepared / "research.json"), "user_inputs": [], "execution_started": False}
        # One folder per study; never recursively scan arbitrary private files.
        for manifest in sorted(inputs.glob("*/research.json")):
            try:
                identifier = register_file(manifest)
                result["user_inputs"].append({"manifest": str(manifest), "id": identifier, "status": "registered"})
            except (ValueError, OSError, TypeError, KeyError):
                result["user_inputs"].append({"manifest": str(manifest), "status": "invalid"})
        from memstara.pipeline.checkpoint import atomic_json

        atomic_json(destination / "registration.json", result)
        return result


if __name__ == "__main__":
    result = bootstrap()
    invalid = sum(item["status"] == "invalid" for item in result["user_inputs"])
    print(
        f"HeartFailure registered; {len(result['user_inputs']) - invalid} user studies registered; "
        f"{invalid} invalid. See outputs/bundled-research/registration.json. No experiment started."
    )
