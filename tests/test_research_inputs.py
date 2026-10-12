"""Research preparation preserves source data and rejects ambiguous configuration."""
import json
import csv
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from memstara.research_inputs import inspect, register, list_inputs
from memstara.research_inputs import prepare, activate, verify_materialized, instructions


@pytest.fixture
def sample(tmp_path, monkeypatch):
    pytest.importorskip('motoro')
    from memstara.mcp_servers import okf
    monkeypatch.setattr(okf, '_load', lambda root: ([SimpleNamespace(domain='cardiac')], []))
    data = tmp_path / 'data.csv'
    data.write_text('record_id,a,b,c,d,outcome\n1,1,2,3,4,yes\n2,2,3,4,5,no\n3,3,4,5,6,yes\n4,4,5,6,7,no\n')
    corpus = tmp_path / 'okf'
    corpus.mkdir()
    (corpus / 'index.md').write_text('Example synthetic corpus')
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path / 'registry'))
    return {'name': 'Synthetic example', 'dataset_path': str(data), 'knowledge_path': str(corpus),
            'excluded_columns': ['record_id'], 'target': {
                'column': 'outcome', 'description': 'Synthetic binary outcome',
                'positive_label': 'yes', 'negative_label': 'no', 'prediction_time': 'At enrollment'}}


@pytest.mark.parametrize('replacement', ['', 'different,outcome\n1,yes\n',
                                         'a,record_id,b,c,d,outcome\n1,1,2,3,4,yes\n'])
def test_source_changed_after_inspection_is_not_published(sample, monkeypatch, replacement):
    from memstara import research_inputs

    record = register(sample)
    original_inspect = research_inputs.inspect

    def inspect_then_truncate(configuration):
        checked = original_inspect(configuration)
        Path(sample['dataset_path']).write_text(replacement)
        return checked

    monkeypatch.setattr(research_inputs, 'inspect', inspect_then_truncate)
    with pytest.raises(ValueError, match='Dataset changed'):
        prepare(record['id'])
    parent = research_inputs.registry_root() / 'prepared'
    assert not list(parent.rglob('manifest.json'))
    assert not list(parent.glob('.preparing-*'))


def test_valid_inputs_are_not_falsely_marked_pipeline_ready(sample):
    result = inspect(sample)
    assert result['input_checks_passed']
    assert not result['execution_ready']
    assert result['dataset']['eligible_predictor_count'] == 4
    assert result['dataset']['target_counts'] == {'positive': 2, 'negative': 2}
    assert 'rows' not in result or isinstance(result['rows'], int)
    assert 'yes' not in json.dumps(result['dataset'])


def test_missing_target_semantics_and_identifiers_are_explicit(sample):
    sample['target'] = {}
    sample['excluded_columns'] = []
    result = inspect(sample)
    codes = {x['code'] for x in result['issues']}
    assert {'target_column', 'target_description', 'target_prediction_time', 'identifier_review'} <= codes
    assert not result['input_checks_passed']


def test_missing_cells_block_without_rewriting_source(sample):
    from pathlib import Path
    p = Path(sample['dataset_path'])
    p.write_text(p.read_text().replace('1,1,2,3,4,yes', '1,?,2,3,4,yes'))
    before = p.read_bytes()
    result = inspect(sample)
    assert result['dataset']['missing_cells'] == 1
    assert any(x['code'] == 'missing_values' for x in result['issues'])
    assert p.read_bytes() == before


@pytest.mark.parametrize('cell', ['"1"unexpected', '"' + 'x' * 150000 + '"'],
                         ids=['invalid-quote', 'oversized-field'])
def test_malformed_or_oversized_csv_cells_are_input_errors(sample, cell):
    path = Path(sample['dataset_path'])
    path.write_text(path.read_text().replace('1,1,2,3,4,yes', f'1,{cell},2,3,4,yes'))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='CSV parsing failed'):
        inspect(sample)
    assert path.read_bytes() == before


def test_valid_quoted_csv_fields_remain_supported(sample):
    path = Path(sample['dataset_path'])
    path.write_text(path.read_text().replace('1,1,2,3,4,yes', '1,"1",2,3,4,"yes"'))
    assert inspect(sample)['input_checks_passed']


def test_fingerprint_tracks_data_target_and_knowledge_changes(sample):
    from pathlib import Path
    first = inspect(sample)['fingerprint']
    sample['target']['description'] = 'Another user-defined objective'
    second = inspect(sample)['fingerprint']
    assert second != first
    (Path(sample['knowledge_path']) / 'index.md').write_text('Changed corpus')
    assert inspect(sample)['fingerprint'] != second


