"""Wrapped transport failures retain safe, actionable provenance."""
import json

import pytest

from memstara.pipeline.failures import (
    PipelineExecutionFailure, exception_chain, failure_summary, stop_execution,
    provider_error_details, retryable_model_error, visible_failure,
)


def test_historical_429_display_is_corrected_without_changing_evidence(tmp_path):
    path = tmp_path / 'pipeline_failure.json'
    original = json.dumps({'code': 'model_request_rejected', 'http_status': 429,
                           'message': 'The model rejected the request settings.',
                           'stage': 'hypothesis0', 'loop': 1})
    path.write_text(original)
    shown = visible_failure(tmp_path)
    assert shown['code'] == 'model_rate_limit'
    assert 'does not establish' in shown['message']
    assert shown['stage'] == 'hypothesis0'
    assert path.read_text() == original


def provider_error(status, message='private payload'):
    import httpx
    from openai import APIStatusError
    response = httpx.Response(status, request=httpx.Request('POST', 'https://example.invalid'),
                              headers={'x-request-id': 'synthetic-request'})
    return APIStatusError(message, response=response,
                          body={'activityId': 'synthetic-activity', 'message': message})


@pytest.mark.parametrize('status', [500, 502, 503, 504, 529])
def test_wrapped_provider_server_status_is_retryable_and_safely_recorded(tmp_path, status):
    pytest.importorskip('openai')
    error = RuntimeError('wrapper')
    error.__cause__ = provider_error(status)
    assert retryable_model_error(error)
    assert failure_summary(error)[0] == 'model_server'
    with pytest.raises(PipelineExecutionFailure):
        stop_execution(tmp_path, 'hypothesis0', 1, error)
    record = json.loads((tmp_path / 'pipeline_failure.json').read_text())
    assert record['http_status'] == status
    assert record['provider_request_id'] == 'synthetic-request'
    assert record['provider_activity_id'] == 'synthetic-activity'
    assert 'private' not in json.dumps(record)


@pytest.mark.parametrize('status', [400, 401, 403, 404, 422, 429, 501, 505])
def test_nonretryable_status_overrides_misleading_error_text(status):
    pytest.importorskip('openai')
    # The response may echo a request containing words like timeout or HTTP 500.
    error = provider_error(status, 'timeout; error code: 500')
    assert not retryable_model_error(error)


def test_unsafe_correlation_values_are_not_persisted():
    pytest.importorskip('openai')
    error = provider_error(500)
    error.body['activityId'] = 'patient content / secret'
    assert 'provider_activity_id' not in provider_error_details(error)


@pytest.mark.parametrize('message', [
    'InternalServerError: OpenAIException - Connection error.',
    '[Errno 54] Connection reset by peer',
    'RemoteProtocolError: Server disconnected without sending a response',
])
def test_provider_transport_wrappers_are_not_generic_agent_failures(message):
    assert failure_summary(RuntimeError(message))[0] == 'model_connection'


def test_failure_chain_is_safe_and_cycle_bounded(tmp_path):
    underlying = ConnectionResetError('secret patient value or API key')
    wrapper = RuntimeError('wrapped')
    wrapper.__cause__ = underlying
    underlying.__context__ = wrapper
    assert len(list(exception_chain(wrapper))) == 2
    with pytest.raises(PipelineExecutionFailure):
        stop_execution(tmp_path, 'ml#1', 4, wrapper)
    payload = json.loads((tmp_path / 'pipeline_failure.json').read_text())
    assert payload['code'] == 'model_connection'
    assert payload['loop'] == 4
    assert payload['exception_types'] == ['RuntimeError', 'ConnectionResetError']
    assert 'secret' not in json.dumps(payload)


@pytest.mark.parametrize('message,code', [
    ('BadRequestError: 400', 'model_request_rejected'),
    ('AuthenticationError', 'model_access'),
    ('ValueError: invalid estimator', 'agent_execution_failed'),
])
def test_nontransport_failures_keep_their_meaning(message, code):
    assert failure_summary(RuntimeError(message))[0] == code


@pytest.mark.parametrize('wrapped_json', [False, True])
def test_azure_lookup_failure_is_retryable_without_claiming_bad_settings(wrapped_json):
    error = provider_error(429)
    body = {'error': {'code': 'rate_limiting_lookup_failed', 'message': 'private'}}
    if wrapped_json:
        error = provider_error(429, 'Azure_aiException - ' + json.dumps(body))
    else:
        error.body = body
    assert retryable_model_error(error)
    code, message = failure_summary(error)
    assert code == 'model_service_unavailable'
    assert 'private' not in message


def test_ordinary_quota_failure_is_not_misclassified_as_bad_settings():
    error = provider_error(429)
    error.body = {'error': {'code': 'insufficient_quota'}}
    assert not retryable_model_error(error)
    assert failure_summary(error)[0] == 'model_rate_limit'
@pytest.mark.parametrize('detail,code', [
    ('heart-failure-cardiovascular: Hypothesis skill does not match the selected corpus (general).',
     'startup_corpus_mismatch'),
    ('unrecognized arguments: PRIVATE_SENTINEL', 'startup_configuration_rejected'),
])
def test_startup_rejection_visible_without_execution_file_and_without_raw_values(tmp_path, detail, code):
    log = tmp_path / 'control.log'
    original = 'usage: board.py\nboard.py: error: ' + detail + '\n'
    log.write_text(original)
    result = visible_failure(tmp_path)
    assert result['code'] == code
    assert result['stage'] == 'preflight'
    assert 'PRIVATE_SENTINEL' not in str(result)
    assert visible_failure(tmp_path, include_legacy=False) is None
    assert log.read_text() == original
