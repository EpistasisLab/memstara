"""Seed identity must survive serialization, order changes and missing records."""
import json
from types import SimpleNamespace
import pytest
from memstara.seed_schedule import create, seed_for


@pytest.mark.parametrize('policy', ['shared_replicates', 'independent_pipelines'])
def test_persisted_seeds_are_independent_of_execution_order(policy):
    schedule = create(3, 4, policy)
    restored = json.loads(json.dumps(schedule))
    round_robin = {(p, r): seed_for(schedule, p, r) for r in range(1, 5) for p in range(1, 4)}
    pipeline_first = {(p, r): seed_for(restored, p, r) for p in range(1, 4) for r in range(1, 5)}
    assert round_robin == pipeline_first
    assert len(set(round_robin.values())) == (4 if policy == 'shared_replicates' else 12)
    restored['seeds'][0].pop()
    with pytest.raises(ValueError, match='incomplete'):
        seed_for(restored, 1, 1)


def test_policy_and_coordinates_are_explicit():
    with pytest.raises(ValueError, match='explicit'):
        create(2, 3, None)
    schedule = create(2, 3, 'shared_replicates')
    with pytest.raises(ValueError, match='outside'):
        seed_for(schedule, 3, 1)
    schedule['seeds'][1][0] += 1
    with pytest.raises(ValueError, match='differ'):
        seed_for(schedule, 1, 1)


def experiment(order):
    stages = ['hypothesis', 'data', 'ml', 'interpreter', 'report']
    return {'partition_policy': 'two_way_stratified_v1', 'mode': 'pipeline',
            'dataset_sha256': 'input-hash', 'y_column': 'outcome', 'waves': 6, 'trials': 1,
            'combination_plan': {'combinations': 2, 'repetitions': 3, 'total_loops': 6,
                'execution_order': order, 'skills': {s: [{'id': 'a'}, {'id': 'b'}] if s == 'ml'
                    else [{'id': s}] for s in stages}}}


def test_shared_schedule_freezes_once_and_replays_both_orders(monkeypatch):
    from memstara.seed_schedule import freeze, task_seed
    from memstara.combinations import loop_flavors
    first = experiment('all_pipelines_first')
    args = SimpleNamespace(continuous=False)
    freeze(first, args)
    assert first['seed_schedule']['policy'] == 'shared_replicates'
    original = json.loads(json.dumps(first))
    def no_redraw(*args, **kwargs):
        pytest.fail('Seeds were redrawn during resume/retry')
    monkeypatch.setattr('memstara.seed_schedule.create', no_redraw)
    resumed = experiment('all_pipelines_first')
    freeze(resumed, args, original)
    assert resumed == original
    retry = experiment('pipeline_replicates_first')
    args.retry_source_run = 'original-run'
    args.retry_seed_schedule = json.dumps({k: original[k] for k in
                                          ('seed_schedule', 'dataset_sha256', 'y_column')})
    freeze(retry, args)
    for state in (original, resumed, retry):
        for trial in range(6):
            identity = loop_flavors(state['combination_plan'], trial + 1)
            assert task_seed(state, trial) == original['seed_schedule']['seeds'][0][identity['repetition'] - 1]


@pytest.mark.parametrize('field,value', [('dataset_sha256', 'changed'), ('y_column', 'changed'),
                                        ('seed_schedule', {'version': 'invalid'})])
def test_retry_rejects_changed_input_and_corrupt_seeds(field, value):
    from memstara.seed_schedule import freeze
    state = experiment('all_pipelines_first')
    freeze(state, SimpleNamespace())
    record = {k: state[k] for k in ('seed_schedule', 'dataset_sha256', 'y_column')}
    record[field] = value
    with pytest.raises(ValueError):
        freeze(experiment('all_pipelines_first'), SimpleNamespace(
            retry_source_run='original', retry_seed_schedule=json.dumps(record)))


def test_missing_seed_record_blocks_new_policy_but_preserves_history():
    from memstara.seed_schedule import freeze, task_seed, VERSION
    assert task_seed({}, 0) is None
    historical = experiment('all_pipelines_first')
    freeze(historical, SimpleNamespace(), historical.copy())
    assert 'seed_schedule' not in historical
    with pytest.raises(ValueError, match='missing'):
        task_seed({'seed_policy': VERSION}, 0)
    with pytest.raises(ValueError, match='missing'):
        freeze({}, SimpleNamespace(), {'seed_policy': VERSION})


def test_ordinary_run_preallocates_all_trials_and_rejects_unbounded_schedule():
    from memstara.seed_schedule import freeze, task_seed
    state = {**experiment('all_pipelines_first'), 'combination_plan': None, 'waves': 2, 'trials': 3}
    with pytest.raises(ValueError, match='finite'):
        freeze(state, SimpleNamespace(continuous=True))
    freeze(state, SimpleNamespace())
    assert len({task_seed(state, n) for n in range(6)}) == 6


def test_shared_seed_produces_same_rows_only_for_same_split_contract(monkeypatch):
    import pandas as pd
    import numpy as np
    from memstara import evaluation
    monkeypatch.setattr(evaluation, 'active_plan', lambda: {})
    labels = pd.Series([0, 1] * 100)
    schedule = create(2, 2, 'shared_replicates')
    seen = []
    for replicate in (1, 2):
        splits = []
        for pipeline, engine in [(1, 'logistic_regression'), (2, 'xgboost')]:
            plan = evaluation.validate({'engine': engine, 'seed': seed_for(schedule, pipeline, replicate),
                                        'test_size': .3})
            splits.append(evaluation.evaluation_splits(labels, plan)[0])
        assert np.array_equal(splits[0][1], splits[1][1])
        assert np.array_equal(splits[0][2], splits[1][2])
        seen.append(splits[0][2])
    assert not np.array_equal(seen[0], seen[1])
    balanced = evaluation.validate({'seed': seed_for(schedule, 1, 1), 'test_size': .5})
    assert len(evaluation.evaluation_splits(labels, balanced)[0][2]) != len(seen[0])
