import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer' / 'api'))
import run_artifacts


def test_historical_429_matches_control_projection_and_preserves_archive(tmp_path):
    from memstara.pipeline.failures import visible_failure
    path = tmp_path / 'pipeline_failure.json'
    original = json.dumps({'code': 'model_request_rejected', 'http_status': 429,
                           'message': 'The model rejected the request settings.',
                           'stage': 'hypothesis0', 'loop': 1})
    path.write_text(original)
    result = run_artifacts.pipeline_state(tmp_path)
    assert result['code'] == 'model_rate_limit'
    assert result['message'] == visible_failure(tmp_path)['message']
    assert path.read_text() == original


def test_first_failure_overrides_generic_group_error_without_mutating_archive(tmp_path):
    status = {'status': 'failed', 'error_type': 'ExceptionGroup',
              'message': 'Pipeline could not safely continue; inspect console.log and trace/.'}
    failure = {'code': 'tool_argument_validation', 'stage': 'question0-1', 'loop': 1,
               'message': 'Tool argument correction exhausted.', 'exception_types': ['ValueError']}
    for name, value in [('pipeline_status.json', status), ('pipeline_failure.json', failure)]:
        (tmp_path / name).write_text(json.dumps(value))
    state = run_artifacts.pipeline_state(tmp_path)
    assert state['message'] == failure['message']
    assert state['stage'] == 'question0-1' and state['loop'] == 1
    assert state['code'] == 'tool_argument_validation'
    assert json.loads((tmp_path / 'pipeline_status.json').read_text()) == status


def test_failure_visible_before_outer_status_write(tmp_path):
    (tmp_path / 'pipeline_failure.json').write_text(json.dumps({
        'message': 'Question generation failed.', 'stage': 'question', 'loop': 1}))
    assert run_artifacts.pipeline_state(tmp_path)['status'] == 'failed'


def test_completed_status_not_replaced_by_stale_failure(tmp_path):
    (tmp_path / 'pipeline_status.json').write_text(json.dumps({'status': 'completed'}))
    (tmp_path / 'pipeline_failure.json').write_text(json.dumps({'message': 'Historical failure'}))
    assert run_artifacts.pipeline_state(tmp_path) == {'status': 'completed'}


def test_legacy_provider_exception_is_explained_without_inventing_http_status(tmp_path):
    (tmp_path / 'pipeline_failure.json').write_text(json.dumps({
        'message': 'An agent failed.', 'code': 'agent_execution_failed',
        'exception_types': ['InternalServerError', 'HTTPStatusError'], 'stage': 'hypothesis0'}))
    state = run_artifacts.pipeline_state(tmp_path)
    assert state['code'] == 'model_server'
    assert 'internal server error' in state['message']
    assert '500' not in state['message']


def test_artifacts_are_scoped_and_do_not_expose_prompts(tmp_path, monkeypatch):
    monkeypatch.setattr(run_artifacts, 'ROOT', tmp_path)
    for tag in ('first', 'second'):
        directory = tmp_path / tag
        directory.mkdir()
        (directory / 'config.json').write_text(json.dumps({
            'run_tag': tag, 'hypotheses': 3, 'skill': tag + '-source', 'prompts': 'private'}))
        (directory / 'execution.json').write_text(json.dumps({'calls': [{'run_id': tag}]}))
        (directory / 'report.md').write_text(tag + ' report')
    selected = run_artifacts.lookup('first')
    assert selected['calls'] == [{'run_id': 'first'}]
    assert selected['config']['skill'] == 'first-source'
    assert selected['report']['text'] == 'first report'
    assert 'prompts' not in selected['config']
    assert run_artifacts.lookup('../first') is None


def test_index_does_not_rescan_directories_without_configs(tmp_path, monkeypatch):
    monkeypatch.setattr(run_artifacts, 'ROOT', tmp_path)
    for name in ('archived', 'first', 'second'):
        (tmp_path / name).mkdir()
    (tmp_path / 'first' / 'config.json').write_text(json.dumps({'run_tag': 'first'}))
    original = run_artifacts.read_json
    reads = []
    def counted(path):
        reads.append(path)
        return original(path)
    monkeypatch.setattr(run_artifacts, 'read_json', counted)
    run_artifacts.configs()
    initial = len(reads)
    for _ in range(46):
        run_artifacts.config_for('first')
    assert len(reads) == initial


