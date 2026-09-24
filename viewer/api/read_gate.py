"""Coalesce expensive observer reads without cancelling another reader's work."""
import asyncio
import weakref
import time

_states = weakref.WeakKeyDictionary()


async def shared_read(key, read):
    loop = asyncio.get_running_loop()
    state = _states.setdefault(loop, (asyncio.Semaphore(1), {}, {}))
    gate, pending, settled = state
    hit = settled.get(key)
    if hit and time.monotonic() - hit[0] < 8:
        return hit[1]
    task = pending.get(key)
    if task is None:
        if len(pending) >= 32:
            raise TimeoutError('Too many distinct history reads are pending')

        async def bounded():
            async with asyncio.timeout(60):
                async with gate:
                    return await read()

        task = asyncio.create_task(bounded())
        pending[key] = task

        def finished(done):
            if pending.get(key) is done:
                pending.pop(key, None)
            if not done.cancelled():
                error = done.exception()
                if error is None:
                    if len(settled) >= 32:
                        settled.pop(min(settled, key=lambda k: settled[k][0]))
                    settled[key] = (time.monotonic(), done.result())

        task.add_done_callback(finished)
    return await asyncio.shield(task)
