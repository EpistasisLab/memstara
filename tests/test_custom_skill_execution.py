"""Saved custom instructions retain an executable policy in immutable run snapshots."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from memstara import data_allocation, ml_configuration, seed_schedule
from memstara.control import catalog
from memstara.combinations import build_plan, task_books
from memstara.pipeline.snapshot import freeze


def test_custom_skills_freeze_and_execute_each_selected_policy(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    source = tmp_path / 'data.csv'
    rng = np.random.default_rng(9)
    pd.DataFrame({**{c: rng.normal(size=100) for c in 'abcd'}, 'outcome': [0, 1] * 50}).to_csv(source, index=False)
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(source))
    custom = {}
    expected = {}
    for stage, bases in {'data': ['data_training_heavy', 'data_balanced_stratified'],
                         'ml': ['ml_logistic_regression', 'ml_xgboost']}.items():
        custom[stage] = []
        for base in bases:
            entry = catalog.register({'stage': stage, 'name': 'same-text',
                'content': '# Research instructions\nPreserve the configured execution policy.', 'base_skill': base})
            custom[stage].append(entry['id'])
            expected[entry['id']] = base
        assert len(set(custom[stage])) == 2  # Same Markdown, different execution policies.
    plan = build_plan({'hypothesis': ['hypothesis_general'], **custom,
                      'interpreter': ['shared-shap'], 'report': ['shared-addiction']}, 2)
    args = SimpleNamespace(evaluation=json.dumps({'seed': 708, 'test_size': .3, 'replicates': 1}),
        y_column='outcome', baseline_columns='[]', run_tag='custom-skills', question='',
        hypothesis_agents=1, trials=1, waves=8, combination_plan=json.dumps(plan))
    run = tmp_path / 'run'
    run.mkdir()
    snapshot = freeze(args, run, {})
    assert snapshot['skill_bindings'] == expected
    assert len({seed_schedule.task_seed(snapshot, n) for n in range(8)}) == 8
    for trial in range(8):
        books = task_books(snapshot, trial)
        allocation = data_allocation.request(snapshot, trial)
        ratio = .3 if expected[books['data'][0]] == 'data_training_heavy' else .5
        assert allocation['minimum_test_size'] == allocation['maximum_test_size'] == ratio
        assert allocation['skill'] == books['data'][0]
        subset = tmp_path / f'subset-{trial}.csv'
        subset.write_bytes(source.read_bytes())
        task = {'task_id': trial + 1, 'trial': trial, 'columns': list('abcd'), 'y_column': 'outcome'}
        prepared = data_allocation.prepare(allocation['required_data_plan'], task, snapshot, subset)
        assert prepared is not None
        subset.with_suffix('.comparison.json').write_text(json.dumps({'trial': trial}))
        scoped = ml_configuration.for_dataset(snapshot, subset)
        assert ml_configuration.selected_model(scoped) == expected[books['ml'][0]].removeprefix('ml_')
        assert not ml_configuration.uses_default(scoped)
        template = ml_configuration.context(scoped, snapshot['evaluation'])['proposal_template']
        assert template['primary_model'] == ml_configuration.selected_model(scoped)
        assert snapshot['prompts']['board/data:' + books['data'][0]]
    saved = (run / 'config.json').read_bytes()
    # Resume uses frozen bindings, even if catalog metadata later changes.
    resolve = catalog.resolve
    monkeypatch.setattr(catalog, 'resolve', lambda name: {k: v for k, v in resolve(name).items() if k != 'base_skill'})
    args.resume = True
    assert freeze(args, run, {}) == snapshot
    assert (run / 'config.json').read_bytes() == saved


@pytest.mark.parametrize('stage,base', [('hypothesis', 'ml_xgboost'), ('ml', 'data_training_heavy'),
                                     ('data', 'data_manual_split'), ('data', [])])
def test_invalid_policy_is_not_registered(tmp_path, monkeypatch, stage, base):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    with pytest.raises(ValueError):
        catalog.register({'stage': stage, 'name': 'invalid', 'content': '# Invalid', 'base_skill': base})
