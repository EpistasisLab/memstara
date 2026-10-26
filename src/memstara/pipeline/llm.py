"""Adapt Memstara requests to Qwen without changing Motoro or stored messages."""
import asyncio
import copy
import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast
from uuid import uuid4

from tenacity import retry, stop_after_attempt

from motoro.services.llm_service import LLMService
from memstara.pipeline.runtime import provider_policy, runtime_timeouts, TRANSPORT_RETRY_DELAYS

_options: ContextVar[dict[str, Any] | None] = ContextVar('memstara_request_options', default=None)
_installed = False


class _RetryWrapped(Protocol):
    """Tenacity's runtime extension to Motoro's decorated async methods."""

    def retry_with(self, **kwargs: Any) -> Callable[..., Awaitable[Any]]: ...


def record_response(context, response, max_tokens):
    """Persist termination evidence without response text or tool arguments."""
    if not context:
        return
    choices = getattr(response, 'choices', []) or []
    usage = getattr(response, 'usage', None)
    from memstara.pipeline.diagnostics import request_id
    event = dict(at=datetime.now(UTC).isoformat(), run_id=context[1], stage=context[2],
                 request_id=request_id.get(),
                 response_id=getattr(response, 'id', None), max_tokens=max_tokens,
                 finish_reasons=[getattr(c, 'finish_reason', None) for c in choices],
                 completion_tokens=getattr(usage, 'completion_tokens', None))
    with (Path(context[0]) / 'model_response_outcomes.jsonl').open('a') as stream:
        stream.write(json.dumps(event) + '\n')


def interpretation_saved(messages):
    """Only a successful tool receipt establishes an already committed handoff."""
    submissions = set()
    for message in messages:
        for call in message.get('tool_calls', []) or []:
            if call.get('function', {}).get('name', '').endswith('submit_result'):
                submissions.add(call.get('id'))
        if message.get('role') == 'tool' and message.get('tool_call_id') in submissions:
            try:
                receipt = json.loads(message.get('content', ''))
            except (TypeError, ValueError):
                continue
            if isinstance(receipt, dict) and receipt.get('ok') is True and not receipt.get('error'):
                return True
    return False


def request_options(kwargs):
    options = _options.get()
    if options is None:
        return kwargs
    import httpx
    result = {**kwargs, 'num_retries': 0, 'max_retries': 0}
    # Motoro's capability table may lag the installed provider adapter. Use the
    # same local capability check as that adapter, including trial overrides.
    model = kwargs.get('model', '')
    if 'claude' in model.lower():
        from litellm.llms.anthropic.common_utils import AnthropicModelInfo
        if not AnthropicModelInfo._supports_sampling_params(model):
            removed = {key: result.pop(key) for key in ('temperature', 'top_p', 'top_k')
                       if key in result}
            if removed:
                from memstara.pipeline.diagnostics import call_context
                context = call_context.get()
                if context:
                    with (Path(context[0]) / 'model_request_adjustments.jsonl').open('a') as stream:
                        stream.write(json.dumps(dict(
                            at=datetime.now(UTC).isoformat(), stage=context[2],
                            run_id=context[1], model=model, omitted_sampling_parameters=removed,
                            reason='Installed Anthropic adapter disables sampling parameters',
                        )) + '\n')
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
            async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
                from memstara.pipeline.diagnostics import call_context
                record_response(call_context.get(), response_obj, kwargs.get('max_tokens'))

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
        return [{'role': 'system', 'content': content}, *messages[end:]]
    else:
        blocks: list[dict[str, Any]] = []
        for item in contents:
            blocks.extend([{'type': 'text', 'text': item}] if isinstance(item, str) else item)
    return [{'role': 'system', 'content': blocks}, *messages[end:]]


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
    from memstara.pipeline.diagnostics import request_id
    record = dict(at=datetime.now(UTC).isoformat(), run_id=context[1], stage=context[2],
                  loop=loop, request_id=request_id.get(), state=state,
                  attempt=attempt, max_attempts=6, delay_seconds=delay,
                  error_type=type(error).__name__ if error else None,
                  **provider_error_details(error))
    with (Path(context[0]) / 'model_retries.jsonl').open('a') as stream:
        stream.write(json.dumps(record) + '\n')
    print(f"Model request · {context[2]} · {state} · attempt {attempt}/6", flush=True)


