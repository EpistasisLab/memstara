"""Incomplete model turns must never be mistaken for a completed handoff."""
import asyncio
import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

pytest.importorskip('motoro')
from memstara.pipeline.diagnostics import call_context
from memstara.pipeline.failures import PipelineExecutionFailure
from memstara.pipeline.llm import PipelineLLMService, record_response


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    token = call_context.set((str(tmp_path), 'test-run', 'interpret#1'))
    yield tmp_path
    call_context.reset(token)


def completion(tokens=10, text='', calls=None):
    return NS(record=NS(failure_reason=None, completion_tokens=tokens),
              text=text, tool_calls=calls or [])


def test_capped_turn_repaired_before_any_tool_dispatch(context, monkeypatch):
    service = PipelineLLMService()
    original = [{'role': 'tool', 'tool_call_id': 'claimed', 'content': '{"task_id": 1084}'}]
    history = copy.deepcopy(original)
    observed = []
    valid = completion(calls=[NS(name='submit_result')])
    async def once(config, messages, tools, principal_id):
        observed.append((config.max_tokens, copy.deepcopy(messages)))
        return (completion(4096, calls=[NS(name='partial_call')]), None) if len(observed) == 1 else (valid, None)
    monkeypatch.setattr(service, '_complete_with_tools_once', once)
    config = NS(model='claude-haiku-5-5', max_tokens=4096, fallback_models=[])
    assert asyncio.run(service.complete_with_tools(config, history, [])) is valid
    assert [x[0] for x in observed] == [4096, 8192]
    assert config.max_tokens == 4096 and history == original
    assert observed[1][1][0] == original[0]
    assert 'do not claim it again' in observed[1][1][-1]['content']


def test_empty_turn_is_bounded_and_latches_interpretation_failure(context, monkeypatch):
    service = PipelineLLMService()
    budgets = []
    async def once(config, *args):
        budgets.append(config.max_tokens)
        return completion(), None
    monkeypatch.setattr(service, '_complete_with_tools_once', once)
    config = NS(model='claude-haiku-5-5', max_tokens=4096, fallback_models=[])
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(service.complete_with_tools(config, [], []))
    assert budgets == [4096, 8192, 16384, 16384, 16384, 16384]
    failure = json.loads((context / 'pipeline_failure.json').read_text())
    assert failure['stage'] == 'interpret#1'
    assert failure['code'] == 'model_output_incomplete'


def test_empty_answer_after_successful_save_does_not_repeat_mutation(context, monkeypatch):
    service = PipelineLLMService()
    valid = completion()
    invoke = AsyncMock(return_value=(valid, None))
    monkeypatch.setattr(service, '_complete_with_tools_once', invoke)
    history = [
        {'role': 'assistant', 'tool_calls': [{'id': 'saved', 'function': {'name': 'submit_result'}}]},
        {'role': 'tool', 'tool_call_id': 'saved', 'content': '{"ok":true,"status":"done"}'},
    ]
    assert asyncio.run(service.complete_with_tools(
        NS(model='claude-haiku-5-5', max_tokens=4096, fallback_models=[]), history, [])) is valid
    invoke.assert_awaited_once()


def test_substantive_uncapped_response_is_preserved_for_existing_handoff(context, monkeypatch):
    service = PipelineLLMService()
    valid = completion(text='Assessment: measured results and limitations.')
    invoke = AsyncMock(return_value=(valid, None))
    monkeypatch.setattr(service, '_complete_with_tools_once', invoke)
    assert asyncio.run(service.complete_with_tools(
        NS(model='claude-haiku-5-5', max_tokens=4096, fallback_models=[]), [], [])) is valid
    invoke.assert_awaited_once()


def test_provider_termination_evidence_excludes_response_content(context):
    record_response((str(context), 'run', 'interpret#1'), NS(
        id='response-1', choices=[NS(finish_reason='length', message='private text')],
        usage=NS(completion_tokens=4096)), 4096)
    raw = (context / 'model_response_outcomes.jsonl').read_text()
    assert 'private text' not in raw
    assert json.loads(raw)['finish_reasons'] == ['length']
