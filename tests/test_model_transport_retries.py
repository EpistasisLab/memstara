"""Retry only model transport requests, with one bounded retry owner."""
import asyncio
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

pytest.importorskip('motoro')
from memstara.pipeline.llm import PipelineLLMService
from memstara.pipeline.diagnostics import call_context, call_loop
from memstara.pipeline.failures import PipelineExecutionFailure, stop_execution
from memstara.pipeline.runtime import runtime_timeouts, TRANSPORT_RETRY_DELAYS


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    token = call_context.set((str(tmp_path), 'synthetic', 'ml#1'))
    loop = call_loop.set(4)
    monkeypatch.setattr('memstara.pipeline.llm.asyncio.sleep', AsyncMock())
    try:
        yield tmp_path
    finally:
        call_context.reset(token)
        call_loop.reset(loop)


def request(invoke):
    return PipelineLLMService()._request(invoke, NS(model='qwen-test'), [{'role':'user','content':'synthetic'}])


def test_fifth_retry_can_succeed_without_replaying_agent_tools(context):
    invoke = AsyncMock(side_effect=[ConnectionResetError('private')] * 5 + ['result'])
    assert asyncio.run(request(invoke)) == 'result'
    assert invoke.await_count == 6
    assert all(c.args[1] == [{'role':'user','content':'synthetic'}] for c in invoke.await_args_list)
    assert not (context / 'pipeline_failure.json').exists()
    events = [json.loads(line) for line in (context / 'model_retries.jsonl').read_text().splitlines()]
    assert [e['delay_seconds'] for e in events[:-1]] == list(TRANSPORT_RETRY_DELAYS)
    assert events[-1]['state'] == 'recovered'
    assert events[-1]['attempt'] == 6
    assert 'private' not in json.dumps(events)


def test_sixth_failure_latches_and_prevents_later_requests(context):
    invoke = AsyncMock(side_effect=ConnectionResetError('private'))
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(request(invoke))
    assert invoke.await_count == 6
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(request(invoke))
    assert invoke.await_count == 6
    failure = json.loads((context / 'pipeline_failure.json').read_text())
    assert failure['loop'] == 4
    assert failure['code'] == 'model_connection'


@pytest.mark.parametrize('error', [ValueError('bad schema'), RuntimeError('AuthenticationError'),
                                  RuntimeError('BadRequestError: 400')])
def test_nonconnection_errors_are_not_retried(context, error):
    invoke = AsyncMock(side_effect=error)
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(request(invoke))
    invoke.assert_awaited_once()


def test_cancellation_is_not_retried_or_marked_provider_failure(context):
    invoke = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(request(invoke))
    invoke.assert_awaited_once()
    assert not (context / 'pipeline_failure.json').exists()


def test_other_worker_failure_during_backoff_blocks_retry(context, monkeypatch):
    async def backoff(_):
        try:
            stop_execution(context, 'data#1', 4, ValueError('synthetic'))
        except PipelineExecutionFailure:
            pass
    monkeypatch.setattr('memstara.pipeline.llm.asyncio.sleep', backoff)
    invoke = AsyncMock(side_effect=ConnectionResetError())
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(request(invoke))
    invoke.assert_awaited_once()


def test_long_context_outer_deadline_allows_five_retries():
    limits = runtime_timeouts('qwen-test')
    assert limits['hook_timeout_seconds'] > 6 * limits['llm_call_timeout_seconds'] + sum(TRANSPORT_RETRY_DELAYS)
    assert limits['agent_timeout_seconds'] > limits['hook_timeout_seconds']


def test_user_pause_blocks_retry_until_resume(context, monkeypatch):
    marker = context / 'pause.request'
    invoke = AsyncMock(side_effect=[ConnectionResetError(), 'result'])
    waits = []
    async def wait(delay):
        waits.append(delay)
        assert invoke.await_count == 1
        if delay == 2:
            marker.touch()
        else:
            assert delay == .25
            marker.unlink()  # Simulated explicit user resume.
    monkeypatch.setattr('memstara.pipeline.llm.asyncio.sleep', wait)
    assert asyncio.run(request(invoke)) == 'result'
    assert waits == [2, .25]
    assert invoke.await_count == 2


@pytest.mark.parametrize('status', [500, 502, 503, 504, 529])
def test_server_error_recovers_on_fifth_retry_with_unchanged_tool_history(context, status):
    from test_failure_diagnostics import provider_error
    messages = [{'role': 'system', 'content': 'synthetic'},
                {'role': 'assistant', 'tool_calls': [{'id': 'done', 'type': 'function',
                 'function': {'name': 'read', 'arguments': '{}'}}]},
                {'role': 'tool', 'tool_call_id': 'done', 'content': 'already executed'}]
    original = json.loads(json.dumps(messages))
    attempts = []

    async def invoke(config, history):
        attempts.append(json.loads(json.dumps(history)))
        history.append({'role': 'user', 'content': 'SDK mutation'})
        if len(attempts) < 6:
            raise provider_error(status)
        return 'recovered'

    service = PipelineLLMService()
    assert asyncio.run(service._request(invoke, NS(model='qwen-test'), messages)) == 'recovered'
    assert attempts == [original] * 6
    assert messages == original
    assert not (context / 'pipeline_failure.json').exists()
    events = [json.loads(line) for line in (context / 'model_retries.jsonl').read_text().splitlines()]
    assert [e['http_status'] for e in events[:-1]] == [status] * 5
    assert events[-1]['state'] == 'recovered'


def test_persistent_server_error_stops_after_six_requests(context):
    from test_failure_diagnostics import provider_error
    invoke = AsyncMock(side_effect=provider_error(500))
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(request(invoke))
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(request(invoke))
    assert invoke.await_count == 6
    failure = json.loads((context / 'pipeline_failure.json').read_text())
    assert failure['code'] == 'model_server'
    assert failure['http_status'] == 500


def test_retry_cannot_switch_to_another_stage_model(context, monkeypatch):
    profiles = {'qwen': {'provider': 'openai', 'model': 'qwen-test'},
                'sonnet': {'provider': 'azure_foundry', 'model': 'claude-sonnet-test'}}
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {'stage_models': profiles})
    config = NS(provider='openai', model='qwen-test')
    async def mutate_then_fail(*args, **kwargs):
        config.model = 'claude-sonnet-test'
        raise ConnectionResetError('synthetic')
    invoke = AsyncMock(side_effect=mutate_then_fail)
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(PipelineLLMService()._request(invoke, config, []))
    assert invoke.await_count == 1
