"""Round scheduling with cooperative pause and cancellation."""
import asyncio
import itertools
from pathlib import Path
from typing import TYPE_CHECKING
from contextvars import ContextVar

current_agent_gate: ContextVar[tuple["ExecutionGate", str] | None] = ContextVar("memstara_agent_gate", default=None)

if TYPE_CHECKING:
    from memstara.pipeline.checkpoint import Checkpoint


async def rounds(limit: int, continuous: bool, run_dir: Path, *, start=0):
    """Yield zero-based rounds; pause only between complete rounds."""
    for wave in (itertools.count(start) if continuous else range(start, limit)):
        while (run_dir / "pause.request").exists():
            await asyncio.sleep(1)
        yield wave


async def wait_for_new_questions(run_dir: Path, dry_streak: int):
    """Back off without holding DB connections; cancellation remains immediate."""
    delay = min(900, 60 * 2 ** min(max(dry_streak - 1, 0), 4))
    marker = run_dir / "questions.waiting"
    marker.touch()
    try:
        await asyncio.sleep(delay)
    finally:
        marker.unlink(missing_ok=True)


def write_progress(run_dir, iteration, stage, tasks=None, *, completed=False):
    """Publish stage-based progress; elapsed time never implies completion."""
    import json
    from datetime import UTC, datetime
    data = {"iteration": iteration, "stage": stage, "updated_at": datetime.now(UTC).isoformat()}
    stages = ("hypothesis", "data", "ml", "interpreter", "report")
    data["stage_percent"] = 100 if completed else (stages.index(stage) * 20 if stage in stages else None)
    data["iteration_completed"] = completed
    data["progress_basis"] = "Five equally weighted stages; not elapsed time"
    if tasks is not None:
        data["counts"] = {state: sum(t.get("status") == state for t in tasks)
                          for state in ("ready", "in_progress", "done", "failed")}
    summary = round_summary(run_dir)
    if summary is not None:
        data["exploration"] = summary
    target = run_dir / "progress.json"
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(data))
    temporary.replace(target)


def record_round(run_dir, iteration, outcome, reason=""):
    """Keep attempted rounds separate from verified end-to-end completion.

    A round is updated, not appended twice, so replaying a status write cannot
    inflate counts. Only the controller writes this journal; no agent prose enters it.
    """
    import json
    path = run_dir / "iteration_outcomes.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    import time
    previous = state.get(str(iteration), {})
    timing = {key: previous[key] for key in ('started_at', 'ended_at') if key in previous}
    if outcome == 'running':
        timing.setdefault('started_at', time.time())
        timing.pop('ended_at', None)
    elif outcome != 'analysis_complete':
        timing['ended_at'] = time.time()
    state[str(iteration)] = {"outcome": outcome, "reason": reason, **timing}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state))
    temporary.replace(path)


def round_summary(run_dir):
    import json
    path = run_dir / "iteration_outcomes.json"
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    latest = state[max(state, key=int)] if state else {}
    return {"attempted": len(state),
            "completed": sum(v["outcome"] == "completed" for v in state.values()),
            "blocked": sum(v["outcome"] == "blocked" for v in state.values()),
            "skipped": sum(v["outcome"] == "skipped" for v in state.values()),
            "outcome": latest.get("outcome"), "reason": latest.get("reason", "")}


def finalize_rounds(run_dir, report_completed):
    import json
    path = run_dir / "iteration_outcomes.json"
    if not path.exists():
        return
    for key, value in json.loads(path.read_text()).items():
        if value["outcome"] == "analysis_complete":
            record_round(run_dir, int(key), "completed" if report_completed else "blocked",
                         "" if report_completed else "Analysis saved; report did not complete.")


def close_active_round(run_dir, outcome, reason):
    """A stopped process must not leave its latest round labelled running."""
    import json
    summary = round_summary(run_dir)
    if not summary or summary["outcome"] not in ("running", "analysis_complete"):
        return
    progress_path = run_dir / "progress.json"
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    record_round(run_dir, summary["attempted"], outcome, reason)
    write_progress(run_dir, summary["attempted"], progress.get("stage", "hypothesis"))


class ExecutionGate:
    """Stop scheduling agent calls while retaining the live Python continuation.

    Tools and local fits finish before waiting. Versioned model-request pause
    cancels the provider await and retains the live agent's messages for resume.
    No model call is started while the durable pause marker exists. This is not
    process suspension: database transactions are never frozen with SIGSTOP.
    Durable driver checkpoints permit recovery at verified boundaries after a crash.
    """

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.active_calls = 0
        self.paused_calls: set[str] = set()
        self.checkpoint: Checkpoint | None = None
        self.publish()

    def publish(self):
        from memstara.pipeline.checkpoint import atomic_json
        requested = (self.run_dir / 'pause.request').exists()
        pending = self.active_calls > len(self.paused_calls)
        data = {'resumable': True, 'active_calls': self.active_calls,
                'paused_model_calls': len(self.paused_calls),
                'state': ('stopping' if pending else 'paused') if requested else 'running'}
        if data == getattr(self, '_last_state', None):
            return
        atomic_json(self.run_dir / 'execution_control.json', data)
        # Cache only confirmed publication; failed writes must be retried.
        self._last_state = data

    async def wait(self):
        from memstara.pipeline.run_ownership import require_ownership, await_ownership
        await await_ownership()
        require_ownership()
        while (self.run_dir / 'pause.request').exists():
            self.publish()
            await asyncio.sleep(.25)
            require_ownership()
        require_ownership()
        self.publish()

    async def call(self, operation, *args, **kwargs):
        await self.wait()
        import uuid
        call_key = uuid.uuid4().hex
        if self.checkpoint:
            self.checkpoint.call_started(call_key)
        self.active_calls += 1
        self.publish()
        binding = current_agent_gate.set((self, call_key))
        try:
            result = await operation(*args, **kwargs)
        finally:
            current_agent_gate.reset(binding)
            self.paused_calls.discard(call_key)
            self.active_calls -= 1
            self.publish()
        from memstara.pipeline.run_ownership import require_ownership
        require_ownership()
        if self.checkpoint:
            self.checkpoint.call_finished(call_key)
        # Durable drivers publish the enclosing phase result before the next call
        # waits. Legacy drivers retain the original in-memory continuation.
        if not self.checkpoint:
            await self.wait()
        return result
