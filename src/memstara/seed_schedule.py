"""Immutable seeds keyed by scientific condition and replicate, not execution order."""

import json
import secrets

VERSION = "recorded_replicate_seeds_v1"
POLICIES = ("shared_replicates", "independent_pipelines")
SEQUENTIAL = "pipeline_sequence_v1"
FIXED = "fixed_experiment_v1"
INCREMENTING = "execution_sequence_v1"


def sequential(pipelines, replicates, base_seed=None):
    """Legacy schedule helper; new runs use independently drawn execution seeds."""
    if any(type(n) is not int or n < 1 for n in (pipelines, replicates)) or pipelines * replicates > 10000:
        raise ValueError("Invalid seed schedule dimensions")
    limit = 2147483648 - replicates
    if base_seed is not None and (type(base_seed) is not int or not 0 <= base_seed <= limit):
        raise ValueError("Starting seed plus replicates exceeds the supported seed range")
    bases = []
    for _ in range(pipelines):
        if base_seed is not None:
            bases.append(base_seed)
            continue
        candidate = secrets.randbelow(limit + 1)
        while any(abs(candidate - value) < replicates for value in bases):
            candidate = secrets.randbelow(limit + 1)
        bases.append(candidate)
    return {
        "version": VERSION,
        "policy": SEQUENTIAL,
        "pipelines": pipelines,
        "replicates": replicates,
        "seeds": [[s + r for r in range(replicates)] for s in bases],
    }


def create(pipelines, replicates, policy):
    """Generate a complete schedule once; callers must persist it before execution."""
    if policy not in POLICIES:
        raise ValueError("Choose an explicit pipeline seed sharing policy")
    if any(type(n) is not int or n < 1 for n in (pipelines, replicates)):
        raise ValueError("Pipeline and replicate counts must be positive integers")
    count = replicates if policy == "shared_replicates" else pipelines * replicates
    if count > 10000:
        raise ValueError("Seed schedule exceeds the supported 10000 executions")
    unique: set[int] = set()
    while len(unique) < count:
        unique.add(secrets.randbelow(2147483648))
    # Randomize assignment too: sorting would bias early replicate seeds lower.
    values = list(unique)
    secrets.SystemRandom().shuffle(values)
    rows = [
        values[:] if policy == "shared_replicates" else values[p * replicates : (p + 1) * replicates]
        for p in range(pipelines)
    ]
    return {"version": VERSION, "policy": policy, "pipelines": pipelines, "replicates": replicates, "seeds": rows}


def mode_schedule(pipelines, replicates, base_seed, *, manual, plan=None):
    """Manual fixed seeds, plus the historical incrementing schedule for replay."""
    if any(type(n) is not int or n < 1 for n in (pipelines, replicates)) or pipelines * replicates > 10000:
        raise ValueError("Invalid seed schedule dimensions")
    if type(base_seed) is not int or not 0 <= base_seed <= 2147483647:
        raise ValueError("Invalid starting seed")
    plan = plan or {}
    order = plan.get("execution_order", "all_pipelines_first")
    start = plan.get("start_index", 0)
    batch = plan.get("repetitions", replicates)
    if order not in ("all_pipelines_first", "pipeline_replicates_first"):
        raise ValueError("Invalid seed execution order")
    if type(start) is not int or not 0 <= start < pipelines or type(batch) is not int or batch < 1:
        raise ValueError("Invalid seed schedule order metadata")

    def position(p, r):
        offset = (p - start) % pipelines
        if order == "pipeline_replicates_first":
            cycle, within = divmod(r, batch)
            return cycle * pipelines * batch + offset * batch + within
        return r * pipelines + offset

    rows = [[base_seed if manual else base_seed + position(p, r) for r in range(replicates)] for p in range(pipelines)]
    if max(max(row) for row in rows) > 2147483647:
        raise ValueError("Starting seed plus scheduled executions exceeds the supported seed range")
    return {
        "version": VERSION,
        "policy": FIXED if manual else INCREMENTING,
        "pipelines": pipelines,
        "replicates": replicates,
        "base_seed": base_seed,
        "execution_order": order,
        "start_index": start,
        "repetitions": batch,
        "seeds": rows,
    }


