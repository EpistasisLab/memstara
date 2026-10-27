"""Pause time is not agent execution time; ML waits are observable across processes."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import time


def pause_wrapper_settings(settings, policy):
    """Delegate wall-clock wrappers to the application's active-time watchdog.

    Motoro accepts integer wall-clock limits, not a pause clock. Its outer
    wrappers must not cancel a paused request/tool before active_timeout can
    supervise it. Actual provider attempts remain bounded in PipelineLLMService;
    active agent work and ML workers retain their own deadlines. This process
    owns one frozen execution, so all concurrent agents share this policy.
    """
    if policy != 'fresh_request_and_ml_restart_v2':
        return settings
    ceiling = 2147483647
    fields = ('llm_call_timeout_seconds', 'tool_timeout_seconds', 'hook_timeout_seconds')
    return settings.model_copy(update={key: ceiling for key in fields})


@asynccontextmanager
async def active_timeout(seconds, root):
    marker = Path(root) / 'pause.request' if root else None
    remaining = seconds
    async with asyncio.timeout(None) as timeout:
        async def watch():
            nonlocal remaining
            last = time.monotonic()
            was_paused = bool(marker and marker.exists())
            while True:
                now = time.monotonic()
                if not was_paused:
                    remaining -= now - last
                paused = bool(marker and marker.exists())
                # Check Pause before expiring the budget, including a pause at
                # the deadline boundary. Never leave a wall-clock alarm armed
                # while waiting for the next observation of the pause marker.
                if not paused and remaining <= 0:
                    timeout.reschedule(asyncio.get_running_loop().time())
                    return
                last, was_paused = now, paused
                await asyncio.sleep(min(.025, seconds / 4))
        watcher = asyncio.create_task(watch()) if seconds is not None else None
        try:
            yield
        finally:
            if watcher:
                watcher.cancel()
                try:
                    await watcher
                except asyncio.CancelledError:
                    pass


def ml_pause_count(root):
    """Ignore records from exited/reused process identities."""
    import psutil
    count = 0
    for path in (Path(root) / 'paused_ml').glob('*.json'):
        try:
            record = json.loads(path.read_text())
            if psutil.Process(record['pid']).create_time() == record['created']:
                count += 1
        except (OSError, ValueError, KeyError, psutil.Error):
            continue
    return count


def wait_for_ml_resume(marker, lock):
    """The worker is already dead. Release the global fit slot while paused."""
    import fcntl
    import psutil
    from memstara.pipeline.checkpoint import atomic_json
    folder = marker.parent / 'paused_ml'
    folder.mkdir(exist_ok=True)
    record = folder / f'{os.getpid()}.json'
    fcntl.flock(lock, fcntl.LOCK_UN)
    atomic_json(record, {'pid': os.getpid(), 'created': psutil.Process().create_time()})
    try:
        while True:
            while marker.exists():
                time.sleep(.1)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                time.sleep(.1)
                continue
            if not marker.exists():
                return
            fcntl.flock(lock, fcntl.LOCK_UN)
    finally:
        record.unlink(missing_ok=True)
