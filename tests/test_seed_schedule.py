"""Seed identity must survive serialization, order changes and missing records."""
import json
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