def seed_for(schedule, pipeline, replicate):
    """Never generate a replacement seed when metadata is missing or corrupted."""
    if schedule.get("version") != VERSION or schedule.get("policy") not in (*POLICIES, SEQUENTIAL, FIXED, INCREMENTING):
        raise ValueError("Unsupported recorded seed schedule")
    count, repeats = schedule.get("pipelines"), schedule.get("replicates")
    if any(type(n) is not int or n < 1 for n in (count, repeats, pipeline, replicate)):
        raise ValueError("Invalid seed schedule coordinates")
    rows = schedule.get("seeds")
    if (
        not isinstance(rows, list)
        or len(rows) != count
        or any(
            not isinstance(row, list)
            or len(row) != repeats
            or any(type(seed) is not int or not 0 <= seed <= 2147483647 for seed in row)
            for row in rows
        )
    ):
        raise ValueError("Recorded seed schedule is incomplete")
    if schedule["policy"] == "shared_replicates" and any(row != rows[0] for row in rows):
        raise ValueError("Shared replicate seeds differ between pipelines")
    if schedule["policy"] in (FIXED, INCREMENTING):
        expected = mode_schedule(
            count, repeats, schedule.get("base_seed"), manual=schedule["policy"] == FIXED, plan=schedule
        )
        if rows != expected["seeds"]:
            raise ValueError("Recorded seeds do not match the frozen Data settings seed policy")
    if schedule["policy"] != FIXED and any(len(set(row)) != repeats for row in rows):
        raise ValueError("Replicates must have distinct recorded seeds")
    if schedule["policy"] == "independent_pipelines" and len({seed for row in rows for seed in row}) != count * repeats:
        raise ValueError("Independent executions must have distinct recorded seeds")
    if schedule["policy"] == SEQUENTIAL and any(row != list(range(row[0], row[0] + repeats)) for row in rows):
        raise ValueError("Pipeline seeds must increase by one per replicate")
    if pipeline > count or replicate > repeats:
        raise ValueError("Execution is outside the recorded seed schedule")
    return rows[pipeline - 1][replicate - 1]


def task_seed(snapshot, trial):
    """Resolve a task from its frozen schedule; retries retain the original ordinal."""
    if type(trial) is not int or trial < 0:
        raise ValueError("Task trial must be a non-negative integer")
    schedule = snapshot.get("seed_schedule")
    if not schedule:
        if snapshot.get("seed_policy") == VERSION:
            raise ValueError("Recorded seed schedule is missing; do not generate replacement seeds")
        return None  # Historical agent-chosen seeds remain supported.
    plan = snapshot.get("combination_plan")
    if plan:
        from memstara.combinations import loop_flavors

        identity = loop_flavors(plan, trial + 1)
        return seed_for(schedule, identity["combination"], identity["repetition"])
    return seed_for(schedule, 1, trial + 1)


def dimensions(snapshot):
    """Include the largest replicate ordinal in truncated or extended schedules."""
    plan = snapshot.get("combination_plan")
    if plan:
        from memstara.combinations import loop_flavors

        repeats = max(loop_flavors(plan, n)["repetition"] for n in range(1, plan["total_loops"] + 1))
        return plan["combinations"], repeats
    return 1, snapshot["waves"] * snapshot["trials"]


def freeze(snapshot, args, previous=None):
    """Attach the approved seed schedule before agents start, never redraw on resume."""
    if previous is not None:
        if previous.get("seed_policy") == VERSION and not previous.get("seed_schedule"):
            raise ValueError("Recorded seed schedule is missing; recovery requires the original record")
        if "seed_schedule" in previous:
            schedule = previous["seed_schedule"]
            seed_for(schedule, 1, 1)
            snapshot["seed_schedule"] = json.loads(json.dumps(schedule))
        if "seed_policy" in previous:
            snapshot["seed_policy"] = previous["seed_policy"]
        return  # Pre-policy records keep their original agent-selected seed behavior.
    if snapshot.get("partition_policy") != "two_way_stratified_v1" or snapshot.get("mode") == "report_only":
        return
    if getattr(args, "continuous", False):
        raise ValueError("Recorded replicate seeds require a finite number of replicates")
    count, repeats = dimensions(snapshot)
    recorded = json.loads(getattr(args, "retry_seed_schedule", "") or "null")
    if recorded is not None:
        if not getattr(args, "retry_source_run", ""):
            raise ValueError("A recorded retry seed schedule requires its source execution")
        if (
            recorded.get("dataset_sha256") != snapshot["dataset_sha256"]
            or recorded.get("y_column") != snapshot["y_column"]
        ):
            raise ValueError("Retry seed schedule belongs to a different dataset or target")
        schedule = recorded["seed_schedule"]
        seed_for(schedule, count, repeats)
        if (schedule["pipelines"], schedule["replicates"]) != (count, repeats):
            raise ValueError("Retry seed schedule differs from the original experiment dimensions")
    else:
        if getattr(args, "retry_source_run", ""):
            return  # A historical retry must not silently acquire a new schedule.
        plan = snapshot.get("combination_plan")
        data = [item["id"] for item in plan["skills"]["data"]] if plan else snapshot.get("books", {}).get("data", [])
        manual = not data or data == ["data_manual_split"]
        if "data_manual_split" in data and not manual:
            raise ValueError("Manual split cannot be mixed with Data skills")
        schedule = (
            mode_schedule(count, repeats, snapshot.get("evaluation", {}).get("seed", 42), manual=True, plan=plan)
            if manual
            else create(count, repeats, "independent_pipelines")
        )
    snapshot["seed_schedule"] = schedule
    snapshot["seed_policy"] = VERSION
