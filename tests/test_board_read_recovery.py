import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from memstara.pipeline import board_reads as reads


def test_transient_read_retries_without_replaying_work_and_records_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(reads.asyncio, 'sleep', AsyncMock())
    invoke = AsyncMock(side_effect=[reads.BoardReadError('TooManyConnectionsError', True),
                                  {'count': 1, 'tasks': [{'status': 'in_progress'}]}])
    result = asyncio.run(reads.verified_read(invoke, directory=tmp_path))
    assert result['count'] == 1 and invoke.await_count == 2
    events = [json.loads(line) for line in (tmp_path / 'board_read_events.jsonl').read_text().splitlines()]
    assert [e['state'] for e in events] == ['retry', 'recovered']


def test_persistent_read_failure_is_bounded_not_empty_success(tmp_path, monkeypatch):
    monkeypatch.setattr(reads.asyncio, 'sleep', AsyncMock())
    invoke = AsyncMock(side_effect=TimeoutError('sensitive connection details'))
    with pytest.raises(reads.BoardReadError):
        asyncio.run(reads.verified_read(invoke, directory=tmp_path))
    assert invoke.await_count == 5
    assert 'sensitive' not in (tmp_path / 'board_read_events.jsonl').read_text()


def test_permanent_error_and_cancellation_are_not_retried(monkeypatch):
    for error in (reads.response_error({'error_type': 'InvalidCatalogNameError'}), asyncio.CancelledError()):
        invoke = AsyncMock(side_effect=error)
        with pytest.raises(type(error)):
            asyncio.run(reads.verified_read(invoke))
        assert invoke.await_count == 1


def test_data_handoff_recovery_is_scoped_bounded_and_never_marks_success(monkeypatch):
    from memstara.mcp_servers import blackboard as bb
    monkeypatch.setattr(bb, '_pipeline_run', lambda: 'run')
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    row = {'status': 'in_progress', 'task_type': 'data', 'claimed_by': 'data#1', 'evaluation': {}}
    conn.fetchrow.return_value = row
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    reply = json.loads(asyncio.run(bb.recover_data_handoff(10, 'data#1')))
    assert reply['status'] == 'ready'
    assert json.loads(conn.execute.call_args.args[2])['data_handoff_recovery_count'] == 1
    row['evaluation'] = {'data_handoff_recovery_count': 5}
    assert not json.loads(asyncio.run(bb.recover_data_handoff(10, 'data#1')))['ok']
    row['claimed_by'] = 'data#2'
    assert 'error' in json.loads(asyncio.run(bb.recover_data_handoff(10, 'data#1')))
    row['status'] = 'done'
    assert not json.loads(asyncio.run(bb.recover_data_handoff(10, 'data#1')))['ok']


def test_finished_data_worker_without_submission_requeues_not_fabricates(monkeypatch):
    from memstara.pipeline import board
    monkeypatch.setattr(board, 'board_state', AsyncMock(return_value={'tasks': [
        {'task_id': 10, 'task_type': 'data', 'status': 'in_progress', 'claimed_by': 'data#1'}]}))
    tool = AsyncMock(return_value={'ok': True, 'status': 'ready'})
    monkeypatch.setattr(board, 'call_board_tool', tool)
    asyncio.run(board.settle_finished_workers(None, 'run', {'data#1'}))
    assert tool.await_count == 1
    assert tool.call_args.args[1] == 'recover_data_handoff'


def test_real_driver_decodes_transient_response_and_keeps_current_tasks(monkeypatch):
    from types import SimpleNamespace
    from memstara.pipeline import board
    monkeypatch.setattr(board, '_TRACE_DIR', None)
    monkeypatch.setattr(board, 'get_server_by_name', AsyncMock(return_value=SimpleNamespace(id='board')))
    monkeypatch.setattr(reads.asyncio, 'sleep', AsyncMock())
    invoke = AsyncMock(side_effect=[(False, json.dumps({'error': 'Board storage read unavailable',
                                                      'error_type': 'ConnectionDoesNotExistError'})),
                                  (False, json.dumps({'tasks': [{'status': 'in_progress'}], 'count': 1}))])
    monkeypatch.setattr('motoro.services.mcp_service.call_server_tool', invoke)
    result = asyncio.run(board.board_state(None, 'run'))
    assert result['tasks'][0]['status'] == 'in_progress'
    assert invoke.await_count == 2
    assert all(c.args[1] == 'read_board' for c in invoke.call_args_list)


@pytest.mark.parametrize('code', ['InvalidPasswordError', 'InvalidCatalogNameError', 'UndefinedTableError'])
def test_permanent_database_error_never_spends_retries(code):
    invoke = AsyncMock(side_effect=reads.response_error({'error_type': code, 'error': 'redacted'}))
    with pytest.raises(reads.BoardReadError) as raised:
        asyncio.run(reads.verified_read(invoke))
    assert raised.value.code == code and invoke.await_count == 1


def test_cancel_during_recovery_backoff_propagates(monkeypatch):
    monkeypatch.setattr(reads.asyncio, 'sleep', AsyncMock(side_effect=asyncio.CancelledError()))
    invoke = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(reads.verified_read(invoke))
    assert invoke.await_count == 1


@pytest.mark.parametrize('stage', ['data', 'ml', 'interpret'])
def test_terminal_task_failure_stops_future_calls_and_preserves_completed_results(tmp_path, stage):
    from memstara.pipeline.failures import ensure_tasks_not_failed, ensure_not_failed, PipelineExecutionFailure
    (tmp_path / 'report.md').write_text('Earlier completed result')
    tasks = [{'task_id': 1, 'task_type': stage, 'status': 'failed', 'error': 'private details'},
             {'task_id': 2, 'task_type': 'interpret', 'status': 'done'}]
    with pytest.raises(PipelineExecutionFailure):
        ensure_tasks_not_failed(tmp_path, 4, tasks)
    with pytest.raises(PipelineExecutionFailure):
        ensure_not_failed(tmp_path)
    assert json.loads((tmp_path / 'pipeline_failure.json').read_text())['code'] == 'stage_task_failed'
    assert json.loads((tmp_path / 'failed_tasks.json').read_text())['tasks'] == [
        {'task_id': 1, 'task_type': stage, 'status': 'failed'}]
    assert (tmp_path / 'report.md').read_text() == 'Earlier completed result'
    assert 'private details' not in (tmp_path / 'failed_tasks.json').read_text()


def test_work_in_progress_is_not_a_terminal_failure(tmp_path):
    from memstara.pipeline.failures import ensure_tasks_not_failed
    ensure_tasks_not_failed(tmp_path, 1, [{'status': 'ready'}, {'status': 'in_progress'}, {'status': 'done'}])
    assert not (tmp_path / 'pipeline_failure.json').exists()
