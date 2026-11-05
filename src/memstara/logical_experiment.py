"""One logical experiment, immutable attempts, verified per-combination outputs.

Only explicit continuation links authorize ancestry. A matching pipeline name
alone never groups independent experiments. No historical artifact is moved or
rewritten, and candidate selection never consults performance values.
"""
import hashlib
import json
from pathlib import Path

VERSION = 'logical_experiment_v1'


def read(path):
    return json.loads(Path(path).read_text())


def lineage(snapshot, run_root):
    run_root = Path(run_root)
    parent = run_root.parent.resolve()
    chain = [(snapshot, run_root)]
    seen = {snapshot['run_tag']}
    while True:
        current, directory = chain[-1]
        selection = current.get('retry_selection') or {}
        source = selection.get('source_run_tag')
        path = directory/'retry_lineage.json'
        if path.exists():
            saved = read(path)
            if not isinstance(saved, dict) or not saved.get('source_run_tag'):
                raise ValueError('Continuation history is invalid')
            if source and source != saved['source_run_tag']:
                raise ValueError('Continuation history disagrees with its frozen configuration')
            source = saved['source_run_tag']
        if not source:
            break
        if source in seen or len(chain) >= 64:
            raise ValueError('Continuation history is cyclic or too long')
        matches = []
        for candidate in parent.iterdir():
            path = candidate/'config.json'
            if not candidate.is_dir() or candidate.is_symlink() or not path.is_file() or path.is_symlink():
                continue
            try:
                value = read(path)
            except (OSError,ValueError):
                continue
            if not isinstance(value,dict):
                continue
            if value.get('run_tag') == source and value.get('mode') != 'report_only':
                matches.append((value,candidate))
        if len(matches) != 1:
            raise ValueError('Continuation source is missing or ambiguous')
        value, candidate = matches[0]
        for key in ('pipeline_id','dataset_sha256','y_column'):
            if not current.get(key) or current[key] != value.get(key):
                raise ValueError('Continuation source belongs to a different study')
        for key in ('combination_plan','knowledge_hashes'):
            if current.get(key) != value.get(key):
                raise ValueError('Continuation source changed the frozen schedule or knowledge scope')
        seen.add(source)
        chain.append((value,candidate))
    return list(reversed(chain))


def selected_loops(snapshot, directory):
    total = snapshot['combination_plan']['total_loops']
    selection = (snapshot.get('retry_selection') or {}).get('loops')
    if selection is not None:
        from memstara.pipeline.retry_selection import validate_loops

        return validate_loops(selection,total)
    path = Path(directory)/'retry_lineage.json'
    first = read(path).get('first_loop',1) if path.exists() else 1
    if type(first) is not int or not 1 <= first <= total:
        raise ValueError('Invalid original combination range')
    return list(range(first,total+1))


def verified_report(snapshot, directory, loop):
    path = Path(directory)/'explanation_io'/f'loop-{loop}.json'
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError('Explanation index must not be a symlink')
    item = read(path)
    receipt = item['receipt']
    source = Path(receipt['path'])
    boundary = Path(directory).resolve()/'explanation_io'
    if source.is_symlink() or source.resolve().parent != boundary or boundary.is_symlink():
        raise ValueError('Explanation receipt escapes its original execution')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt['sha256']:
        raise ValueError('Explanation receipt integrity mismatch')
    record = json.loads(raw)
    if (record.get('run_tag') != snapshot['run_tag'] or record.get('config_hash') != snapshot['config_hash']
            or record.get('loop') != loop):
        raise ValueError('Saved Explanation report belongs to another condition')
    expected = {**record['provenance'],'output':receipt}
    if item.get('summary') != expected:
        raise ValueError('Saved Explanation provenance integrity mismatch')
    if (record.get('execution',{}).get('status') != 'completed' or expected.get('status') != 'completed'
            or not isinstance(record.get('output'),str) or not record['output'].strip()):
        raise ValueError('Saved Explanation report is not complete')
    return {'loop':loop,'run_tag':snapshot['run_tag'],'config_hash':snapshot['config_hash'],
            'receipt':receipt,'summary':expected,'output':record['output']}


def report_index(snapshot, run_root):
    sources = lineage(snapshot,run_root)
    reports,attempts = {},[]
    for config,directory in sources:
        selected = selected_loops(config,directory)
        attempts.append({'run_tag':config['run_tag'],'config_hash':config['config_hash'],'selected_loops':selected})
        for loop in selected:
            report = verified_report(config,directory,loop)
            if report:
                # Last verified attempt wins by lineage order, never by AUROC.
                reports[loop] = report
    total = snapshot['combination_plan']['total_loops']
    missing = [loop for loop in range(1,total+1) if loop not in reports]
    return {'version':VERSION,'id':sources[0][0]['run_tag'],'name':snapshot.get('pipeline_name'),
            'latest_run_tag':snapshot['run_tag'],'expected_combinations':total,'attempts':attempts,
            'selection_policy':'latest_verified_completed_attempt_per_original_loop',
            'missing_loops':missing,'status':'incomplete' if missing else 'completed',
            'reports':[{key:value for key,value in reports[loop].items() if key!='output'} for loop in sorted(reports)]}, reports