def test_immutable_registration_and_no_inference(sample):
    a, b = register(sample), register(sample)
    assert a['id'] != b['id'] and a['fingerprint'] == b['fingerprint']
    assert len(list_inputs()) == 2
    assert all(not x['execution_ready'] for x in list_inputs())


def test_path_escape_via_corpus_symlink_is_rejected(sample, tmp_path):
    from pathlib import Path
    outside = tmp_path / 'outside.md'
    outside.write_text('Not in the corpus')
    (Path(sample['knowledge_path']) / 'escape.md').symlink_to(outside)
    with pytest.raises(ValueError, match='inside'):
        inspect(sample)


def test_no_implicit_imputation(sample):
    sample['missing_policy'] = 'impute'
    with pytest.raises(ValueError, match='no automatic'):
        inspect(sample)


def test_preparation_maps_only_explicit_labels_and_exclusions(sample):
    source = Path(sample['dataset_path'])
    original = source.read_bytes()
    environment = dict(os.environ)
    record = register(sample)
    profile = prepare(record['id'])
    with (Path(profile['root']) / 'dataset.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert [r['outcome'] for r in rows] == ['1', '0', '1', '0']
    assert all('record_id' not in row for row in rows)
    assert len(rows) == 4 and rows[0]['a'] == '1'
    assert source.read_bytes() == original
    assert dict(os.environ) == environment  # Control service must not switch other runs.
    assert prepare(record['id']) == profile


def test_source_drift_requires_new_version_but_resume_keeps_frozen_inputs(sample):
    record = register(sample)
    frozen = prepare(record['id'])
    Path(sample['knowledge_path'], 'index.md').write_text('Revised source')
    with pytest.raises(ValueError, match='new version'):
        prepare(record['id'])
    assert verify_materialized(frozen) == frozen
    fresh = prepare(register(sample)['id'])
    assert fresh['root'] != frozen['root']


@pytest.mark.parametrize('change', ['dataset', 'knowledge', 'extra'])
def test_resume_rejects_tampered_prepared_files(sample, change):
    profile = prepare(register(sample)['id'])
    root = Path(profile['root'])
    path = root / {'dataset':'dataset.csv', 'knowledge':'okf/index.md', 'extra':'okf/extra.md'}[change]
    path.write_text('Changed')
    with pytest.raises(ValueError, match='Frozen'):
        verify_materialized(profile)


def test_activation_and_target_contract_follow_each_study(sample, monkeypatch):
    first = prepare(register(sample)['id'])
    second_config = {**sample, 'target': {**sample['target'], 'description':'Different research objective'}}
    second = prepare(register(second_config)['id'])
    # Preserve all environment changes made by the child-only activation for this test.
    with monkeypatch.context() as context:
        context.setattr(os, 'environ', dict(os.environ))
        activate(first)
        first_output = os.environ['MEMSTARA_OUTPUT_DIR']
        activate(second)
        assert os.environ['MEMSTARA_OUTPUT_DIR'] != first_output
        assert os.environ['MEMSTARA_DATASET_PATH'] == str(Path(second['root']) / 'dataset.csv')
        assert os.environ['MEMSTARA_OUTCOME_COLUMN'] == 'outcome'
        assert os.environ['AGENTIC_OKF_BUNDLE_DIR'] == str(Path(second['root']) / 'okf')
    assert 'Different research objective' in instructions(second)
    assert 'positive label as 1' in instructions(second)


def test_registered_target_replaces_stale_browser_target(sample, monkeypatch):
    from memstara.control.request import build_argv
    record = register(sample)
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'test-model')
    from memstara import stage_models
    monkeypatch.setattr(stage_models, 'resolve_run_profiles', lambda _: {})
    argv = build_argv({'research_input_id': record['id'], 'y_column': 'stale_target'}, [])
    assert argv[argv.index('--y-column') + 1] == 'outcome'
    assert argv[argv.index('--research-input-id') + 1] == record['id']
    with pytest.raises(ValueError, match='saved research'):
        build_argv({'research_input_id':'../outside'}, [])


def test_prepare_rejects_invalid_inputs_before_any_runtime(sample):
    sample['target']['prediction_time'] = ''
    record = register(sample)
    with pytest.raises(ValueError, match='need review'):
        prepare(record['id'])


