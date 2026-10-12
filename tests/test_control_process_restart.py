"""Real HTTP/controller restart around an isolated synthetic execution gate."""

import json
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from memstara.control.recovery import identity, save_record


WORKER = '''
import asyncio, sys
from pathlib import Path
from memstara.pipeline.exploration import ExecutionGate
from memstara.pipeline.checkpoint import atomic_json
root = Path(sys.argv[1])
async def main():
    gate = ExecutionGate(root)
    counter = 0
    while True:
        await gate.wait()
        counter += 1
        atomic_json(root / 'ticks.json', {'count': counter})
        await asyncio.sleep(.05)
try:
    asyncio.run(main())
except KeyboardInterrupt:
    atomic_json(root / 'pipeline_status.json', {'status': 'completed'})
'''

CONTROLLER = '''
import sys
from pathlib import Path
from http.server import ThreadingHTTPServer
import memstara.paths as paths
# Isolate globals before importing the real control module; do not load .env.
paths.RUNS_DIR = Path(sys.argv[1])
from memstara.control.service import Handler
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
Path(sys.argv[2]).write_text(str(server.server_port))
server.serve_forever()
'''


def wait_for(probe, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value:
                return value
        except (OSError, ValueError, URLError):
            pass
        time.sleep(.05)
    raise AssertionError('Synthetic lifecycle condition did not become ready')


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_controller_restart_reattaches_pauses_resumes_and_ends_same_worker(tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    controllers = []
    with (tmp_path / 'worker.log').open('w') as log:
        worker = subprocess.Popen([sys.executable, '-u', '-c', WORKER, str(run)],
                                  stdout=log, stderr=log, start_new_session=True)
    try:
        wait_for(lambda: (run / 'ticks.json').exists())
        save_record({'run_tag': 'synthetic-restart', 'run_dir': str(run),
                     'pid': worker.pid, 'process_identity': identity(worker.pid),
                     'resumable': True})

        def start_controller(number):
            port_file = tmp_path / f'port-{number}'
            with (tmp_path / f'controller-{number}.log').open('w') as log:
                process = subprocess.Popen(
                    [sys.executable, '-u', '-c', CONTROLLER, str(tmp_path), str(port_file)],
                    stdout=log, stderr=log)
            controllers.append(process)
            wait_for(port_file.exists)
            return f'http://127.0.0.1:{port_file.read_text()}'

        def request(base, path='/control/runs', post=False):
            req = Request(base + path, data=b'{}' if post else None,
                          headers={'Content-Type': 'application/json'})
            with urlopen(req, timeout=5) as response:
                return json.load(response)

        first = start_controller(1)
        assert request(first)['running']['pid'] == worker.pid
        stop(controllers[0])
        assert worker.poll() is None
        second = start_controller(2)
        assert request(second)['running']['pid'] == worker.pid
        request(second, '/control/runs/synthetic-restart/pause', True)
        wait_for(lambda: request(second)['running']['execution_state'] == 'paused')
        # Allow a write already past the boundary to finish before comparing counts.
        time.sleep(.15)
        count = json.loads((run / 'ticks.json').read_text())['count']
        time.sleep(.35)
        assert json.loads((run / 'ticks.json').read_text())['count'] == count
        assert worker.poll() is None
        request(second, '/control/runs/synthetic-restart/resume', True)
        wait_for(lambda: json.loads((run / 'ticks.json').read_text())['count'] > count)
        assert request(second)['running']['pid'] == worker.pid
        request(second, '/control/runs/synthetic-restart/end', True)
        assert worker.wait(timeout=10) == 0
        status = wait_for(lambda: (result if (result := request(second))['running'] is None else None))
        assert status['finished'][0]['exit_code'] == 0
        stop(controllers[1])
        third = start_controller(3)
        final = request(third)
        assert final['running'] is None
        assert final['finished'][0]['run_tag'] == 'synthetic-restart'
        assert final['finished'][0]['exit_code'] == 0
    finally:
        for controller in controllers:
            stop(controller)
        stop(worker)
