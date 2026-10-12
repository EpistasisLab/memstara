"""Bounded stage workers with completion-driven handoffs and cancellation cleanup."""
import asyncio


class StageWorkers:
    def __init__(self):
        self.active = {}
        self.last_slot = {}

    def progress_stage(self, tasks, *, seed_done):
        """Keep submitted work active until its agent invocation has settled.

        A tool can finish its board row before the model returns its final
        acknowledgement. Pending downstream rows are not evidence of activity.
        For overlapping workers, retain the earliest active pipeline stage.
        """
        order = ("hypothesis", "data", "ml", "interpreter")
        active = {stage for stage, _ in self.active}
        if not seed_done:
            active.add("hypothesis")
        if active:
            return next(stage for stage in order if stage in active)
        observed = ([task for task in tasks if task.get("status") == "in_progress"]
                    or [task for task in tasks if task.get("status") == "ready"])
        if observed:
            stage = observed[0]["task_type"]
            return "interpreter" if stage == "interpret" else stage
        return "report"

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
