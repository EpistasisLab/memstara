"""Run a frozen 64-condition batch serially; stop the queue on any incomplete run."""
import argparse
import json
from pathlib import Path
import time
import urllib.request
from datetime import datetime, UTC

import memstara  # noqa: F401 — initialize logging policy before dependency imports
from memstara.env import load_env
from memstara.combinations import build_plan, loop_flavors
from memstara.stage_models import deployment_profiles


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def request(path, body=None):
    req = urllib.request.Request('http://127.0.0.1:8072/control/' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180 if body else 30) as response:
        return json.load(response)


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    choices = json.loads(Path('outputs/experiments/agent-combinations-pilot/specialist-config.draft.json')
                         .read_text())['choices']
    plan = build_plan(choices, 1, max_loops=64)
    assert plan['combinations'] == plan['total_loops'] == 64
    base = json.loads(Path('outputs/experiments/haiku55_compatible_20261008/guided/configuration.json').read_text())
    base['stage_models'] = deployment_profiles()
    assert all(p['model'] == 'claude-haiku-5-5' for p in base['stage_models'].values())
    base.pop('controlled_comparison', None)
    entries = []
    fields = dict(hypothesis='playbook_hypothesis', data='playbook_data', ml='playbook_ml',
                  interpreter='playbook_interpreter', report='playbook_explanation')
    for n in range(1, 65):
        flavor = loop_flavors(plan, n)
        config = json.loads(json.dumps(base))
        config['combination_skills'] = {a['stage']: [a['id']] for a in flavor['agents']}
        for a in flavor['agents']:
            config[fields[a['stage']]] = a['id']
        config.update(waves=1, combination_repetitions=1, combination_max_loops=1, continuous=False)
        directory = root / f'C{n:02d}'
        directory.mkdir()
        save(directory / 'configuration.json', config)
        entries.append({'id': f'C{n:02d}', 'skills': config['combination_skills'], 'state': 'pending'})
    save(root / 'schedule.json', plan)
    save(root / 'status.json', {'state': 'prepared', 'completed': 0, 'combinations': entries})
    save(root / 'protocol.json', {'created_at': datetime.now(UTC).isoformat(),
         'planned_runs': 64, 'repetitions': 1, 'concurrency': 1,
         'feature_size': '4-20', 'ml_settings': 'LLM-selected under existing resource safeguards',
         'models': base['stage_models'], 'stop_on_failure': True,
         'memory': 'Existing shared question catalog; not an independent matched causal comparison',
         'results': 'Each condition has a separate run ID, database registry record and original run folder.'})
    print(root, flush=True)


def execute(root):
    status = json.loads((root / 'status.json').read_text())
    if status['state'] != 'prepared':
        raise SystemExit('Batch already started; inspect status before any explicit recovery.')
    lock = root / 'runner.lock'
    with lock.open('x') as stream:
        import os
        stream.write(str(os.getpid()))
    status['state'] = 'running'
    save(root / 'status.json', status)
    try:
        for row in status['combinations']:
            if (root / 'pause.request').exists():
                status['state'] = 'paused'
                break
            directory = root / row['id']
            config = json.loads((directory / 'configuration.json').read_text())
            # Revalidate current skill hashes against the frozen catalog schedule.
            from memstara.combinations import validate_plan
            validate_plan(json.loads((root / 'schedule.json').read_text()))
            health = request('health')
            if health.get('running') or health.get('stage_model_error'):
                raise RuntimeError('Control is busy or model settings are invalid; no launch attempted')
            row['state'] = 'launching'
            status['current'] = row['id']
            save(root / 'status.json', status)
            launch = request('runs', config)
            save(directory / 'launch.json', launch)
            row.update(state='running', run_tag=launch['run_tag'], run_dir=launch['run_dir'])
            save(root / 'status.json', status)
            print(json.dumps({'condition': row['id'], **launch}), flush=True)
            run = Path(launch['run_dir'])
            while True:
                health = request('health')
                active = health.get('running')
                if not active or active.get('run_tag') != launch['run_tag']:
                    break
                time.sleep(10)
            result = json.loads((run / 'pipeline_status.json').read_text())
            save(directory / 'pipeline_status.json', result)
            registry = json.loads((run / 'registry_status.json').read_text())
            if result.get('status') != 'completed' or not result.get('report_completed'):
                raise RuntimeError(f"{row['id']} did not complete: {result.get('code', result.get('status'))}")
            if registry.get('status') != 'synced':
                raise RuntimeError('Registry is not synchronized; subsequent executions stopped')
            for name in ['execution.json', 'iteration_outcomes.json', 'cost_ledger.jsonl', 'registry_status.json']:
                (directory / name).write_bytes((run / name).read_bytes())
            row['state'] = 'completed'
            status['completed'] += 1
            save(root / 'status.json', status)
            print(json.dumps({'completed': status['completed'], 'total': 64}), flush=True)
        else:
            status['state'] = 'completed'
    except Exception as exc:
        row['state'] = 'needs_attention'
        status.update(state='paused_on_error', error=str(exc), stopped_at=datetime.now(UTC).isoformat())
        print(json.dumps({'state': status['state'], 'error': str(exc)}), flush=True)
    finally:
        save(root / 'status.json', status)


if __name__ == '__main__':
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    execute(args.root) if args.execute else prepare(args.root)
