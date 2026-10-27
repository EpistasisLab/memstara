"""One outcome-isolated scientific policy for newly frozen MVP experiments."""

import json
from typing import Any

VERSION = 'independent_replicates_v1'


def enabled(plan):
    return (plan or {}).get('experiment_policy', {}).get('version') == VERSION


def freeze(state, args: Any, previous=None):
    """Keep historical scientific contracts intact; new runs never learn from scores."""
    retry = getattr(args, 'retry_experiment_policy', '')
    if previous is None and getattr(args, 'retry_source_run', ''):
        if not retry:
            raise ValueError('Retry requires the original experiment policy; do not change feedback semantics')
        previous = json.loads(retry)
        if (previous.get('dataset_sha256'), previous.get('y_column')) != (
                state['dataset_sha256'], state['y_column']):
            raise ValueError('Retry experiment policy belongs to different inputs')
    if previous is not None:
        state['hypothesis_policy'] = previous.get('hypothesis_policy', {})
        if 'experiment_policy' in previous:
            state['experiment_policy'] = previous['experiment_policy']
        return
    if state.get('mode') == 'report_only' or state.get('controlled_comparison'):
        return
    if getattr(args, 'no_curator', False):
        raise ValueError('New MVP experiments require knowledge-driven question generation')
    if getattr(args, 'continuous', False):
        raise ValueError('New MVP experiments require a finite replicate schedule')
    state['experiment_policy'] = {
        'version': VERSION,
        'prior_outcome_feedback': False,
        'operational_records': 'retained_not_supplied_to_hypothesis',
        'question_scope': 'current_replicate',
    }
    state['hypothesis_policy'] = {
        **state['hypothesis_policy'], 'version': 'knowledge_only_v1',
        'kind': 'independent_combination', 'prior_ml_feedback': False,
        'refinement': 'none',
        'combination_questions': 'independent_combination_questions_v1',
    }
