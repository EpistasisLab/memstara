"""Exercise the provider boundary, scoped discovery, and fatal execution propagation."""
import asyncio
import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

pytest.importorskip('motoro')
from memstara.pipeline import board
from memstara.pipeline.core import tools_for, BOARD_TOOLS, QUESTION_TOOLS
from memstara.pipeline.failures import PipelineExecutionFailure, require_tools, stop_execution, visible_failure
from memstara.pipeline.llm import PipelineLLMService, provider_messages


def test_sampling_policy_uses_adapter_capabilities_and_preserves_input(monkeypatch):
    from litellm.llms.anthropic.common_utils import AnthropicModelInfo
    from memstara.pipeline.llm import request_scope, request_options
    monkeypatch.setattr(AnthropicModelInfo, '_supports_sampling_params', lambda model: False)
    original = dict(model='azure_ai/claude-haiku-5-5', temperature=.7, top_p=.9,
                    top_k=10, max_tokens=8192)
    with request_scope(original['model']):
        result = request_options(original)
    assert not {'temperature', 'top_p', 'top_k'} & result.keys()
    assert result['max_tokens'] == 8192
    assert original['temperature'] == .7
    monkeypatch.setattr(AnthropicModelInfo, '_supports_sampling_params', lambda model: True)
    with request_scope(original['model']):
        assert request_options(original)['temperature'] == .7
from memstara.pipeline.recovery import ensure_artifact
from motoro.mcp.registry import MCPServerRegistry, ServerEntry
from motoro.services.llm_service import LLMService


@pytest.mark.parametrize('model', ['qwen--qwen38-27b', 'openai/qwen--qwen36-27b'])
def test_qwen_normalizes_prefix_without_changing_history(model):
    messages = [{'role': 'system', 'content': s} for s in ['rules', 'skill', 'goal']]
    messages += [{'role': 'user', 'content': 'task'},
                 {'role': 'assistant', 'tool_calls': [{'id': 'x'}]},
                 {'role': 'tool', 'tool_call_id': 'x', 'content': 'result'}]
    before = copy.deepcopy(messages)
    normalized = provider_messages(messages, model)
    assert normalized == [{'role': 'system', 'content': 'rules\n\nskill\n\ngoal'}, *messages[3:]]
    assert messages == before
    assert provider_messages(messages, 'claude-sonnet-5') == before
    assert provider_messages(normalized, model) == normalized


def test_content_blocks_and_images_remain_in_order():
    messages = [{'role': 'system', 'content': 'rules'},
                {'role': 'system', 'content': [{'type': 'text', 'text': 'skill'}]},
                {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'test'}}]}]
    assert provider_messages(messages, 'qwen-test') == [
        {'role': 'system', 'content': [{'type': 'text', 'text': 'rules'}, {'type': 'text', 'text': 'skill'}]},
        messages[2]]


@pytest.mark.parametrize('method', ['complete', 'complete_text', 'complete_with_tools'])
def test_actual_service_entrypoints_use_adapter(method, monkeypatch):
    invoke = AsyncMock(return_value='response')
    monkeypatch.setattr(LLMService, method, invoke)
    service = PipelineLLMService()
    messages = [{'role': 'system', 'content': 'a'}, {'role': 'system', 'content': 'b'},
                {'role': 'user', 'content': 'c'}]
    args = [NS(model='qwen--qwen38-27b'), messages]
    if method == 'complete_with_tools':
        args.append([{'name': 'test'}])
    assert asyncio.run(getattr(service, method)(*args)) == 'response'
    assert [m['role'] for m in invoke.call_args.args[1]] == ['system', 'user']
    assert len(messages) == 3


