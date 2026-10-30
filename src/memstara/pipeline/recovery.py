"""Bounded recovery driven by persisted artifacts, never by agent prose."""

import asyncio
from memstara.pipeline.failures import PipelineExecutionFailure

MAX_ATTEMPTS = 2


async def ensure_artifact(invoke, present, *, attempts=MAX_ATTEMPTS):
    """Check before replay, including when a call failed after committing its work.

    A failed presence read propagates: uncertainty is not permission to replay a
    mutation. Cancellation also propagates immediately. Callers must additionally
    provide idempotent writes for the commit/check race.
    """
    if attempts < 1:
        raise ValueError("attempts must be positive")
    last_error = None
    for attempt in range(attempts):
        if await present():
            return True, None
        try:
            await invoke(attempt)
        except PipelineExecutionFailure:
            raise
        except Exception as exc:
            last_error = type(exc).__name__
        if await present():
            return True, None
        if attempt + 1 < attempts:
            await asyncio.sleep(0)  # cancellation checkpoint; no held DB connection
    return False, last_error or "No persisted artifact after bounded attempts"


def complete_interpretation(text):
    """Accept a substantive structured agent response, not a completion claim."""
    if not isinstance(text, str) or len(text.strip()) < 200:
        return False
    lowered = text.casefold().replace("**", "")
    return all(
        label in lowered
        for label in (
            "assessment:",
            "biological/clinical meaning:",
            "how the model uses the features:",
            "actionability and threshold:",
            "limitations and next validation:",
        )
    )
