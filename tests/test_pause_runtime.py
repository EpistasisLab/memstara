"""Real process cancellation and active-time budgets, without provider calls."""
import asyncio
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from memstara.paired_ml import FitPaused, supervise
from memstara.pipeline.pause_runtime import active_timeout, ml_pause_count, wait_for_ml_resume


def test_outer_framework_deadlines_do_not_cancel_a_long_pause(tmp_path):
    from motoro import CoreSettings
    from memstara.pipeline.pause_runtime import pause_wrapper_settings
    original = CoreSettings().model_copy(update={'tool_timeout_seconds': .05,
                'llm_call_timeout_seconds': .05, 'hook_timeout_seconds': .05})
    settings = pause_wrapper_settings(original, 'fresh_request_and_ml_restart_v2')
    assert pause_wrapper_settings(original, 'fresh_model_request_v1') is original
    async def scenario():
        marker = tmp_path/'pause.request'
        async def paused_work():
            marker.touch()
            await asyncio.sleep(.3)
            marker.unlink()
            await asyncio.sleep(.02)
            return 'saved output'
        async with active_timeout(.15, tmp_path):
            result = await asyncio.wait_for(asyncio.wait_for(asyncio.wait_for(
                paused_work(), settings.tool_timeout_seconds),
                settings.llm_call_timeout_seconds), settings.hook_timeout_seconds)
            assert result == 'saved output'
    asyncio.run(scenario())


def test_paused_time_does_not_expire_agent_budget(tmp_path):
    async def scenario():
        marker = tmp_path / 'pause.request'
        async with active_timeout(.15, tmp_path):
            marker.touch()
            await asyncio.sleep(.4)
            marker.unlink()
            await asyncio.sleep(.03)
        with pytest.raises(TimeoutError):
            async with active_timeout(.05, tmp_path):
                await asyncio.sleep(.3)
    asyncio.run(scenario())


def test_external_cancellation_during_pause_is_preserved(tmp_path):
    async def scenario():
        (tmp_path/'pause.request').touch()
        started = asyncio.Event()
        async def work():
            async with active_timeout(.1, tmp_path):
                started.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(work())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())


def test_pause_kills_incomplete_worker_but_preserves_completed_output(tmp_path):
    marker, output = tmp_path/'pause.request', tmp_path/'result.json'
    pid_file = tmp_path/'pid'
    command = [sys.executable, '-c',
               'import os,time; from pathlib import Path; '
               f'Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(30)']
    def pause():
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        marker.touch()
    thread = threading.Thread(target=pause)
    thread.start()
    try:
        with pytest.raises(FitPaused):
            supervise(command, env=os.environ.copy(), limits={}, pause_marker=marker, output_path=output)
    finally:
        thread.join()
    import psutil
    assert not psutil.pid_exists(int(pid_file.read_text()))
    assert not output.exists()
    # A published complete result wins a simultaneous pause.
    output.write_text('{"complete":true}')
    supervise([sys.executable, '-c', 'pass'], env=os.environ.copy(), limits={},
              pause_marker=marker, output_path=output)
    assert output.read_text() == '{"complete":true}'


def test_paused_fit_releases_global_lock_and_publishes_wait(tmp_path):
    import fcntl
    marker = tmp_path/'pause.request'
    marker.touch()
    checked = []
    def resume():
        deadline = time.monotonic()+5
        while not ml_pause_count(tmp_path) and time.monotonic()<deadline:
            time.sleep(.01)
        with (tmp_path/'fit.lock').open('a') as other:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            checked.append(True)
        marker.unlink()
    with (tmp_path/'fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        thread = threading.Thread(target=resume)
        thread.start()
        wait_for_ml_resume(marker, lock)
        thread.join()
    assert checked == [True]
    assert ml_pause_count(tmp_path) == 0
