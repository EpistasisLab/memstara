"""Offline HTTP smoke test; no experiments, credentials or provider requests.

Runs inside every runtime image build so local deployment cannot bypass CI's
query-route coverage. Fixtures and server exist only in this isolated process.
"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer


def main():
    with TemporaryDirectory(prefix='memstara-route-check-') as directory:
        os.environ['MEMSTARA_CONFIG_MODE'] = 'environment'
        os.environ['MEMSTARA_OUTPUT_DIR'] = directory
        from memstara.control import service
        from memstara.combinations import build_plan
        from motoro.services.model_capabilities import get_capabilities, ModelCapabilities
        root = Path(directory) / 'synthetic-run'
        root.mkdir()
        plan = build_plan({'hypothesis': ['hypothesis_general'], 'data': ['data_training_heavy'],
                          'ml': ['ml_logistic_regression'], 'interpreter': ['shared-shap'],
                          'report': ['shared-addiction']}, 2)
        (root / 'config.json').write_text(json.dumps({'combination_plan': plan}))
        (root / 'execution.json').write_text(json.dumps({'calls': [
            {'loop': 1, 'stage': 'data#1', 'status': 'completed'},
            {'loop': 2, 'stage': 'ml#1', 'status': 'started'}]}))
        (root / 'control.log').write_text('first\nsecond\n')
        manager = SimpleNamespace(running=lambda: {'run_dir': str(root), 'run_tag': 'synthetic'})
        service.WORKSPACE = SimpleNamespace(manager=lambda key: manager)
        service.RUNS = SimpleNamespace(locate=lambda tag: ('synthetic', root))
        server = ThreadingHTTPServer(('127.0.0.1', 0), service.Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            def get(path):
                with urlopen(base + path, timeout=10) as response:
                    assert response.status == 200
                    return json.load(response)
            # Test both request orders: a route must not rely on a prior request.
            for _ in range(2):
                for loop in (1, 2):
                    body = get(f'/control/pipelines/test/combinations?loop={loop}')
                    assert body['planned']['repetition'] == loop
                    assert len(body['calls']) == 1 and body['calls'][0]['loop'] == loop
                assert get('/control/runs/synthetic/log?offset=6')['text'] == 'second\n'
                assert get('/control/model-catalog')['source'] == 'motoro'
                # Motoro 0.15 does not infer sampling support from a model ID.
                # Verify the HTTP contract against installed Motoro metadata,
                # including unknown support for a custom Azure deployment.
                for model in ('gpt-5', 'synthetic-deployment'):
                    caps = get(f'/control/model-capabilities?provider=azure_foundry&model={model}')['capabilities']
                    ModelCapabilities.model_validate(caps)
                    assert caps == get_capabilities(model).model_dump(mode='json')
            try:
                get('/control/pipelines/test/combinations?loop=invalid')
                raise AssertionError('Invalid loop must return a JSON 400 response')
            except HTTPError as error:
                assert error.code == 400 and json.load(error)['error']
            print('Control HTTP smoke passed: Replicate records, log offsets, model catalog/capabilities, invalid query.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
