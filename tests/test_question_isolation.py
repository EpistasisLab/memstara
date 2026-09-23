"""New executions must not consume questions saved by previous executions."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline import board


def test_question_generation_never_reuses_saved_questions(monkeypatch):
    saved = {"question_id": 1, "origin_run": "old", "origin_wave": 0}
    reader = AsyncMock(return_value={"questions": [saved]})
    monkeypatch.setattr(board, "call_board_tool", reader)
    monkeypatch.setattr(board, "call_agent", AsyncMock())
    rows, dry = asyncio.run(board.questions_for_wave(
        None, {"hypothesis": object()}, {"question": []},
        run_tag="new", wave=0, want=2,
    ))
    assert rows == []
    assert dry


def test_only_new_questions_from_current_run_and_wave_are_used(monkeypatch):
    saved = {"question_id": 1, "origin_run": "old", "origin_wave": 0}
    current = {"question_id": 2, "origin_run": "new", "origin_wave": 0}
    other_run = {"question_id": 3, "origin_run": "other", "origin_wave": 0}
    other_wave = {"question_id": 4, "origin_run": "new", "origin_wave": 1}
    monkeypatch.setattr(board, "call_board_tool", AsyncMock(side_effect=[
        {"questions": [saved]}, {"questions": [other_run, saved, current, other_wave]},
    ]))
    monkeypatch.setattr(board, "call_agent", AsyncMock())
    rows, dry = asyncio.run(board.questions_for_wave(
        None, {"hypothesis": object()}, {"question": []},
        run_tag="new", wave=0, want=2,
    ))
    assert rows == [current]
    assert not dry


@pytest.mark.parametrize("want,allocations", [(5, [2, 2, 1]), (2, [1, 1]), (0, [])])
def test_question_writers_share_budget_and_overlap(monkeypatch, want, allocations):
    async def scenario():
        started = []
        completed = []
        all_started = asyncio.Event()
        async def call(agent, ask, **kwargs):
            started.append((agent, ask))
            if len(started) == len(allocations):
                all_started.set()
            # A sequential implementation deadlocks here instead of passing.
            await asyncio.wait_for(all_started.wait(), timeout=1)
            completed.append(agent)
        monkeypatch.setattr(board, "call_agent", call)
        async def read_bank(*args):
            return {"questions": ([{"question_id": i + 1, "origin_run": "new", "origin_wave": 0}
                                  for i in range(want)] if completed else [])}
        monkeypatch.setattr(board, "call_board_tool", read_bank)
        agents = {"hypothesis": "a", "hypothesis2": "b", "hypothesis3": "c", "report": "r"}
        await board.questions_for_wave(None, agents, {"question": []}, run_tag="new", wave=0, want=want)
        assert len(completed) == len(started) == len(allocations)
        for (agent, ask), allocation in zip(started, allocations, strict=True):
            assert agent != "r"
            assert f"up to {allocation} grounded questions" in ask
            assert "Pass writer=" in ask
    asyncio.run(scenario())
