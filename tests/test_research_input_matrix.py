"""Synthetic input-mode, target-validation and control-launch regression matrix.

Real CSV and OKF parsers are exercised. Process launch and provider calls are
blocked; these checks do not certify live LLM or real database execution.
"""
import copy
import csv
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import pytest

from memstara import research_inputs as inputs

pytestmark = pytest.mark.unit
MODES = [(knowledge, data) for knowledge in ('okf', 'llm_only') for data in ('dataset', 'proposal')]


@pytest.fixture
def study(tmp_path, monkeypatch):
    from memstara.paths import REPO_ROOT
    from memstara import stage_models
    from memstara.pipeline.llm import PipelineLLMService
    for method in ('complete', 'complete_text', 'complete_with_tools'):
        monkeypatch.setattr(PipelineLLMService, method,
                            AsyncMock(side_effect=AssertionError('Unexpected real provider call')))
    monkeypatch.setattr(stage_models, 'deployment_profiles', lambda: {})
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'offline-fixture')
    monkeypatch.setenv('MEMSTARA_DATABASE_URL', 'postgresql://test:secret@localhost:15501/board')
    monkeypatch.setenv('MOTORO_DATABASE_URL', 'postgresql://test:secret@localhost:15502/runtime')
    monkeypatch.setenv('MOTORO_REDIS_URL', 'redis://localhost:16380/0')
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path / 'registry'))
    cfg = json.loads((REPO_ROOT / 'examples/research-inputs/research.json').read_text())
    dataset = tmp_path / 'source.csv'
    shutil.copyfile(REPO_ROOT / cfg['dataset_path'], dataset)
    corpus = tmp_path / 'corpus'
    shutil.copytree(REPO_ROOT / cfg['knowledge_path'], corpus)
    cfg.update(dataset_path=str(dataset), knowledge_path=str(corpus))
    return cfg


def select_modes(study, knowledge, data):
    cfg = copy.deepcopy(study)
    cfg.update(knowledge_mode=knowledge, data_mode=data)
    if knowledge == 'llm_only':
        cfg['knowledge_path'] = '/unselected/missing/corpus'
    if data == 'proposal':
        cfg['dataset_path'] = '/unselected/missing/dataset.csv'
        cfg['target'] = {'description': 'Investigate a synthetic follow-up event'}
    return cfg


def launch_fixture(tmp_path, monkeypatch):
    from memstara.control import service
    responses = []
    manager = SimpleNamespace(start=Mock(return_value={'run_tag': 'offline-fixture'}))
    monkeypatch.setattr(service, 'new_run_dir', Mock(return_value=tmp_path / 'run'))
    monkeypatch.setattr(service, 'skills', Mock(return_value=[]))
    handler = object.__new__(service.Handler)
    handler._send = lambda status, value: responses.append((status, value))
    return service, handler, manager, responses


@pytest.mark.parametrize(('knowledge', 'data'), MODES)
def test_four_modes_reach_control_launch_with_saved_inputs_and_no_server_environment_change(
    study, tmp_path, monkeypatch, knowledge, data,
):
    cfg = select_modes(study, knowledge, data)
    record = inputs.register(cfg)
    assert record['input_checks_passed']
    service, handler, manager, responses = launch_fixture(tmp_path, monkeypatch)
    environment = dict(os.environ)
    # Saved research mode/target must supersede stale form values.
    handler._launch({'research_input_id': record['id'], 'y_column': 'old_target',
                     'knowledge_mode': 'okf', 'data_mode': 'dataset'}, manager)
    assert responses[0][0] == 201, responses
    manager.start.assert_called_once()
    argv = manager.start.call_args.args[0]
    assert (argv[argv.index('--knowledge-mode') + 1] if '--knowledge-mode' in argv else 'okf') == knowledge
    assert (argv[argv.index('--data-mode') + 1] if '--data-mode' in argv else 'dataset') == data
    assert argv[argv.index('--y-column') + 1] == (cfg['target'].get('column') or 'outcome')
    assert dict(os.environ) == environment
    if knowledge == 'llm_only':
        service.skills.assert_not_called()
    else:
        service.skills.assert_called_once_with(Path(inputs.prepare(record['id'])['root']) / 'okf')
    assert not (tmp_path / 'run').exists()  # No real process, model, DB or run output.


