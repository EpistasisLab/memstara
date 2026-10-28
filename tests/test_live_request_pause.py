"""Fault-injected live pause: preserve tools, cancel only provider requests."""
import asyncio
import json
import threading
from types import SimpleNamespace

import pytest

from memstara.pipeline.diagnostics import call_context
from memstara.pipeline.exploration import ExecutionGate
from memstara.pipeline.llm import PipelineLLMService
from memstara.pipeline.request_pause import invoke, VERSION


def enabled(monkeypatch):
    from memstara.pipeline.request_pause import RESTART_ML_VERSION
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {'pause_policy': RESTART_ML_VERSION})
    monkeypatch.setattr('memstara.stage_models.validate_call', lambda *args: None)


def test_resume_calls_model_again_without_replaying_completed_tools(tmp_path, monkeypatch):
    enabled(monkeypatch)
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        calls, effects = [], []
        async def provider(config, messages, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return 'response'
        gate = ExecutionGate(tmp_path)
        async def agent():
            effects.append('tool_completed')
            return await PipelineLLMService()._request(provider, SimpleNamespace(model='test'),
                [{'role': 'user', 'content': 'saved input and completed tool output'}])
        token = call_context.set((str(tmp_path), 'agent-test', 'ml#1'))
        try:
            task = asyncio.create_task(gate.call(agent))
            await asyncio.wait_for(started.wait(), 2)
            (tmp_path/'pause.request').touch()
            await asyncio.wait_for(cancelled.wait(), 2)
            for _ in range(50):
                if gate.paused_calls:
                    break
                await asyncio.sleep(.02)
            assert json.loads((tmp_path/'execution_control.json').read_text())['state'] == 'paused'
            assert len(calls) == 1 and not task.done()
            (tmp_path/'pause.request').unlink()
            assert await asyncio.wait_for(task, 2) == 'response'
            assert calls[0] == calls[1]
            assert effects == ['tool_completed']
        finally:
            call_context.reset(token)
    asyncio.run(scenario())
    events = [json.loads(x) for x in (tmp_path/'request_events.jsonl').read_text().splitlines()]
    starts = [x for x in events if x['state']=='started']
    assert len(starts) == 2 and starts[0]['request_id'] != starts[1]['request_id']
    assert any(x.get('reason')=='user_pause' for x in events)
    costs = [json.loads(x) for x in (tmp_path/'cost_ledger.jsonl').read_text().splitlines()]
    assert costs[0]['usd'] is None and 'interrupted' in costs[0]['reason']


def test_external_cancellation_never_triggers_new_provider_call(tmp_path, monkeypatch):
    enabled(monkeypatch)
    async def scenario():
        stopped = asyncio.Event()
        async def provider():
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        task = asyncio.create_task(invoke(provider, (str(tmp_path),'run','data')))
        await asyncio.sleep(.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError('Cancellation must propagate')
        assert stopped.is_set()
    asyncio.run(scenario())


def test_completed_response_is_retained_when_pause_already_exists(tmp_path, monkeypatch):
    enabled(monkeypatch)
    (tmp_path/'pause.request').touch()
    async def provider():
        return 'completed'
    assert asyncio.run(invoke(provider,(str(tmp_path),'run','data'))) == 'completed'


def test_pause_does_not_cancel_a_tool_or_fit(tmp_path):
    async def scenario():
        gate = ExecutionGate(tmp_path)
        started, finish = asyncio.Event(), asyncio.Event()
        async def tool():
            started.set()
            await finish.wait()
            return 'saved_fit'
        task = asyncio.create_task(gate.call(tool))
        await started.wait()
        (tmp_path/'pause.request').touch()
        gate.publish()
        assert json.loads((tmp_path/'execution_control.json').read_text())['state']=='stopping'
        assert not task.done()
        finish.set()
        await asyncio.sleep(.02)
        assert not task.done()  # Wait at the next boundary after saving the fit.
        (tmp_path/'pause.request').unlink()
        assert await asyncio.wait_for(task, 2) == 'saved_fit'
    asyncio.run(scenario())


def test_completed_response_waits_for_resume_before_next_tool(tmp_path, monkeypatch):
    enabled(monkeypatch)
    async def scenario():
        effects = []
        async def provider(config, messages, **kwargs):
            (tmp_path/'pause.request').touch()
            return 'tool instruction'
        gate = ExecutionGate(tmp_path)
        token = call_context.set((str(tmp_path), 'agent-test', 'ml#1'))
        async def agent():
            result = await PipelineLLMService()._request(provider, SimpleNamespace(model='test'), [])
            effects.append('next_tool')
            return result
        try:
            task = asyncio.create_task(gate.call(agent))
            async with asyncio.timeout(2):
                while not gate.paused_calls:
                    await asyncio.sleep(.01)
            assert not effects and not task.done()
            (tmp_path/'pause.request').unlink()
            assert await asyncio.wait_for(task, 2) == 'tool instruction'
            assert effects == ['next_tool']
        finally:
            call_context.reset(token)
    asyncio.run(scenario())
    events = [json.loads(x) for x in (tmp_path/'request_events.jsonl').read_text().splitlines()]
    assert sum(e['state']=='started' for e in events) == 1


@pytest.mark.parametrize('active,paused,expected', [(1,1,'paused'), (2,1,'stopping'),
                                                 (1,0,'stopping'), (0,0,'paused')])
def test_control_reports_waiting_model_calls_as_paused(tmp_path, monkeypatch, active, paused, expected):
    from memstara.control.service import _Runs
    manager = object.__new__(_Runs)
    manager._lock = threading.Lock()
    manager._live = {'run_dir': str(tmp_path), 'run_tag': 'test'}
    monkeypatch.setattr(manager, '_reap', lambda: None)
    monkeypatch.setattr('memstara.pipeline.run_ownership.infrastructure_status', lambda root: {})
    (tmp_path/'pause.request').touch()
    (tmp_path/'execution_control.json').write_text(json.dumps({
        'active_calls':active, 'paused_model_calls':paused, 'resumable':True}))
    assert manager.running()['execution_state'] == expected
