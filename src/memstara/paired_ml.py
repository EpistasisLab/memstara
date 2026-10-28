"""Serialized child-process execution for the selected ML model."""
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


def exceeds_limit(limits, key, value):
    """Honor explicit historical ceilings; null or absent ceilings are unlimited."""
    ceiling = limits.get(key)
    return ceiling is not None and value > ceiling


def atomic(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        json.dump(value, stream, allow_nan=False, indent=2)
        temporary = Path(stream.name)
    temporary.replace(path)


class FitPaused(Exception):
    """No complete worker output was accepted; restart only on explicit Resume."""


def supervise(command, *, env, limits, pass_fds=(), pause_marker=None, output_path=None):
    """Return only after the whole worker process group has exited or been killed."""
    import psutil
    memory_limit = limits.get('memory_bytes')
    ceiling = (min(memory_limit, int(psutil.virtual_memory().available * .4))
               if memory_limit is not None else None)
    if ceiling is not None and ceiling < 256 * 1024**2:
        raise RuntimeError('Insufficient free memory to start paired ML safely')
    began = time.monotonic()
    process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True, pass_fds=pass_fds)
    peak = 0
    try:
        monitor = psutil.Process(process.pid)
        while process.poll() is None:
            if pause_marker and pause_marker.exists() and not (output_path and output_path.exists()):
                raise FitPaused()
            if limits.get('wall_seconds') is not None and time.monotonic() - began > limits['wall_seconds']:
                raise RuntimeError('Paired ML exceeded its wall-time budget')
            try:
                children = monitor.children(recursive=True)
                used = monitor.memory_info().rss + sum(p.memory_info().rss for p in children if p.is_running())
                peak = max(peak, used)
            except psutil.NoSuchProcess:
                continue
            if ceiling is not None and used > ceiling:
                raise RuntimeError('Paired ML exceeded its memory budget')
            if ceiling is not None and psutil.virtual_memory().available < 128 * 1024**2:
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
    from memstara.pipeline.paused_recovery import saved_fit, save_fit, fit_path
    restored = saved_fit(path, snapshot)
    if restored:
        if restored['target'] != target or restored['evaluation'] != evaluation:
            raise ValueError('Paused ML target or evaluation changed')
        proposal = restored['proposal']
        snapshot = {**snapshot, **({'_ml_plan_resolution': restored['snapshot']['_ml_plan_resolution']}
                                  if '_ml_plan_resolution' in restored['snapshot'] else {})}
    limits = snapshot['ml_configuration_policy']
    if exceeds_limit(limits, 'max_csv_bytes', path.stat().st_size):
        raise ValueError('Input exceeds paired ML CSV size budget')
    accepted = config.validate(proposal, snapshot, evaluation)
    record = config.identity(path, snapshot, evaluation, accepted)
    handoff = json.loads(path.with_suffix('.comparison.json').read_text())
    recorded_splits = (handoff.get('data_allocation') or {}).get('replicates', [])
    if accepted['folds'] and any(accepted['folds'] > min(r['train_class_counts'].values())
                                  for r in recorded_splits):
        raise ValueError('Reduce training CV folds to the smallest training class count')
    variants = 2 + len(handoff.get('groups', {})) if snapshot.get('comparison_policy') else 1
    if exceeds_limit(limits, 'max_fits', evaluation['replicates'] * (accepted['folds'] + 2) * variants):
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
                result = json.loads(result_path.read_text())
                # A recorded failure is returned unchanged, never retrained.
                # Successful reuse requires intact saved model artifacts.
                if result.get('status') != 'failed' and not result.get('error'):
                    from memstara.ml_artifact_recovery import verify_result
                    verify_result(result, root)
                return result
            if not restored:
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
                marker = None
                if snapshot.get('pause_policy') == 'fresh_request_and_ml_restart_v2' and env.get('MEMSTARA_RUN_CONFIG'):
                    frozen = Path(env['MEMSTARA_RUN_CONFIG'])
                    if json.loads(frozen.read_text()).get('run_tag') != snapshot.get('run_tag'):
                        raise ValueError('ML pause ownership differs from the frozen execution')
                    marker = frozen.parent / 'pause.request'
                interruptions = 0
                if restored and marker:
                    fit_path(marker.parent, path).unlink(missing_ok=True)
                    interruptions = 1
                while True:
                    try:
                        if marker and marker.exists():
                            raise FitPaused()
                        usage = supervise(
                            [sys.executable, "-m", "memstara.paired_ml", str(request_path), str(output_path)],
                            env=env,
                            limits=limits,
                            pass_fds=(lock.fileno(),),
                            **({"pause_marker": marker, "output_path": output_path} if marker else {}),
                        )
                        usage['pause_restarts'] = interruptions
                        break
                    except FitPaused:
                        if marker is None:
                            raise
                        if output_path.exists():
                            # Atomic publication may have won the race with termination.
                            usage = {'pause_restarts': interruptions, 'completed_during_pause': True}
                            break
                        interruptions += 1
                        atomic(progress_path, {'phase': 'paused', 'completed_models': {},
                                               'restart_on_resume': True, 'pause_restarts': interruptions})
                        from memstara.pipeline.pause_runtime import wait_for_ml_resume
                        save_fit(marker.parent, request)
                        wait_for_ml_resume(marker, lock)
                        fit_path(marker.parent, path).unlink(missing_ok=True)
                        if config.identity(path, snapshot, evaluation, accepted) != record:
                            raise ValueError('ML inputs changed while paused') from None
                        atomic(progress_path, {'phase': 'restarting', 'completed_models': {},
                                               'pause_restarts': interruptions})
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
    from memstara.preprocessing_policy import typed_predictors

    declared = (
        snapshot.get("research_profile", {}).get("configuration", {}).get("categorical_columns", [])
        if typed_predictors(snapshot)
        else []
    )
    categorical = X[[c for c in X if c in declared or c in X.select_dtypes(exclude='number').columns]]
    width = len(X.columns) - len(categorical.columns) + sum(categorical.nunique(dropna=False))
    limits = snapshot['ml_configuration_policy']
    if (exceeds_limit(limits, 'max_encoded_columns', width)
            or exceeds_limit(limits, 'max_dense_cells', width * len(frame))):
        raise DataQualityError('Encoded design matrix exceeds ML memory budget')
    handoff = json.loads(path.with_suffix('.comparison.json').read_text())
    variants = 2 + len(handoff.get('groups', {})) if snapshot.get('comparison_policy') else 1
    models_to_fit = (proposal['primary_model'],)
    estimated_fits = len(models_to_fit) * evaluation['replicates'] * (proposal['folds'] + 2) * variants
    if exceeds_limit(limits, 'max_fits', estimated_fits):
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
    deadline = request['snapshot']['ml_configuration_policy'].get('wall_seconds')
    signal.alarm(deadline if deadline is not None else 0)
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
