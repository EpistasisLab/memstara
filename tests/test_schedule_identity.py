import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer' / 'api'))
from schedule_identity import identity


def test_full_cycles_keep_pipeline_and_replicate_distinct():
    config = {'combination_plan': {'combinations': 48, 'total_loops': 480}}
    assert identity(config, 49) == dict(pipeline_number=1, pipeline_count=48, replicate_number=2, replicate_count=10)
    assert identity(config, 480) == dict(pipeline_number=48, pipeline_count=48, replicate_number=10, replicate_count=10)


def test_random_start_and_partial_legacy_schedule():
    config = {'combination_plan': {'combinations': 4, 'total_loops': 6, 'start_index': 3}}
    assert identity(config, 1) == dict(pipeline_number=4, pipeline_count=4, replicate_number=1, replicate_count=2)
    assert identity(config, 4) == dict(pipeline_number=3, pipeline_count=4, replicate_number=1, replicate_count=1)
    assert identity(config, 5)['replicate_number'] == 2
    assert identity(config, 7) == {}


def test_single_pipeline_and_invalid_position():
    assert identity({'waves': 10}, 3)['replicate_number'] == 3
    for value in [None, 0, -1, True, 2.5]:
        assert identity({}, value) == {}


def test_display_matches_actual_scheduler_for_all_480_positions(monkeypatch):
    import memstara.control.catalog as catalog
    from memstara.combinations import STAGES, build_plan, loop_flavors
    choices = {stage: [f'{stage}-{i}' for i in range(3 if stage == 'hypothesis' else 2)] for stage in STAGES}
    monkeypatch.setattr(catalog, 'resolve', lambda name: {
        'id': name, 'stage': name.rsplit('-', 1)[0], 'title': name, 'hash': name})
    plan = build_plan(choices, 10, random_start=True, start_index=17)
    assert plan['combinations'] == 48 and plan['total_loops'] == 480
    for position in range(1, 481):
        actual = loop_flavors(plan, position)
        displayed = identity({'combination_plan': plan}, position)
        assert displayed['pipeline_number'] == actual['combination']
        assert displayed['replicate_number'] == actual['repetition']
        assert displayed['replicate_count'] == 10
