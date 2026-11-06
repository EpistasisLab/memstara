"""Frozen model controls must reach Azure's proper native request format, without inference."""
import asyncio
from unittest.mock import AsyncMock

import pytest

pytest.importorskip('motoro')


@pytest.mark.parametrize('model,expected', [
    ('azure_ai/claude-synthetic', {'output_config': {'effort': 'high'}, 'temperature': .3}),
    ('azure_ai/gpt-synthetic', {'reasoning_effort': 'high', 'temperature': .3}),
])
def test_azure_sampling_survives_the_installed_motoro_adapter(monkeypatch, model, expected):
    from motoro.schemas.agent import ModelConfig
    from motoro.services import _sampling_transport as transport
    from motoro.services.llm_service import _sampling_kwargs

    config = ModelConfig(provider='azure_foundry', model=model.split('/', 1)[1],
        effort='high', temperature=.3,
        resolved_capabilities={'supports_effort': True, 'supports_temperature': True,
                               'effort_levels': ['high'], 'temperature_effort_levels': ['high']})
    sampling = _sampling_kwargs(config, model)
    delegate = type('Delegate', (), {'post': AsyncMock(return_value='synthetic response')})()
    captured = []

    async def adapter(**kwargs):
        if 'claude' in model:
            assert 'extra_body' not in kwargs
            await kwargs['client'].post('https://synthetic.invalid', json={'messages': []})
            body = delegate.post.await_args.kwargs['json']
        else:
            body = kwargs['extra_body']
        captured.append(body)
        return 'synthetic response'

    monkeypatch.setattr(transport.litellm, 'acompletion', adapter)
    result = asyncio.run(transport.acompletion(model=model, client=delegate, messages=[], **sampling))
    assert result == 'synthetic response'
    assert {key: value for key, value in captured[0].items() if key != 'messages'} == expected
