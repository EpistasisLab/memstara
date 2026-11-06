"""Current-loop work stays bounded without losing history or replaying writes."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline import board, board_reads
from memstara.pipeline.failures import PipelineExecutionFailure


@pytest.fixture
def transport(monkeypatch, tmp_path):
    monkeypatch.setattr(board, '_TRACE_DIR', tmp_path / 'trace')
    monkeypatch.setattr(board, 'get_server_by_name', AsyncMock(return_value=SimpleNamespace(id='board')))
    invoke = AsyncMock()
    monkeypatch.setattr('motoro.services.mcp_service.call_server_tool', invoke)
    monkeypatch.setattr(board_reads.asyncio, 'sleep', AsyncMock())
    return invoke


def test_poll_bounds_cover_all_trials_in_current_wave_and_do_not_scope_final_archive(transport):
    transport.return_value = (False, json.dumps({'count': 0, 'tasks': []}))
    token = board._CURRENT_TRIAL_RANGE.set((64, 66))
    try:
        asyncio.run(board.board_state(None, 'run', state_only=True))
        assert transport.call_args.args[2] == {
            'run_tag': 'run', 'state_only': True, 'trial_start': 64, 'trial_end': 66,
        }
        asyncio.run(board.board_state(None, 'run'))
        assert transport.call_args.args[2] == {'run_tag': 'run'}
    finally:
        board._CURRENT_TRIAL_RANGE.reset(token)


def test_result_timeout_retries_same_read_and_records_scope_not_contents(transport, tmp_path):
    transport.side_effect = [TimeoutError(), (False, json.dumps({'count': 1, 'results': [{'trial': 32}]}))]
    query = {'run_tag': 'run', 'trial_start': 32, 'trial_end': 33}
    result = asyncio.run(board.call_board_tool(None, 'read_results', query))
    assert result['results'] == [{'trial': 32}]
    assert transport.await_count == 2
    assert all(call.args[2] == query for call in transport.call_args_list)
    events = [json.loads(line) for line in (tmp_path / 'board_read_events.jsonl').read_text().splitlines()]
    assert any(event['state'] == 'recovered' for event in events)
    payload = next(event for event in events if event['state'] == 'read_payload')
    assert payload['rows'] == 1 and payload['response_bytes'] > 0
    assert payload['operation']['trial_start'] == 32


def test_exhausted_result_timeout_is_storage_failure_not_model_failure(transport, tmp_path):
    transport.side_effect = TimeoutError()
    token = board._CURRENT_LOOP.set(33)
    try:
        with pytest.raises(PipelineExecutionFailure):
            asyncio.run(board.call_board_tool(None, 'read_results', {
                'run_tag': 'run', 'trial_start': 32, 'trial_end': 33,
            }))
    finally:
        board._CURRENT_LOOP.reset(token)
    failure = json.loads((tmp_path / 'pipeline_failure.json').read_text())
    assert failure['code'] == 'board_read_unavailable'
    assert failure['loop'] == 33
    assert transport.await_count == 3
    events = [json.loads(line) for line in (tmp_path / 'board_read_events.jsonl').read_text().splitlines()]
    assert events[-1]['exception']['error_type'] == 'TimeoutError'


def test_write_timeout_is_never_replayed(transport):
    transport.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        asyncio.run(board.call_board_tool(None, 'submit_result', {'task_id': 12}))
    assert transport.await_count == 1