def test_live_report_updates_and_report_recovery_are_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(run_artifacts, 'ROOT', tmp_path)
    base = tmp_path / 'base'
    recovery = tmp_path / 'recovery'
    for directory, config in ((base, {'run_tag': 'run', 'hypotheses': 2}),
                              (recovery, {'run_tag': 'run', 'mode': 'report_only'})):
        directory.mkdir()
        (directory / 'config.json').write_text(json.dumps(config))
    (recovery / 'execution.json').write_text(json.dumps({'calls': [
        {'stage': 'report', 'started_at': 1, 'status': 'completed'}]}))
    (recovery / 'report.md').write_text('first version')
    assert run_artifacts.lookup('run')['config']['hypotheses'] == 2
    assert run_artifacts.lookup('run')['config']['skill'] is None
    assert run_artifacts.lookup('run')['report']['text'] == 'first version'
    (recovery / 'report.md').write_text('updated version')
    assert run_artifacts.lookup('run')['report']['text'] == 'updated version'


def test_iteration_labels_use_frozen_trial_allocation_not_result_order():
    config = {"pipeline_id": "p1", "pipeline_name": "Pipeline 1", "trials": 2}
    assert run_artifacts.result_identity(config, "run1", 0)["iteration"] == 1
    # Missing trials must not collapse later iteration numbers.
    assert run_artifacts.result_identity(config, "run1", 6)["iteration"] == 4
    assert run_artifacts.result_identity({}, "legacy", 6)["iteration"] is None


def test_pipeline_results_keeps_all_outputs_and_run_identity(monkeypatch):
    import asyncio
    import pytest
    pytest.importorskip("fastapi", reason="Viewer API dependencies are installed in its container")
    import main as api
    async def results(tag):
        return [{"result_id": 1 if tag == "a" else 2, "trial": 0},
                {"result_id": 3 if tag == "a" else 4, "trial": 3}]
    async def board(tag):
        return []
    monkeypatch.setattr(api.scene, "_board", board)
    monkeypatch.setattr(api.scene, "_results", results)
    monkeypatch.setattr(api.run_artifacts, "configs", lambda: {
        tag: {"pipeline_id": tag, "pipeline_name": tag, "trials": 1} for tag in ("a", "b")})
    monkeypatch.setattr(api.pools.health, "as_dict", lambda: {"memstara": {"up": True}})
    response = asyncio.run(api.pipeline_results("a,b"))
    assert len(response["results"]) == 4
    assert [(r["run_tag"], r["iteration"]) for r in response["results"]] == [
        ("a", 1), ("a", 4), ("b", 1), ("b", 4)]


def test_specialist_report_provenance_survives_api(tmp_path,monkeypatch):
    monkeypatch.setattr(run_artifacts,'ROOT',tmp_path)
    directory=tmp_path/'expert'
    directory.mkdir()
    (directory/'config.json').write_text(json.dumps({'run_tag':'expert'}))
    metadata={'status':'completed','expert':'hiv','database_ids':['hiv-fixture'],
              'interpretation_methods':['shap'],'task_ids':[12]}
    (directory/'report_status.json').write_text(json.dumps({'status':'completed','specialist_explanation':metadata}))
    assert run_artifacts.lookup('expert')['report']['specialist_explanation']==metadata


def test_explanation_recovery_is_bound_to_selected_run(tmp_path, monkeypatch):
    monkeypatch.setattr(run_artifacts, 'ROOT', tmp_path)
    directory = tmp_path / 'run'
    recovery = directory / 'report-recovery-1' / 'report_io'
    recovery.mkdir(parents=True)
    (directory / 'config.json').write_text(json.dumps({'run_tag': 'selected'}))
    (recovery / 'loop-2-result-3-input.json').write_text(json.dumps({
        'run_tag': 'selected', 'loop': 2, 'result_id': 3, 'sha256': 'bound'}))
    (recovery / 'loop-2-result-3-output.json').write_text(json.dumps({
        'input_sha256': 'bound', 'output': 'Recovered narrative', 'execution': {'status': 'completed'}}))
    report = run_artifacts.lookup('selected')['report']
    assert report['text'] == ''
    assert report['explanation_outputs'][0]['text'] == 'Recovered narrative'


def test_config_cache_reuses_only_unchanged_files(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    path.write_text('{"run_tag":"a"}')
    original = run_artifacts.read_json
    reads = []
    def read(p):
        reads.append(p)
        return original(p)
    monkeypatch.setattr(run_artifacts, 'read_json', read)
    assert run_artifacts.read_config(path) == {'run_tag': 'a'}
    assert run_artifacts.read_config(path) == {'run_tag': 'a'}
    assert len(reads) == 1
    path.write_text('{"run_tag":"changed"}')
    assert run_artifacts.read_config(path) == {'run_tag': 'changed'}
    path.unlink()
    assert run_artifacts.read_config(path) is None
