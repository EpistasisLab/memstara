"""Engineer diagnostics retain attempts while keeping payloads out of summaries."""
import asyncio
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline.diagnostics import call_context, call_loop, request_id, record_event
from memstara.trace.diagnose import inspect


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    context = call_context.set((str(tmp_path), 'agent-test', 'interpret#1'))
    loop = call_loop.set(2)
    try:
        yield tmp_path
    finally:
        call_loop.reset(loop)
        call_context.reset(context)


def request(method):
    pytest.importorskip('motoro')
    from memstara.pipeline.llm import PipelineLLMService
    return PipelineLLMService()._request(method, NS(model='claude-haiku-test'),
                                        [{'role': 'user', 'content': 'PRIVATE-PAYLOAD'}])


def test_timeout_retry_correlates_receipts_and_preserves_original_exception(context, monkeypatch):
    monkeypatch.setattr('memstara.pipeline.llm.asyncio.sleep', AsyncMock())
    method = AsyncMock(side_effect=[TimeoutError('PRIVATE-KEY'), 'result'])
    assert asyncio.run(request(method)) == 'result'
    report = inspect(context)
    assert report['request_evidence_complete']
    assert [r['state'] for r in report['requests']] == ['failed', 'completed']
    assert report['requests'][0]['error_types'] == ['TimeoutError']
    assert len({r['request_id'] for r in report['requests']}) == 2
    assert all(r['loop'] == 2 and r['run_id'] == 'agent-test' for r in report['requests'])
    assert all(r['duration_seconds'] >= 0 for r in report['requests'])
    assert report['retries'][0]['request_id'] == report['requests'][0]['request_id']
    assert report['retries'][1]['request_id'] == report['requests'][1]['request_id']
    assert 'PRIVATE-' not in json.dumps(report)
    assert 'PRIVATE-' not in (context / 'request_events.jsonl').read_text()
    assert request_id.get() is None


def test_cancellation_has_terminal_event_without_provider_failure(context):
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(request(AsyncMock(side_effect=asyncio.CancelledError())))
    report = inspect(context)
    assert report['request_evidence_complete']
    assert report['requests'][0]['state'] == 'cancelled'
    assert not (context / 'pipeline_failure.json').exists()
    assert request_id.get() is None


def test_started_event_is_readable_while_request_is_waiting(context):
    async def invoke(*args, **kwargs):
        report = inspect(context)
        assert report['requests'][0]['state'] == 'unresolved'
        assert report['requests'][0]['ended_at'] is None
        assert not report['request_evidence_complete']
        return 'done'
    asyncio.run(request(invoke))
    assert inspect(context)['request_evidence_complete']


def test_concurrent_requests_do_not_share_ids(context):
    async def invoke(*args, **kwargs):
        before = request_id.get()
        await asyncio.sleep(0)
        assert request_id.get() == before
        return 'done'
    async def run():
        return await asyncio.gather(request(invoke), request(invoke))
    assert asyncio.run(run()) == ['done', 'done']
    report = inspect(context)
    assert report['request_evidence_complete']
    assert len(report['requests']) == 2
    assert len({r['request_id'] for r in report['requests']}) == 2


def test_failed_writer_does_not_hide_model_result(context, caplog):
    (context / 'request_events.jsonl').mkdir()
    assert asyncio.run(request(AsyncMock(return_value='done'))) == 'done'
    assert 'audit evidence is incomplete' in caplog.text
    assert not inspect(context)['request_evidence_complete']


def test_failed_writer_does_not_mask_original_provider_error(context, caplog):
    from memstara.pipeline.failures import PipelineExecutionFailure, exception_chain
    (context / 'request_events.jsonl').mkdir()
    with pytest.raises(PipelineExecutionFailure) as error:
        asyncio.run(request(AsyncMock(side_effect=ValueError('PRIVATE-ERROR'))))
    assert any(isinstance(e, ValueError) for e in exception_chain(error.value))
    assert 'audit evidence is incomplete' in caplog.text
    assert 'PRIVATE-ERROR' not in caplog.text


def test_cross_execution_terminal_and_receipt_cannot_certify_complete(tmp_path):
    rows = [{'request_id': 'a', 'state': state, 'run_id': run, 'stage': 'ml', 'loop': 1}
            for state, run in [('started', 'owner'), ('completed', 'other')]]
    (tmp_path / 'request_events.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (tmp_path / 'cost_ledger.jsonl').write_text(json.dumps(
        {'request_id': 'a', 'agent_run_id': 'other', 'stage': 'ml'}) + '\n')
    report = inspect(tmp_path)
    assert not report['request_evidence_complete']
    assert len(report['issues']) == 2


def test_truncated_journal_and_historical_run_are_explicitly_incomplete(tmp_path):
    assert not inspect(tmp_path)['request_evidence_complete']
    (tmp_path / 'request_events.jsonl').write_text('{"request_id":"a","state":"started"}\n{')
    report = inspect(tmp_path)
    assert not report['request_evidence_complete']
    assert any('malformed line 2' in issue for issue in report['issues'])
    assert any('unterminated' in issue for issue in report['issues'])


def test_metadata_serialization_error_is_visible_and_nonfatal(context, caplog):
    assert record_event((context, 'run', 'ml'), 'started', duration_seconds=float('nan')) is False
    assert 'incomplete' in caplog.text


def test_missing_receipt_and_duplicate_terminals_are_incomplete(tmp_path):
    rows = [{'request_id': 'a', 'state': state} for state in ('started', 'completed', 'completed')]
    (tmp_path / 'request_events.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    report = inspect(tmp_path)
    assert not report['request_evidence_complete']
    assert len(report['issues']) == 2


def test_orphan_receipt_detects_both_lost_boundary_records(tmp_path):
    (tmp_path / 'cost_ledger.jsonl').write_text('{"request_id":"lost"}\n')
    report = inspect(tmp_path)
    assert not report['request_evidence_complete']
    assert any('usage receipt has no request events' in issue for issue in report['issues'])
