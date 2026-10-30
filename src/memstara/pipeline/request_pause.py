"""Pause only an in-flight model request, never a tool call or local fit.

The live agent continuation owns its messages and completed tool results. Process
loss still requires checkpoint reconciliation; this does not authorize replay of
unknown tool side effects.
"""

import asyncio
from pathlib import Path

VERSION = "fresh_model_request_v1"
RESTART_ML_VERSION = "fresh_request_and_ml_restart_v2"


class RequestPaused(Exception):
    """The local provider coroutine stopped before returning a response."""


async def invoke(operation, context):
    from memstara.evaluation import active_plan

    enabled = context and (active_plan() or {}).get("pause_policy") in (VERSION, RESTART_ML_VERSION)
    if not enabled:
        return await operation()
    task = asyncio.create_task(operation())
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.1)
            # A returned response wins a simultaneous pause: retain it, do not
            # issue another paid request for an already completed response.
            if done:
                return task.result()
            if (Path(context[0]) / "pause.request").exists():
                task.cancel()
                try:
                    return await task
                except asyncio.CancelledError:
                    current = asyncio.current_task()
                    if current is not None and current.cancelling():
                        raise
                    raise RequestPaused() from None
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def mark_waiting(waiting):
    from memstara.pipeline.exploration import current_agent_gate

    binding = current_agent_gate.get()
    if binding is not None:
        gate, identity = binding
        from . import paused_recovery

        if gate.checkpoint and paused_recovery.enabled(gate.run_dir):
            metadata = gate.checkpoint.state.get("call_metadata", {}).get(identity)
            if waiting and metadata:
                paused_recovery.paused(gate.run_dir, identity, metadata)
            elif not waiting:
                paused_recovery.unpaused(gate.run_dir, identity)
        if waiting:
            gate.paused_calls.add(identity)
        else:
            gate.paused_calls.discard(identity)
        gate.publish()
