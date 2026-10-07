"""Adapt Memstara requests to Qwen without changing Motoro or stored messages."""
import asyncio
import copy
import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

from motoro.services.llm_service import LLMService
from memstara.pipeline.runtime import provider_policy, runtime_timeouts, TRANSPORT_RETRY_DELAYS

_options = ContextVar('memstara_request_options', default=None)
_installed = False


def request_options(kwargs):
    options = _options.get()
    if options is None:
        return kwargs
    import httpx
    result = {**kwargs, 'num_retries': 0, 'max_retries': 0}
    if runtime_timeouts(kwargs.get('model', '')):
        result['timeout'] = httpx.Timeout(1800, connect=15, read=1800, write=60, pool=15)
    if 'max_tokens' in options:
        result['max_tokens'] = max(kwargs.get('max_tokens') or 0, options['max_tokens'])
        result['extra_body'] = {**(kwargs.get('extra_body') or {}), **options['extra_body']}
    return result


@contextmanager
def request_scope(model):
    global _installed
    if not _installed:
        import litellm
        from litellm.integrations.custom_logger import CustomLogger
        class RequestPolicy(CustomLogger):
            async def async_pre_call_deployment_hook(self, kwargs, call_type):
                from memstara.pipeline.run_ownership import await_ownership
                await await_ownership()
                from memstara.pipeline.diagnostics import call_context
                from memstara.pipeline.failures import ensure_not_failed
                context = call_context.get()
                if _options.get() is not None and context:
                    ensure_not_failed(context[0])
                return request_options(kwargs)
        litellm.callbacks.append(RequestPolicy())
        _installed = True
    options = provider_policy(model)
    from memstara.pipeline.diagnostics import call_context
    context = call_context.get()
    if 'stage_reasoning_effort' in options and context and context[2].startswith('report'):
        options['extra_body']['reasoning_effort'] = options['stage_reasoning_effort']['report']
    token = _options.set(options)
    try:
        yield
    finally:
        _options.reset(token)


def provider_messages(messages, model):
    if not model.lower().rsplit('/', 1)[-1].startswith('qwen'):
        return list(messages)
    end = 0
    while end < len(messages) and messages[end].get('role') == 'system':
        end += 1
    if end < 2:
        return list(messages)
    contents = [m['content'] for m in messages[:end]]
    if all(isinstance(c, str) for c in contents):
        content = '\n\n'.join(contents)
    else:
        content = []
        for item in contents:
            content.extend([{'type': 'text', 'text': item}] if isinstance(item, str) else item)
    return [{'role': 'system', 'content': content}, *messages[end:]]


async def request_ready(context):
    """Respect user pause, another worker's failure, and execution ownership."""
    from memstara.pipeline.failures import ensure_not_failed
    from memstara.pipeline.run_ownership import await_ownership
    await await_ownership()
    if context:
        while True:
            ensure_not_failed(context[0])
            if not (Path(context[0]) / 'pause.request').exists():
                break
            await asyncio.sleep(.25)
            await await_ownership()


def record_retry(context, loop, state, attempt, error=None, delay=0):
    """Retain retry evidence without prompts, arguments, endpoints or credentials."""
    if not context:
        return
    from memstara.pipeline.failures import provider_error_details
    record = dict(at=datetime.now(UTC).isoformat(), run_id=context[1], stage=context[2],
                  loop=loop, state=state, attempt=attempt, max_attempts=6, delay_seconds=delay,
                  error_type=type(error).__name__ if error else None,
                  **provider_error_details(error))
    with (Path(context[0]) / 'model_retries.jsonl').open('a') as stream:
        stream.write(json.dumps(record) + '\n')
    print(f"Model request · {context[2]} · {state} · attempt {attempt}/6", flush=True)


class PipelineLLMService(LLMService):
    def __init__(self, *args, **kwargs):
        from memstara.pricing_compat import install
        install()
        super().__init__(*args, **kwargs)

    async def _request(self, method, config, messages, *args, **kwargs):
        from memstara.pipeline.diagnostics import call_context, call_loop
        from memstara.pipeline.failures import stop_execution, retryable_model_error
        if getattr(method, '__name__', '') in ('complete', 'complete_with_tools'):
            kwargs['max_retries'] = 0
        context = call_context.get()
        prepared = provider_messages(messages, config.model)
        if context and context[2] == 'report':
            from memstara.evaluation import active_plan
            if (active_plan() or {}).get('specialist_explanation_policy'):
                from memstara.specialist_explanation import record_model
                record_model(config, context, call_loop.get())
        with request_scope(config.model):
            for attempt in range(6):
                await request_ready(context)
                try:
                    if context:
                        from memstara.evaluation import active_plan
                        from memstara.stage_models import validate_call
                        validate_call(config, context[2], active_plan())
                    result = await method(config, copy.deepcopy(prepared), *args, **kwargs)
                except Exception as exc:
                    retryable = retryable_model_error(exc)
                    if retryable and attempt < len(TRANSPORT_RETRY_DELAYS):
                        delay = TRANSPORT_RETRY_DELAYS[attempt]
                        record_retry(context, call_loop.get(), 'retry_wait', attempt + 1, exc, delay)
                        await asyncio.sleep(delay)
                        continue
                    if retryable:
                        record_retry(context, call_loop.get(), 'exhausted', attempt + 1, exc)
                    if context:
                        stop_execution(context[0], context[2], call_loop.get(), exc)
                    raise
                if attempt:
                    record_retry(context, call_loop.get(), 'recovered', attempt + 1)
                return result

    async def complete(self, config, messages, *args, **kwargs):
        return await self._request(super().complete, config, messages, *args, **kwargs)

    async def complete_text(self, config, messages, *args, **kwargs):
        return await self._request(super().complete_text, config, messages, *args, **kwargs)

    async def complete_with_tools(self, config, messages, tools, *args, **kwargs):
        return await self._request(super().complete_with_tools, config, messages, tools, *args, **kwargs)

    async def _complete(self, *args, **kwargs):
        from tenacity import stop_after_attempt
        return await LLMService._complete.retry_with(stop=stop_after_attempt(1))(self, *args, **kwargs)

    async def _complete_with_tools_once(self, *args, **kwargs):
        from tenacity import stop_after_attempt
        return await LLMService._complete_with_tools_once.retry_with(stop=stop_after_attempt(1))(
            self, *args, **kwargs)

    async def _complete_text(self, *args, **kwargs):
        from tenacity import stop_after_attempt
        return await LLMService._complete_text.retry_with(stop=stop_after_attempt(1))(self, *args, **kwargs)
