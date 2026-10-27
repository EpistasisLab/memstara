"""Meeting 17/18/22: manual split fractions and immutable per-execution seeds."""
import json
from types import SimpleNamespace

import pytest

from memstara import data_allocation, evaluation
from memstara.seed_schedule import freeze, sequential, seed_for


def test_manual_split_uses_user_fraction_and_server_seed_for_every_replicate(monkeypatch):
    draws = iter([178, 493, 821])
    monkeypatch.setattr("memstara.seed_schedule.secrets.randbelow", lambda _: next(draws))
    state = {'partition_policy': data_allocation.TWO_WAY_VERSION,
             'data_allocation_policy': {'version': data_allocation.TWO_WAY_VERSION},
             'evaluation': evaluation.validate({'seed': 708, 'test_size': .4}),
             'books': {}, 'prompts': {}, 'waves': 3, 'trials': 1}
    freeze(state, SimpleNamespace())
    assert state['seed_schedule']['policy'] == 'fixed_experiment_v1'
    assert state['seed_schedule']['seeds'][0] == [708, 708, 708]
    for trial in range(3):
        expected_seed = seed_for(state['seed_schedule'], 1, trial + 1)
        requested = data_allocation.request(state, trial)
        assert requested['required_data_plan'] == {'test_size': .4, 'seed': expected_seed, 'stratify': True}
        assert requested['population'] == 'entire_registered_dataset'
        with pytest.raises(ValueError, match='frozen'):
            data_allocation.validate({'test_size': .3, 'seed': expected_seed, 'stratify': True},
                                     requested, state['evaluation'])


def test_sequential_seeds_have_independent_bases_and_survive_round_trip():
    saved = json.loads(json.dumps(sequential(5, 4)))
    assert len({v for row in saved['seeds'] for v in row}) == 20
    for pipeline in range(1, 6):
        base = seed_for(saved, pipeline, 1)
        assert [seed_for(saved, pipeline, r) for r in range(1, 5)] == list(range(base, base + 4))
    with pytest.raises(ValueError, match='range'):
        sequential(1, 3, 2147483646)
    saved['seeds'][1][2] += 10
    with pytest.raises(ValueError, match='increase'):
        seed_for(saved, 2, 1)


def test_empty_data_selection_builds_manual_split_and_disallows_mixing():
    from memstara.combinations import build_plan
    choices = {'hypothesis': ['hypothesis_general'], 'data': [], 'ml': [],
               'interpreter': ['shared-shap'], 'report': ['report_general']}
    plan = build_plan(choices, 2)
    assert plan['skills']['data'][0]['id'] == 'data_manual_split'
    assert plan['combinations'] == 1
    with pytest.raises(ValueError, match='either'):
        build_plan({**choices, 'data': ['data_manual_split', 'data_training_heavy']})
