"""Live acceptance must preserve the selected installation's output boundary."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_live_batch_respects_configured_output_directory(tmp_path, monkeypatch):
    from memstara import env, stage_models

    path = Path(__file__).parent / 'live' / 'test_haiku_pipeline.py'
    spec = importlib.util.spec_from_file_location('live_acceptance_path_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(env, 'load_env', lambda: [])
    monkeypatch.setattr(stage_models, 'deployment_profiles', lambda: {
        'question': {'model': 'claude-haiku-5-5'},
    })
    configured = tmp_path / 'separate-installation' / 'outputs'
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(configured))
    options = SimpleNamespace(getoption=lambda key: 1 if key == '--live-loops' else None)
    batch = module.live_batch.__wrapped__(options)
    assert batch['root'].parent == configured / 'verification'
    assert batch['root'].is_dir()
