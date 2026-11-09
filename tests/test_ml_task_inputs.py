"""Task-bound ML survives filename transcription errors without changing evidence."""
import copy
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from memstara import data_allocation, evaluation, ml_configuration, ml_task_inputs
from memstara.comparisons import write_context
from memstara.mcp_servers import ml


@pytest.fixture
def task_input(tmp_path, monkeypatch):
    rng = np.random.default_rng(23)
    subset = tmp_path / 'task_665_sub_run__loop367.csv'
    pd.DataFrame({'x': rng.normal(size=80), 'z': rng.normal(size=80),
                  'Y': [0, 1] * 40}).to_csv(subset, index=False)
    plan = {'pipeline_id': 'pipeline', 'run_tag': 'run', 'config_hash': 'frozen', 'y_column': 'Y',
            'dataset_sha256': hashlib.sha256(subset.read_bytes()).hexdigest(),
            'partition_policy': data_allocation.TWO_WAY_VERSION,
            'data_allocation_policy': {'version': data_allocation.TWO_WAY_VERSION},
            'evaluation': evaluation.validate({'engine': 'xgboost'}),
            'ml_configuration_policy': ml_configuration.policy(),
            'comparison_policy': {'baseline_columns': []},
            'books': {'data': ['data_balanced_stratified'], 'ml': ['ml_xgboost']},
            'prompts': {'board/data:data_balanced_stratified': {'system_prompt': 'Synthetic data skill'}}}
    task = {'task_id': 665, 'run_tag': 'run', 'trial': 366, 'task_type': 'ml',
            'status': 'in_progress', 'claimed_by': 'ml#1', 'subset_path': str(subset),
            'y_column': 'Y', 'columns': ['x', 'z'], 'evaluation': {'config_hash': 'frozen'}}
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(subset))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    monkeypatch.setattr(evaluation, 'active_plan', lambda: plan)
    allocation = data_allocation.prepare({'test_size': .5, 'seed': 7, 'stratify': True}, task, plan, subset)
    write_context(subset, task, plan, data_allocation=allocation)
    task['evaluation']['data_allocation'] = allocation
    lookup = AsyncMock(side_effect=lambda task_id, tag: copy.deepcopy(task)
                       if task_id == task['task_id'] and tag == task['run_tag'] else None)
    monkeypatch.setattr(ml_task_inputs, 'read_task', lookup)
    return subset, plan, task, lookup


@pytest.mark.asyncio
async def test_actual_fit_uses_recorded_subset_and_split_even_with_mistyped_legacy_arguments(task_input):
    subset, plan, task, lookup = task_input
    original_csv = subset.read_bytes()
    original_handoff = subset.with_suffix('.comparison.json').read_bytes()
    original_task = copy.deepcopy(task)
    typo = str(subset).replace('__loop', '_loop')
    settings = json.loads(await ml.get_ml_configuration(typo, 'wrong-target', task_id=665, worker='ml#1'))
    assert 'error' not in settings, settings
    proposal = settings['proposal_template']
    proposal['rationale'] = 'Synthetic task binding regression'
    proposal['models']['xgboost']['parameters'].update(n_estimators=10, max_depth=2)
    result = json.loads(await ml.train_and_score_async(
        typo, 'wrong-target', task_id=665, worker='ml#1', ml_plan=proposal))
    assert 'error' not in result, result
    assert result['y_column'] == 'Y'
    assert result['data_allocation'] == task['evaluation']['data_allocation']
    actual = result['evaluation']['replicates'][0]
    expected = task['evaluation']['data_allocation']['replicates'][0]
    assert actual['split_id'] == expected['split_id']
    assert actual['seed'] == expected['seed'] == 7
    assert subset.with_suffix('.evaluation.json').is_file()
    assert subset.read_bytes() == original_csv
    assert subset.with_suffix('.comparison.json').read_bytes() == original_handoff
    assert task == original_task  # A lookup never changes old task or failure records.
    assert lookup.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('tool', ['get_ml_configuration', 'train_and_score_async'])
