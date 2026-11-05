"""Missing housing data regenerates a question instead of entering Explanation."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline.executable_question import seed, require_analysis
from memstara.pipeline.failures import PipelineExecutionFailure


def identity():
    return {"run_tag": "r", "config_hash": "hash", "trial": 0, "wave": 0, "writer": "hypothesis"}


@pytest.mark.asyncio
async def test_missing_housing_regenerates_same_trial_and_only_committed_task_succeeds(tmp_path):
    task = False
    answered = []
    initial = {"question_id": 31, "text": "housing instability"}
    replacement = {"question_id": 32, "text": "age and sex"}
    async def present():
        return task
    async def answer(q, attempt):
        nonlocal task
        answered.append(q["question_id"])
        if q["question_id"] == 32:
            task = True
        return "Housing has no defensible column" if not task else "task saved"
    async def regenerate(rejected, reason):
        assert rejected == [31]
        assert "Housing" in reason["agent_response"]
        assert reason["question"] == initial
        return replacement
    result = await seed(initial, root=tmp_path, identity=identity(), present=present, answer=answer, regenerate=regenerate)
    assert result == replacement and answered == [31, 31, 32]
    saved = json.loads((tmp_path / "question_mapping_recovery/trial-0.json").read_text())
    assert saved["status"] == "ready" and saved["identity"]["trial"] == 0
    assert initial["question_id"] == 31


@pytest.mark.asyncio
async def test_existing_task_never_replays_agent_or_generates_question(tmp_path):
    answer, regenerate = AsyncMock(), AsyncMock()
    q = {"question_id": 31}
    assert await seed(q, root=tmp_path, identity=identity(), present=AsyncMock(return_value=True),
                      answer=answer, regenerate=regenerate) == q
    answer.assert_not_awaited()
    regenerate.assert_not_awaited()


@pytest.mark.asyncio
async def test_exhaustion_is_explicit_and_never_returns_empty_success(tmp_path):
    regenerate = AsyncMock(return_value=None)
    with pytest.raises(PipelineExecutionFailure):
        await seed({"question_id": 31}, root=tmp_path, identity=identity(), present=AsyncMock(return_value=False),
                   answer=AsyncMock(return_value="No housing measure"), regenerate=regenerate, attempts=3)
    failure = json.loads((tmp_path / "pipeline_failure.json").read_text())
    assert failure["code"] == "question_mapping_exhausted" and failure["loop"] == 1
    assert regenerate.await_count == 2
    saved = json.loads((tmp_path / "question_mapping_recovery/trial-0.json").read_text())
    assert saved["status"] == "needs_review"


@pytest.mark.asyncio
async def test_unknown_commit_status_does_not_regenerate(tmp_path):
    regenerate = AsyncMock()
    with pytest.raises(OSError):
        await seed({"question_id": 31}, root=tmp_path, identity=identity(),
                   present=AsyncMock(side_effect=OSError("DB unavailable")), answer=AsyncMock(), regenerate=regenerate)
    regenerate.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_and_resume_keeps_rejected_question_out(tmp_path):
    present = AsyncMock(return_value=False)
    with pytest.raises(asyncio.CancelledError):
        await seed({"question_id": 31}, root=tmp_path, identity=identity(), present=present,
                   answer=AsyncMock(return_value="No housing measure"), regenerate=AsyncMock(side_effect=asyncio.CancelledError))
    async def regenerate(rejected, reason):
        assert rejected == [31]
        return {"question_id": 32}
    async def answer(q, attempt):
        assert q["question_id"] == 32
        present.return_value = True
        return "saved"
    result = await seed({"question_id": 31}, root=tmp_path, identity=identity(), present=present,
                        answer=answer, regenerate=regenerate)
    assert result["question_id"] == 32


@pytest.mark.parametrize("tasks", [[], [{"trial": 0, "status": "failed"}], [{"trial": 1, "status": "done"}],
                                   [{"trial": 0, "status": "ready"}], [{"trial": 0, "status": "done"}] * 2])
def test_incomplete_or_duplicate_analysis_blocks_explanation(tmp_path, tasks):
    with pytest.raises(PipelineExecutionFailure):
        require_analysis(tasks, [0], tmp_path, 1)
    assert json.loads((tmp_path / "pipeline_failure.json").read_text())["code"] == "analysis_required_before_report"


def test_completed_analysis_can_enter_explanation(tmp_path):
    require_analysis([{"trial": 0, "status": "done"}], [0], tmp_path, 1)
    assert not (tmp_path / "pipeline_failure.json").exists()


def test_full_catalog_lookup_includes_columns_omitted_from_preview(monkeypatch):
    from memstara.mcp_servers.blackboard import lookup_predictor_catalog
    features = [{"column": f"CAT__OTHER__{i}", "meaning": "other"} for i in range(100)]
    features += [{"column": "CURRENT_AGE", "meaning": "age in years"}, {"column": "Y", "meaning": "outcome"}]
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: {
        "question_feasibility_policy": "explicit_columns_v1", "y_column": "Y", "feature_context": {"features": features}})
    value = json.loads(asyncio.run(lookup_predictor_catalog(["age"])))
    assert value["matches"] == [{"column": "CURRENT_AGE", "meaning": "age in years"}]
    assert json.loads(asyncio.run(lookup_predictor_catalog(["housing", "homeless", "Z59"]))) ["total"] == 0
    page = json.loads(asyncio.run(lookup_predictor_catalog([], offset=100)))
    assert page["total"] == 101 and len(page["matches"]) == 1 and page["next_offset"] is None


def test_new_question_requires_explicit_mapping_even_when_similarity_returns_candidates():
    from memstara.pipeline.question_contract import make_contract
    plan = {"y_column": "Y", "question_feasibility_policy": "explicit_columns_v1",
            "feature_context": {"features": [{"column": "CURRENT_AGE"}]}}
    item = {"predictor_concepts": ["Age"], "rationale": "Knowledge-supported age association", "source_ids": ["paper"]}
    with pytest.raises(ValueError, match="proposed_mapping"):
        make_contract(item, plan)
    item["proposed_mapping"] = [{"concept": "Age", "column": "CURRENT_AGE", "source_id": "paper", "rationale": "Direct age measurement"}]
    assert make_contract(item, plan)["proposed_mapping"] == item["proposed_mapping"]
    item["proposed_mapping"][0]["column"] = "HOUSING"
    with pytest.raises(ValueError, match="unavailable"):
        make_contract(item, plan)


@pytest.mark.asyncio
async def test_writer_does_not_reuse_failed_or_another_writers_question(monkeypatch):
    from memstara.pipeline import board
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: {})
    rows = [{"question_id": 31, "origin_run": "r", "origin_wave": 0, "writer": "hypothesis"},
            {"question_id": 32, "origin_run": "r", "origin_wave": 0, "writer": "hypothesis#2"}]
    async def tool(*args):
        return {"questions": list(rows)}
    async def agent(*args, **kwargs):
        rows.append({"question_id": 33, "origin_run": "r", "origin_wave": 0, "writer": "hypothesis"})
    monkeypatch.setattr(board, "call_board_tool", tool)
    monkeypatch.setattr(board, "call_agent", agent)
    result, _ = await board.questions_for_wave(None, {"hypothesis": "agent"}, {"question": []},
                                               run_tag="r", wave=0, want=1,
                                               excluded_question_ids=frozenset({31}), writer="hypothesis")
    assert [q["question_id"] for q in result] == [33]
