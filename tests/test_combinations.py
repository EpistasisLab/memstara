import asyncio
from collections import Counter
import pytest
from memstara.combinations import STAGES, build_plan, loop_flavors, prepare_loop
from memstara.control import catalog


@pytest.fixture
def skills(monkeypatch):
    counts = [2, 3, 2, 2, 1]
    entries = {f'{stage}-{i}': {'id': f'{stage}-{i}', 'title': f'{stage} {i}',
                              'stage': stage, 'hash': f'{stage}-hash-{i}'}
               for stage, count in zip(STAGES, counts, strict=True) for i in range(count)}
    monkeypatch.setattr(catalog, 'resolve', lambda key: entries.get(key, {}))
    return {stage: [key for key in entries if entries[key]['stage'] == stage] for stage in STAGES}


def test_twenty_four_combinations_three_rows_repeat_exactly(skills):
    plan = build_plan(skills, 2)
    assert (plan['combinations'], plan['rows'], plan['total_loops']) == (24, 3, 48)
    loops = [loop_flavors(plan, n) for n in range(1, 49)]
    assert set(Counter(tuple(a['id'] for a in row['agents']) for row in loops).values()) == {2}
    assert all([a['stage'] for a in row['agents']] == list(STAGES) for row in loops)
    assert loops[24]['combination'] == 1 and loops[24]['repetition'] == 2


def test_duplicates_do_not_add_rows_or_loops(skills):
    skills['data'] += skills['data']
    assert build_plan(skills)['combinations'] == 24


def test_wrong_roles_rejected(skills):
    skills['data'] = skills['ml']
    with pytest.raises(ValueError):
        build_plan(skills)


def test_resume_selects_same_flavors_and_actual_agent_ids(skills):
    plan = build_plan(skills, 2)
    seen = []
    async def provision(**kwargs):
        seen.append(kwargs)
        assert all(len(ids) == 1 for ids in kwargs['playbooks'].values())
        return {stage: f'actual-{stage}' for stage in STAGES}
    agents, flavors, books, namespace = asyncio.run(prepare_loop(
        plan, 27, provider='test', model='test', run_tag='run', provision=provision))
    assert flavors['combination'] == 3
    assert flavors['repetition'] == 2
    assert all(a['agent_id'] == agents[a['stage']] for a in flavors['agents'])
    assert books == seen[0]['playbooks']
    assert namespace == 'run-combination-3'


def test_workspace_and_launch_preserve_full_schedule(skills, monkeypatch):
    import json
    from memstara.control.workspace import PipelineWorkspace
    from memstara.control.request import build_argv
    for role in ('QUESTION', 'HYPOTHESIS', 'DATA', 'ML', 'INTERPRETATION', 'EXPLANATION'):
        monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER', 'openai')
        monkeypatch.setenv(f'MEMSTARA_{role}_MODEL', 'test-model')
    config = PipelineWorkspace.configuration({'combination_skills': skills, 'combination_repetitions': 2})
    assert config['waves'] == 48
    assert config['trials'] == config['hypothesis_agents'] == config['interpret_agents'] == 1
    argv = build_argv(config, [], [key for ids in skills.values() for key in ids], STAGES)
    assert argv[argv.index('--waves') + 1] == '48'
    frozen = json.loads(argv[argv.index('--combination-plan') + 1])
    assert frozen['rows'] == 3 and frozen['total_loops'] == 48


def test_selected_pipeline_limits_unchanged():
    from memstara.control.workspace import PipelineWorkspace
    with pytest.raises(ValueError):
        PipelineWorkspace.configuration({'waves': 24})
    assert PipelineWorkspace.configuration({'waves': 4})['waves'] == 4


def test_task_provenance_tracks_current_combination(skills):
    from memstara.combinations import task_books
    config = {'combination_plan': build_plan(skills, 2), 'books': skills}
    for trial in range(48):
        books = task_books(config, trial)
        assert all(len(ids) == 1 for ids in books.values())
        assert books == {a['stage']: [a['id']] for a in loop_flavors(config['combination_plan'], trial + 1)['agents']}
    assert task_books(config, 0)['interpreter'] != task_books(config, 1)['interpreter']
    assert task_books({'books': skills}, 99) == skills


