"""Real synthetic stratified splits through the web tool handoff; no paid calls."""
import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from memstara import data_allocation as allocation
from memstara import evaluation
from memstara.comparisons import write_context


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    rng = np.random.default_rng(42)
    source = tmp_path / 'input.csv'
    frame = pd.DataFrame({**{c: rng.normal(size=200) for c in 'abcd'}, 'Y': [0]*160+[1]*40})
    frame.to_csv(source, index=False)
    shared = evaluation.validate({'engine': 'logistic_regression', 'test_size': .25, 'seed': 42})
    skills = list(allocation.SKILLS)
    stages = ['hypothesis', 'data', 'ml', 'interpreter', 'report']
    plan = {'run_tag': 'run', 'config_hash': 'config', 'y_column': 'Y', 'evaluation': shared,
            'dataset_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'comparison_policy': {'baseline_columns': []},
            'data_allocation_policy': {'version': allocation.PREVIOUS_VERSION},
            'validation_partition': evaluation.discovery_partition(frame.Y, 42),
            'combination_plan': {'total_loops': 2, 'combinations': 2,
                                'skills': {s: [{'id': key} for key in skills] if s == 'data'
                                           else [{'id': s}] for s in stages}},
            'prompts': {f'board/data:{skill}': {'system_prompt': skill} for skill in skills}}
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(source))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    monkeypatch.setattr(evaluation, 'active_plan', lambda: plan)
    monkeypatch.setattr(evaluation, '_explain', lambda *args: ({}, {'status': 'completed'}))
    return source, plan


@pytest.mark.parametrize('trial,fraction,accepted', [(0,.1,True),(0,.3,True),(0,.09,False),
    (0,.31,False),(1,.5,True),(1,.49,False),(1,.51,False),(0,float('nan'),False)])
def test_skill_bounds(experiment, trial, fraction, accepted):
    _, plan = experiment
    value = {'test_size': fraction, 'seed': 7, 'stratify': True}
    spec = allocation.request(plan, trial)
    if accepted:
        assert allocation.validate(value, spec, plan['evaluation'])['test_size'] == fraction
    else:
        with pytest.raises(ValueError):
            allocation.validate(value, spec, plan['evaluation'])


@pytest.mark.parametrize('change', [{'seed': True}, {'seed': -1}, {'stratify': False},
                                  {'seed': 2147483648}, {'unexpected': 0}])
def test_invalid_agent_plans(experiment, change):
    _, plan = experiment
    with pytest.raises(ValueError):
        allocation.validate({'test_size': .2, 'seed': 7, 'stratify': True, **change},
                            allocation.request(plan, 0), plan['evaluation'])


def task(trial):
    return {'task_id': trial+1, 'trial': trial, 'columns': list('abcd'), 'y_column': 'Y', 'evaluation': {}}


@pytest.mark.parametrize('trial,fraction,n_train,n_test', [(0,.2,128,32), (1,.5,80,80)])
def test_actual_ml_uses_data_plan_and_preserves_reserve(experiment, trial, fraction, n_train, n_test):
    from memstara.mcp_servers.ml import train_and_score
    source, plan = experiment
    subset = source.with_name(f'subset-{trial}.csv')
    subset.write_bytes(source.read_bytes())
    record = allocation.prepare({'test_size': fraction, 'seed': 7, 'stratify': True},
                                task(trial), plan, subset)
    write_context(subset, task(trial), plan, data_allocation=record)
    first = record['replicates'][0]
    assert (first['n_train'], first['n_test'], record['reserved_count']) == (n_train,n_test,40)
    assert not set(record['reserved_rows']) & set(first['train_rows'] + first['test_rows'])
    assert abs(first['test_class_counts']['1'] / n_test - .2) <= 1/n_test
    measured = json.loads(train_and_score(str(subset), 'Y', seed=999, test_size=.1))
    assert not measured.get('error'), measured
    assert measured['data_allocation'] == record
    real = measured['evaluation']['replicates'][0]
    assert (real['seed'], real['n_train'], real['n_test'], real['split_id']) == (7,n_train,n_test,first['split_id'])
    bundle = Path(measured['evaluation']['reproducibility']['bundle_path'])
    assert json.loads((bundle/'data-allocation.json').read_text()) == record
    assert allocation.load_effective(subset, plan, plan['evaluation'])[1] == record
    alternative = {**record, 'agent_plan': {**record['agent_plan'], 'seed': 8}}
    with pytest.raises(ValueError, match='cannot be changed'):
        write_context(subset, task(trial), plan, data_allocation=alternative)
    sidecar = subset.with_suffix('.comparison.json')
    payload = json.loads(sidecar.read_text())
    payload['data_allocation']['replicates'][0]['train_rows'].reverse()
    sidecar.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='does not reproduce'):
        allocation.load_effective(subset, plan, plan['evaluation'])