TARGET_ERRORS = [
    ('column', 'absent_target', 'target_column'),
    ('description', '', 'target_description'),
    ('prediction_time', '', 'target_prediction_time'),
    ('positive_label', '', 'target_positive_label'),
    ('negative_label', '', 'target_negative_label'),
    ('positive_label', 'no_event', 'target_mapping'),
    ('positive_label', 'unexpected', 'unmapped_target'),
]


@pytest.mark.parametrize('knowledge', ['okf', 'llm_only'])
@pytest.mark.parametrize(('field', 'value', 'code'), TARGET_ERRORS)
def test_invalid_target_cannot_prepare_or_start_child(study, tmp_path, monkeypatch, knowledge, field, value, code):
    cfg = select_modes(study, knowledge, 'dataset')
    cfg['target'][field] = value
    original = Path(cfg['dataset_path']).read_bytes()
    record = inputs.register(cfg)
    assert code in {issue['code'] for issue in record['issues']}
    assert not record['input_checks_passed']
    with pytest.raises(ValueError, match='need review'):
        inputs.prepare(record['id'])
    service, handler, manager, responses = launch_fixture(tmp_path, monkeypatch)
    handler._launch({'research_input_id': record['id']}, manager)
    assert responses[0][0] == 422
    assert responses[0][1]['code'] == 'input_validation_failed'
    manager.start.assert_not_called()
    service.new_run_dir.assert_not_called()
    assert Path(cfg['dataset_path']).read_bytes() == original


@pytest.mark.parametrize('knowledge', ['okf', 'llm_only'])
@pytest.mark.parametrize('data', ['dataset', 'proposal'])
def test_input_switch_clears_unselected_paths_and_keeps_target_contract(study, monkeypatch, knowledge, data):
    first = inputs.prepare(inputs.register(study)['id'])
    second_cfg = select_modes(study, knowledge, data)
    second_cfg['target']['description'] = 'A distinct synthetic objective'
    second = inputs.prepare(inputs.register(second_cfg)['id'])
    assert second['root'] != first['root']
    with monkeypatch.context() as context:
        context.setattr(os, 'environ', dict(os.environ))
        inputs.activate(first)
        inputs.activate(second)
        assert os.environ['MEMSTARA_DATASET_PATH'] == (
            str(Path(second['root']) / 'dataset.csv') if data == 'dataset' else '')
        assert os.environ['MEMSTARA_LEAKAGE_RULES_PATH'] == (
            str(Path(second['root']) / 'matcher_rules.json') if data == 'dataset' else '')
        assert os.environ['AGENTIC_OKF_BUNDLE_DIR'] == (
            str(Path(second['root']) / 'okf') if knowledge == 'okf' else '')
        assert os.environ['MEMSTARA_OUTPUT_DIR'] == str(Path(second['root']) / 'derived')
    assert 'A distinct synthetic objective' in inputs.instructions(second)
    assert inputs.verify_materialized(first) == first


@pytest.mark.parametrize('knowledge', ['okf', 'llm_only'])
def test_alternate_target_and_reversed_positive_mapping_are_source_preserving(study, knowledge):
    cfg = select_modes(study, knowledge, 'dataset')
    source = Path(cfg['dataset_path'])
    text = source.read_text().replace('simulated_event', 'future_event')
    source.write_text(text)
    cfg['target'].update(column='future_event', positive_label='no_event', negative_label='event',
                         description='Predict absence of the generated event')
    original = source.read_bytes()
    profile = inputs.prepare(inputs.register(cfg)['id'])
    with source.open() as f:
        raw = list(csv.DictReader(f))
    with (Path(profile['root']) / 'dataset.csv').open() as f:
        analysis = list(csv.DictReader(f))
    assert len(raw) == len(analysis) == 120
    assert all(row['future_event'] == ('1' if prior['future_event'] == 'no_event' else '0')
               for prior, row in zip(raw, analysis, strict=True))
    assert all('record_id' not in row and 'simulated_event' not in row for row in analysis)
    from memstara.pipeline.feature_context import freeze_feature_context
    features = freeze_feature_context(Path(profile['root']) / 'dataset.csv', 'future_event', require_complete=True)
    assert len(features['features']) == 4
    assert 'future_event' not in {f['column'] for f in features['features']}
    assert source.read_bytes() == original


