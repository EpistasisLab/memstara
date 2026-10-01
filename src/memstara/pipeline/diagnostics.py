"""Provider-response diagnostics without prompts, patient values or generated text."""
import json
from contextvars import ContextVar
from pathlib import Path

call_context = ContextVar('memstara_call', default=None)
call_loop = ContextVar('memstara_call_loop', default=None)
_installed = False


def summarize(response, kwargs):
    choices = getattr(response, 'choices', []) or []
    calls = []
    for choice in choices:
        for tool in getattr(choice.message, 'tool_calls', []) or []:
            raw = tool.function.arguments or ''
            try:
                arguments = json.loads(raw)
                valid = isinstance(arguments, dict)
            except (TypeError, ValueError):
                arguments, valid = {}, False
            calls.append({'name': tool.function.name, 'argument_characters': len(raw),
                          'valid_json_object': valid,
                          'argument_keys': sorted(arguments) if valid else [],
                          'has_answer': valid and isinstance(arguments.get('answer'), str)
                          and bool(arguments['answer'])})
    usage = getattr(response, 'usage', None)
    return {'finish_reasons': [getattr(c, 'finish_reason', None) for c in choices],
            'requested_max_tokens': kwargs.get('max_tokens'),
            'completion_tokens': getattr(usage, 'completion_tokens', None), 'tool_calls': calls}


def install():
    global _installed
    if _installed:
        return
    import litellm
    from litellm.integrations.custom_logger import CustomLogger

    class Diagnostics(CustomLogger):
        async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
            context = call_context.get()
            if context is None:
                return
            directory, run_id, stage = context
            record = {'run_id': run_id, 'stage': stage, **summarize(response_obj, kwargs)}
            with (Path(directory) / 'provider_diagnostics.jsonl').open('a') as stream:
                stream.write(json.dumps(record) + '\n')

    litellm.callbacks.append(Diagnostics())
    _installed = True
