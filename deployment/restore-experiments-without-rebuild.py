"""Restore retained experiment definitions using the existing control image.

The controller is stopped briefly to avoid racing its in-memory workspace.
All live experiments must already be paused and pass checkpoint recovery checks.
Only workspace metadata is changed. Experiments are never started or resumed.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = '''
import hashlib,json,urllib.request
from pathlib import Path
from memstara.paths import output_dir
from memstara.pipeline.checkpoint import recovery_status
from memstara.pipeline.paused_recovery import TOOLS
data=json.load(urllib.request.urlopen('http://127.0.0.1:8072/control/pipelines',timeout=20))
runs=[]
for item in data['pipelines']:
    run=item.get('running')
    if not run: continue
    if run.get('execution_state')!='paused' or not run.get('pause_requested'):
        raise SystemExit('Pause every running experiment before restoring workspace metadata.')
    state=recovery_status(Path(run['run_dir']))
    if not state.get('recoverable'):
        checkpoint=json.loads((Path(run['run_dir'])/'checkpoint.json').read_text())
        active=checkpoint.get('calls',{})
        metadata=checkpoint.get('call_metadata',{})
        details=[{'stage':metadata.get(key,{}).get('stage'),
                  'recorded_safe':metadata.get(key,{}).get('safe'),
                  'unapproved_tools':sorted(set(metadata.get(key,{}).get('tools',[]))-TOOLS)}
                 for key in active]
        raise SystemExit('No services changed. Recovery check failed: '+str(state)+
                         '\\nPaused call details: '+json.dumps(details)+
                         '\\nDo not restart the container or change checkpoint flags. '
                         'The live execution must reach a verified recoverable pause first.')
    runs.append({'run_tag':run['run_tag'],'run_dir':run['run_dir']})
workspace=output_dir()/'runs/pipeline_workspace.json'
print(json.dumps({'workspace':str(workspace),'sha256':hashlib.sha256(workspace.read_bytes()).hexdigest(),'paused':runs}))
'''
VERIFY = '''
import json,sys,time,urllib.request
expected=set(json.loads(sys.argv[1]))
for attempt in range(30):
    try:
        data=json.load(urllib.request.urlopen('http://127.0.0.1:8072/control/pipelines',timeout=5))
        actual={p['id'] for p in data['pipelines']}
        if not expected<=actual: raise ValueError('Restored experiments are missing from the UI API')
        print(json.dumps([{'number':p['number'],'name':p['name'],'id':p['id']} for p in data['pipelines']],indent=2))
        break
    except (OSError,ValueError):
        if attempt==29: raise
        time.sleep(1)
'''


def merge(current, entries):
    result = list(current)
    for entry in entries:
        if any(item['id'] == entry['id'] for item in result):
            continue
        if any(item['number'] == entry['number'] for item in result):
            raise ValueError('Requested experiment number is occupied; nothing was restored')
        result.append(entry)
    return sorted(result, key=lambda item: item['number'])


def worker(plan_path):
    from memstara.pipeline.checkpoint import atomic_json, recovery_status
    from uuid import uuid4

    plan = json.loads(Path(plan_path).read_text())
    workspace = Path(plan['workspace'])
    raw = workspace.read_bytes()
    if hashlib.sha256(raw).hexdigest() != plan['sha256']:
        raise ValueError('Workspace changed after preflight; no metadata was replaced')
    for run in plan['paused']:
        status = recovery_status(Path(run['run_dir']))
        if not status.get('recoverable'):
            raise ValueError('Paused recovery verification failed: ' + str(status))
    spec = importlib.util.spec_from_file_location('restoration_definition', '/admin/definition.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries = [module.definition(workspace.parent, tag, number) for tag, number in plan['selected']]
    current = json.loads(raw)
    restored = merge(current, entries)
    if restored != current:
        backup = workspace.with_name('workspace-before-restore-' + uuid4().hex + '.json')
        atomic_json(backup, current, overwrite=False)
        atomic_json(workspace, restored)
        print('Workspace backup: ' + str(backup), file=sys.stderr)
    print(json.dumps([entry['id'] for entry in entries]))


def run(argv, **kwargs):
    return subprocess.run(argv, cwd=ROOT, check=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='append', required=True, metavar='NUMBER=RUN_TAG')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    selected = []
    for value in args.restore:
        number, separator, tag = value.partition('=')
        if not separator or not number.isdigit() or int(number) < 1 or not tag:
            parser.error('Use --restore NUMBER=RUN_TAG')
        selected.append((tag, int(number)))
    cid = run(['docker', 'compose', 'ps', '-q', 'control'], capture_output=True).stdout.strip()
    if not cid or '\n' in cid:
        raise RuntimeError('Exactly one running control container is required')
    image = run(['docker', 'inspect', '--format', '{{.Image}}', cid], capture_output=True).stdout.strip()
    plan = json.loads(run(['docker', 'exec', cid, '/app/.venv/bin/python', '-c', PREFLIGHT], capture_output=True).stdout)
    plan['selected'] = selected
    # Validate source identities and number conflicts before stopping anything.
    sys.path.insert(0, str(ROOT / 'src'))
    from memstara.control.restore import definition
    entries = [definition(ROOT / 'outputs/runs', tag, number) for tag, number in selected]
    local_workspace = ROOT / 'outputs/runs/pipeline_workspace.json'
    if hashlib.sha256(local_workspace.read_bytes()).hexdigest() != plan['sha256']:
        raise RuntimeError('This checkout is not the controller workspace; nothing changed')
    merge(json.loads(local_workspace.read_text()), entries)
    print(json.dumps([{'number': e['number'], 'name': e['name'], 'id': e['id']} for e in entries], indent=2), flush=True)
    if not args.apply:
        print('Preflight passed. Use --apply to restore metadata with a brief controller restart.')
        return
    private = ROOT / '.private-tmp'
    private.mkdir(mode=0o700, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='workspace-restore-', dir=private))
    plan_file = folder / 'plan.json'
    plan_file.write_text(json.dumps(plan))
    os.chmod(plan_file, 0o600)
    stopped = False
    try:
        # Start the exact same container again, even if restoration fails. Never
        # rebuild or recreate it: recovery verifies the original runtime code.
        stopped = True
        run(['docker', 'stop', '--time', '60', cid])
        result = run(['docker', 'run', '--rm', '--network', 'none', '--volumes-from', cid,
                      '--mount', f'type=bind,src={Path(__file__).resolve()},dst=/admin/restore.py,readonly',
                      '--mount', f'type=bind,src={ROOT / "src/memstara/control/restore.py"},dst=/admin/definition.py,readonly',
                      '--mount', f'type=bind,src={plan_file},dst=/admin/plan.json,readonly',
                      '--entrypoint', '/app/.venv/bin/python', image,
                      '/admin/restore.py', '--worker', '/admin/plan.json'], capture_output=True)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        restored_ids = json.loads(result.stdout)
    finally:
        if stopped:
            run(['docker', 'start', cid])
    run(['docker', 'exec', cid, '/app/.venv/bin/python', '-c', VERIFY, json.dumps(restored_ids)])
    print('Restored. Refresh the browser: results and costs are linked by the original IDs. No experiment was resumed.')


if __name__ == '__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--worker':
            worker(sys.argv[2])
        else:
            main()
    except subprocess.CalledProcessError as error:
        print(error.stderr or str(error), file=sys.stderr)
        raise SystemExit(1) from None