def test_new_data_agent_seed_and_validation_fraction_are_frozen_per_run(experiment, tmp_path, monkeypatch):
    source, base = experiment
    subset = source.with_name('agent-seeded-subset.csv')
    subset.write_bytes(source.read_bytes())
    run_config = tmp_path / 'config.json'
    run_config.write_text('{}')
    plan = {**base, 'validation_partition': None,
            'validation_partition_policy': 'data_agent_seed_v1',
            'data_allocation_policy': {'version': allocation.VERSION}}
    plan['combination_plan']['skills']['data'] = [{'id': 'data_training_heavy'}]
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(run_config))
    task0 = task(0)
    plan0 = {'test_size': .2, 'seed': 7, 'stratify': True,
             'validation_size': .15, 'validation_seed': 1234, 'replicates': 3}
    request0 = allocation.request(plan, 0)
    assert 'validation_size' in request0['schema'] and 'validation_seed' in request0['schema']
    record = allocation.prepare(plan0, task0, plan, subset)
    frozen = json.loads((tmp_path / 'validation_partition.json').read_text())
    assert frozen['seed'] == 1234 and frozen['fraction'] == .15
    assert record['validation_partition'] == {k: frozen[k] for k in
        ('version', 'seed', 'row_count', 'reserved_count', 'reserved_split_id', 'status', 'fraction')}
    refreshed = {**plan, 'validation_partition': frozen}
    later = {'test_size': .3, 'seed': 987, 'stratify': True,
             'validation_size': .15, 'validation_seed': 1234, 'replicates': 5}
    request1 = allocation.request(refreshed, 1)
    assert request1['required_validation_partition'] == {'validation_seed': 1234, 'validation_size': .15}
    assert allocation.validate(later, request1, base['evaluation'])['seed'] == 987
    with pytest.raises(ValueError, match='validation settings'):
        allocation.validate({**later, 'validation_size': .2}, request1, base['evaluation'])


def test_reordered_rows_and_missing_plan_block_before_ml(experiment):
    source, plan = experiment
    subset = source.with_name('reordered.csv')
    pd.read_csv(source).iloc[::-1].to_csv(subset, index=False)
    with pytest.raises(ValueError, match='changed rows'):
        allocation.prepare({'test_size': .2, 'seed': 7, 'stratify': True}, task(0), plan, subset)
    with pytest.raises(ValueError, match='requires data_plan'):
        allocation.prepare(None, task(0), plan, source)
    with pytest.raises(ValueError, match='handoff is required'):
        allocation.load_effective(source, plan, plan['evaluation'])


def test_ordinary_extraction_and_historical_policy_remain_unchanged(experiment):
    source, plan = experiment
    plan.pop('data_allocation_policy')
    assert allocation.request(plan, 0) is None
    assert allocation.prepare(None, task(0), plan, source) is None
    assert allocation.load_effective(source, plan, plan['evaluation']) == (plan['evaluation'], None)


def test_web_submit_result_routes_plan_into_ml(experiment, monkeypatch):
    from memstara.mcp_servers import blackboard as bb
    source, plan = experiment
    monkeypatch.setattr(bb, '_pipeline_run', lambda: '')
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    conn.fetchval.return_value = None
    current = {**task(1), 'task_type': 'data', 'status': 'in_progress', 'claimed_by': 'data',
               'subset_path': '', 'perspective': 'fixture', 'hypothesis': 'fixture'}
    conn.fetchrow.return_value = current
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    value = {'test_size': .5, 'seed': 7, 'stratify': True}
    result = json.loads(asyncio.run(bb.submit_result(2, subset_path=str(source), worker='data', data_plan=value)))
    assert result.get('ok'), result
    payloads = [json.loads(c.args[2]) for c in conn.execute.call_args_list
                if c.args[0].startswith('UPDATE memstara_blackboard SET evaluation=')]
    assert payloads[0]['data_allocation']['agent_plan'] == value
    record = json.loads(source.with_name('task_2_input.comparison.json').read_text())
    assert record['data_allocation'] == payloads[0]['data_allocation']


def test_web_configuration_freezes_both_skill_requests(experiment, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from memstara.control import catalog
    from memstara.control.request import build_argv
    from memstara.control.workspace import PipelineWorkspace
    from memstara.pipeline.snapshot import freeze
    source, _ = experiment
    stages = ['hypothesis','data','ml','interpreter','report']
    choices = {s: list(allocation.SKILLS) if s == 'data' else [s] for s in stages}
    monkeypatch.setattr(catalog, 'resolve', lambda key: {'id': key, 'title': key, 'hash': key,
                        'stage': 'data' if key in allocation.SKILLS else key})
    monkeypatch.setattr('memstara.pipeline.snapshot.load_prompt',
                        lambda role, book: {'system_prompt': book, 'goal': role})
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'test')
    config = PipelineWorkspace.configuration({'combination_skills': choices})
    argv = build_argv(config, [], [key for values in choices.values() for key in values], stages)
    args = SimpleNamespace(run_tag='web', question='', hypothesis_agents=1, y_column='Y',
                           evaluation=json.dumps({'engine':'logistic_regression'}), trials=1, waves=2,
                           combination_plan=argv[argv.index('--combination-plan')+1])
    run = tmp_path / 'web-run'
    run.mkdir()
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', '')
    frozen = freeze(args, run, {})
    assert frozen["ml_configuration_policy"]["version"] == "agent_selected_ml_v2"
    assert allocation.request(frozen, 0)['maximum_test_size'] == .3
    assert allocation.request(frozen, 1)['minimum_test_size'] == .5
    assert (run/'feature_reproduction/source/data_allocation.py').is_file()