@pytest.mark.parametrize('problem', ['duplicate_header', 'ragged_row', 'missing', 'nonfinite', 'single_class'])
def test_bad_csv_rejected_without_cleanup_or_process_start(study, tmp_path, monkeypatch, problem):
    cfg = select_modes(study, 'llm_only', 'dataset')
    source = Path(cfg['dataset_path'])
    with source.open() as f:
        rows = list(csv.reader(f))
    if problem == 'duplicate_header':
        rows[0][1] = rows[0][2]
    elif problem == 'ragged_row':
        rows[1].pop()
    elif problem in ('missing', 'nonfinite'):
        rows[1][1] = '' if problem == 'missing' else 'inf'
    else:
        for row in rows[1:]:
            row[-1] = 'event'
    with source.open('w', newline='') as f:
        csv.writer(f).writerows(rows)
    original = source.read_bytes()
    if problem in ('duplicate_header', 'ragged_row'):
        with pytest.raises(ValueError):
            inputs.register(cfg)
    else:
        record = inputs.register(cfg)
        assert not record['input_checks_passed']
        service, handler, manager, responses = launch_fixture(tmp_path, monkeypatch)
        handler._launch({'research_input_id': record['id']}, manager)
        assert responses[0][0] == 422
        manager.start.assert_not_called()
        service.new_run_dir.assert_not_called()
    assert source.read_bytes() == original


@pytest.mark.parametrize('data', ['dataset', 'proposal'])
def test_explicit_broken_corpus_is_not_silent_llm_only_fallback(study, data):
    cfg = select_modes(study, 'okf', data)
    cfg['knowledge_path'] = '/explicitly-selected/missing/corpus'
    with pytest.raises(ValueError, match='existing local OKF'):
        inputs.register(cfg)


@pytest.mark.parametrize(('knowledge', 'data'), MODES)
def test_changed_source_requires_new_registration_in_every_applicable_mode(study, knowledge, data):
    cfg = select_modes(study, knowledge, data)
    record = inputs.register(cfg)
    frozen = inputs.prepare(record['id'])
    if data == 'dataset':
        source = Path(cfg['dataset_path'])
        source.write_text(source.read_text() + source.read_text().splitlines()[1] + '\n')
    elif knowledge == 'okf':
        with (Path(cfg['knowledge_path']) / 'index.md').open('a') as f:
            f.write('\nUpdated synthetic introduction\n')
    else:
        # No source to drift: a new objective creates a distinct research identity.
        cfg['target']['description'] = 'A different proposal objective'
        new = inputs.prepare(inputs.register(cfg)['id'])
        assert new['fingerprint'] != frozen['fingerprint']
        return
    with pytest.raises(ValueError, match='new version'):
        inputs.prepare(record['id'])
    assert inputs.verify_materialized(frozen) == frozen
    assert inputs.prepare(inputs.register(cfg)['id'])['fingerprint'] != frozen['fingerprint']


@pytest.mark.parametrize('damaged', ['[]', '{}', '{broken'])
def test_corrupt_registration_returns_422_without_launch(study, tmp_path, monkeypatch, damaged):
    record = inputs.register(select_modes(study, 'llm_only', 'proposal'))
    path = inputs.registry_root() / (record['id'] + '.json')
    path.write_text(damaged)
    service, handler, manager, responses = launch_fixture(tmp_path, monkeypatch)
    handler._launch({'research_input_id': record['id']}, manager)
    assert responses[0][0] == 422
    assert responses[0][1]['code'] == 'input_validation_failed'
    assert 'Research input record is invalid' in responses[0][1]['error']
    manager.start.assert_not_called()
    service.new_run_dir.assert_not_called()
    assert path.read_text() == damaged