def test_loop_api_uses_frozen_execution_and_filters_actual_calls(skills, tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    import memstara.paths
    monkeypatch.setattr(memstara.paths, 'RUNS_DIR', tmp_path)
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.control import service
    plan = build_plan(skills, 2)
    (tmp_path/'config.json').write_text(json.dumps({'combination_plan': plan}))
    executed = {**loop_flavors(plan, 27), 'agents': [{**a, 'agent_id': f'actual-{a["stage"]}'}
                                                 for a in loop_flavors(plan, 27)['agents']]}
    (tmp_path/'loop_27_flavors.json').write_text(json.dumps(executed))
    (tmp_path/'execution.json').write_text(json.dumps({'calls': [
        {'loop': 26, 'stage': 'report', 'run_id': 'other'},
        {'loop': 27, 'stage': 'question26-1', 'run_id': 'correct'}]}))
    manager = SimpleNamespace(running=lambda: None,
                              finished=lambda: [{'run_tag': 'finished', 'run_dir': str(tmp_path)}])
    monkeypatch.setattr(service, 'WORKSPACE', SimpleNamespace(manager=lambda key: manager))
    handler = object.__new__(service.Handler)
    handler.headers = {'Host': 'localhost'}
    handler.path = '/control/pipelines/p/combinations?loop=27'
    handler._send = MagicMock()
    handler.do_GET()
    code, data = handler._send.call_args.args
    assert code == 200 and data['total_loops'] == 48
    assert data['planned']['repetition'] == 2 and data['planned']['combination'] == 3
    assert data['executed'] == executed
    assert [c['run_id'] for c in data['calls']] == ['correct']
    handler.path = '/control/pipelines/p/combinations?loop=49'
    handler.do_GET()
    assert handler._send.call_args.args[0] == 400


def test_identical_content_different_ids_deduplicates_by_hash(skills, monkeypatch):
    original = catalog.resolve
    monkeypatch.setattr(catalog, 'resolve', lambda key: {**original(key), 'hash': 'same'}
                        if key.startswith('hypothesis') else original(key))
    plan = build_plan(skills, 2)
    assert plan['combinations'] == 12
    assert plan['total_loops'] == 24
    assert len(plan['skills']['hypothesis']) == 1


def test_execution_factors_use_provisioned_combination_agents(tmp_path, monkeypatch):
    import json
    from unittest.mock import AsyncMock
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.pipeline import board
    (tmp_path/'prompts.json').write_text(json.dumps({'hypothesis': {'agent_id': 'unused-template'}}))
    (tmp_path/'loop_1_flavors.json').write_text(json.dumps({'agents': [
        {'stage':'hypothesis','agent_id':'actual-h','id':'domain-skill','hash':'sha'}]}))
    monkeypatch.setattr(board, '_CALLS', [
        {'seq':0,'agent_id':'actual-h','stage':'question0','status':'completed'},
        {'seq':1,'agent_id':'actual-h','stage':'hypothesis0','status':'completed'}])
    monkeypatch.setattr(board, '_trace_one', AsyncMock())
    asyncio.run(board.write_traces(tmp_path))
    factors=json.loads((tmp_path/'factors.json').read_text())['agents']
    assert len(factors)==1 and factors[0]['called']
    assert factors[0]['agent_id']=='actual-h' and factors[0]['calls']==2
    assert factors[0]['skill']=='domain-skill'


def test_loop_api_during_startup_is_pending_not_bad_request(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.control import service
    manager=SimpleNamespace(running=lambda:{'run_tag':'starting','run_dir':str(tmp_path)})
    monkeypatch.setattr(service,'WORKSPACE',SimpleNamespace(manager=lambda key:manager))
    handler=object.__new__(service.Handler)
    handler.headers={'Host':'localhost'}
    handler.path='/control/pipelines/p/combinations?loop=1'
    handler._send=MagicMock()
    handler.do_GET()
    code,data=handler._send.call_args.args
    assert code==200 and data['preparing'] and not data['calls']


def test_random_start_is_frozen_and_wraps_without_early_duplicates(skills, monkeypatch):
    import json
    from memstara.combinations import validate_plan, task_books
    draws = []
    monkeypatch.setattr('memstara.combinations.secrets.randbelow', lambda n: draws.append(n) or 22)
    plan = build_plan(skills, random_start=True, max_loops=27)
    assert draws == [24]
    assert plan['total_loops'] == 27 and plan['start_index'] == 22
    frozen = json.loads(json.dumps(plan))
    assert validate_plan(frozen) == plan
    assert draws == [24]  # Validation/replay never samples again.
    combinations = [loop_flavors(frozen, n)['combination'] for n in range(1, 28)]
    assert combinations[:4] == [23, 24, 1, 2]
    assert len(set(combinations[:24])) == 24
    assert combinations[24:] == [23, 24, 1]
    assert loop_flavors(frozen, 25)['repetition'] == 2
    for loop in (1, 3, 25, 27):
        flavors = loop_flavors(frozen, loop)
        assert flavors['selection_policy'] == 'random_start_then_cycle_v1'
        assert flavors['start_combination'] == 23
        assert task_books({'combination_plan': frozen}, loop - 1) == {
            a['stage']: [a['id']] for a in flavors['agents']}
    with pytest.raises(ValueError, match='outside'):
        loop_flavors(frozen, 28)


def test_maximum_loops_can_cover_partial_set_or_multiple_cycles(skills):
    from memstara.combinations import validate_plan
    for maximum in (1, 10, 24, 49, 10000):
        plan = build_plan(skills, max_loops=maximum)
        assert plan['total_loops'] == maximum
        assert plan['start_index'] == 0
        assert validate_plan(plan) == plan
        assert loop_flavors(plan, maximum)['loop'] == maximum
    # Historical schedules still retain their original representation.
    old = build_plan(skills, 2)
    assert old['version'] == 1 and 'start_index' not in old
    assert validate_plan(old) == old


@pytest.mark.parametrize('maximum', [0, -1, 10001, True, 1.5, '10'])
def test_invalid_maximum_rejected(skills, maximum):
    with pytest.raises(ValueError, match='Maximum Loops'):
        build_plan(skills, max_loops=maximum)


@pytest.mark.parametrize('value', ['true', 1, None])
def test_invalid_random_flag_rejected(skills, value):
    with pytest.raises(ValueError, match='boolean'):
        build_plan(skills, random_start=value, max_loops=10)


def test_tampered_frozen_plan_rejected_without_random_draw(skills, monkeypatch):
    from memstara.combinations import validate_plan
    plan = build_plan(skills, random_start=True, max_loops=10, start_index=7)
    monkeypatch.setattr('memstara.combinations.secrets.randbelow', lambda _: pytest.fail('Unexpected draw'))
    for patch in ({'start_index': None}, {'start_index': 24}, {'total_loops': 11},
                  {'selection_policy': 'manager_agent'}, {'max_loops': 0}):
        with pytest.raises(ValueError):
            validate_plan({**plan, **patch})


def test_workspace_does_not_draw_but_each_new_launch_does(skills, monkeypatch):
    import json
    from memstara.control.workspace import PipelineWorkspace
    from memstara.control.request import build_argv
    from memstara.combinations import validate_plan
    for role in ('QUESTION', 'HYPOTHESIS', 'DATA', 'ML', 'INTERPRETATION', 'EXPLANATION'):
        monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER', 'openai')
        monkeypatch.setenv(f'MEMSTARA_{role}_MODEL', 'test-model')
    monkeypatch.setattr('memstara.combinations.secrets.randbelow', lambda _: pytest.fail('Workspace drew randomness'))
    config = PipelineWorkspace.configuration({'combination_skills': skills,
        'combination_random_start': True, 'combination_max_loops': 7, 'continuous': True})
    assert config['waves'] == 7 and config['continuous'] is False
    assert PipelineWorkspace.configuration(config) == config
    draws = iter([3, 17])
    monkeypatch.setattr('memstara.combinations.secrets.randbelow', lambda _: next(draws))
    for expected in (3, 17):
        argv = build_argv({**config, 'continuous': True}, [], [k for ids in skills.values() for k in ids], STAGES)
        assert argv[argv.index('--waves') + 1] == '7'
        assert '--continuous' not in argv
        frozen = json.loads(argv[argv.index('--combination-plan') + 1])
        assert validate_plan(frozen)['start_index'] == expected


def test_capped_runner_and_resumed_provisioning_preserve_flavors(skills, tmp_path):
    from memstara.pipeline.exploration import rounds
    plan = build_plan(skills, random_start=True, max_loops=3, start_index=23)
    async def provision(**kwargs):
        return {stage: f"{kwargs['namespace']}-{stage}" for stage in STAGES}
    async def run(start):
        records = []
        async for wave in rounds(plan['total_loops'], False, tmp_path, start=start):
            _, flavors, _, _ = await prepare_loop(plan, wave + 1, provider='test', model='test',
                                                  run_tag='frozen-run', provision=provision)
            records.append(flavors)
        return records
    initial = asyncio.run(run(0))
    resumed = asyncio.run(run(1))
    assert [r['combination'] for r in initial] == [24, 1, 2]
    assert resumed == initial[1:]
    assert len(initial) == 3
