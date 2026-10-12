import asyncio
from unittest.mock import AsyncMock

import pytest
pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")

from memstara.pipeline import board

import json

from memstara.pipeline.board import save_report
from types import SimpleNamespace


@pytest.mark.parametrize('raw', [None, (True, '{"tasks": [], "count": 0}'),
                                (False, None), (False,), 'broken', 'null', '[]'])
def test_driver_tool_rejects_unavailable_or_invalid_response(monkeypatch, raw):
    monkeypatch.setattr(board, 'get_server_by_name', AsyncMock(return_value=SimpleNamespace(id='board')))
    monkeypatch.setattr('motoro.services.mcp_service.call_server_tool', AsyncMock(return_value=raw))
    with pytest.raises(RuntimeError):
        asyncio.run(board.call_board_tool(None, 'read_questions', {}))


def test_driver_tool_missing_server_is_explicit(monkeypatch):
    monkeypatch.setattr(board, 'get_server_by_name', AsyncMock(return_value=None))
    invoke = AsyncMock()
    monkeypatch.setattr('motoro.services.mcp_service.call_server_tool', invoke)
    with pytest.raises(RuntimeError, match='not registered'):
        asyncio.run(board.call_board_tool(None, 'read_questions', {}))
    invoke.assert_not_awaited()


@pytest.mark.parametrize('raw', ['{"questions": []}', (False, '{"questions": []}')])
def test_driver_tool_accepts_supported_response_envelopes(monkeypatch, raw):
    monkeypatch.setattr(board, 'get_server_by_name', AsyncMock(return_value=SimpleNamespace(id='board')))
    monkeypatch.setattr('motoro.services.mcp_service.call_server_tool', AsyncMock(return_value=raw))
    assert asyncio.run(board.call_board_tool(None, 'read_questions', {})) == {'questions': []}


def test_board_state_transport_error_cannot_look_like_an_empty_board(monkeypatch):
    monkeypatch.setattr(board, 'get_server_by_name', AsyncMock(return_value=SimpleNamespace(id='board')))
    monkeypatch.setattr('motoro.services.mcp_service.call_server_tool',
                        AsyncMock(return_value=(True, '{"tasks": [], "count": 0}')))
    with pytest.raises(RuntimeError, match='tool failed'):
        asyncio.run(board.board_state(None, 'synthetic'))


def test_driver_preserves_application_rejection_for_caller_recovery(monkeypatch):
    monkeypatch.setattr(board, 'get_server_by_name', AsyncMock(return_value=SimpleNamespace(id='board')))
    monkeypatch.setattr('motoro.services.mcp_service.call_server_tool',
                        AsyncMock(return_value=(False, '{"error": "invalid transition"}')))
    assert asyncio.run(board.call_board_tool(None, 'submit_result', {})) == {
        'error': 'invalid transition'}


def test_report_failure_preserves_previous_report_and_records_failure(tmp_path):
    (tmp_path / "report.md").write_text("Previous valid report")
    assert not save_report(tmp_path, "", {"status": "failed", "error": "Timeout"})
    assert (tmp_path / "report.md").read_text() == "Previous valid report"
    assert json.loads((tmp_path / "report_status.json").read_text())["error"] == "Timeout"


def test_completed_but_empty_report_is_not_success(tmp_path):
    assert not save_report(tmp_path, "  ", {"status": "completed"})
    assert not (tmp_path / "report.md").exists()


def test_valid_report_is_saved(tmp_path):
    assert save_report(tmp_path, "# Measured results", {"status": "completed", "run_id": "test"})
    assert (tmp_path / "report.md").read_text() == "# Measured results"
    assert json.loads((tmp_path / "report_status.json").read_text())["status"] == "completed"




@pytest.mark.parametrize("payload", ["broken", "null", '{"error":"offline"}',
                                     '{"count":1,"tasks":[]}', '{"count":0,"tasks":null}'])
def test_board_read_failure_cannot_be_mistaken_for_completion(payload):
    with pytest.raises(RuntimeError):
        board.decode_board_state(payload)


def test_report_retries_once_then_recovers(monkeypatch):
    call = AsyncMock(side_effect=[("", {"status": "failed"}), ("Report", {"status": "completed"})])
    monkeypatch.setattr(board, "call_agent", call)
    text, entry = asyncio.run(board.call_report("agent", "prompt", stage="report"))
    assert text == "Report" and entry["status"] == "completed" and call.await_count == 2


def test_report_retry_is_bounded_even_when_service_raises(monkeypatch):
    call = AsyncMock(side_effect=TimeoutError)
    monkeypatch.setattr(board, "call_agent", call)
    text, entry = asyncio.run(board.call_report("agent", "prompt", stage="report"))
    assert not text and entry["status"] == "failed" and call.await_count == 2


@pytest.mark.parametrize("stage", ["data", "ml", "interpret"])
def test_finished_worker_without_submission_cannot_stay_running(stage, monkeypatch):
    monkeypatch.setattr(board, "board_state", AsyncMock(return_value={"tasks": [
        {"task_id": 10, "task_type": stage, "status": "in_progress", "claimed_by": f"{stage}#1"},
        {"task_id": 11, "task_type": stage, "status": "ready"},
    ]}))
    responses = ([{"error": "No artifact"}] if stage == "ml" else []) + [{"ok": True, "status": "failed"}]
    submit = AsyncMock(side_effect=responses)
    monkeypatch.setattr(board, "call_board_tool", submit)
    asyncio.run(board.settle_finished_workers(None, "test"))
    last = submit.call_args.args[2]
    assert last["task_id"] == 10 and last["error"] and last["worker"] == f"{stage}#1"
    assert all(call.args[2]["task_id"] != 11 for call in submit.call_args_list)


def test_settlement_failure_is_not_silently_ignored(monkeypatch):
    monkeypatch.setattr(board, "board_state", AsyncMock(return_value={"tasks": [
        {"task_id": 10, "task_type": "data", "status": "in_progress", "claimed_by": "data#1"},
    ]}))
    monkeypatch.setattr(board, "call_board_tool", AsyncMock(return_value={"error": "DB unavailable"}))
    with pytest.raises(RuntimeError):
        asyncio.run(board.settle_finished_workers(None, "test"))


def test_provider_diagnostics_identify_truncation_without_recording_content():
    from types import SimpleNamespace as NS
    from memstara.pipeline.diagnostics import summarize
    response = NS(choices=[NS(finish_reason="length", message=NS(tool_calls=[
        NS(function=NS(name="final_answer", arguments='{"answer":"private generated content"}'))
    ]))], usage=NS(completion_tokens=4096))
    record = summarize(response, {"max_tokens": 4096})
    assert record["finish_reasons"] == ["length"]
    assert record["tool_calls"][0]["has_answer"]
    assert "private generated content" not in json.dumps(record)