def test_current_registry_scopes_local_tools_but_excludes_foreign_owners():
    registry = MCPServerRegistry()
    for owner, name in [(None, 'allowed'), (uuid4(), 'foreign')]:
        key = uuid4()
        tool = NS(name=name, description='', input_schema={}, title=None, output_schema=None, annotations=None)
        client = NS(connected=True, tools=[tool], instructions='')
        registry._servers[key] = ServerEntry(
            server_id=key, name='memstara-data', owner_id=owner, is_system=False,
            transport='stdio', command=None, url=None, config_revision=0, client=client,
        )
    assert registry.get_all_tools() == []  # Reproduces the old unscoped lookup failure.
    assert [t['tool_name'] for t in tools_for(registry, {'memstara-data'})] == ['allowed']
    assert tools_for(registry, {'memstara-data'}, only={'foreign'}) == []


def test_preflight_refuses_even_one_missing_tool(tmp_path):
    required = {**BOARD_TOOLS, 'question': QUESTION_TOOLS}
    available = {stage: [{'tool_name': t} for t in names] for stage, names in required.items()}
    require_tools(available, required, tmp_path)
    available['question'] = [t for t in available['question'] if t['tool_name'] != 'propose_questions']
    with pytest.raises(PipelineExecutionFailure, match='propose_questions'):
        require_tools(available, required, tmp_path)
    assert visible_failure(tmp_path)['code'] == 'missing_tools'


@pytest.fixture
def isolated_board(tmp_path, monkeypatch):
    monkeypatch.setattr('memstara.stage_models.deployment_profiles', lambda: {})
    trace = tmp_path / 'trace'
    trace.mkdir()
    monkeypatch.setattr(board, '_TRACE_DIR', trace)
    monkeypatch.setattr(board, '_CALLS', [])
    monkeypatch.setattr(board, '_EXECUTION_GATE', None)
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    monkeypatch.setattr(board, 'create_run', AsyncMock(return_value=NS(id=uuid4(), owner_id=None)))
    monkeypatch.setattr(board, 'execute_run', AsyncMock(return_value=NS(
        status='failed', error='BadRequestError: System message must be at the beginning. secret-key', output='')))
    return tmp_path


def test_failure_is_durable_and_blocks_every_later_role(isolated_board):
    for stage in ['question0-1', 'hypothesis', 'data', 'ml', 'interpreter', 'report']:
        with pytest.raises(PipelineExecutionFailure):
            asyncio.run(board.call_agent('agent', 'synthetic', tools=[], registry=None, stage=stage))
    assert board.create_run.await_count == board.execute_run.await_count == 1
    record = visible_failure(isolated_board)
    assert record['code'] == 'model_message_format'
    assert record['stage'] == 'question0-1'
    assert 'secret-key' not in json.dumps(record)
    assert json.loads((isolated_board / 'execution.json').read_text())['calls'][0]['status'] == 'failed'


def test_question_failure_does_not_trigger_retry(isolated_board, monkeypatch):
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': []}))
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(board.questions_for_wave(
            None, {'hypothesis': 'agent'}, {'question': []}, run_tag='test', wave=0, want=1))
    assert board.execute_run.await_count == 1


def test_report_failure_does_not_trigger_retry(isolated_board):
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(board.call_report('agent', 'synthetic', tools=[], registry=None, stage='report'))
    assert board.execute_run.await_count == 1


def test_run_creation_failure_also_stops_question_retries(isolated_board, monkeypatch):
    board.create_run.side_effect = ConnectionError('private detail')
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': []}))
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(board.questions_for_wave(
            None, {'hypothesis': 'agent'}, {'question': []}, run_tag='test', wave=0, want=1))
    assert board.create_run.await_count == 1
    assert board.execute_run.await_count == 0
    assert visible_failure(isolated_board)['code'] == 'model_connection'


def test_artifact_recovery_does_not_swallow_execution_failure():
    invoke = AsyncMock(side_effect=PipelineExecutionFailure('stop'))
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(ensure_artifact(invoke, AsyncMock(return_value=False)))
    assert invoke.await_count == 1


def test_legacy_failure_is_read_only_and_new_execution_is_clear(tmp_path):
    old = tmp_path / 'old'
    old.mkdir()
    path = old / 'execution.json'
    path.write_text(json.dumps({'calls': [{'status': 'failed', 'stage': 'question0-1',
                                         'error': 'System message must be at the beginning. private'}]}))
    original = path.read_bytes()
    assert visible_failure(old)['code'] == 'model_message_format'
    assert 'private' not in visible_failure(old)['message']
    assert 'stopped' not in visible_failure(old)['message']
    assert path.read_bytes() == original
    assert list(old.iterdir()) == [path]
    assert visible_failure(tmp_path / 'new') is None