def test_public_example_freezes_complete_research_contract(tmp_path, monkeypatch):
    pytest.importorskip('motoro')
    from memstara.paths import REPO_ROOT
    from memstara.pipeline.snapshot import freeze
    from memstara.evaluation import preflight, validate
    from memstara.pipeline.feature_context import freeze_feature_context
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path / 'registry'))
    config = json.loads((REPO_ROOT / 'examples/research-inputs/research.json').read_text())
    record = register(config)  # Real OKF parser, no original private files.
    assert record['input_checks_passed'] and record['knowledge']['documents'] == 1
    profile = prepare(record['id'])
    root = Path(profile['root'])
    preflight(root / 'dataset.csv', 'simulated_event', validate({}), reserve_validation=True)
    features = freeze_feature_context(root / 'dataset.csv', 'simulated_event', require_complete=True)
    assert len(features['features']) == 4
    assert not {'record_id', 'simulated_event'} & {f['column'] for f in features['features']}
    run = tmp_path / 'run'
    run.mkdir()
    args = SimpleNamespace(evaluation='{}', y_column='simulated_event', baseline_columns='[]',
                           run_tag='synthetic-study', question='', hypothesis_agents=1,
                           trials=1, waves=1, research_profile=profile)
    with monkeypatch.context() as context:
        context.setattr(os, 'environ', dict(os.environ))
        os.environ.pop('MEMSTARA_RUN_CONFIG', None)
        activate(profile)
        frozen = freeze(args, run, {'hypothesis':['hypothesis_research']})
        assert frozen['research_profile'] == profile
        assert frozen['y_column'] == 'simulated_event'
        assert frozen['knowledge_path'] == str(root / 'okf')
        assert frozen['missing_value_policy'] == 'reject'
        assert freeze(args, run, {'hypothesis':['hypothesis_research']}) == frozen


def test_matcher_caches_are_isolated_and_integrity_checked(sample, monkeypatch):
    import numpy as np
    from memstara.matcher import embedder
    from memstara.research_inputs import ensure_matcher
    calls = []
    def encoder(_):
        calls.append(True)
        return lambda texts: np.ones((len(texts), 8), dtype=np.float32)
    monkeypatch.setattr(embedder, 'sentence_transformer_encoder', encoder)
    first = prepare(register(sample)['id'])
    second = prepare(register({**sample, 'target':{**sample['target'], 'description':'A second study'}})['id'])
    with monkeypatch.context() as context:
        context.setattr(os, 'environ', dict(os.environ))
        activate(first)
        ensure_matcher(first)
        ensure_matcher(first)
        assert len(calls) == 1
        activate(second)
        ensure_matcher(second)
        assert len(calls) == 2
        catalog = Path(second['root']) / 'derived/matcher_catalog.json'
        catalog.write_text('Corrupted cache')
        ensure_matcher(second)
        assert len(calls) == 3
        assert 'record_id' not in catalog.read_text()
        assert 'outcome' not in catalog.read_text()


def test_generic_profiles_do_not_silently_apply_legacy_domain_skills():
    from memstara.research_inputs import validate_skills
    validate_skills({'hypothesis':['hypothesis_research', 'random_features'],
                     'report':['report_clinical_explanations']})
    with pytest.raises(ValueError, match='corpus-independent'):
        validate_skills({'hypothesis':['comorbidity']})
    with pytest.raises(ValueError, match='specialist domain'):
        validate_skills({'report':['shared-anil-hiv']})


def test_control_launch_uses_selected_inputs_without_changing_server_environment(sample, tmp_path, monkeypatch):
    from memstara.control import service
    from memstara import stage_models
    source = Path(sample['dataset_path'])
    lines = source.read_text().splitlines()
    source.write_text('\n'.join([lines[0], *(lines[1:] * 30)]) + '\n')
    record = register(sample)
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(tmp_path / 'unrelated-missing.csv'))
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'test-model')
    monkeypatch.setattr(stage_models, 'resolve_run_profiles', lambda _: {})
    scopes, launches, responses = [], [], []
    def skills(root=None):
        scopes.append(root)
        return []
    monkeypatch.setattr(service, 'skills', skills)
    monkeypatch.setattr(service, 'new_run_dir', lambda *args: tmp_path / 'run')
    manager = SimpleNamespace(start=lambda argv, *args: launches.append(argv) or {'run_tag':'fixture'})
    handler = object.__new__(service.Handler)
    handler._send = lambda status, payload: responses.append((status, payload))
    before = dict(os.environ)
    handler._launch({'research_input_id':record['id'], 'y_column':'stale'}, manager)
    assert responses[0][0] == 201
    assert len(launches) == 1
    argv = launches[0]
    assert argv[argv.index('--y-column') + 1] == 'outcome'
    assert argv[argv.index('--research-input-id') + 1] == record['id']
    assert scopes == [Path(prepare(record['id'])['root']) / 'okf']
    assert dict(os.environ) == before
