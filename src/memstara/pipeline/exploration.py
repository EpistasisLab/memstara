"""Round scheduling with cooperative pause and cancellation."""
import asyncio
import itertools
from pathlib import Path


async def rounds(limit: int, continuous: bool, run_dir: Path):
    """Yield zero-based rounds; pause only between complete rounds."""
    for wave in (itertools.count() if continuous else range(limit)):
        while (run_dir / "pause.request").exists():
            await asyncio.sleep(1)
        yield wave


async def wait_for_new_questions(run_dir: Path, dry_streak: int):
    """Back off without holding DB connections; cancellation remains immediate."""
    delay = min(900, 60 * 2 ** min(max(dry_streak - 1, 0), 4))
    marker = run_dir / "questions.waiting"
    marker.touch()
    try:
        await asyncio.sleep(delay)
    finally:
        marker.unlink(missing_ok=True)


def write_progress(run_dir, iteration, stage, tasks=None, *, completed=False):
    """Publish stage-based progress; elapsed time never implies completion."""
    import json
    from datetime import UTC, datetime
    data = {"iteration": iteration, "stage": stage, "updated_at": datetime.now(UTC).isoformat()}
    stages = ("hypothesis", "data", "ml", "interpreter", "report")
    data["stage_percent"] = 100 if completed else (stages.index(stage) * 20 if stage in stages else None)
    data["iteration_completed"] = completed
    data["progress_basis"] = "Five equally weighted stages; not elapsed time"
    if tasks is not None:
        data["counts"] = {state: sum(t.get("status") == state for t in tasks)
                          for state in ("ready", "in_progress", "done", "failed")}
    target = run_dir / "progress.json"
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(data))
    temporary.replace(target)
