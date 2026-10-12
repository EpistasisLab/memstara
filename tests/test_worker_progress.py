"""Progress must follow outstanding invocations after a tool commits its row."""
import asyncio
import json

import pytest

from memstara.pipeline.exploration import write_progress
from memstara.pipeline.scheduler import StageWorkers


@pytest.mark.parametrize("stage,next_type,status", [
    ("interpreter", "interpret", "done"),
    ("ml", "interpret", "ready"),
    ("data", "ml", "ready"),
])
def test_committed_row_does_not_advance_past_live_agent(tmp_path, stage, next_type, status):
    async def scenario():
        workers = StageWorkers()
        release = asyncio.Event()
        rows = [{"task_type": next_type, "status": status}]
        workers.launch(stage, 1, release.wait())
        try:
            await asyncio.sleep(0)
            current = workers.progress_stage(rows, seed_done=True)
            write_progress(tmp_path, 2, current, rows)
            saved = json.loads((tmp_path / "progress.json").read_text())
            assert saved["stage"] == stage
            assert not saved["iteration_completed"]
            release.set()
            await workers.wait()
            await workers.completed()
            expected = "report" if status == "done" else "interpreter" if next_type == "interpret" else next_type
            assert workers.progress_stage(rows, seed_done=True) == expected
        finally:
            await workers.close()
    asyncio.run(scenario())


def test_overlapping_workers_use_earliest_active_stage():
    async def scenario():
        workers = StageWorkers()
        release = asyncio.Event()
        workers.launch("interpreter", 1, release.wait())
        workers.launch("ml", 1, release.wait())
        try:
            assert workers.progress_stage([], seed_done=True) == "ml"
            assert workers.progress_stage([], seed_done=False) == "hypothesis"
        finally:
            await workers.close()
    asyncio.run(scenario())


def test_board_fallback_prefers_claimed_work_and_normalizes_interpretation():
    workers = StageWorkers()
    assert workers.progress_stage([
        {"task_type": "ml", "status": "ready"},
        {"task_type": "interpret", "status": "in_progress"},
    ], seed_done=True) == "interpreter"
    assert workers.progress_stage([], seed_done=False) == "hypothesis"
    assert workers.progress_stage([], seed_done=True) == "report"
