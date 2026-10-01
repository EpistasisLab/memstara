"""Wrapped transport failures retain safe, actionable provenance."""
import json

import pytest

from memstara.pipeline.failures import (
    PipelineExecutionFailure, exception_chain, failure_summary, stop_execution,
)


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
