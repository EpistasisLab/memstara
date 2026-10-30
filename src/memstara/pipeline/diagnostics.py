"""Provider-response diagnostics without prompts, patient values or generated text."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

call_context: ContextVar[tuple[str | Path, str, str] | None] = ContextVar("memstara_call", default=None)
call_loop: ContextVar[int | None] = ContextVar("memstara_call_loop", default=None)
request_id: ContextVar[str | None] = ContextVar("memstara_request_id", default=None)
_installed = False


def record_event(context, state, **fields):
    """Append metadata before awaiting a provider; never accept payloads or errors as text.

    A failed writer must not replace the original provider error or successful result.
    The inspection command treats an absent/truncated journal as incomplete evidence.
    """
    if context is None:
        return False
    row = dict(
        at=datetime.now(UTC).isoformat(),
        schema_version=1,
        request_id=request_id.get(),
        run_id=str(context[1]),
        stage=context[2],
        loop=call_loop.get(),
        state=state,
        **fields,
    )
    try:
        with (Path(context[0]) / "request_events.jsonl").open("a") as stream:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
        return True
    except (OSError, ValueError, TypeError):
        logging.getLogger(__name__).warning("Request diagnostic write failed; audit evidence is incomplete")
        return False


def summarize(response, kwargs):
    choices = getattr(response, "choices", []) or []
    calls = []
    for choice in choices:
        for tool in getattr(choice.message, "tool_calls", []) or []:
            raw = tool.function.arguments or ""
            try:
                arguments = json.loads(raw)
                valid = isinstance(arguments, dict)
            except (TypeError, ValueError):
                arguments, valid = {}, False
            calls.append(
                {
                    "name": tool.function.name,
                    "argument_characters": len(raw),
                    "valid_json_object": valid,
                    "argument_keys": sorted(arguments) if valid else [],
                    "has_answer": valid and isinstance(arguments.get("answer"), str) and bool(arguments["answer"]),
                }
            )
    usage = getattr(response, "usage", None)
    return {
        "finish_reasons": [getattr(c, "finish_reason", None) for c in choices],
        "requested_max_tokens": kwargs.get("max_tokens"),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "tool_calls": calls,
    }


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
            record = {
                "at": datetime.now(UTC).isoformat(),
                "request_id": request_id.get(),
                "run_id": run_id,
                "stage": stage,
                "loop": call_loop.get(),
                **summarize(response_obj, kwargs),
            }
            with (Path(directory) / "provider_diagnostics.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\n")

    litellm.callbacks.append(Diagnostics())
    _installed = True
