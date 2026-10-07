"""Wrapped transport failures retain safe, actionable provenance."""
import json

import pytest

from memstara.pipeline.failures import (
    PipelineExecutionFailure, exception_chain, failure_summary, stop_execution,
    provider_error_details, retryable_model_error,
)


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
