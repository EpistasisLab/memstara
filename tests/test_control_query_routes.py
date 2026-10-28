"""Exercise query-string HTTP handlers together, including live Replicate records."""
import json
from types import SimpleNamespace
import pytest


def request(service, path):
    handler = object.__new__(service.Handler)
    handler.path = path
    handler._refuse_stranger = lambda: False
    responses = []
    handler._send = lambda code, body: responses.append((code, body))
    handler.do_GET()
    assert len(responses) == 1
    return responses[0]


@pytest.mark.parametrize('loop', [1, 2])
def test_replicate_query_after_model_capabilities(tmp_path, monkeypatch, loop):
    from memstara.control import service
    from memstara.combinations import build_plan
    plan = build_plan({'hypothesis': ['hypothesis_general'], 'data': ['data_training_heavy'],
                      'ml': ['ml_logistic_regression'], 'interpreter': ['shared-shap'],
                      'report': ['shared-addiction']}, 2)
    (tmp_path/'config.json').write_text(json.dumps({'combination_plan': plan}))
    (tmp_path/'execution.json').write_text(json.dumps({'calls': [
        {'loop': 1, 'stage': 'data#1', 'status': 'completed'},
        {'loop': 2, 'stage': 'ml#1', 'status': 'started'}]}))
    manager = SimpleNamespace(running=lambda: {'run_dir': str(tmp_path), 'run_tag': 'synthetic-live'})
    monkeypatch.setattr(service, 'WORKSPACE', SimpleNamespace(manager=lambda key: manager))
    # Each request is a fresh handler, as in ThreadingHTTPServer.
    assert request(service, '/control/model-capabilities?provider=azure_foundry&model=gpt-5')[0] == 200
    status, body = request(service, f'/control/pipelines/experiment/combinations?loop={loop}')
    assert status == 200
    assert body['run_tag'] == 'synthetic-live'
    assert body['planned']['repetition'] == loop
    assert len(body['calls']) == 1 and body['calls'][0]['loop'] == loop


def test_invalid_replicate_query_returns_json_error(monkeypatch):
    from memstara.control import service
    monkeypatch.setattr(service, 'WORKSPACE', SimpleNamespace(manager=lambda key: None))
    status, body = request(service, '/control/pipelines/experiment/combinations?loop=invalid')
    assert status == 400 and body['error']


def test_actual_http_query_routes_in_isolated_process():
    import subprocess
    import sys
    from pathlib import Path
    script = Path(__file__).resolve().parents[1] / 'deployment/check_control_routes.py'
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Control HTTP smoke passed' in result.stdout
