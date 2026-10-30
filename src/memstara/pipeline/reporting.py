"""Optional console output must not invalidate a persisted agent result."""

from memstara.pipeline.checkpoint import atomic_json
from memstara.pipeline.failures import exception_locations


async def show_console_summary(operation, entry, trace_dir):
    try:
        await operation(entry)
    except OSError as exc:
        if trace_dir is None:
            raise
        # Failure to persist this diagnostic remains a real storage failure.
        atomic_json(
            trace_dir / f"{entry['seq']:02d}_console_warning.json",
            {
                "stage": entry["stage"],
                "status": "console_unavailable",
                "exception_locations": exception_locations(exc),
            },
        )
