"""Question failures stay in the same Loop; only verified questions complete its phase."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline import question_regeneration as regeneration
from memstara.pipeline.checkpoint import Checkpoint
from memstara.pipeline.exploration import ExecutionGate


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(regeneration, "retry_delay", AsyncMock())


def arguments(tmp_path, **extra):
    return dict(root=tmp_path, wave=0, run_tag="run", config_hash="hash", **extra)


def read_state(tmp_path):
    return json.loads((tmp_path / "question_regeneration/loop-1/state.json").read_text())


@pytest.mark.asyncio
async def test_empty_batches_do_not_complete_or_advance_loop(tmp_path, fast):
    checkpoint = Checkpoint(tmp_path)
    prompts = []

    async def generate():
        assert checkpoint.state["next_wave"] == 0
        assert checkpoint.state["phases"]["0:questions"]["status"] == "active"
        prompts.append(regeneration.writer_feedback("hypothesis"))
        regeneration.remember_writer("hypothesis", "Try another supported mechanism")
        return ([{"question_id": 7}], False) if len(prompts) == 5 else ([], True)

    result = await checkpoint.phase("0:questions", lambda: regeneration.until_saved(generate, **arguments(tmp_path)))
    assert result == ([{"question_id": 7}], False)
    assert len(set(prompts)) == 5
    assert "Try another supported mechanism" not in prompts[-1]
    assert "previous_response_sha256" in prompts[-1]
    assert checkpoint.state["next_wave"] == 0
    assert checkpoint.state["phases"]["0:questions"]["status"] == "done"
    assert read_state(tmp_path)["attempt"] == 5
    outcomes = json.loads((tmp_path / "iteration_outcomes.json").read_text())
    assert set(outcomes) == {"1"}
    assert outcomes["1"]["outcome"] == "running"  # Analysis/report have not happened.


@pytest.mark.asyncio
async def test_pause_stops_regeneration_and_resume_keeps_loop(tmp_path, fast):
    gate = ExecutionGate(tmp_path)
    first = asyncio.Event()
    count = 0

    async def generate():
        nonlocal count
        count += 1
        if count == 1:
            (tmp_path / "pause.request").touch()
            first.set()
            return [], True
        return [{"question_id": 8}], False

    task = asyncio.create_task(regeneration.until_saved(generate, **arguments(tmp_path, wait=gate.wait)))
    try:
        await asyncio.wait_for(first.wait(), 2)
        await asyncio.sleep(0.05)
        assert count == 1 and not task.done()
        assert json.loads((tmp_path / "execution_control.json").read_text())["state"] == "paused"
        (tmp_path / "pause.request").unlink()
        assert await asyncio.wait_for(task, 2) == ([{"question_id": 8}], False)
        assert count == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_restart_uses_durable_attempt_and_feedback(tmp_path, fast):
    async def interrupted():
        regeneration.remember_writer("hypothesis", "A required predictor was unavailable")
        return [], True

    waits = 0

    async def stop_before_next_request():
        nonlocal waits
        waits += 1
        if waits == 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await regeneration.until_saved(interrupted, **arguments(tmp_path, wait=stop_before_next_request))
    assert read_state(tmp_path)["attempt"] == 2

    async def resume():
        prompt = regeneration.writer_feedback("hypothesis")
        assert "ROUND 2" in prompt and "predictor was unavailable" not in prompt
        assert "previous_response_sha256" in prompt
        return [{"question_id": 9}], False

    assert await regeneration.until_saved(resume, **arguments(tmp_path)) == ([{"question_id": 9}], False)


@pytest.mark.asyncio
async def test_infrastructure_error_is_not_repeated_or_skipped(tmp_path, fast):
    generate = AsyncMock(side_effect=ConnectionError("DB unavailable"))
    with pytest.raises(ConnectionError):
        await regeneration.until_saved(generate, **arguments(tmp_path))
    generate.assert_awaited_once()
    assert read_state(tmp_path)["attempt"] == 1


@pytest.mark.asyncio
async def test_mapping_failure_does_not_trigger_regeneration(tmp_path, fast):
    (tmp_path / "question_repair_0_writer.json").write_text(
        json.dumps(
            {
                "run_tag": "run",
                "config_hash": "hash",
                "response": {"rejected": [{"code": "mapping_preflight_unavailable"}]},
            }
        )
    )
    generate = AsyncMock(return_value=([], True))
    with pytest.raises(RuntimeError, match="infrastructure"):
        await regeneration.until_saved(generate, **arguments(tmp_path))
    generate.assert_awaited_once()
    assert read_state(tmp_path)["attempt"] == 1


@pytest.mark.asyncio
async def test_readback_after_interruption_reuses_saved_question(tmp_path, fast, monkeypatch):
    from memstara.pipeline import board

    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: {})
    agent = AsyncMock()
    monkeypatch.setattr(board, "call_agent", agent)
    monkeypatch.setattr(
        board,
        "call_board_tool",
        AsyncMock(return_value={"questions": [{"question_id": 10, "origin_run": "run", "origin_wave": 0}]}),
    )
    result = await regeneration.until_saved(
        lambda: board.questions_for_wave(None, {"hypothesis": "h"}, {"question": []}, run_tag="run", wave=0, want=1),
        **arguments(tmp_path),
    )
    assert result[0][0]["question_id"] == 10
    agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_question_helper_regenerates_with_feedback_and_distinct_cache_keys(tmp_path, fast, monkeypatch):
    from memstara.pipeline import board
    from memstara.pipeline.paused_recovery import VERSION

    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "run_tag": "run",
                "config_hash": "hash",
                "pause_recovery_policy": VERSION,
            }
        )
    )
    checkpoint = Checkpoint(tmp_path)
    gate = ExecutionGate(tmp_path)
    gate.checkpoint = checkpoint
    monkeypatch.setattr(board, "_EXECUTION_GATE", gate)
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: {})
    saved = []
    prompts = []

    async def model(agent, prompt, **kwargs):
        prompts.append(prompt)
        if len(prompts) == 5:
            saved.append({"question_id": 11, "origin_run": "run", "origin_wave": 0})
        return "Need a different supported predictor", {"status": "completed"}

    async def bank(*args):
        return {"questions": saved[:]}

    monkeypatch.setattr(board, "_call_agent_uncontrolled", model)
    monkeypatch.setattr(board, "call_board_tool", bank)
    result = await checkpoint.phase(
        "0:questions",
        lambda: regeneration.until_saved(
            lambda: board.questions_for_wave(
                None, {"hypothesis": "h"}, {"question": []}, run_tag="run", wave=0, want=1
            ),
            **arguments(tmp_path, wait=gate.wait),
        ),
    )
    assert result[0][0]["question_id"] == 11
    assert len(prompts) == len(set(prompts)) == 5
    assert "Need a different supported predictor" not in prompts[2]
    assert "previous_response_sha256" in prompts[2]
    assert len(list((tmp_path / "completed_agents").glob("*.json"))) == 5
    assert checkpoint.state["next_wave"] == 0
    assert not checkpoint.state["calls"]


@pytest.mark.asyncio
async def test_mismatched_saved_state_is_rejected(tmp_path, fast):
    generate = AsyncMock(return_value=([{"question_id": 1}], False))
    await regeneration.until_saved(generate, **arguments(tmp_path))
    with pytest.raises(ValueError, match="does not match"):
        await regeneration.until_saved(generate, **{**arguments(tmp_path), "run_tag": "other"})
    assert generate.await_count == 1
