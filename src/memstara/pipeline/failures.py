"""Persist the first execution failure and prevent subsequent model calls."""
import json
from datetime import UTC, datetime
from pathlib import Path


class PipelineExecutionFailure(RuntimeError):
    """An execution error is not an unproductive research question."""


def failure_summary(error):
    text = f'{type(error).__name__}: {error}'.lower()
    if 'system message must be at the beginning' in text:
        return 'model_message_format', 'The model rejected the system-message format. Further execution was stopped.'
    if any(s in text for s in ('badrequest', 'bad request', 'error code: 400', 'status code: 400')):
        return 'model_request_rejected', 'The model rejected the request settings. Further execution was stopped.'
    if any(s in text for s in ('authentication', 'unauthorized', 'permissiondenied',
                               'error code: 401', 'error code: 403')):
        return 'model_access', 'The model rejected access. Check the deployment credentials and permissions.'
    if any(s in text for s in ('timeout', 'timed out', 'connectionerror')):
        return 'model_connection', ('The model connection failed or timed out. '
                                    'Saved results are retained; further execution was stopped.')
    return 'agent_execution_failed', ('An agent execution failed. '
                                     'Further execution was stopped; inspect its saved trace.')


def read_failure(run_dir):
    """Read the first persisted failure for this execution."""
    root = Path(run_dir)
    try:
        failure = json.loads((root / 'pipeline_failure.json').read_text())
        if isinstance(failure, dict) and isinstance(failure.get('message'), str):
            return failure
    except (OSError, ValueError):
        pass
    return None


def ensure_not_failed(run_dir):
    if run_dir and (failure := read_failure(run_dir)):
        raise PipelineExecutionFailure(failure['message'])


def stop_execution(run_dir, stage, loop, error, *, code=None, message=None):
    kind, summary = failure_summary(error)
    record = dict(code=code or kind, message=message or summary, stage=stage, loop=loop,
                  at=datetime.now(UTC).isoformat())
    if run_dir:
        from memstara.pipeline.checkpoint import atomic_json
        root = Path(run_dir)
        original = read_failure(root)
        if original:
            record = original
        else:
            atomic_json(root / 'pipeline_failure.json', record)
        atomic_json(root / 'pipeline_status.json', {'status': 'failed', 'failure': record,
                                                   'message': record['message']})
    raise PipelineExecutionFailure(record['message'])


def require_tools(by_stage, required, run_dir=None):
    missing = {}
    for stage, names in required.items():
        available = {t.get('tool_name') for t in by_stage.get(stage, [])}
        if absent := set(names) - available:
            missing[stage] = sorted(absent)
    if missing:
        detail = '; '.join(f'{stage}: {", ".join(names)}' for stage, names in missing.items())
        stop_execution(run_dir, 'preflight', None, '', code='missing_tools',
                       message=f'Required tools are unavailable ({detail}). No model calls were started.')


def visible_failure(run_dir, *, include_legacy=True):
    """Surface an older failed run's cause without altering its original artifacts."""
    if failure := read_failure(run_dir):
        return failure
    if not include_legacy:
        return None
    try:
        calls = json.loads((Path(run_dir) / 'execution.json').read_text()).get('calls', [])
        for call in calls:
            if call.get('status') == 'failed' and call.get('error'):
                code, message = failure_summary(call['error'])
                # Historical runs may have continued after an error; do not claim they stopped immediately.
                message = message.replace(' Further execution was stopped.', '')
                message = message.replace('; further execution was stopped.', '.')
                message = message.replace(' Further execution was stopped; inspect its saved trace.',
                                          ' Inspect its saved trace.')
                return {'code': code, 'message': message,
                        'stage': call.get('stage'), 'loop': call.get('loop')}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None
