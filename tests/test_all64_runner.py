"""A failed/ambiguous launch must stop a costly batch rather than duplicate work."""
import importlib.util
import json
from pathlib import Path

# Repository scripts are not part of the installed package. Load this script by
# its explicit path so the pytest console entry point needs no cwd in sys.path.
spec = importlib.util.spec_from_file_location(
    "run_all64", Path(__file__).parents[1] / "scripts/run_all64.py"
)
run_all64 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_all64)
execute, save = run_all64.execute, run_all64.save


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr('memstara.combinations.validate_plan', lambda _: None)
    save(tmp_path / 'schedule.json', {})
    save(tmp_path / 'status.json', {'state': 'prepared', 'completed': 0,
         'combinations': [{'id': 'C01', 'state': 'pending'}, {'id': 'C02', 'state': 'pending'}]})
    for name in ['C01', 'C02']:
        (tmp_path / name).mkdir()
        save(tmp_path / name / 'configuration.json', {})


def test_failed_run_stops_before_second_launch(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    run = tmp_path / 'run'
    run.mkdir()
    save(run / 'pipeline_status.json', {'status': 'failed', 'code': 'model_output_incomplete'})
    save(run / 'registry_status.json', {'status': 'synced'})
    posts = []
    def request(path, body=None):
        if body is None:
            return {'running': None}
        posts.append(body)
        return {'run_tag': 'test-run', 'run_dir': str(run)}
    monkeypatch.setattr(run_all64, 'request', request)
    execute(tmp_path)
    result = json.loads((tmp_path / 'status.json').read_text())
    assert len(posts) == 1
    assert result['state'] == 'paused_on_error' and result['completed'] == 0
    assert result['combinations'][1]['state'] == 'pending'


def test_ambiguous_launch_timeout_is_not_retried(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    posts = []
    def request(path, body=None):
        if body is None:
            return {'running': None}
        posts.append(body)
        raise TimeoutError('Launch acknowledgement unavailable')
    monkeypatch.setattr(run_all64, 'request', request)
    execute(tmp_path)
    assert len(posts) == 1
    assert json.loads((tmp_path / 'status.json').read_text())['state'] == 'paused_on_error'
