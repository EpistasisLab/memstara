"""Bounded stage workers with completion-driven handoffs and cancellation cleanup."""
import asyncio


class StageWorkers:
    def __init__(self):
        self.active = {}
        self.last_slot = {}

    def available(self, stage, capacity, waiting, eligible=None):
        occupied = {slot for (kind, slot) in self.active if kind == stage}
        if capacity < 1 or waiting < 1:
            return []
        # Rotate even when tasks arrive one at a time, so later interpreter
        # skills do not starve behind the first slot. Busy slots are skipped.
        start = self.last_slot.get(stage, 0)
        order = [(start + offset) % capacity + 1 for offset in range(capacity)]
        return [slot for slot in order if slot not in occupied
                and (eligible is None or slot in eligible)][:waiting]

    def launch(self, stage, slot, coroutine):
        key = stage, slot
        if key in self.active:
            coroutine.close()
            raise RuntimeError(f"Worker {key} is already running")
        self.active[key] = asyncio.create_task(coroutine)
        self.last_slot[stage] = slot

    async def completed(self):
        finished = [key for key, task in self.active.items() if task.done()]
        results = await asyncio.gather(*(self.active.pop(key) for key in finished),
                                       return_exceptions=True)
        return list(zip(finished, results, strict=True))

    async def wait(self, interval=1.0):
        if self.active:
            await asyncio.wait(self.active.values(), timeout=interval,
                               return_when=asyncio.FIRST_COMPLETED)
        else:
            await asyncio.sleep(interval)

    async def close(self):
        for task in self.active.values():
            task.cancel()
        await asyncio.gather(*self.active.values(), return_exceptions=True)
        self.active.clear()
