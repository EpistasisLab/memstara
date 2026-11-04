"""Select unfinished original ordinals without renumbering combinations or seeds."""

import json


def validate_loops(value, total):
    if (
        type(total) is not int
        or not 1 <= total <= 10000
        or not isinstance(value, list)
        or not value
        or any(type(i) is not int or not 1 <= i <= total for i in value)
        or value != sorted(set(value))
    ):
        raise ValueError("Retry Loops must be unique sorted original ordinals within the saved schedule")
    return list(value)


def from_arguments(args, total):
    raw = getattr(args, "retry_loops", "")
    if not raw:
        return None
    if not getattr(args, "retry_source_run", ""):
        raise ValueError("Selective retry requires an original execution")
    loops = validate_loops(json.loads(raw), total)
    if getattr(args, "start_loop", 1) != loops[0]:
        raise ValueError("Selective retry must start at its first selected Loop")
    return loops


def pending_loops(outcomes, total, saved):
    if type(total) is not int or not 1 <= total <= 10000:
        raise ValueError("Invalid saved schedule size")
    raw = saved.get("retry_loops", "")
    if raw:
        candidates = validate_loops(json.loads(raw), total)
    else:
        start = saved.get("start_loop", 1)
        if type(start) is not int or not 1 <= start <= total:
            raise ValueError("Invalid original starting Loop")
        candidates = list(range(start, total + 1))
    allowed = {"completed", "blocked", "skipped", "interrupted", "analysis_complete", "running"}
    for key, value in outcomes.items():
        if (
            not isinstance(key, str)
            or not key.isdigit()
            or not 1 <= int(key) <= total
            or not isinstance(value, dict)
            or value.get("outcome") not in allowed
        ):
            raise ValueError("Invalid saved Loop outcome; review before selective retry")
    pending = [i for i in candidates if outcomes.get(str(i), {}).get("outcome") != "completed"]
    if not pending:
        raise ValueError("All selected combinations are already completed")
    return pending
