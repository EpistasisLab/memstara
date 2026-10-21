"""Real process death and local TCP loss; never touches deployment services or credentials."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from memstara.pipeline.checkpoint import Checkpoint, RecoveryBlocked, atomic_json


WORKER = r'''
import asyncio, sys, time
from pathlib import Path
from memstara.pipeline.checkpoint import Checkpoint, atomic_json
root, moment = Path(sys.argv[1]), sys.argv[2]
cp = Checkpoint(root)
atomic_json(root/'resume_arguments.json', {'run_tag': 'fault-fixture'})
async def effect():
    atomic_json(root/'effect.json', {'committed': True})
    return {'receipt': 'saved'}
if moment == 'safe':
    asyncio.run(cp.phase('data', effect))
    cp.advance(0, waves_run=1)
elif moment == 'call':
    cp.call_started('provider-request')
    asyncio.run(effect())
elif moment == 'phase':
    async def incomplete():
        await effect()
        atomic_json(root/'ready.json', {'ready': True})
        await asyncio.Future()
    asyncio.run(cp.phase('data', incomplete))
atomic_json(root/'ready.json', {'ready': True})
while True: time.sleep(1)
'''


def kill_at_ready(tmp_path, source, *args):
    """Parent sends SIGKILL only to its own isolated child after durable evidence exists."""
    with (tmp_path / 'child.log').open('w') as log:
        process = subprocess.Popen([sys.executable, '-u', '-c', source, str(tmp_path), *args],
                                   stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 20
            while not (tmp_path / 'ready.json').exists():
                assert process.poll() is None, (tmp_path / 'child.log').read_text()
                assert time.monotonic() < deadline, 'Child did not reach the injected crash boundary'
                time.sleep(.02)
            process.kill()
            assert process.wait(timeout=5) != 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.parametrize('moment', ['safe', 'call', 'phase'])
def test_sigkill_replays_no_committed_effect(tmp_path, moment):
    kill_at_ready(tmp_path, WORKER, moment)
    before = (tmp_path / 'effect.json').read_bytes()
    if moment == 'safe':
        checkpoint = Checkpoint(tmp_path, resume=True)

        async def forbidden():
            pytest.fail('Saved side effect must not execute twice')

        assert asyncio.run(checkpoint.phase('data', forbidden)) == {'receipt': 'saved'}
        assert checkpoint.state['next_wave'] == 1
    else:
        with pytest.raises(RecoveryBlocked):
            Checkpoint(tmp_path, resume=True)
    assert (tmp_path / 'effect.json').read_bytes() == before


def test_sigkill_during_final_scoring_preserves_finished_and_never_replays_uncertain(tmp_path, monkeypatch):
    from memstara import final_validation
    tasks = [{
        'task_id': i, 'trial': i - 1, 'status': 'done', 'y_column': 'Y',
        'columns_used': ['X'], 'subset_path': 'synthetic.csv',
        'evaluation': {'auc': .6, 'ml_configuration': {'effective': {'primary_model': 'xgboost'}}},
    } for i in (1, 2, 3)]
    atomic_json(tmp_path / 'tasks.json', tasks)
    source = r'''
import json, sys, time
from pathlib import Path
from memstara import final_validation
from memstara.pipeline.checkpoint import atomic_json
root = Path(sys.argv[1])
def score(task, *_):
    atomic_json(root/f"effect-{task['task_id']}.json", {'scored': task['task_id']})
    if task['task_id'] == 2:
        atomic_json(root/'ready.json', {'ready': True})
        while True: time.sleep(1)
    return {'status': 'completed', 'task_id': task['task_id']}
final_validation._evaluate_with_budget = score
final_validation.run(root, {}, json.loads((root/'tasks.json').read_text()))
'''
    kill_at_ready(tmp_path, source)
    before = json.loads((tmp_path / 'final_validation.json').read_text())
    assert [r['status'] for r in before['results']] == ['completed', 'in_progress', 'pending']
    calls = []

    def score(task, *_):
        calls.append(task['task_id'])
        return {'status': 'completed', 'task_id': task['task_id']}

    monkeypatch.setattr(final_validation, '_evaluate_with_budget', score)
    result = final_validation.run(tmp_path, {}, tasks)
    assert calls == [3]
    assert result['status'] == 'failed'
    assert [r['status'] for r in result['results']] == ['completed', 'interrupted', 'completed']
    assert result['results'][0] == before['results'][0]
    assert final_validation.run(tmp_path, {}, tasks) == result
    assert calls == [3]  # terminal failure is not permission to rescore


@pytest.mark.parametrize('disconnects', [1, 6])
def test_real_tcp_disconnects_have_bounded_request_retries_and_no_tool_replay(tmp_path, monkeypatch, disconnects):
    """The HTTP adapter is local; this is not an Azure or model-availability test."""
    from memstara.pipeline import llm
    from memstara.pipeline.diagnostics import call_context, call_loop
    from memstara.pipeline.failures import PipelineExecutionFailure

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.rfile.read(int(self.headers['Content-Length'])))
            if len(received) <= disconnects:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(llm, 'TRANSPORT_RETRY_DELAYS', (0, 0, 0, 0, 0))
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    context = call_context.set((str(tmp_path), 'fault-fixture', 'ml#1'))
    loop = call_loop.set(2)
    # Completed tool effects are deliberately outside the retried HTTP operation.
    effect = tmp_path / 'tool-effect.json'
    atomic_json(effect, {'writes': 1})
    before = effect.read_bytes()

    async def scenario():
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            async def invoke(_config, messages):
                response = await client.post(f'http://127.0.0.1:{server.server_port}', json=messages)
                response.raise_for_status()
                return response.text
            return await llm.PipelineLLMService()._request(
                invoke, SimpleNamespace(model='local-fault-fixture'), [{'role': 'user', 'content': 'synthetic'}])

    try:
        if disconnects == 6:
            with pytest.raises((httpx.RemoteProtocolError, PipelineExecutionFailure)):
                asyncio.run(scenario())
            assert (tmp_path / 'pipeline_failure.json').is_file()
        else:
            assert asyncio.run(scenario()) == '{}'
            assert not (tmp_path / 'pipeline_failure.json').exists()
        assert len(received) == (6 if disconnects == 6 else 2)
        assert len(set(received)) == 1
        assert effect.read_bytes() == before
        events = [json.loads(line) for line in (tmp_path / 'model_retries.jsonl').read_text().splitlines()]
        assert events[-1]['state'] == ('exhausted' if disconnects == 6 else 'recovered')
    finally:
        call_context.reset(context)
        call_loop.reset(loop)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