class PipelineLLMService(LLMService):
    async def _request(self, method, config, messages, *args, **kwargs):
        from memstara.pipeline.diagnostics import call_context, call_loop, request_id, record_event
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
            attempt = 0
            resumed_from = None
            while attempt < 6:
                await request_ready(context)
                identity_token = request_id.set(str(uuid4()))
                started = time.monotonic()
                provider = getattr(getattr(config, 'provider', None), 'value', getattr(config, 'provider', None))
                record_event(context, 'started', attempt=attempt + 1,
                             resumed_from_request_id=resumed_from,
                             operation=getattr(method, '__name__', 'completion'),
                             model=config.model, provider=provider,
                             message_count=len(prepared),
                             requested_max_tokens=getattr(config, 'max_tokens', None),
                             timeout_policy=runtime_timeouts(config.model))
                from memstara.pipeline.request_evidence import save
                input_evidence = save(context, 'input', {
                    'messages': prepared, 'arguments': args, 'options': kwargs,
                    'model': config.model, 'provider': provider,
                    'temperature': getattr(config, 'temperature', None),
                    'configured_max_tokens': getattr(config, 'max_tokens', None),
                })
                record_event(context, 'input_saved' if input_evidence else 'input_unavailable',
                             evidence=input_evidence)
                from memstara.cost_accounting import record_attempt
                from memstara.pipeline.request_pause import invoke, RequestPaused, mark_waiting
                try:
                    if context:
                        from memstara.evaluation import active_plan
                        from memstara.stage_models import validate_call
                        validate_call(config, context[2], active_plan())
                    # Provider-level HTTP timeouts may be inactivity timers, and some
                    # adapters ignore them. Bound the whole awaited request as well so
                    # a dropped connection cannot leave the driver/checkpoint active
                    # indefinitely. Keep this per-attempt limit aligned with the
                    # frozen runtime policy; the existing bounded retry loop owns
                    # recovery and records each timed-out attempt.
                    call_timeout = runtime_timeouts(config.model).get('llm_call_timeout_seconds')
                    if call_timeout:
                        async with asyncio.timeout(call_timeout):
                            result = await invoke(
                                lambda: method(config, copy.deepcopy(prepared), *args, **kwargs), context)
                    else:
                        result = await invoke(lambda: method(config, copy.deepcopy(prepared), *args, **kwargs), context)
                except RequestPaused:
                    record_event(context, 'cancelled', duration_seconds=time.monotonic() - started,
                                 reason='user_pause', provider_outcome='unknown',
                                 resume_policy='fresh_model_request_v1')
                    record_attempt(context, call_loop.get(), config, interrupted=True)
                    resumed_from = request_id.get()
                    mark_waiting(True)
                    try:
                        await request_ready(context)
                    finally:
                        mark_waiting(False)
                    record_event(context, 'resume_requested', resume_policy='fresh_model_request_v1')
                    continue  # A user pause does not consume a transport retry.
                except Exception as exc:
                    from memstara.pipeline.failures import provider_error_details, exception_chain
                    record_event(context, 'failed', duration_seconds=time.monotonic() - started,
                                 error_types=[type(e).__name__ for e in exception_chain(exc)],
                                 retryable=retryable_model_error(exc),
                                 failure_evidence=save(context, 'failure', {
                                     'error_types': [type(e).__name__ for e in exception_chain(exc)],
                                     **provider_error_details(exc)}), **provider_error_details(exc))
                    record_attempt(context, call_loop.get(), config, error=True)
                    retryable = retryable_model_error(exc)
                    if retryable and attempt < len(TRANSPORT_RETRY_DELAYS):
                        delay = TRANSPORT_RETRY_DELAYS[attempt]
                        record_retry(context, call_loop.get(), 'retry_wait', attempt + 1, exc, delay)
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                    if retryable:
                        record_retry(context, call_loop.get(), 'exhausted', attempt + 1, exc)
                    if context:
                        stop_execution(context[0], context[2], call_loop.get(), exc)
                    raise
                except asyncio.CancelledError:
                    record_event(context, 'cancelled', duration_seconds=time.monotonic() - started)
                    raise
                else:
                    record = getattr(result, 'record', None)
                    if record is None and isinstance(result, tuple):
                        record = next((v for v in result if hasattr(v, 'cost_estimate')), None)
                    record_attempt(context, call_loop.get(), config, record)
                    record_event(context, 'completed', duration_seconds=time.monotonic() - started,
                                 output_evidence=save(context, 'output', result),
                                 response_model=getattr(record, 'model', None),
                                 prompt_tokens=getattr(record, 'prompt_tokens', None),
                                 completion_tokens=getattr(record, 'completion_tokens', None))
                    if attempt:
                        record_retry(context, call_loop.get(), 'recovered', attempt + 1)
                finally:
                    request_id.reset(identity_token)
                # A response may win the race with Pause. Keep its receipt and
                # output, but do not let Motoro execute its next tool until Resume.
                if context and (Path(context[0]) / 'pause.request').exists():
                    from memstara.evaluation import active_plan
                    if (active_plan() or {}).get('pause_policy') == 'fresh_model_request_v1':
                        mark_waiting(True)
                        try:
                            await request_ready(context)
                        finally:
                            mark_waiting(False)
                return result

    async def complete(self, config, messages, *args, **kwargs):
        return await self._request(super().complete, config, messages, *args, **kwargs)

    async def complete_text(self, config, messages, *args, **kwargs):
        return await self._request(super().complete_text, config, messages, *args, **kwargs)

    async def complete_with_tools(self, config, messages, tools, *args, **kwargs):
        # Motoro can return a completion with no tool calls and a validation
        # failure in its record. Returning it unchanged makes the agent appear
        # completed even though its proposed action never ran. Own this repair
        # loop separately from transport retries; never replay executed tools.
        from memstara.pipeline.diagnostics import call_context, call_loop
        from memstara.pipeline.failures import stop_execution
        history = copy.deepcopy(messages)
        current_config = config
        for attempt in range(6):
            result = await self._request(super().complete_with_tools, current_config, history,
                                         tools, *args, **kwargs)
            context = call_context.get()
            record = getattr(result, 'record', None)
            limit = max(getattr(current_config, 'max_tokens', 4096),
                        provider_policy(config.model).get('max_tokens', 0))
            capped = (getattr(record, 'completion_tokens', 0) or 0) >= limit
            empty_interpretation = (context and context[2].startswith('interpret')
                                    and not getattr(result, 'tool_calls', [])
                                    and not getattr(result, 'text', '').strip()
                                    and not interpretation_saved(history))
            if capped or empty_interpretation:
                # This completion has not reached Motoro's tool executor. Reissue
                # only this uncommitted turn, retaining every earlier tool receipt.
                next_limit = min(limit * 2, max(16384, getattr(config, 'max_tokens', 4096)))
                event = dict(at=datetime.now(UTC).isoformat(), stage=context[2] if context else None,
                             run_id=context[1] if context else None, attempt=attempt + 1,
                             max_attempts=6, reason='output_limit' if capped else 'empty_interpretation',
                             max_tokens=limit, next_max_tokens=next_limit,
                             state='retry' if attempt < 5 else 'exhausted')
                if context:
                    with (Path(context[0]) / 'model_completion_repairs.jsonl').open('a') as stream:
                        stream.write(json.dumps(event) + '\n')
                if attempt == 5:
                    message = 'The model did not finish a usable response within the bounded output-repair budget.'
                    if context:
                        stop_execution(context[0], context[2], call_loop.get(), ValueError(message),
                                       code='model_output_incomplete', message=message)
                    raise ValueError(message)
                current_config = copy.copy(current_config)
                current_config.max_tokens = next_limit
                history.append({'role': 'user', 'content': (
                    'Your previous response was incomplete and was not executed. '
                    'Use the existing tool results above; do not repeat successful actions. '
                    'Keep the response concise and complete the pending task through its required tool. '
                    'If an interpretation task is already claimed, call submit_result with the '
                    'required interpretation and task_id; do not claim it again. '
                    'Do not return an empty answer or invent missing evidence.'
                )})
                continue
            reason = getattr(getattr(result, 'record', None), 'failure_reason', None)
            if not reason:
                return result
            repairable = any(code in reason for code in
                             ('tool_args_schema_invalid', 'tool_args_parse_error'))
            context = call_context.get()
            if context:
                with (Path(context[0]) / 'tool_argument_repairs.jsonl').open('a') as stream:
                    stream.write(json.dumps(dict(
                        at=datetime.now(UTC).isoformat(), run_id=context[1], stage=context[2],
                        loop=call_loop.get(), attempt=attempt + 1, max_attempts=6,
                        state='retry' if repairable and attempt < 5 else 'exhausted',
                    )) + '\n')
            if not repairable or attempt == 5:
                message = ('The model did not produce a valid tool call. Further execution was '
                           'stopped; inspect the saved tool-argument validation trace.')
                if context:
                    stop_execution(context[0], context[2], call_loop.get(),
                                   ValueError('Tool argument validation failed'),
                                   code='tool_argument_validation', message=message)
                raise ValueError(message)
            history.extend([
                {'role': 'assistant', 'content': 'My proposed tool arguments were rejected before execution.'},
                {'role': 'user', 'content': (
                    f'Tool argument validation failed: {reason[:2000]}. '
                    'Re-issue the intended tool calls using the declared schema. '
                    'Object parameters (including filters) must be JSON objects, not '
                    'JSON-encoded strings. Use only allowed keys and values. Do not repeat '
                    'earlier successful actions; none of the rejected calls were executed.'
                )},
            ])

    # Preserve the upstream decorated-method interface without adding retries.
    # The request-level recovery loop remains the only transport retry owner.
    @retry(stop=stop_after_attempt(1), reraise=True)
    async def _complete(self, *args, **kwargs):
        return await cast(_RetryWrapped, LLMService._complete).retry_with(
            stop=stop_after_attempt(1))(self, *args, **kwargs)

    @retry(stop=stop_after_attempt(1), reraise=True)
    async def _complete_with_tools_once(self, *args, **kwargs):
        return await cast(_RetryWrapped, LLMService._complete_with_tools_once).retry_with(stop=stop_after_attempt(1))(
            self, *args, **kwargs)

    @retry(stop=stop_after_attempt(1), reraise=True)
    async def _complete_text(self, *args, **kwargs):
        return await cast(_RetryWrapped, LLMService._complete_text).retry_with(
            stop=stop_after_attempt(1))(self, *args, **kwargs)
