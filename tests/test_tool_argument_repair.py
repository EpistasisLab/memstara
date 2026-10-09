"""A rejected tool-call turn must be repaired or fail, never look completed."""
import asyncio
import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

pytest.importorskip('motoro')
from memstara.pipeline.llm import PipelineLLMService
from memstara.pipeline.diagnostics import call_context
from memstara.pipeline.failures import PipelineExecutionFailure


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    token = call_context.set((str(tmp_path), 'test-run', 'question0-1'))
    yield tmp_path
    call_context.reset(token)


def completion(reason=None):
    return NS(record=NS(failure_reason=reason), tool_calls=[])


def test_schema_repair_preserves_history_and_returns_only_valid_turn(context, monkeypatch):
    service = PipelineLLMService()
    reason = "okf_search: tool_args_schema_invalid: filters requires an object"
    invalid, valid = completion(reason), completion()
    calls = []
    async def once(config, messages, tools, principal_id):
        calls.append(copy.deepcopy(messages))
        return (invalid, reason) if len(calls) == 1 else (valid, None)
    monkeypatch.setattr(service, '_complete_with_tools_once', once)
    history = [{'role': 'user', 'content': 'Generate one question.'}]
    original = copy.deepcopy(history)
    result = asyncio.run(service.complete_with_tools(
        NS(model='qwen-test', fallback_models=[]), history, []))
    assert result is valid
    assert len(calls) == 2
    assert history == original
    assert calls[0] == original
    assert 'JSON objects' in calls[1][-1]['content']
    assert reason in calls[1][-1]['content']
    assert not (context / 'pipeline_failure.json').exists()


def test_exhausted_schema_repairs_latch_failure_instead_of_returning_prose(context, monkeypatch):
    service = PipelineLLMService()
    reason = 'okf_search: tool_args_schema_invalid: private argument contents'
    invoke = AsyncMock(return_value=(completion(reason), reason))
    monkeypatch.setattr(service, '_complete_with_tools_once', invoke)
    config = NS(model='qwen-test', fallback_models=[])
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(service.complete_with_tools(config, [], []))
    assert invoke.await_count == 6
    failure = json.loads((context / 'pipeline_failure.json').read_text())
    assert failure['code'] == 'tool_argument_validation'
    assert failure['stage'] == 'question0-1'
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(service.complete_with_tools(config, [], []))
    assert invoke.await_count == 6
    events = (context / 'tool_argument_repairs.jsonl').read_text()
    assert 'private argument' not in events
    assert json.loads(events.splitlines()[-1])['state'] == 'exhausted'


def test_json_parse_failure_uses_same_repair_path(context, monkeypatch):
    service = PipelineLLMService()
    reason = 'okf_search: tool_args_parse_error: malformed JSON'
    valid = completion()
    invoke = AsyncMock(side_effect=[(completion(reason), reason), (valid, None)])
    monkeypatch.setattr(service, '_complete_with_tools_once', invoke)
    assert asyncio.run(service.complete_with_tools(
        NS(model='qwen-test', fallback_models=[]), [], [])) is valid
    assert invoke.await_count == 2


def test_nonvalidation_completion_failure_is_not_silently_accepted(context, monkeypatch):
    service = PipelineLLMService()
    invoke = AsyncMock(return_value=(completion('unrecognized failure'), None))
    monkeypatch.setattr(service, '_complete_with_tools_once', invoke)
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(service.complete_with_tools(NS(model='qwen-test', fallback_models=[]), [], []))
    invoke.assert_awaited_once()


def test_object_string_mismatch_reproduces_in_installed_motoro_validator():
    from motoro.services.llm_service import _validate_tool_call_args
    tools = [{'type': 'function', 'function': {'name': 'okf_search', 'parameters': {
        'type': 'object', 'properties': {'filters': {'anyOf': [
            {'type': 'object', 'properties': {'mechanism_family': {'enum': ['comorbidity']}},
             'additionalProperties': False}, {'type': 'null'}]}},
    }}}]
    valid = {'filters': {'mechanism_family': 'comorbidity'}}
    assert _validate_tool_call_args('okf_search', valid, tools) is None
    assert _validate_tool_call_args('okf_search', {'filters': json.dumps(valid['filters'])}, tools)
    assert _validate_tool_call_args('okf_search', {'filters': {'terminus_kind': 'invented'}}, tools)


def test_fifth_schema_retry_succeeds_without_replaying_prior_tool_history(context, monkeypatch):
    service = PipelineLLMService()
    reason = 'okf_search: tool_args_schema_invalid: filters requires an object'
    valid = completion()
    histories = []
    async def once(config, messages, tools, principal_id):
        histories.append(copy.deepcopy(messages))
        return (completion(reason), reason) if len(histories) < 6 else (valid, None)
    monkeypatch.setattr(service, '_complete_with_tools_once', once)
    messages = [
        {'role': 'assistant', 'tool_calls': [{'id': 'already-done', 'type': 'function',
         'function': {'name': 'read_question_catalog', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'already-done', 'content': 'Saved result'},
    ]
    original = copy.deepcopy(messages)
    assert asyncio.run(service.complete_with_tools(
        NS(model='qwen-test', fallback_models=[]), messages, [])) is valid
    assert len(histories) == 6 and messages == original
    for index, history in enumerate(histories):
        assert history[:2] == original
        assert len(history) == 2 + index * 2
        assert sum(row.get('role') == 'tool' for row in history) == 1
    assert not (context / 'pipeline_failure.json').exists()


def test_another_stage_failure_prevents_schema_retry(context, monkeypatch):
    from memstara.pipeline.failures import stop_execution
    service = PipelineLLMService()
    reason = 'okf_search: tool_args_schema_invalid: filters requires an object'
    async def once(*args):
        try:
            stop_execution(context, 'data', 1, RuntimeError('Synthetic failure'))
        except PipelineExecutionFailure:
            pass
        return completion(reason), reason
    invoke = AsyncMock(side_effect=once)
    monkeypatch.setattr(service, '_complete_with_tools_once', invoke)
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(service.complete_with_tools(NS(model='qwen-test', fallback_models=[]), [], []))
    invoke.assert_awaited_once()
    assert json.loads((context / 'pipeline_failure.json').read_text())['stage'] == 'data'