def test_first_failure_is_not_overwritten(tmp_path):
    for stage, error in [('question', 'System message must be at the beginning.'), ('report', TimeoutError())]:
        with pytest.raises(PipelineExecutionFailure):
            stop_execution(tmp_path, stage, 1, error)
    assert visible_failure(tmp_path)['stage'] == 'question'


def test_question_failure_cancels_other_writer(monkeypatch):
    async def scenario():
        ready, cancelled = asyncio.Event(), asyncio.Event()
        async def call(agent, *args, **kwargs):
            if agent == 'bad':
                await ready.wait()
                raise PipelineExecutionFailure('request rejected')
            ready.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        monkeypatch.setattr(board, 'call_agent', call)
        monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
        monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': []}))
        with pytest.raises(PipelineExecutionFailure):
            await asyncio.wait_for(board.questions_for_wave(
                None, {'hypothesis': 'bad', 'hypothesis#2': 'slow'}, {'question': []},
                run_tag='test', wave=0, want=2), timeout=1)
        assert cancelled.is_set()
    asyncio.run(scenario())


def test_three_loop_driver_stops_on_first_rejection_and_cleans_up(isolated_board, monkeypatch):
    from memstara.pipeline import snapshot
    from memstara import blackboard
    from memstara.pipeline.core import board_workers
    agents = {key: key for key in board_workers({})}
    registry = NS(disconnect_all=AsyncMock())
    from memstara.pipeline import preparation
    monkeypatch.setattr(preparation, 'configure', lambda _: None)
    settings = NS()
    settings.model_copy = lambda **kw: settings
    monkeypatch.setattr(preparation, 'Settings', lambda: settings)
    monkeypatch.setattr(snapshot, 'freeze', lambda *args: None)
    monkeypatch.setattr(blackboard, 'create', AsyncMock())
    monkeypatch.setattr(board, 'setup_logging', lambda **kwargs: None)
    monkeypatch.setattr(board, 'provision_board_agents', AsyncMock(return_value=agents))
    monkeypatch.setattr(board, 'setup_tools', AsyncMock(return_value=registry))
    monkeypatch.setattr(board, 'tools_for', lambda registry, servers, only: [{'tool_name': name} for name in only])
    monkeypatch.setattr(board, 'reclaim_stalled', AsyncMock(return_value=0))
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': []}))
    traces = AsyncMock(return_value=0)
    monkeypatch.setattr(board, 'write_traces', traces)
    args = NS(pipeline_id='', waves=3, continuous=False, trials=1, hypothesis_agents=1,
              interpret_agents=1, report_only=False, resume=False, verbose=False,
              run_tag='synthetic-driver', y_column='Y', skill='', provider='openai', model='qwen-test',
              no_curator=False, stale_after=600)
    for stage in BOARD_TOOLS:
        setattr(args, f'playbook_{stage}', '')
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(board.run(args, isolated_board))
    assert board.execute_run.await_count == 1
    assert [call['stage'] for call in board._CALLS] == ['question0-1']
    registry.disconnect_all.assert_awaited_once()
    traces.assert_awaited_once()
    assert visible_failure(isolated_board)['loop'] == 1


def test_fatal_preflight_cannot_be_advertised_as_resumable(tmp_path):
    from memstara.pipeline.checkpoint import Checkpoint, recovery_status, RecoveryBlocked
    Checkpoint(tmp_path)
    (tmp_path / 'resume_arguments.json').write_text(json.dumps({'run_tag': 'test'}))
    with pytest.raises(PipelineExecutionFailure):
        require_tools({}, {'question': {'propose_questions'}}, tmp_path)
    status = recovery_status(tmp_path)
    assert not status['recoverable']
    assert 'Correct the cause' in status['recovery_blocked']
    with pytest.raises(RecoveryBlocked):
        Checkpoint(tmp_path, resume=True)


