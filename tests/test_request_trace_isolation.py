"""Concurrent model calls must never drain another call's request evidence."""
import asyncio
import logging
from memstara.logging_setup import _LLMRequestGate, drain_llm_requests
from memstara.pipeline.diagnostics import call_context


def test_interleaved_calls_keep_their_own_requests(monkeypatch):
    monkeypatch.delenv('MEMSTARA_LLM_RAW', raising=False)
    gate = _LLMRequestGate()
    async def worker(name):
        token = call_context.set(('/test', name, 'hypothesis'))
        try:
            for n in range(3):
                gate.filter(logging.LogRecord('LiteLLM', logging.DEBUG, '', 0,
                    f'POST Request Sent from LiteLLM {name}:{n}', (), None))
                await asyncio.sleep(0)
        finally:
            call_context.reset(token)
    async def run():
        await asyncio.gather(worker('a'), worker('b'))
    asyncio.run(run())
    for name in ('a','b'):
        requests = drain_llm_requests(name)
        assert len(requests) == 3
        assert all(f'{name}:{n}' in msg for n,msg in enumerate(requests))
        assert drain_llm_requests(name) == []
