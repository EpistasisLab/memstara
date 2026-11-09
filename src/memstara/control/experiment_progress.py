"""Count original schedule positions across explicit continuation attempts."""

from collections import Counter
from pathlib import Path

from memstara.logical_experiment import lineage, read, selected_loops


def summarize(record):
    if not record:
        return None
    try:
        directory = Path(record["run_dir"])
        config = read(directory / "config.json")
        if not config.get("combination_plan"):
            return None
        sources = lineage(config, directory)
        total = config["combination_plan"]["total_loops"]
        attempts: Counter[int] = Counter()
        completed: set[int] = set()
        latest = {}
        for snapshot, root in sources:
            allowed = set(selected_loops(snapshot, root))
            journal = read(root / "iteration_outcomes.json")
            if not isinstance(journal, dict):
                raise ValueError("Invalid outcome journal")
            for key, value in journal.items():
                if not key.isdigit() or not isinstance(value, dict):
                    raise ValueError("Invalid outcome entry")
                loop = int(key)
                if loop not in allowed:
                    continue  # Old retry writers also recorded phantom local ordinals.
                attempts[loop] += 1
                latest[loop] = value.get("outcome")
                if value.get("outcome") == "completed":
                    completed.add(loop)
        return {
            "status": "available",
            "basis": "unique_original_schedule_positions_in_recorded_outcome_journals",
            "run_tags": [snapshot["run_tag"] for snapshot, _ in sources],
            "scheduled": total,
            "completed": len(completed),
            "started": len(attempts),
            "attempts": sum(attempts.values()),
            "retries": sum(n - 1 for n in attempts.values()),
            "not_started": total - len(attempts),
            "blocked": sum(
                state in ("blocked", "skipped", "interrupted") and loop not in completed
                for loop, state in latest.items()
            ),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "unavailable", "message": "Complete experiment history could not be verified."}