def test_long_context_deadlines_and_request_scope_are_consistent():
    from memstara.pipeline.runtime import runtime_timeouts
    from memstara.pipeline.llm import request_scope, request_options
    from memstara.pipeline.diagnostics import call_context
    limits = runtime_timeouts('qwen--qwen38-27b')
    assert 120 < limits['llm_call_timeout_seconds'] < limits['hook_timeout_seconds'] < limits['agent_timeout_seconds']
    original = {'model': 'openai/qwen--qwen38-27b', 'max_tokens': 4096, 'extra_body': {'keep': True}}
    with request_scope('qwen--qwen38-27b'):
        prepared = request_options(original)
        assert prepared['num_retries'] == prepared['max_retries'] == 0
        assert prepared['timeout'].read == limits['llm_call_timeout_seconds']
        assert prepared['timeout'].connect == 15
        assert prepared['extra_body'] == {'keep': True, 'reasoning_effort': 'none'}
        assert prepared['max_tokens'] == 8192
    assert request_options(original) is original
    assert original['max_tokens'] == 4096
    token = call_context.set(('/synthetic', 'id', 'report'))
    try:
        with request_scope('qwen--qwen38-27b'):
            assert request_options(original)['extra_body']['reasoning_effort'] == 'low'
    finally:
        call_context.reset(token)


def test_timeout_is_not_retried_inside_motoro_service(monkeypatch):
    monkeypatch.setattr('memstara.pipeline.llm.asyncio.sleep', AsyncMock())
    from motoro.schemas.agent import ModelConfig, LLMProvider
    from motoro.services import llm_service
    invoke = AsyncMock(side_effect=TimeoutError())
    monkeypatch.setattr(llm_service.litellm, 'acompletion', invoke)
    monkeypatch.setattr(llm_service.litellm, 'get_supported_openai_params', lambda **kw: [])
    monkeypatch.setattr(llm_service, '_resolve_connection_for_principal', AsyncMock(return_value={
        'model': 'openai/qwen-test', 'api_key': 'synthetic', 'api_base': 'https://example.invalid'}))
    monkeypatch.setattr(llm_service, 'settings', NS(llm_call_timeout_seconds=1800))
    config = ModelConfig(provider=LLMProvider('openai'), model='qwen-test')
    with pytest.raises(TimeoutError):
        asyncio.run(PipelineLLMService().complete_with_tools(config, [{'role': 'user', 'content': 'test'}], []))
    assert invoke.await_count == 6  # One outer retry owner; no multiplied SDK retries.


def test_provider_failure_preserves_loop_before_engine_wraps_it(tmp_path, monkeypatch):
    monkeypatch.setattr('memstara.pipeline.llm.asyncio.sleep', AsyncMock())
    from memstara.pipeline.diagnostics import call_context, call_loop
    invoke = AsyncMock(side_effect=ConnectionResetError('private connection detail'))
    context = call_context.set((str(tmp_path), 'synthetic-call', 'ml#1'))
    loop = call_loop.set(4)
    try:
        with pytest.raises(PipelineExecutionFailure):
            asyncio.run(PipelineLLMService()._request(invoke, NS(model='qwen-test'), []))
    finally:
        call_context.reset(context)
        call_loop.reset(loop)
    record = visible_failure(tmp_path)
    assert record['loop'] == 4
    assert record['stage'] == 'ml#1'
    assert record['code'] == 'model_connection'
    assert invoke.await_count == 6


def test_raised_agent_failure_saves_final_duration(isolated_board):
    board.execute_run.side_effect = ConnectionResetError('synthetic')
    with pytest.raises(PipelineExecutionFailure):
        asyncio.run(board.call_agent('agent', 'synthetic', tools=[], registry=None, stage='ml#1'))
    call = json.loads((isolated_board / 'execution.json').read_text())['calls'][0]
    assert call['status'] == 'failed'
    assert call['duration_seconds'] >= 0
