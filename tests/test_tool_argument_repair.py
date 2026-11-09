"""A rejected tool-call turn must be repaired or fail, never look completed."""
import asyncio
import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

pytest.importorskip('motoro')
from memstara.pipeline.llm import PipelineLLMService, question_submission_instructions
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


QUESTION_TOOLS = [{'type': 'function', 'function': {
    'name': 'propose_questions', 'parameters': {
        'type': 'object', 'required': ['questions'], 'additionalProperties': False,
        'properties': {'questions': {'type': 'array', 'items': {
            'type': 'object', 'required': ['predictor_concepts', 'rationale'],
            'properties': {'predictor_concepts': {'type': 'array', 'items': {'type': 'string'}},
                           'rationale': {'type': 'string'}},
        }}},
    },
}}]


@pytest.mark.parametrize('bad_args,capped', [
    ({}, False),
    ({'questions': [{'predictor_concepts': ['measured feature'], 'rationale': 'Evidence'}],
      'rationale': 'Misplaced rationale'}, False),
    ({}, True),  # Production Loop 129: missing questions at the output ceiling.
])
def test_question_envelope_repair_validates_before_return(context, monkeypatch, bad_args, capped):
    from motoro.services.llm_service import _validate_tool_call_args

    service = PipelineLLMService()
    reason = 'propose_questions: tool_args_schema_invalid: ' + _validate_tool_call_args(
        'propose_questions', bad_args, QUESTION_TOOLS)
    good_args = {'questions': [{'predictor_concepts': ['measured feature'], 'rationale': 'Evidence'}]}
    valid_call = NS(name='propose_questions', arguments=good_args)
    valid = NS(record=NS(failure_reason=None, completion_tokens=100), tool_calls=[valid_call])
    observed = []

    async def once(config, messages, tools, principal_id):
        observed.append((config.max_tokens, copy.deepcopy(messages)))
        assert tools == QUESTION_TOOLS
        if len(observed) == 1:
            return NS(record=NS(failure_reason=reason, completion_tokens=4096 if capped else 50),
                      tool_calls=[]), reason
        assert _validate_tool_call_args('propose_questions', good_args, tools) is None
        return valid, None

    monkeypatch.setattr(service, '_complete_with_tools_once', once)
    history = [{'role': 'user', 'content': 'Generate a supported hypothesis.'}]
    original = copy.deepcopy(history)
    tools_before = copy.deepcopy(QUESTION_TOOLS)
    config = NS(model='claude-haiku-5-5', max_tokens=4096, fallback_models=[])
    result = asyncio.run(service.complete_with_tools(config, history, QUESTION_TOOLS))
    assert result is valid and result.tool_calls == [valid_call]
    assert len(observed) == 2
    assert [x[0] for x in observed] == [4096, 8192 if capped else 4096]
    assert history == original and QUESTION_TOOLS == tools_before and config.max_tokens == 4096
    assert 'INSIDE each proposal' in observed[0][1][-1]['content']
    assert 'INSIDE each proposal' in observed[1][1][-1]['content']
    # Repair never inserts a fabricated candidate or blank submission.
    assert all('tool_calls' not in m for _, messages in observed for m in messages)
    log = context / ('model_completion_repairs.jsonl' if capped else 'tool_argument_repairs.jsonl')
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert [e['state'] for e in events] == ['retry', 'recovered']
    assert events[-1]['scientific_acceptance'] == 'requires_tool_receipt'
    assert not (context / 'pipeline_failure.json').exists()


def test_submission_guidance_does_not_add_tools_or_leak_knowledge_to_other_roles():
    assert question_submission_instructions([]) == ''
    other = copy.deepcopy(QUESTION_TOOLS)
    other[0]['function']['name'] = 'freeze_hybrid_candidate'
    assert question_submission_instructions(other) == ''
    guidance = question_submission_instructions(QUESTION_TOOLS)
    assert 'okf_read' not in guidance and 'okf_search' not in guidance
    assert 'never substitute an empty list' in guidance
