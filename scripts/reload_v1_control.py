"""Refresh control while preserving any durably recorded, recoverable pipeline."""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from memstara.control.recovery import identity, recover

root = Path(__file__).resolve().parents[1]
url = 'http://127.0.0.1:8072/control/'
with urllib.request.urlopen(url + 'health', timeout=5) as response:
    health = json.load(response)
try:
    with urllib.request.urlopen(url + 'pipelines', timeout=30) as response:
        pipelines = json.load(response)['pipelines']
except urllib.error.HTTPError as error:
    if error.code != 404:
        raise
    pipelines = []
independent = []
for pipeline in pipelines:
    live = pipeline.get('running')
    if live:
        record, _ = recover(root / 'outputs' / 'runs', pipeline['id'])
        if not record or record['pid'] != live['pid']:
            raise SystemExit('Not restarted: independent pipeline recovery is unverified.')
        independent.append((pipeline['id'], live['pid'], identity(live['pid'])))
active = health.get('running')
if active:
    recovered, _ = recover(root / 'outputs' / 'runs')
    if not recovered or recovered['pid'] != active['pid'] or recovered['run_tag'] != active['run_tag']:
        raise SystemExit('Not restarted: the active pipeline has no verified recovery record.')
    active_identity = identity(active['pid'])
pids = subprocess.check_output(['lsof', '-t', '-iTCP:8072', '-sTCP:LISTEN'], text=True).split()
if len(pids) != 1:
    raise SystemExit('Expected exactly one control listener')
pid = int(pids[0])
command = subprocess.check_output(['ps', '-p', str(pid), '-o', 'command='], text=True)
if 'memstara.control' not in command:
    raise SystemExit('Listener is not the expected control module; no process changed')
os.kill(pid, signal.SIGTERM)
for _ in range(50):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        break
    time.sleep(.1)
with open('/tmp/memstara-v1-control.log', 'ab') as log:
    child = subprocess.Popen([sys.executable, '-u', '-m', 'memstara.control'], cwd=root,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
for _ in range(50):
    try:
        with urllib.request.urlopen(url + 'playbooks', timeout=30) as response:
            menu = json.load(response)
        assert menu['catalog'] and menu['max_hypotheses'] == 4
        if active and identity(active['pid']) == active_identity:
            with urllib.request.urlopen(url + 'health', timeout=2) as response:
                restored = json.load(response).get('running')
            assert restored and restored['pid'] == active['pid']
        with urllib.request.urlopen(url + 'pipelines', timeout=30) as response:
            restored_pipelines = {p['id']: p for p in json.load(response)['pipelines']}
        for pipeline_id, live_pid, before in independent:
            if identity(live_pid) == before:
                restored_run = restored_pipelines[pipeline_id]['running']
                assert restored_run and restored_run['pid'] == live_pid
        print(f'Control refreshed; {len(menu["catalog"])} catalog entries; hypothesis cap 4; PID {child.pid}')
        break
    except (OSError, AssertionError, KeyError):
        time.sleep(.1)
else:
    raise SystemExit('Control did not become ready; inspect /tmp/memstara-v1-control.log')
