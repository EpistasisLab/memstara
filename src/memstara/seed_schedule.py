"""Immutable seeds keyed by scientific condition and replicate, not execution order."""
import json
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
    if len(set(rows[0])) != repeats:
        raise ValueError('Replicates must have distinct recorded seeds')
    if pipeline > count or replicate > repeats:
        raise ValueError('Execution is outside the recorded seed schedule')
    return rows[pipeline - 1][replicate - 1]


def task_seed(snapshot, trial):
    """Resolve a task from its frozen schedule; retries retain the original ordinal."""
    if type(trial) is not int or trial < 0:
        raise ValueError('Task trial must be a non-negative integer')
    schedule = snapshot.get('seed_schedule')
    if not schedule:
        if snapshot.get('seed_policy') == VERSION:
            raise ValueError('Recorded seed schedule is missing; do not generate replacement seeds')
        return None  # Historical agent-chosen seeds remain supported.
    plan = snapshot.get('combination_plan')
    if plan:
        from memstara.combinations import loop_flavors
        identity = loop_flavors(plan, trial + 1)
        return seed_for(schedule, identity['combination'], identity['repetition'])
    return seed_for(schedule, 1, trial + 1)


def dimensions(snapshot):
    """Include the largest replicate ordinal in truncated or extended schedules."""
    plan = snapshot.get('combination_plan')
    if plan:
        from memstara.combinations import loop_flavors
        repeats = max(loop_flavors(plan, n)['repetition'] for n in range(1, plan['total_loops'] + 1))
        return plan['combinations'], repeats
    return 1, snapshot['waves'] * snapshot['trials']


def freeze(snapshot, args, previous=None):
    """Attach the approved seed schedule before agents start, never redraw on resume."""
    if previous is not None:
        if previous.get('seed_policy') == VERSION and not previous.get('seed_schedule'):
            raise ValueError('Recorded seed schedule is missing; recovery requires the original record')
        if 'seed_schedule' in previous:
            snapshot['seed_schedule'] = previous['seed_schedule']
        if 'seed_policy' in previous:
            snapshot['seed_policy'] = previous['seed_policy']
        return  # Pre-policy records keep their original agent-selected seed behavior.
    if snapshot.get('partition_policy') != 'two_way_stratified_v1' or snapshot.get('mode') == 'report_only':
        return
    if getattr(args, 'continuous', False):
        raise ValueError('Recorded replicate seeds require a finite number of replicates')
    count, repeats = dimensions(snapshot)
    recorded = json.loads(getattr(args, 'retry_seed_schedule', '') or 'null')
    if recorded is not None:
        if not getattr(args, 'retry_source_run', ''):
            raise ValueError('A recorded retry seed schedule requires its source execution')
        if (recorded.get('dataset_sha256') != snapshot['dataset_sha256']
                or recorded.get('y_column') != snapshot['y_column']):
            raise ValueError('Retry seed schedule belongs to a different dataset or target')
        schedule = recorded['seed_schedule']
        seed_for(schedule, count, repeats)
        if (schedule['pipelines'], schedule['replicates'], schedule['policy']) != (
                count, repeats, 'shared_replicates'):
            raise ValueError('Retry seed schedule differs from the original experiment dimensions')
    else:
        if getattr(args, 'retry_source_run', ''):
            return  # A historical retry must not silently acquire a new schedule.
        schedule = create(count, repeats, 'shared_replicates')
    snapshot['seed_schedule'] = schedule
    snapshot['seed_policy'] = VERSION
