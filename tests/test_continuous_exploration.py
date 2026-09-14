"""Continuous scheduling must remain pausable and cancellable without an LLM."""
import asyncio

import pytest

from memstara.control.request import build_argv
from memstara.pipeline.exploration import rounds


def test_continuous_request_is_explicit_and_validated():
    assert "--continuous" not in build_argv({}, [])
    assert "--continuous" in build_argv({"continuous": True}, [])
    for invalid in ("false", "true", 1, None):
        with pytest.raises(ValueError, match="continuous"):
            build_argv({"continuous": invalid}, [])


def test_finite_rounds_and_continuous_rounds(tmp_path):
    async def scenario():
        assert [n async for n in rounds(2, False, tmp_path)] == [0, 1]
        iterator = rounds(1, True, tmp_path)
        assert [await anext(iterator) for _ in range(4)] == [0, 1, 2, 3]
        await iterator.aclose()
    asyncio.run(scenario())


def test_pause_resume_and_stop_while_paused(tmp_path):
    async def scenario():
        iterator = rounds(1, True, tmp_path)
        assert await anext(iterator) == 0
        marker = tmp_path / "pause.request"
        marker.touch()
        pending = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0.02)
        assert not pending.done()
        marker.unlink()
        assert await asyncio.wait_for(pending, 2) == 1
        marker.touch()
        pending = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0.02)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await iterator.aclose()
    asyncio.run(scenario())


def test_empty_exploration_waits_and_clears_state_on_cancellation(tmp_path, monkeypatch):
    from memstara.pipeline import exploration
    async def scenario():
        observed = []
        async def sleep(delay):
            observed.append(delay)
            assert (tmp_path / "questions.waiting").exists()
            raise asyncio.CancelledError()
        monkeypatch.setattr(exploration.asyncio, "sleep", sleep)
        for streak in (1, 2, 100):
            with pytest.raises(asyncio.CancelledError):
                await exploration.wait_for_new_questions(tmp_path, streak)
            assert not (tmp_path / "questions.waiting").exists()
        assert observed == [60, 120, 900]
    asyncio.run(scenario())


def test_stage_progress_resets_and_only_explicit_completion_reaches_100(tmp_path):
    import json
    from memstara.pipeline.exploration import write_progress
    write_progress(tmp_path, 4, "report")
    assert json.loads((tmp_path / "progress.json").read_text())["stage_percent"] == 80
    write_progress(tmp_path, 4, "report", completed=True)
    assert json.loads((tmp_path / "progress.json").read_text())["stage_percent"] == 100
    write_progress(tmp_path, 5, "hypothesis")
    current = json.loads((tmp_path / "progress.json").read_text())
    assert current["stage_percent"] == 0
    assert current["iteration"] == 5
