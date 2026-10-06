"""Offline portable input preservation and feature replay, using synthetic data only."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from memstara import feature_reproduction as reproduction
from memstara.pipeline.feature_selection import freeze, context, validate


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(reproduction, 'environment', lambda: {'python': 'test', 'packages': {}})
    data = tmp_path / 'source.csv'
    data.write_text('a,b,c,d,Y\n1,2,3,4,0\n')
    knowledge = tmp_path / 'knowledge'
    knowledge.mkdir()
    (knowledge / 'source.md').write_text('Synthetic evidence')
    stages = ('hypothesis', 'data', 'ml', 'interpreter', 'report')
    p = {'feature_reproduction': {'version': 1}, 'run_tag': 'test', 'pipeline_id': 'pipeline',
         'config_hash': 'fixture', 'y_column': 'Y',
         'dataset_sha256': reproduction.digest(data), 'evaluation': {'seed': 42},
         'prompts': {'hypothesis': {'system_prompt': 'Synthetic frozen prompt'}},
         'knowledge_hashes': {'source.md': reproduction.digest(knowledge / 'source.md')},
         'feature_context': {'features': [{'column': c} for c in 'abcd']},
         'combination_plan': {'total_loops': 2, 'combinations': 2,
          'skills': {s: [{'id': 'random_features'}, {'id': 'guided'}] if s == 'hypothesis'
                    else [{'id': s}] for s in stages}}}
    p['feature_selection_policy'] = freeze(p)
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'config.json').write_text(json.dumps(p))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(run / 'config.json'))
    directory = reproduction.archive(p, data, knowledge, run)
    return directory, p, data, knowledge


def test_archive_survives_original_removal_and_replays_random_selection(bundle):
    directory, p, data, knowledge = bundle
    data.unlink()
    (knowledge / 'source.md').unlink()
    assert reproduction.replay(directory) == {
        'status': 'verified', 'random_loops_replayed': 1, 'guided_loops_configured': 1,
        'accepted_extractions_validated': 0, 'environment_matches': True,
        'llm_regenerated': False, 'ml_retrained': False}
    assert (directory / 'input.csv').read_text().startswith('a,b,c,d,Y')
    assert (directory / 'knowledge/source.md').read_text() == 'Synthetic evidence'
    assert json.loads((directory / 'config.json').read_text())['prompts'] == p['prompts']
    assert (directory.stat().st_mode & 0o777) == 0o700
    assert all((f.stat().st_mode & 0o777) == 0o600 for f in directory.rglob('*') if f.is_file())


@pytest.mark.parametrize('name', ['input.csv', 'knowledge/source.md', 'selections.json',
                                 'environment.json', 'source/pipeline/feature_selection.py'])
def test_corruption_fails_closed(bundle, name):
    directory, *_ = bundle
    (directory / name).write_text('corrupted')
    with pytest.raises(ValueError, match='integrity'):
        reproduction.replay(directory)


def test_guided_and_random_records_are_preserved_and_checked(bundle):
    directory, p, *_ = bundle
    for wave in range(2):
        selected = context(p, wave)['required_features'] or list('abcd')
        record = reproduction.record_extraction({'task_id': wave + 1, 'question_id': 7}, p,
                                               validate(selected, p, wave))
        assert record['stage'] == 'verified_extraction_before_ml'
        assert record['manifest_sha256'] == reproduction.digest(directory / 'manifest.json')
    assert reproduction.replay(directory)['accepted_extractions_validated'] == 2
    path = directory / 'accepted/task-2.json'
    record = json.loads(path.read_text())
    record['selection']['features'].reverse()
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='integrity'):
        reproduction.replay(directory)


def test_environment_difference_is_reported_without_false_full_reproduction(bundle, monkeypatch):
    directory, *_ = bundle
    monkeypatch.setattr(reproduction, 'environment', lambda: {'python': 'different'})
    result = reproduction.replay(directory)
    assert result['status'] == 'verified' and not result['environment_matches']
    assert not result['llm_regenerated'] and not result['ml_retrained']


def test_current_code_mismatch_refuses_execution(bundle, monkeypatch, tmp_path):
    directory, *_ = bundle
    source = tmp_path / 'code'
    (source / 'pipeline').mkdir(parents=True)
    (source / 'pipeline/feature_selection.py').write_text('raise Exception("must not execute")')
    monkeypatch.setattr(reproduction, 'SOURCE', source)
    with pytest.raises(ValueError, match='Installed source differs'):
        reproduction.replay(directory)


def test_repeated_archive_preserves_existing_bundle_and_cli_is_offline(bundle):
    directory, p, data, knowledge = bundle
    assert reproduction.archive(p, data, knowledge, directory.parent) == directory
    completed = subprocess.run([sys.executable, '-m', 'memstara.feature_reproduction', str(directory)],
                               capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    result = json.loads(completed.stdout)
    assert result['random_loops_replayed'] == 1
    assert not result['llm_regenerated'] and not result['ml_retrained']


def test_changed_input_never_publishes_incomplete_bundle(tmp_path):
    data = tmp_path / 'input.csv'
    data.write_text('changed')
    with pytest.raises(ValueError, match='Dataset changed'):
        reproduction.archive({'dataset_sha256': 'other'}, data, tmp_path, tmp_path)
    assert not (tmp_path / 'feature_reproduction').exists()
    assert not list(tmp_path.glob('.feature-reproduction-*'))


def test_ml_bundle_carries_feature_selection_reference(bundle, tmp_path, monkeypatch):
    from memstara.evaluation import score
    directory, p, *_ = bundle
    selected = validate(context(p, 0)['required_features'], p, 0)
    record = reproduction.record_extraction({'task_id': 1}, p, selected)
    subset = tmp_path / 'subset.csv'
    subset.write_text('a,b,c,d,Y\n' + ''.join(
        f'{i % 7},{i % 3},{i % 5},{i % 11},{i % 2}\n' for i in range(80)))
    subset.with_suffix('.comparison.json').write_text(json.dumps({'feature_selection': record}))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    result = score(subset, 'Y', {'engine': 'logistic_regression', 'search_trials': 1,
                                 'replicates': 1, 'folds': 2}, explain=False)
    ml = Path(result['evaluation']['reproducibility']['bundle_path'])
    assert json.loads((ml / 'feature-selection.json').read_text()) == record
    manifest = json.loads((ml / 'manifest.json').read_text())
    assert manifest['files']['feature-selection.json'] == reproduction.digest(ml / 'feature-selection.json')
    assert record['manifest_sha256'] == reproduction.digest(directory / 'manifest.json')


def test_required_bundle_cannot_disappear_silently(monkeypatch):
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)
    with pytest.raises(ValueError, match='Required feature reproduction bundle'):
        reproduction.record_extraction({}, {'feature_reproduction': {'version': 1}}, {})
    assert reproduction.record_extraction({}, {}, {}) is None


def test_extraction_cannot_write_into_another_runs_bundle(bundle):
    _, plan, *_ = bundle
    with pytest.raises(ValueError, match='another run'):
        reproduction.record_extraction({'task_id': 1}, {**plan, 'run_tag': 'other'}, {})
