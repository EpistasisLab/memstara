"""Persist the first execution failure and prevent subsequent model calls."""
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn


class PipelineExecutionFailure(RuntimeError):
    """An execution error is not an unproductive research question."""


RETRYABLE_SERVER_STATUSES = frozenset({500, 502, 503, 504, 529})


def rate_limit_lookup_failed(error):
    """Recognize Azure's internal lookup failure, not ordinary quota exhaustion."""
    for item in exception_chain(error):
        candidates = [getattr(item, 'body', None)]
        response = getattr(item, 'response', None)
        if response is not None:
            try:
                candidates.append(response.json())
            except (ValueError, AttributeError):
                pass
        # Anthropic/LiteLLM wrappers sometimes retain only the JSON error message.
        candidates.append(str(item))
        for body in candidates:
            if isinstance(body, str):
                try:
                    body = json.loads(body[body.index('{'):])
                except (ValueError, TypeError):
                    continue
            if isinstance(body, dict):
                detail = body.get('error', {})
                if isinstance(detail, dict) and detail.get('code') == 'rate_limiting_lookup_failed':
                    return True
    return False


def provider_error_details(error):
    """Extract bounded correlation metadata, never response text or request contents."""
    details: dict[str, int | str] = {}
    for item in exception_chain(error):
        response = getattr(item, 'response', None)
        status = getattr(item, 'status_code', None)
        if status is None:
            status = getattr(response, 'status_code', None)
        if type(status) is int and 100 <= status <= 599:
            details.setdefault('http_status', status)
        headers = getattr(response, 'headers', {}) or {}
        request_id = getattr(item, 'request_id', None)
        if not request_id:
            request_id = next((headers.get(key) for key in
                               ('x-request-id', 'x-ms-request-id', 'apim-request-id')
                               if headers.get(key)), None)
        body = getattr(item, 'body', None)
        if not isinstance(body, dict):
            body = {}
        for key, value in (('provider_request_id', request_id),
                           ('provider_activity_id', body.get('activityId'))):
            if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value):
                details.setdefault(key, value)
    return details


def retryable_model_error(error):
    """Retry only a failed provider request, not a whole agent or its tools."""
    status = provider_error_details(error).get('http_status')
    if status == 429:
        return rate_limit_lookup_failed(error)
    if status is not None:
        return status in RETRYABLE_SERVER_STATUSES or status == 408
    return failure_summary(error)[0] in ('model_connection', 'model_server')


def exception_chain(error):
    """Inspect wrappers without storing their possibly sensitive messages."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        yield error
        error = getattr(error, '__cause__', None) or getattr(error, '__context__', None)


def failure_summary(error):
    status = provider_error_details(error).get('http_status')
    if status == 429:
        if rate_limit_lookup_failed(error):
            return 'model_service_unavailable', (
                'The model service could not retrieve its rate-limit data. '
                'Saved results are retained; further execution was stopped.')
        return 'model_rate_limit', (
            'The model service returned HTTP 429. Check deployment rate limits and quota. '
            'Saved results are retained; further execution was stopped.')
    if status in RETRYABLE_SERVER_STATUSES:
        return 'model_server', ('The model service returned a server error. '
                                'Saved results are retained; further execution was stopped.')
    if status == 408:
        return 'model_connection', 'The model request timed out. Further execution was stopped.'
    if status in (401, 403):
        return 'model_access', 'The model rejected access. Check the deployment credentials and permissions.'
    if status is not None and 400 <= status < 500:
        return 'model_request_rejected', 'The model rejected the request settings. Further execution was stopped.'
    text = ' '.join(f'{type(e).__name__}: {e}' for e in exception_chain(error)).lower()
    # Historical traces may preserve only text; current retries use structured status.
    if re.search(r'\b(?:error code|status code|http)[\s:]+(?:500|502|503|504|529)\b', text):
        return 'model_server', ('The model service returned a server error. '
                                'Saved results are retained; further execution was stopped.')
    if 'system message must be at the beginning' in text:
        return 'model_message_format', 'The model rejected the system-message format. Further execution was stopped.'
    if any(s in text for s in ('badrequest', 'bad request', 'error code: 400', 'status code: 400')):
        return 'model_request_rejected', 'The model rejected the request settings. Further execution was stopped.'
    if any(s in text for s in ('authentication', 'unauthorized', 'permissiondenied',
                               'error code: 401', 'error code: 403')):
        return 'model_access', 'The model rejected access. Check the deployment credentials and permissions.'
    transport_error = any(isinstance(e, (ConnectionError, TimeoutError)) for e in exception_chain(error))
    if transport_error or any(s in text for s in (
            'timeout', 'timed out', 'connectionerror', 'connection error', 'connection reset',
            'connecterror', 'readerror', 'remoteprotocolerror', 'server disconnected')):
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


def stop_execution(run_dir, stage, loop, error, *, code=None, message=None) -> NoReturn:
    kind, summary = failure_summary(error)
    record = dict(code=code or kind, message=message or summary, stage=stage, loop=loop,
                  exception_types=[type(e).__name__ for e in exception_chain(error)],
                  **provider_error_details(error),
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
        if failure.get('http_status') == 429 and failure.get('code') == 'model_request_rejected':
            return {**failure, 'code': 'model_rate_limit', 'message': (
                'The model service returned HTTP 429. This response does not establish '
                'a request-settings error; inspect the saved provider response. '
                'Saved results are retained; further execution was stopped.')}
        return failure
    if not include_legacy:
        return None
    # CLI validation can exit before execution.json or console.log exists.
    # Classify the captured startup log without exposing its raw arguments.
    if not (Path(run_dir) / 'execution.json').exists():
        try:
            with (Path(run_dir) / 'control.log').open('rb') as log:
                log.seek(0, 2)
                log.seek(max(0, log.tell() - 16384))
                tail = log.read().decode('utf-8', errors='replace')
            if 'board.py: error:' in tail:
                if 'skill does not match the selected corpus' in tail:
                    return {'code': 'startup_corpus_mismatch', 'stage': 'preflight', 'loop': None,
                            'message': 'Start validation rejected a skill/corpus mismatch before agent execution. '
                                       'Review the selected research source and matching skills. '
                                       'After correcting the configuration or application, start a new execution; '
                                       'this saved failed attempt remains in history.'}
                return {'code': 'startup_configuration_rejected', 'stage': 'preflight', 'loop': None,
                        'message': 'Start validation rejected the execution settings before agent execution. '
                                   'Review the saved control.log and correct the settings before starting again.'}
        except OSError:
            pass
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


def ensure_tasks_not_failed(run_dir, loop, tasks):
    """A terminal task failure must stop scheduling, never become a dry Loop."""
    failed = [task for task in tasks if task.get('status') == 'failed']
    if not failed:
        return
    stage = failed[0].get('task_type', '')
    label = {'data': 'Data preparation', 'ml': 'Model training and evaluation',
             'interpret': 'Interpretation'}.get(stage, 'An analysis stage')
    if run_dir:
        from memstara.pipeline.checkpoint import atomic_json
        atomic_json(Path(run_dir) / 'failed_tasks.json', {
            'loop': loop, 'tasks': [{k: t.get(k) for k in ('task_id', 'task_type', 'status')}
                                    for t in failed]})
    stop_execution(run_dir, stage, loop, RuntimeError('Terminal task failure'),
                   code='stage_task_failed',
                   message=f'{label} could not complete. Saved results are retained; further execution was stopped.')
