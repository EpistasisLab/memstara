"""Serialized, bounded child-process execution for the selected ML model."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

from memstara import ml_configuration as config


def atomic(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        json.dump(value, stream, allow_nan=False, indent=2)
        temporary = Path(stream.name)
    temporary.replace(path)


def supervise(command, *, env, limits, pass_fds=()):
    """Return only after the whole worker process group has exited or been killed."""
    import psutil
    available = psutil.virtual_memory().available
    ceiling = min(limits['memory_bytes'], int(available * .4))
    if ceiling < 256 * 1024**2:
        raise RuntimeError('Insufficient free memory to start paired ML safely')
    began = time.monotonic()
    process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True, pass_fds=pass_fds)
    peak = 0
    try:
        monitor = psutil.Process(process.pid)
        while process.poll() is None:
            if time.monotonic() - began > limits['wall_seconds']:
                raise RuntimeError('Paired ML exceeded its wall-time budget')
            try:
                children = monitor.children(recursive=True)
                used = monitor.memory_info().rss + sum(p.memory_info().rss for p in children if p.is_running())
                peak = max(peak, used)
            except psutil.NoSuchProcess:
                continue
            if used > ceiling:
                raise RuntimeError('Paired ML exceeded its memory budget')
            if psutil.virtual_memory().available < 128 * 1024**2:
                raise RuntimeError('Paired ML stopped because system memory is low')
            time.sleep(.1)
        if process.returncode:
            raise RuntimeError('Paired ML worker failed; no complete pair was accepted')
        return {'peak_rss_bytes': peak, 'memory_ceiling_bytes': ceiling,
                'duration_seconds': time.monotonic() - began, 'threads': 1}
    finally:
        # Also kill descendants if the leader exited early.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def execute(path, target, evaluation, snapshot, proposal):
    from memstara.paths import DEFAULT_OUTPUT_DIR
    limits = snapshot['ml_configuration_policy']
    if path.stat().st_size > limits['max_csv_bytes']:
        raise ValueError('Input exceeds paired ML CSV size budget')
    accepted = config.validate(proposal, snapshot, evaluation)
    record = config.identity(path, snapshot, evaluation, accepted)
    handoff = json.loads(path.with_suffix('.comparison.json').read_text())
    recorded_splits = (handoff.get('data_allocation') or {}).get('replicates', [])
    if accepted['folds'] and any(accepted['folds'] > min(r['train_class_counts'].values())
                                  for r in recorded_splits):
        raise ValueError('Reduce training CV folds to the smallest training class count')
    variants = 2 + len(handoff.get('groups', {})) if snapshot.get('comparison_policy') else 1
    if evaluation['replicates'] * (accepted['folds'] + 2) * variants > limits['max_fits']:
        raise ValueError('Reduce training CV folds: selected-model fit count exceeds the resource budget')
    root = Path(os.environ.get('MEMSTARA_OUTPUT_DIR') or DEFAULT_OUTPUT_DIR)
    root.mkdir(parents=True, exist_ok=True)
    # One lock for all processes and pipelines in this local application.
    with (root / '.paired-ml.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'error': 'Another ML job is running; wait and retry the unchanged proposal.', 'retryable': True}
        accepted_path = path.with_suffix('.ml-plan.json')
        result_path = path.with_suffix('.paired-evaluation.json')
        if accepted_path.exists():
            if json.loads(accepted_path.read_text()) != record:
                raise ValueError('Accepted ML settings/input cannot change after evaluation starts')
            if result_path.exists():
                return json.loads(result_path.read_text())
            raise ValueError('Prior ML execution was interrupted; inspect its record before a new run')
        atomic(accepted_path, record)
        progress_path = path.with_suffix('.paired-progress.json')
        atomic(progress_path, {'phase': 'starting', 'completed_models': {}})
        request = {'path': str(path), 'target': target, 'evaluation': evaluation,
                   'snapshot': snapshot, 'proposal': accepted, 'record': record}
        result = None
        try:
            with tempfile.TemporaryDirectory(prefix='paired-', dir=root) as folder:
                request_path = Path(folder) / 'request.json'
                output_path = Path(folder) / 'result.json'
                atomic(request_path, request)
                env = {**os.environ, **{name: '1' for name in (
                    'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS',
                    'NUMEXPR_NUM_THREADS')}}
                usage = supervise([sys.executable, '-m', 'memstara.paired_ml', str(request_path), str(output_path)],
                                  env=env, limits=limits, pass_fds=(lock.fileno(),))
                result = json.loads(output_path.read_text())
                result['ml_resource_usage'] = usage
        except Exception as exc:
            result = {'status': 'failed', 'error': str(exc) if type(exc) is RuntimeError else
                      f'ML failed ({type(exc).__name__})', 'ml_configuration': record,
                      'evaluation': {'dataset_sha256': record['dataset_sha256']}}
        if result.get('status') == 'failed':
            result['partial_progress'] = json.loads(progress_path.read_text())
        atomic(result_path, result)
        return result


def fit(request):
    from threadpoolctl import threadpool_limits
    from memstara.evaluation import score, validate_clean_dataset, DataQualityError
    from memstara.comparisons import score_comparisons
    from memstara import evaluation as evaluation_module
    path = Path(request['path'])
    snapshot, proposal = request['snapshot'], request['proposal']
    evaluation = request['evaluation']
    config.validate(proposal, snapshot, evaluation)
    if config.identity(path, snapshot, evaluation, proposal) != request['record']:
        raise ValueError('ML inputs changed before fitting')
    # All score/comparison helpers use exactly this frozen partition, including ablations.
    evaluation_module.active_plan = lambda: snapshot
    frame = validate_clean_dataset(path, request['target'], allow_missing=proposal['primary_model'] == 'xgboost')
    X = frame.drop(columns=[request['target']])
    categorical = X.select_dtypes(exclude='number')
    width = len(X.columns) - len(categorical.columns) + sum(categorical.nunique(dropna=False))
    limits = snapshot['ml_configuration_policy']
    if width > limits['max_encoded_columns'] or width * len(frame) > limits['max_dense_cells']:
        raise DataQualityError('Encoded design matrix exceeds ML memory budget')
    handoff = json.loads(path.with_suffix('.comparison.json').read_text())
    variants = 2 + len(handoff.get('groups', {})) if snapshot.get('comparison_policy') else 1
    models_to_fit = (proposal['primary_model'],)
    estimated_fits = len(models_to_fit) * evaluation['replicates'] * (proposal['folds'] + 2) * variants
    if estimated_fits > limits['max_fits']:
        raise ValueError('Selected-model fit count exceeds the resource budget')
    from memstara.specialist_xai import request as xai_request
    specialist = xai_request(snapshot, handoff['trial'])
    results: dict[str, Any] = {}
    with threadpool_limits(limits=1):
        for name in models_to_fit:
            atomic(path.with_suffix('.paired-progress.json'), {'phase': name, 'completed_models': results})
            plan = {**evaluation, 'engine': name, 'folds': proposal['folds'], 'search_trials': 1}
            configuration = proposal['models'][name]
            if snapshot.get('comparison_policy'):
                measured = score_comparisons(path, request['target'], plan, snapshot, configuration=configuration,
                                             xai_request=specialist)
            else:
                measured = score(path, request['target'], plan, configuration=configuration, xai_request=specialist)
            results[name] = measured
            atomic(path.with_suffix('.paired-progress.json'), {'phase': name + '_completed',
                                                              'completed_models': results})
    def splits(result):
        return [(r['seed'], r['train_split_id'], r['split_id']) for r in result['evaluation']['replicates']]
    result = {**results[proposal['primary_model']], 'model_results': results,
              'ml_configuration': request['record']}
    if specialist and any(row.get('specialist_xai', {}).get('status') != 'completed' for row in results.values()):
        result.update(status='failed', error='Specialist explanations are incomplete; inspect saved model artifacts.')
    if config.identity(path, snapshot, evaluation, proposal) != request['record']:
        raise ValueError('ML inputs changed during fitting')
    return result


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    # An independent child deadline survives abrupt loss of the supervising server.
    signal.alarm(request['snapshot']['ml_configuration_policy']['wall_seconds'])
    try:
        result = fit(request)
    except Exception as exc:
        import traceback
        from memstara.evaluation import DataQualityError
        frames = [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                  for f in traceback.extract_tb(exc.__traceback__)]
        result = {'status': 'failed', 'error': str(exc) if isinstance(exc, DataQualityError) else
                  f'Paired ML worker failed ({type(exc).__name__})',
                  'failure_trace': {'error_type': type(exc).__name__, 'frames': frames},
                  'ml_configuration': request['record'],
                  'evaluation': {'dataset_sha256': request['record']['dataset_sha256']}}
    atomic(Path(sys.argv[2]), result)


if __name__ == '__main__':
    main()
