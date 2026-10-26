"""Paid request-boundary pause/resume; not a process-loss recovery test."""
import asyncio
import json
from uuid import uuid4

import pytest

pytestmark = pytest.mark.live


def test_real_haiku_request_pause_resume(monkeypatch):
    from memstara.env import load_env
    load_env()
    from memstara.config import Settings
    from motoro import configure
    from memstara.pipeline.runtime import runtime_timeouts
    configure(Settings(**runtime_timeouts('claude-haiku-5-5')))
    from memstara.paths import output_dir
    from memstara.stage_models import deployment_profiles, for_stage
    from memstara.pipeline.diagnostics import call_context
    from memstara.pipeline.exploration import ExecutionGate
    from memstara.pipeline.llm import PipelineLLMService
    from motoro.schemas.agent import ModelConfig
    profiles = deployment_profiles()
    assert all(p['model'] == 'claude-haiku-5-5' for p in profiles.values())
    snapshot = {'pause_policy': 'fresh_model_request_v1', 'stage_models': profiles}
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: snapshot)
    root = output_dir() / 'verification' / ('haiku_pause_' + uuid4().hex[:12])
    root.mkdir(parents=True)
    (root/'config.json').write_text(json.dumps(snapshot, indent=2))
    print(f'PAID PAUSE CHECK: {root}', flush=True)
    model = ModelConfig(**{**for_stage(profiles, 'data'), 'max_tokens': 128})

    async def scenario():
        gate = ExecutionGate(root)
        token = call_context.set((str(root), str(uuid4()), 'data#1'))
        task = None
        try:
            async def operation():
                return await PipelineLLMService().complete_text(model, [
                    {'role':'user', 'content':'Reply with exactly: READY'}])
            task = asyncio.create_task(gate.call(operation))
            async with asyncio.timeout(30):
                while not (root/'request_events.jsonl').exists():
                    await asyncio.sleep(.02)
                await asyncio.sleep(.2)
                assert not task.done(), 'Response finished before interruption; no pause evidence'
                (root/'pause.request').touch()
                while not gate.paused_calls:
                    await asyncio.sleep(.02)
            before = (root/'request_events.jsonl').read_bytes()
            await asyncio.sleep(.5)
            assert before == (root/'request_events.jsonl').read_bytes()
            assert json.loads((root/'execution_control.json').read_text())['state'] == 'paused'
            (root/'pause.request').unlink()
            result = await asyncio.wait_for(task, 180)
            assert result[0].strip(), 'No real model response after resume'
        finally:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            call_context.reset(token)
    try:
        asyncio.run(scenario())
    except Exception as exc:
        (root/'acceptance.json').write_text(json.dumps({
            'status': 'failed', 'scope': 'live provider request pause/resume only',
            'error_type': type(exc).__name__, 'provider_outcome': 'unknown',
            'process_loss_recovery_tested': False}, indent=2))
        raise
    events = [json.loads(x) for x in (root/'request_events.jsonl').read_text().splitlines()]
    cancelled = [x for x in events if x.get('reason') == 'user_pause']
    completed = [x for x in events if x.get('state') == 'completed']
    assert len(cancelled) == len(completed) == 1
    assert cancelled[0]['request_id'] != completed[0]['request_id']
    inputs = [json.loads(p.read_text())['payload'] for p in (root/'model_io').glob('*.input.json')]
    assert len(inputs) >= 2 and all(value == inputs[0] for value in inputs)
    ledger = [json.loads(x) for x in (root/'cost_ledger.jsonl').read_text().splitlines()]
    assert ledger[0]['usd'] is None
    assert any((x.get('response_model') or '').split('/')[-1] == 'claude-haiku-5-5' for x in ledger)
    (root/'acceptance.json').write_text(json.dumps({
        'status':'passed', 'scope':'live provider request pause/resume only',
        'identical_inputs':True, 'fresh_request_id':True, 'interrupted_cost':'unknown',
        'process_loss_recovery_tested':False}, indent=2))