@pytest.mark.parametrize('case,code', [
    ('omitted', 'ml_task_id_required'), ('wrong_id', 'ml_task_not_found'),
    ('other_run', 'ml_task_not_found'), ('other_worker', 'ml_task_not_owned'),
    ('completed', 'ml_task_not_owned'), ('failed', 'ml_task_not_owned'),
    ('data_stage', 'ml_task_not_owned'), ('changed_contract', 'ml_task_contract_mismatch'),
    ('changed_target', 'ml_task_contract_mismatch'), ('missing_csv', 'ml_subset_missing'),
    ('missing_handoff', 'ml_handoff_missing'), ('other_receipt', 'ml_handoff_identity_mismatch'),
    ('outside_root', 'ml_task_path_outside_root'),
])
async def test_invalid_identity_never_reaches_training(task_input, monkeypatch, tool, case, code):
    subset, plan, task, lookup = task_input
    kwargs = {'task_id': 665, 'worker': 'ml#1'}
    if case == 'omitted': kwargs = {'path': str(subset), 'y_column': 'Y'}
    if case == 'wrong_id': kwargs['task_id'] = 666
    if case == 'other_run': task['run_tag'] = 'different-run'
    if case == 'other_worker': kwargs['worker'] = 'ml#2'
    if case in ('completed', 'failed'): task['status'] = case
    if case == 'data_stage': task['task_type'] = 'data'
    if case == 'changed_contract': task['evaluation']['config_hash'] = 'other-config'
    if case == 'changed_target': task['y_column'] = 'other-target'
    if case == 'missing_csv': subset.unlink()
    if case == 'missing_handoff': subset.with_suffix('.comparison.json').unlink()
    if case == 'outside_root': task['subset_path'] = str(subset.parent.parent / 'outside.csv')
    if case == 'other_receipt':
        receipt = subset.with_suffix('.comparison.json')
        value = json.loads(receipt.read_text())
        value['data_allocation']['task_id'] = 666
        receipt.write_text(json.dumps(value))
    fit = MagicMock(side_effect=AssertionError('Invalid identity must not start a fit'))
    monkeypatch.setattr(ml, 'train_and_score', fit)
    result = json.loads(await getattr(ml, tool)(**kwargs))
    assert result['code'] == code, result
    assert result['hint']
    fit.assert_not_called()
    assert not subset.with_suffix('.evaluation.json').exists()


def test_missing_file_and_missing_receipt_are_distinct(task_input):
    subset, plan, _, _ = task_input
    with pytest.raises(ml_task_inputs.MLInputError) as missing:
        data_allocation.load_effective(str(subset).replace('__loop', '_loop'), plan, plan['evaluation'])
    assert missing.value.code == 'ml_subset_missing'
    subset.with_suffix('.comparison.json').unlink()
    with pytest.raises(ml_task_inputs.MLInputError) as handoff:
        data_allocation.load_effective(subset, plan, plan['evaluation'])
    assert handoff.value.code == 'ml_handoff_missing'


@pytest.mark.asyncio
async def test_lookup_is_scoped_and_does_not_write(monkeypatch):
    import asyncpg
    connection = MagicMock()
    connection.fetchrow = AsyncMock(return_value=None)
    connection.close = AsyncMock()
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(asyncpg, 'connect', connect)
    assert await ml_task_inputs.read_task(665, 'run') is None
    sql, *parameters = connection.fetchrow.call_args.args
    assert 'task_id=$1 AND run_tag=$2' in sql
    assert parameters == [665, 'run']
    connection.execute.assert_not_called()
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ml_submission_cannot_overwrite_data_path(task_input, monkeypatch):
    from memstara.mcp_servers import blackboard as bb
    subset, plan, task, _ = task_input
    # An intact saved model receipt: no need to fit a second model in this test.
    subset.with_suffix('.evaluation.json').write_text(json.dumps({
        'y_column': 'Y', 'config_hash': 'frozen', 'auc': .6, 'model': 'xgboost',
        'feature_importance': {}, 'data_allocation': task['evaluation']['data_allocation'],
        'evaluation': {'dataset_sha256': hashlib.sha256(subset.read_bytes()).hexdigest()},
    }))
    connection = MagicMock()
    connection.transaction.return_value.__aenter__ = AsyncMock()
    connection.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    connection.fetchval = AsyncMock(side_effect=['run', json.dumps(task['evaluation'])])
    connection.fetchrow = AsyncMock(return_value=task)
    connection.execute = AsyncMock()
    connection.close = AsyncMock()
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=connection))
    monkeypatch.setattr('memstara.interpretation_fanout.expand', AsyncMock())
    result = json.loads(await bb.submit_result(665, worker='ml#1', subset_path='/wrong/path.csv'))
    assert result['ok'], result
    updates = [c for c in connection.execute.call_args_list if 'subset_path' in c.args[0]]
    assert len(updates) == 1
    assert updates[0].args[2] == ''  # COALESCE keeps the original, server-verified path.
    assert task['subset_path'] == str(subset)


@pytest.mark.asyncio
async def test_frozen_ml_prompt_gets_task_binding_on_resume(monkeypatch):
    from memstara.pipeline import board
    monkeypatch.setattr(evaluation, 'active_plan', lambda: {})
    monkeypatch.setattr(board, 'require_ownership', lambda: None)
    monkeypatch.setattr(board, '_TRACE_DIR', None)
    captured = {}
    class Captured(Exception): pass
    async def create(**kwargs):
        captured.update(kwargs)
        raise Captured
    monkeypatch.setattr(board, 'create_run', create)
    with pytest.raises(Captured):
        await board._call_agent_uncontrolled('agent', 'Old prompt: copy path.',
                                            stage='ml#1', tools=[], registry=None)
    assert ml_task_inputs.INSTRUCTIONS in captured['user_input']
