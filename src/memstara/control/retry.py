"""Prepare a new attempt from the failed ordinal, never rewrite old evidence."""
import copy
import json
from pathlib import Path
from typing import Any


def configuration_for_retry(record, configuration, pipeline_id):
    root = Path(record['run_dir'])
    try:
        failure, saved, frozen, outcomes = [json.loads((root / name).read_text()) for name in
            ('pipeline_status.json', 'resume_arguments.json', 'config.json', 'iteration_outcomes.json')]
    except (OSError, ValueError) as exc:
        raise ValueError('Retry source records are unavailable or invalid') from exc
    if not all(isinstance(value, dict) for value in (failure, saved, frozen, outcomes)):
        raise ValueError('Retry source records are invalid')
    if saved.get('proposal_only'):
        raise ValueError('Proposal-only executions require a new execution')
    tag = record['run_tag']
    if saved.get('pipeline_id') != pipeline_id or saved.get('run_tag') != tag:
        raise ValueError('Retry source does not belong to this pipeline')
    loop = failure.get('loop')
    interrupted = failure.get('status') == 'interrupted'
    if interrupted:
        candidates = [int(key) for key, value in outcomes.items()
                      if key.isdigit() and value.get('outcome') == 'interrupted']
        if len(candidates) != 1:
            raise ValueError('A unique interrupted Loop is required for retry')
        loop = candidates[0]
    start = saved.get('start_loop', 1)
    end = saved.get('waves')
    if (failure.get('status') not in ('failed', 'interrupted') or type(loop) is not int or type(end) is not int
            or type(start) is not int or not 1 <= start <= loop <= end):
        raise ValueError('No failed Loop is available for retry')
    if any(outcomes.get(str(i), {}).get('outcome') != 'completed' for i in range(start, loop)):
        raise ValueError('Earlier unfinished Loops require review before retry')
    if outcomes.get(str(loop), {}).get('outcome') != ('interrupted' if interrupted else 'blocked'):
        raise ValueError('The failed Loop outcome is not confirmed')
    if configuration.get('research_input_id', '') != saved.get('research_input_id', ''):
        raise ValueError('Research source changed; use a separate new execution')
    result = copy.deepcopy(configuration)
    # Preserve original experimental settings; new attempt gets new artifacts and
    # a separate attempt identity, not a pretend continuation of trained models.
    for key in tuple(result):
        if key in saved:
            result[key] = copy.deepcopy(saved[key])
    # CLI snapshots encode structured flags as JSON strings; restore HTTP types.
    defaults: dict[str, Any] = {'evaluation': {}, 'ml_overrides': {},
                                'controlled_comparison': {}, 'baseline_columns': []}
    for key, default in defaults.items():
        value = result.get(key, default)
        if isinstance(value, str):
            try:
                result[key] = json.loads(value) if value.strip() else copy.deepcopy(default)
            except ValueError as exc:
                raise ValueError(f'Invalid saved {key} for retry') from exc
    result.update(waves=end, continuous=False, _retry_from_loop=loop, _retry_source_run=tag)
    plan = frozen.get('combination_plan')
    if plan:
        from memstara.combinations import validate_plan
        result['_retry_combination_plan'] = validate_plan(plan)
        result['combination_skills'] = {stage: [entry['id'] for entry in entries]
                                       for stage, entries in plan['skills'].items()}
    from memstara.seed_schedule import VERSION as seed_version
    if frozen.get('seed_policy') == seed_version and not frozen.get('seed_schedule'):
        raise ValueError('Original seed schedule is missing; restore it before retry')
    if frozen.get('seed_schedule'):
        result['_retry_seed_schedule'] = {key: copy.deepcopy(frozen[key]) for key in
                                          ('seed_schedule', 'dataset_sha256', 'y_column')}
    return result
