"""Restart only a uniquely named synthetic container; no app volumes, credentials or ports."""
import json
from pathlib import Path
import subprocess
import time
import uuid

import pytest

pytestmark = pytest.mark.docker

WORKER = '''
import asyncio, json, time
from pathlib import Path
from memstara.pipeline.checkpoint import Checkpoint, atomic_json
root = Path('/evidence')
cp = Checkpoint(root, resume=(root/'checkpoint.json').exists())
async def effect():
    with (root/'effects').open('a') as stream:
        stream.write('once\\n')
    return {'saved': True}
assert asyncio.run(cp.phase('data', effect)) == {'saved': True}
count = json.loads((root/'starts.json').read_text())['count'] if (root/'starts.json').exists() else 0
atomic_json(root/'starts.json', {'count': count + 1})
while True: time.sleep(1)
'''


def test_container_kill_restart_reuses_durable_phase_without_repeating_effect(tmp_path):
    def docker(*args, timeout=30):
        return subprocess.run(['docker', *args], check=True, text=True, capture_output=True, timeout=timeout)

    # Missing Docker/image is a failure, never a skip or an implicit registry download.
    docker('info', '--format', '{{.ServerVersion}}')
    docker('image', 'inspect', 'python:3.12-slim')
    source = Path(__file__).resolve().parents[2] / 'src'
    worker = tmp_path / 'worker.py'
    worker.write_text(WORKER)
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    name = 'memstara-fault-test-' + uuid.uuid4().hex[:12]
    created = False

    def wait_for_count(expected):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            path = evidence / 'starts.json'
            if path.exists() and json.loads(path.read_text())['count'] == expected:
                return
            state = docker('inspect', '--format', '{{.State.Running}}', name).stdout.strip()
            assert state == 'true', docker('logs', name).stdout
            time.sleep(.1)
        raise AssertionError('Container did not acknowledge restart')

    try:
        docker('create', '--name', name, '--network', 'none', '--memory', '256m', '--cpus', '1',
               '--env', 'PYTHONPATH=/source', '--env', 'MEMSTARA_CONFIG_MODE=environment',
               '--mount', f'type=bind,src={source},dst=/source,readonly',
               '--mount', f'type=bind,src={worker},dst=/worker.py,readonly',
               '--mount', f'type=bind,src={evidence},dst=/evidence',
               'python:3.12-slim', 'python', '/worker.py')
        created = True
        docker('start', name)
        wait_for_count(1)
        before = (evidence / 'checkpoint.json').read_bytes()
        docker('kill', '--signal', 'KILL', name)
        docker('start', name)
        wait_for_count(2)
        assert (evidence / 'effects').read_text() == 'once\n'
        assert (evidence / 'checkpoint.json').read_bytes() == before
    finally:
        if created:
            docker('rm', '--force', name)
