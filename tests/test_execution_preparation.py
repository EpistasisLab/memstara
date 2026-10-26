"""Offline budget, recovery and fail-before-provisioning checks for preparation."""
import asyncio
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

pytest.importorskip('motoro')
from memstara.pipeline import preparation


def arguments(**changes):
    return NS(**({'pipeline_id': 'fixture', 'waves': 1, 'continuous': False,
                  'trials': 3, 'hypothesis_agents': 2, 'interpret_agents': 2,
                  'combination_plan': '', 'model': 'fixture', 'stage_models': {},
                  'resume': False, 'report_only': False, 'run_tag': 'fixture',
                  'y_column': 'target', 'evaluation': '{}'} | changes))


@pytest.mark.parametrize('limit', [1, 64, 10000])
def test_combination_budget_overrides_ordinary_limit_and_worker_counts(limit):
    args = arguments(combination_plan=json.dumps({'total_loops': limit}), continuous=True)
    assert preparation.normalize_budget(args) == {'total_loops': limit}
    assert args.waves == limit and args.continuous is False
    assert args.trials == args.hypothesis_agents == args.interpret_agents == 1


@pytest.mark.parametrize('limit', [0, 10001, True, 1.5, '64', None])
def test_invalid_combination_budget_is_rejected_without_mutation(limit):
    args = arguments(combination_plan=json.dumps({'total_loops': limit}))
    before = vars(args).copy()
    with pytest.raises(ValueError, match='Invalid frozen combination'):
        preparation.normalize_budget(args)
    assert vars(args) == before


def test_ordinary_pipeline_and_unbounded_cli_keep_distinct_budgets():
    continuous = arguments(continuous=True, waves=99)
    assert preparation.normalize_budget(continuous) is None
    assert continuous.waves == 10 and not continuous.continuous
    with pytest.raises(ValueError, match='Maximum Loops'):
        preparation.normalize_budget(arguments(waves=11))
    cli = arguments(pipeline_id='', waves=20)
    preparation.normalize_budget(cli)
    assert cli.waves == 20


def test_resume_reads_own_frozen_models_and_fresh_reads_no_file(tmp_path):
    frozen = {'stage_models': {'non_explanation_agents': {'model': 'original'}}}
    (tmp_path / 'config.json').write_text(json.dumps(frozen))
    assert preparation.frozen_model_source(arguments(resume=True), tmp_path) == frozen
    assert preparation.frozen_model_source(arguments(), tmp_path / 'absent') is None


def test_report_recovery_requires_one_non_report_source(tmp_path, monkeypatch):
    from memstara import paths
    monkeypatch.setattr(paths, 'RUNS_DIR', tmp_path)
    args = arguments(report_only=True)
    with pytest.raises(ValueError, match='unambiguous'):
        preparation.frozen_model_source(args, tmp_path)
    for name, tag, mode in [('source', 'fixture', 'pipeline'),
                            ('report', 'fixture', 'report_only'), ('other', 'other', 'pipeline')]:
        directory = tmp_path / name
        directory.mkdir()
        (directory / 'config.json').write_text(json.dumps({'run_tag': tag, 'mode': mode}))
    assert preparation.frozen_model_source(args, tmp_path)['mode'] == 'pipeline'
    duplicate = tmp_path / 'duplicate'
    duplicate.mkdir()
    (duplicate / 'config.json').write_text(json.dumps({'run_tag': 'fixture', 'mode': 'pipeline'}))
    with pytest.raises(ValueError, match='unambiguous'):
        preparation.frozen_model_source(args, tmp_path)


@pytest.fixture
def preflight(monkeypatch):
    from memstara import stage_models, research_inputs, evaluation, specialist_explanation
    from memstara.pipeline import diagnostics, runtime, snapshot
    events = []
    settings = NS(model_copy=lambda **kw: events.append(('settings', kw)) or 'configured')
    monkeypatch.setattr(preparation, 'Settings', lambda: settings)
    monkeypatch.setattr(preparation, 'configure', lambda value: events.append(('configure', value)))
    monkeypatch.setattr(runtime, 'runtime_timeouts', lambda _: {
        'llm_call_timeout_seconds': 123, 'agent_timeout_seconds': 456})
    monkeypatch.setattr(diagnostics, 'install', lambda: events.append(('diagnostics',)))
    def resolve(profiles, **kwargs):
        events.append(('models', kwargs))
        return {'selected': {'model': 'frozen-fixture'}}
    monkeypatch.setattr(stage_models, 'resolve_run_profiles', resolve)
    monkeypatch.setattr(research_inputs, 'verify_materialized', lambda _: events.append(('verify',)))
    monkeypatch.setattr(research_inputs, 'ensure_matcher', lambda _: events.append(('matcher',)))
    monkeypatch.setattr(evaluation, 'validate', lambda plan: plan)
    monkeypatch.setattr(evaluation, 'preflight', lambda *a, **kw: events.append(('data', kw)))
    async def model_preflight(profiles):
        events.append(('provider', profiles))
    monkeypatch.setattr(stage_models, 'preflight_profiles', model_preflight)
    def freeze(args, directory, books):
        events.append(('freeze', books))
        return {'stage_models': args.stage_models, 'marker': 'frozen'}
    monkeypatch.setattr(snapshot, 'freeze', freeze)
    async def explanation(configuration, directory):
        events.append(('explanation', configuration))
    monkeypatch.setattr(specialist_explanation, 'preflight', explanation)
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', '/synthetic/fixture.csv')
    return events


