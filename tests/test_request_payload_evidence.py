"""Durable private payloads, integrity checks and credential redaction."""
import asyncio
import json
import stat
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline.diagnostics import call_context, request_id
from memstara.pipeline.request_evidence import redact, save
from memstara.trace.diagnose import inspect


def test_redaction_handles_nested_fields_echoed_json_and_known_values(monkeypatch):
    monkeypatch.setenv('SYNTHETIC_API_KEY', 'private-test-api-key')
    original = {'messages': [{'content': 'private-test-api-key Bearer private-token'}],
                'tool_result': '{"api_key":"unknown-key","answer":"Preserved"}',
                'nested': {'password': 'unknown-password'},
                'dsn': 'postgres://user:private-pass@host/db', 'prediction': .7}
    value = redact(original)
    raw = json.dumps(value)
    assert not any(secret in raw for secret in ('private-test-api-key', 'private-token',
                                              'unknown-key', 'unknown-password', 'private-pass'))
    assert 'Preserved' in raw and value['prediction'] == .7
    assert original['nested']['password'] == 'unknown-password'


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    token = call_context.set((tmp_path, 'agent', 'hypothesis0'))
    try:
        yield tmp_path
    finally:
        call_context.reset(token)


def execute(method):
    pytest.importorskip('motoro')
    from memstara.pipeline.llm import PipelineLLMService
    return PipelineLLMService()._request(method, NS(model='claude-haiku-test'),
                                        [{'role': 'user', 'content': 'Synthetic research question'}])


def test_inputs_are_on_disk_before_model_call_and_outputs_are_correlated(context):
    async def invoke(*args, **kwargs):
        files = list((context / 'model_io').glob('*.input.json'))
        assert len(files) == 1
        assert json.loads(files[0].read_text())['payload']['messages'][0]['content'] == 'Synthetic research question'
        assert not list((context / 'model_io').glob('*.output.json'))
        return 'Synthetic hypothesis'
    assert asyncio.run(execute(invoke)) == 'Synthetic hypothesis'
    report = inspect(context)
    assert report['service_io_evidence_complete']
    assert {p['kind'] for p in report['payloads']} == {'input', 'output'}
    assert 'Synthetic hypothesis' not in json.dumps(report)
    for file in (context / 'model_io').glob('*.json'):
        assert stat.S_IMODE(file.stat().st_mode) == 0o600


def test_model_schema_tool_arguments_and_returned_records_are_preserved(context):
    from motoro.schemas.llm import ToolCompletion, LLMCallRecord, LLMToolCall
    record = LLMCallRecord(model='synthetic', prompt_tokens=1, completion_tokens=1,
                           latency_ms=1, cost_estimate=0)
    response = ToolCompletion(text='Synthetic rationale', record=record,
                             tool_calls=[LLMToolCall(id='call-1', name='synthetic_tool', arguments={'column': 'X'})])
    asyncio.run(execute(AsyncMock(return_value=response)))
    report = inspect(context)
    assert report['service_io_evidence_complete']
    file = context / next(p['path'] for p in report['payloads'] if p['kind'] == 'output')
    assert json.loads(file.read_text())['payload']['tool_calls'][0]['arguments'] == {'column': 'X'}


@pytest.mark.parametrize('damage', ['remove', 'change'])
def test_missing_or_modified_output_cannot_appear_complete(context, damage):
    asyncio.run(execute(AsyncMock(return_value='done')))
    path = next((context / 'model_io').glob('*.output.json'))
    if damage == 'remove':
        path.unlink()
    else:
        path.write_text('{"payload":"modified"}')
    report = inspect(context)
    assert report['request_evidence_complete']
    assert not report['service_io_evidence_complete']
    assert any('output payload' in issue for issue in report['payload_issues'])


def test_storage_failure_does_not_replay_or_change_provider_result(context, caplog):
    (context / 'model_io').write_text('Not a directory')
    method = AsyncMock(return_value='done')
    assert asyncio.run(execute(method)) == 'done'
    method.assert_awaited_once()
    assert not inspect(context)['service_io_evidence_complete']
    assert 'input/output audit is incomplete' in caplog.text


def test_failure_packet_keeps_type_but_not_exception_body(context):
    from memstara.pipeline.failures import PipelineExecutionFailure
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(execute(AsyncMock(side_effect=ValueError('private-error-body'))))
    report = inspect(context)
    assert not report['service_io_evidence_complete']
    path = context / next(p['path'] for p in report['payloads'] if p['kind'] == 'failure')
    assert 'private-error-body' not in path.read_text()
    assert json.loads(path.read_text())['payload']['error_types'] == ['ValueError']


def test_unsupported_response_is_unavailable_rather_than_silently_truncated(context):
    assert asyncio.run(execute(AsyncMock(return_value=object()))) is not None
    assert not inspect(context)['service_io_evidence_complete']


def test_path_traversal_reference_is_rejected_without_reading_other_files(context):
    asyncio.run(execute(AsyncMock(return_value='done')))
    path = context / 'request_events.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[-1]['output_evidence']['path'] = '../../other.json'
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    assert not inspect(context)['service_io_evidence_complete']


def test_invalid_request_identity_does_not_write_outside_root(context):
    token = request_id.set('../../escape')
    try:
        assert save((context, 'run', 'ml'), 'input', {'content': 'synthetic'}) is None
        assert not (context / 'model_io').exists()
    finally:
        request_id.reset(token)
