"""Deterministic Cartesian skill schedules, without starting agents or spending tokens."""
from math import prod
import secrets

STAGES = ('hypothesis', 'data', 'ml', 'interpreter', 'report')


def build_plan(choices, repetitions=1, *, random_start=False, max_loops=None, start_index=None):
    """Each complete ordered combination is one Loop, repeated in stable cycles."""
    from memstara.control.catalog import resolve
    if not isinstance(choices, dict) or set(choices) != set(STAGES):
        raise ValueError('Select skills for all five agent roles')
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ValueError('Repetitions must be an integer from 1 to 100')
    if type(random_start) is not bool:
        raise ValueError('Random Start must be a boolean')
    if max_loops is not None and (type(max_loops) is not int or not 1 <= max_loops <= 10000):
        raise ValueError('Maximum Loops must be an integer from 1 to 10000')
    resolved = {}
    for stage in STAGES:
        ids = choices[stage]
        if stage == 'ml' and ids == []:
            ids = ['ml_default_logistic_regression']
        if not isinstance(ids, list) or not ids or not all(isinstance(x, str) for x in ids):
            raise ValueError(f'{stage}: choose at least one skill')
        entries, seen = [], set()
        for skill_id in ids:
            item = resolve(skill_id)
            if not item or item['stage'] != stage:
                raise ValueError(f'{skill_id}: not a skill for {stage}')
            if item['hash'] in seen:
                continue
            seen.add(item['hash'])
            entries.append({key: item[key] for key in ('id', 'title', 'hash')})
        resolved[stage] = entries
    count = prod(len(resolved[stage]) for stage in STAGES)
    total = count * repetitions if max_loops is None else max_loops
    if total > 10000:
        raise ValueError('At most 10000 combination Loops are supported')
    plan = {'version': 1, 'stages': list(STAGES), 'skills': resolved,
            'combinations': count, 'repetitions': repetitions, 'total_loops': total,
            'rows': max(len(items) for items in resolved.values())}
    if random_start or max_loops is not None:
        # Sample only at launch. Workspace validation passes zero; replay passes
        # the recorded index, so neither polling nor resume changes the schedule.
        if start_index is None:
            start_index = secrets.randbelow(count) if random_start else 0
        if type(start_index) is not int or not 0 <= start_index < count:
            raise ValueError('Start index is outside the combination space')
        if not random_start and start_index != 0:
            raise ValueError('Ordered execution must start at combination 1')
        plan.update(version=2, max_loops=max_loops, start_index=start_index,
                    selection_policy='random_start_then_cycle_v1' if random_start else 'ordered_cycle_v1')
    return plan


def validate_plan(plan):
    """Validate a frozen schedule without drawing a new random start."""
    if not isinstance(plan, dict) or plan.get('version') not in (1, 2):
        raise ValueError('Unsupported combination schedule')
    options = {}
    if plan['version'] == 2:
        policy = plan.get('selection_policy')
        if policy not in ('random_start_then_cycle_v1', 'ordered_cycle_v1'):
            raise ValueError('Unsupported combination selection policy')
        options = dict(random_start=policy == 'random_start_then_cycle_v1',
                       max_loops=plan['max_loops'], start_index=plan['start_index'])
        if type(options['start_index']) is not int:
            raise ValueError('Frozen schedule requires an integer start index')
    rebuilt = build_plan({stage: [s['id'] for s in entries]
                          for stage, entries in plan['skills'].items()}, plan['repetitions'], **options)
    if rebuilt != plan:
        raise ValueError('Combination schedule or skill versions changed; rebuild the design')
    return rebuilt


def loop_flavors(plan, loop):
    """Resolve a 1-based Loop without expanding the full Cartesian product in memory."""
    if type(loop) is not int or not 1 <= loop <= plan['total_loops']:
        raise ValueError('Loop is outside this schedule')
    index = (plan.get('start_index', 0) + loop - 1) % plan['combinations']
    remaining = index
    chosen = {}
    for stage in reversed(STAGES):
        variants = plan['skills'][stage]
        chosen[stage] = variants[remaining % len(variants)]
        remaining //= len(variants)
    return {'loop': loop, 'combination': index + 1,
            'repetition': (loop - 1) // plan['combinations'] + 1,
            **({'selection_policy': plan['selection_policy'], 'start_combination': plan['start_index'] + 1}
               if plan.get('version') == 2 else {}),
            'agents': [{'stage': stage, **chosen[stage]} for stage in STAGES]}


async def prepare_loop(plan, loop, *, provider, model, run_tag, provision, stage_models=None):
    """Bind each scheduled flavor to the actual provisioned agent identity."""
    flavors = loop_flavors(plan, loop)
    books = {item['stage']: [item['id']] for item in flavors['agents']}
    namespace = f"{run_tag}-combination-{flavors['combination']}"
    options = {"stage_models": stage_models} if stage_models else {}
    agents = await provision(provider=provider, model=model, playbooks=books, namespace=namespace, **options)
    for item in flavors['agents']:
        item['agent_id'] = str(agents[item['stage']])
    return agents, flavors, books, namespace


def task_books(config, trial):
    """Resolve task provenance from its zero-based trial, not the full skill catalog."""
    plan = config.get('combination_plan')
    if not plan:
        return config.get('books', {})
    return {item['stage']: [item['id']]
            for item in loop_flavors(plan, int(trial) + 1)['agents']}