def test_preparation_order_and_reserved_partition_before_configuration_freeze(tmp_path, preflight):
    args = arguments(research_profile={'id': 'fixture'})
    books = {'hypothesis': ['fixture']}
    prepared = asyncio.run(preparation.prepare_execution(args, tmp_path, books))
    assert [event[0] for event in preflight] == [
        'settings', 'configure', 'diagnostics', 'models', 'verify', 'data',
        'matcher', 'provider', 'freeze', 'explanation']
    assert preflight[0][1] == {'update': {'llm_call_timeout_seconds': 123}}
    assert preflight[5][1] == {'reserve_validation': True, 'missing_policy': 'reject'}
    assert prepared.stage_models == args.stage_models
    assert preflight[-1][1]['stage_models'] == prepared.stage_models
    assert prepared.combination_plan is None


@pytest.mark.parametrize('recovering', [False, True])
def test_model_resolution_receives_original_recovery_configuration(tmp_path, preflight, recovering):
    frozen = {'stage_models': {'selected': {'model': 'original'}}}
    (tmp_path / 'config.json').write_text(json.dumps(frozen))
    asyncio.run(preparation.prepare_execution(arguments(resume=recovering), tmp_path, {}))
    assert next(e[1] for e in preflight if e[0] == 'models') == {
        'recovering': recovering, 'frozen': frozen if recovering else None}
    assert not {'verify', 'data', 'matcher'} & {e[0] for e in preflight}


@pytest.mark.parametrize('boundary', ['verify_materialized', 'preflight_profiles', 'explanation'])
def test_preflight_failure_never_provisions_agents_or_tools(tmp_path, monkeypatch, preflight, boundary):
    from memstara import research_inputs, stage_models, specialist_explanation
    from memstara.pipeline import board
    error = ValueError('fixture rejection')
    if boundary == 'verify_materialized':
        def reject(*args):
            raise error
        monkeypatch.setattr(research_inputs, boundary, reject)
    else:
        module, name = ((specialist_explanation, 'preflight') if boundary == 'explanation'
                        else (stage_models, boundary))
        monkeypatch.setattr(module, name, AsyncMock(side_effect=error))
    provision, tools = AsyncMock(), AsyncMock()
    monkeypatch.setattr(board, 'provision_board_agents', provision)
    monkeypatch.setattr(board, 'setup_tools', tools)
    with pytest.raises(ValueError, match='fixture rejection') as caught:
        asyncio.run(board.run(arguments(research_profile={'id': 'fixture'}), tmp_path))
    assert caught.value is error
    provision.assert_not_awaited()
    tools.assert_not_awaited()
    assert not (tmp_path / 'resume_arguments.json').exists()
    assert not (tmp_path / 'trace').exists()


def test_report_only_model_resolution_uses_source_not_report_config(tmp_path, monkeypatch, preflight):
    from memstara import paths
    sources = tmp_path / 'sources'
    source = sources / 'source'
    source.mkdir(parents=True)
    frozen = {'run_tag': 'fixture', 'mode': 'pipeline',
              'stage_models': {'selected': {'model': 'original'}}}
    (source / 'config.json').write_text(json.dumps(frozen))
    monkeypatch.setattr(paths, 'RUNS_DIR', sources)
    asyncio.run(preparation.prepare_execution(arguments(report_only=True), tmp_path, {}))
    assert next(e[1] for e in preflight if e[0] == 'models') == {
        'recovering': True, 'frozen': frozen}


def test_proposal_dispatch_does_not_enter_empirical_preparation(tmp_path, monkeypatch):
    from memstara.pipeline import board, proposal
    prepare = AsyncMock(side_effect=AssertionError('empirical path accessed'))
    propose = AsyncMock(return_value=0)
    monkeypatch.setattr(preparation, 'prepare_execution', prepare)
    monkeypatch.setattr(proposal, 'run', propose)
    args = arguments(data_mode='proposal')
    assert asyncio.run(board.run(args, tmp_path)) == 0
    prepare.assert_not_awaited()
    propose.assert_awaited_once_with(args, tmp_path)


@pytest.mark.parametrize('changes, message', [
    ({'resume': True}, 'Legacy random'),
    ({'trials': 2}, 'one skill per stage'),
    ({'hypothesis_agents': 2}, 'one skill per stage'),
])
def test_unsafe_standalone_random_configuration_rejected_before_provisioning(tmp_path, preflight, changes, message):
    books = {s: [s] for s in ('data', 'ml', 'interpreter', 'report')}
    books['hypothesis'] = ['random_features']
    args = arguments(**({'trials': 1, 'hypothesis_agents': 1, 'interpret_agents': 1} | changes))
    with pytest.raises(ValueError, match=message):
        asyncio.run(preparation.prepare_execution(args, tmp_path, books))
    assert preflight == []


def test_existing_random_schedule_is_not_resampled():
    args = arguments(combination_plan='{"frozen": true}', resume=True)
    preparation.normalize_random_selection(args, {'hypothesis': ['random_features']})
    assert args.combination_plan == '{"frozen": true}'
