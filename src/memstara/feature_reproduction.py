"""Offline feature-selection replay: python -m memstara.feature_reproduction BUNDLE.

Never executes archived source, contacts a model, or trains an estimator.
"""
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from memstara.pipeline.feature_selection import context, validate

VERSION = 1
SOURCE = Path(__file__).parent
CODE = ('pipeline/feature_selection.py', 'combinations.py', 'feature_reproduction.py', 'data_allocation.py',
        'controlled_comparison.py', 'ml_configuration.py')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))
    path.chmod(0o600)


def environment():
    return {'python': platform.python_version(), 'implementation': platform.python_implementation(),
            'platform': platform.platform(), 'random_source_sha256': digest(random.__file__),
            'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()
                         if d.metadata.get('Name')}}


def archive(plan, dataset, knowledge, run_dir):
    """Finish the local-only immutable bundle before any hypothesis model call."""
    destination = run_dir / 'feature_reproduction'
    if destination.exists():
        result = replay(destination)
        if result['status'] != 'verified' or json.loads((destination / 'config.json').read_text()) != plan:
            raise ValueError('Existing feature reproduction bundle is inconsistent')
        return destination
    temporary = Path(tempfile.mkdtemp(prefix='.feature-reproduction-', dir=run_dir))
    try:
        write_json(temporary / 'config.json', plan)
        shutil.copyfile(dataset, temporary / 'input.csv')
        if digest(temporary / 'input.csv') != plan['dataset_sha256']:
            raise ValueError('Dataset changed while archiving feature selection inputs')
        for name, expected in plan.get('knowledge_hashes', {}).items():
            source = (knowledge / name).resolve()
            source.relative_to(knowledge.resolve())
            target = temporary / 'knowledge' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if digest(target) != expected:
                raise ValueError('Knowledge changed while archiving selection inputs')
        for name in CODE:
            target = temporary / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, target)
        shutil.copyfile(random.__file__, temporary / 'random.py')
        write_json(temporary / 'environment.json', environment())
        try:
            revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE,
                                               stderr=subprocess.DEVNULL, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            revision = None
        selections = [context(plan, wave) for wave in range(plan['combination_plan']['total_loops'])]
        write_json(temporary / 'selections.json', selections)
        (temporary / 'README.txt').write_text(
            'LOCAL PRIVATE REPRODUCTION BUNDLE: contains the original dataset. Do not publish.\n'
            'Run: python -m memstara.feature_reproduction /path/to/feature_reproduction\n'
            'Uses installed, hash-checked source; never executes archived code.\n'
            'Random selections are recalculated. Guided selections can be validated from accepted/ records, '
            'but LLM text is not regenerated. Accepted records mean verified extraction, not completed ML.\n'
            'Preserve the enclosing run folder for call traces, question lineage and final results.\n'
            'ML bundles separately preserve fitted models, splits, predictions and effective parameters.\n')
        files = {str(p.relative_to(temporary)): digest(p) for p in temporary.rglob('*') if p.is_file()}
        write_json(temporary / 'manifest.json', {'version': VERSION, 'git_revision': revision,
                   'source_policy': 'Archived working source is authoritative, including uncommitted changes',
                   'files': files, 'code': {name: digest(SOURCE / name) for name in CODE},
                   'scope': 'Feature selection integrity and replay; not identical LLM generation or full ML replay'})
        for p in temporary.rglob('*'):
            p.chmod(0o700 if p.is_dir() else 0o600)
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return destination


def replay(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('version') != VERSION:
        raise ValueError('Unsupported feature reproduction bundle')
    for name, expected in manifest['files'].items():
        path = (directory / name).resolve()
        path.relative_to(directory)
        if digest(path) != expected:
            raise ValueError('Bundle integrity mismatch: ' + name)
    for name in CODE:
        if manifest['code'].get(name) != digest(SOURCE / name):
            raise ValueError('Installed source differs from archived source: ' + name)
    plan = json.loads((directory / 'config.json').read_text())
    saved = json.loads((directory / 'selections.json').read_text())
    actual = [context(plan, wave) for wave in range(plan['combination_plan']['total_loops'])]
    if saved != actual:
        raise ValueError('Recomputed feature selections differ')
    accepted = []
    for path in sorted((directory / 'accepted').glob('*.json')):
        record = json.loads(path.read_text())
        recorded_hash = record.pop('record_sha256')
        if recorded_hash != hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest():
            raise ValueError('Accepted selection record integrity mismatch')
        if record['manifest_sha256'] != digest(directory / 'manifest.json'):
            raise ValueError('Accepted selection belongs to another bundle')
        expected = validate(record['selection']['features'], plan, record['selection']['loop'] - 1)
        if expected != record['selection'] or record['config_hash'] != plan['config_hash']:
            raise ValueError('Accepted selection differs from the frozen policy')
        accepted.append(record['task_id'])
    return {'status': 'verified', 'random_loops_replayed': sum(s['mode'] == 'random' for s in actual),
            'guided_loops_configured': sum(s['mode'] == 'guided' for s in actual),
            'accepted_extractions_validated': len(accepted),
            'environment_matches': environment() == json.loads((directory / 'environment.json').read_text()),
            'llm_regenerated': False, 'ml_retrained': False}


def record_extraction(task, plan, selection):
    """Save accepted predictor provenance independently of database retention."""
    if not plan.get('feature_reproduction'):
        return None  # Legacy snapshots must never write into a newer run's bundle.
    location = os.environ.get('MEMSTARA_RUN_CONFIG')
    if not location or not (Path(location).parent / 'feature_reproduction').is_dir():
        if plan.get('feature_reproduction'):
            raise ValueError('Required feature reproduction bundle is missing; extraction cannot advance')
        return None  # Historical runs have no bundle; never retrofit their experimental record.
    directory = Path(location).parent / 'feature_reproduction'
    frozen = json.loads((directory / 'config.json').read_text())
    if any(frozen.get(k) != plan.get(k) for k in ('config_hash', 'run_tag')):
        raise ValueError('Feature reproduction bundle belongs to another run')
    record = {'task_id': task['task_id'], 'question_id': task.get('question_id'),
              'config_hash': plan['config_hash'], 'selection': selection,
              'stage': 'verified_extraction_before_ml', 'manifest_sha256': digest(directory / 'manifest.json')}
    record['record_sha256'] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    accepted = directory / 'accepted'
    accepted.mkdir(mode=0o700, exist_ok=True)
    path = accepted / f"task-{int(task['task_id'])}.json"
    if path.exists():
        if json.loads(path.read_text()) != record:
            raise ValueError('Accepted selection record cannot be overwritten')
    else:
        with tempfile.NamedTemporaryFile(mode='w', dir=accepted, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(record, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if json.loads(path.read_text()) != record:
                    raise ValueError('Concurrent selection record differs') from None
        finally:
            temporary.unlink()
    return record


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    try:
        result = replay(args.bundle)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'status': 'verification_failed', 'reason': str(exc)}
    print(json.dumps(result))
    raise SystemExit(0 if result['status'] == 'verified' else 1)


if __name__ == '__main__':
    main()
