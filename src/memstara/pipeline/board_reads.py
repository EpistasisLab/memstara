"""Bounded recovery of read-only board polls, with payload-free diagnostics."""

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

TRANSIENT = frozenset(
    {
        "TimeoutError",
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "ConnectionDoesNotExistError",
        "CannotConnectNowError",
        "TooManyConnectionsError",
        "ConnectionFailureError",
        "AdminShutdownError",
        "CrashShutdownError",
        "QueryCanceledError",
        "DeadlockDetectedError",
        "SerializationError",
    }
)


class BoardReadError(RuntimeError):
    def __init__(self, code, retryable=False):
        self.code = code
        self.retryable = retryable
        super().__init__(f"Blackboard read failed ({code}); task state is unavailable")


def response_error(state):
    code = state.get("error_type")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,80}", code):
        legacy = str(state.get("error", "")).split(":", 1)[0]
        code = legacy if legacy in TRANSIENT else "ApplicationError"
    return BoardReadError(code, code in TRANSIENT)


def audit(directory, attempt, state, code=None, **metadata):
    if directory is None:
        return
    import os

    descriptor = os.open(directory / "board_read_events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a") as stream:
        stream.write(
            json.dumps(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "attempt": attempt,
                    "state": state,
                    "error_type": code,
                    **metadata,
                }
            )
            + "\n"
        )


async def verified_read(invoke, *, directory=None, attempts=5, operation=None):
    import time
    from uuid import uuid4

    metadata = {"operation": operation, "correlation_id": str(uuid4())} if operation else {}
    for attempt in range(1, attempts + 1):
        cause: Exception | None = None
        began = time.monotonic()
        if operation:
            audit(directory, attempt, "started", **metadata)
        try:
            result = await invoke()
        except (TimeoutError, ConnectionError) as exc:
            cause = exc
            error = BoardReadError(type(exc).__name__, True)
        except BoardReadError as exc:
            cause = exc
            error = exc
        except Exception as exc:
            # MCP wraps its own timeout as McpError(ErrorData(code=408)), which
            # is not a Python TimeoutError. Retry only this known read-only case.
            code = getattr(getattr(exc, "error", None), "code", None)
            if type(exc).__name__ != "McpError" or code != 408:
                audit(
                    directory,
                    attempt,
                    "failed",
                    type(exc).__name__,
                    elapsed_seconds=time.monotonic() - began,
                    attempts_limit=attempts,
                    exception=exception_details(exc),
                    **metadata,
                )
                raise
            cause = exc
            error = BoardReadError("MCPRequestTimeout", True)
        else:
            if attempt > 1 or operation:
                audit(
                    directory,
                    attempt,
                    "recovered" if attempt > 1 else "completed",
                    elapsed_seconds=time.monotonic() - began,
                    **metadata,
                )
            return result
        retry = error.retryable and attempt < attempts
        audit(
            directory,
            attempt,
            "retry" if retry else "failed",
            error.code,
            elapsed_seconds=time.monotonic() - began,
            attempts_limit=attempts,
            retry_delay_seconds=min(attempt, 4) if retry else None,
            exception=exception_details(cause),
            **metadata,
        )
        if not retry:
            if cause is not error:
                raise error from cause
            raise error
        await asyncio.sleep(min(attempt, 4))


def exception_details(error, depth=0):
    """Keep nested failure locations/codes, never messages, locals or tool payloads."""
    import traceback

    record: dict[str, Any] = {
        "error_type": type(error).__name__,
        "frames": [
            {"file": f.filename, "line": f.lineno, "function": f.name}
            for f in traceback.extract_tb(error.__traceback__)
        ],
    }
    if isinstance(error, BoardReadError):
        record.update(board_error_code=error.code, retryable=error.retryable)
    code = getattr(getattr(error, "error", None), "code", None)
    if type(code) is int:
        record["mcp_code"] = code
        if code == 408:
            record["reason"] = "MCP response timeout"
    elif isinstance(error, TimeoutError):
        record["reason"] = "Operation exceeded its configured timeout"
    elif isinstance(error, ConnectionError):
        record["reason"] = "Transport connection failed"
    errno = getattr(error, "errno", None)
    if type(errno) is int:
        record["errno"] = errno
    sqlstate = getattr(error, "sqlstate", None)
    if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
        record["sqlstate"] = sqlstate
    from memstara.pipeline.failures import provider_error_details

    provider = provider_error_details(error)
    if provider:
        record["provider"] = provider
    if depth < 6:
        children = list(getattr(error, "exceptions", []))
        if children:
            record["children"] = [exception_details(child, depth + 1) for child in children[:16]]
            if len(children) > 16:
                record["omitted_children"] = len(children) - 16
        elif error.__cause__ is not None or error.__context__ is not None:
            record["cause"] = exception_details(error.__cause__ or error.__context__, depth + 1)
    elif getattr(error, "exceptions", None) or error.__cause__ or error.__context__:
        record["depth_limit_reached"] = True
    return record


def record_stop(directory, event, *, loop=None, stage=None, code=None, error=None, run_tag=None):
    """Append each stop reason, including later Resume failures, without payloads.

    Latest-status files may be replaced on Resume. This journal retains prior
    incidents; a last recorded call provides context and is not blamed as causal.
    """
    import os
    from pathlib import Path
    from uuid import uuid4

    if directory is None:
        return
    root = Path(directory)
    record = {
        "at": datetime.now(UTC).isoformat(),
        "event_id": str(uuid4()),
        "event": event,
        "code": code,
        "loop": loop,
        "stage": stage,
        "run_tag": run_tag,
    }
    try:
        calls = json.loads((root / "execution.json").read_text()).get("calls", [])
        if calls:
            last = calls[-1]
            record["last_recorded_call"] = {
                k: last.get(k) for k in ("run_id", "loop", "stage", "status", "started_at", "ended_at")
            }
            if loop is None:
                record["loop"] = last.get("loop")
                record["identity_source"] = "execution_manifest"
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if isinstance(error, BaseException):
        record["exceptions"] = exception_details(error)
    descriptor = os.open(root / "stop_events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a") as stream:
        stream.write(json.dumps(record) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return record
