"""Immutable seeds keyed by scientific condition and replicate, not execution order."""
import secrets

VERSION = 'recorded_replicate_seeds_v1'
POLICIES = ('shared_replicates', 'independent_pipelines')


def create(pipelines, replicates, policy):
    """Generate a complete schedule once; callers must persist it before execution."""
    if policy not in POLICIES:
        raise ValueError('Choose an explicit pipeline seed sharing policy')
    if any(type(n) is not int or n < 1 for n in (pipelines, replicates)):
        raise ValueError('Pipeline and replicate counts must be positive integers')
    count = replicates if policy == 'shared_replicates' else pipelines * replicates
    if count > 10000:
        raise ValueError('Seed schedule exceeds the supported 10000 executions')
    unique: set[int] = set()
    while len(unique) < count:
        unique.add(secrets.randbelow(2147483648))
    # Randomize assignment too: sorting would bias early replicate seeds lower.
    values = list(unique)
    secrets.SystemRandom().shuffle(values)
    rows = [values[:] if policy == 'shared_replicates'
            else values[p * replicates:(p + 1) * replicates] for p in range(pipelines)]
    return {'version': VERSION, 'policy': policy, 'pipelines': pipelines,
            'replicates': replicates, 'seeds': rows}


def seed_for(schedule, pipeline, replicate):
    """Never generate a replacement seed when metadata is missing or corrupted."""
    if schedule.get('version') != VERSION or schedule.get('policy') not in POLICIES:
        raise ValueError('Unsupported recorded seed schedule')
    count, repeats = schedule.get('pipelines'), schedule.get('replicates')
    if any(type(n) is not int or n < 1 for n in (count, repeats, pipeline, replicate)):
        raise ValueError('Invalid seed schedule coordinates')
    rows = schedule.get('seeds')
    if (not isinstance(rows, list) or len(rows) != count or
            any(not isinstance(row, list) or len(row) != repeats or
                any(type(seed) is not int or not 0 <= seed <= 2147483647 for seed in row)
                for row in rows)):
        raise ValueError('Recorded seed schedule is incomplete')
    if schedule['policy'] == 'shared_replicates' and any(row != rows[0] for row in rows):
        raise ValueError('Shared replicate seeds differ between pipelines')
    if pipeline > count or replicate > repeats:
        raise ValueError('Execution is outside the recorded seed schedule')
    return rows[pipeline - 1][replicate - 1]


def task_seed(snapshot, trial):
    """Resolve a task from its frozen schedule; retries retain the original ordinal."""
    if type(trial) is not int or trial < 0:
        raise ValueError('Task trial must be a non-negative integer')
    schedule = snapshot.get('seed_schedule')
    if not schedule:
        return None  # Historical agent-chosen seeds remain supported.
    plan = snapshot.get('combination_plan')
    if plan:
        from memstara.combinations import loop_flavors
        identity = loop_flavors(plan, trial + 1)
        return seed_for(schedule, identity['combination'], identity['repetition'])
    return seed_for(schedule, 1, trial + 1)
