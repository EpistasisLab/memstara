"""Bounded recovery of read-only board polls, with payload-free diagnostics."""
import asyncio
import json
import re
from datetime import UTC, datetime

TRANSIENT = frozenset({
    'TimeoutError', 'ConnectionError', 'ConnectionResetError', 'ConnectionRefusedError',
    'ConnectionDoesNotExistError', 'CannotConnectNowError', 'TooManyConnectionsError',
    'ConnectionFailureError', 'AdminShutdownError', 'CrashShutdownError',
    'QueryCanceledError', 'DeadlockDetectedError', 'SerializationError',
})


class BoardReadError(RuntimeError):
    def __init__(self, code, retryable=False):
        self.code = code
        self.retryable = retryable
        super().__init__(f'Blackboard read failed ({code}); task state is unavailable')


def response_error(state):
    code = state.get('error_type')
    if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,80}', code):
        legacy = str(state.get('error', '')).split(':', 1)[0]
        code = legacy if legacy in TRANSIENT else 'ApplicationError'
    return BoardReadError(code, code in TRANSIENT)


def audit(directory, attempt, state, code=None):
    if directory is None:
        return
    with (directory / 'board_read_events.jsonl').open('a') as stream:
        stream.write(json.dumps({'at': datetime.now(UTC).isoformat(), 'attempt': attempt,
                                 'state': state, 'error_type': code}) + '\n')


async def verified_read(invoke, *, directory=None, attempts=5):
    for attempt in range(1, attempts + 1):
        try:
            result = await invoke()
        except (TimeoutError, ConnectionError) as exc:
            error = BoardReadError(type(exc).__name__, True)
        except BoardReadError as exc:
            error = exc
        else:
            if attempt > 1:
                audit(directory, attempt, 'recovered')
            return result
        retry = error.retryable and attempt < attempts
        audit(directory, attempt, 'retry' if retry else 'failed', error.code)
        if not retry:
            raise error
        await asyncio.sleep(min(attempt, 4))
