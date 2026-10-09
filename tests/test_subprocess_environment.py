"""Tool processes honor cache/resource settings without receiving provider secrets."""
import os
import subprocess
import sys

import pytest


def test_real_tool_environment_preserves_isolated_cache_and_limits(tmp_path, monkeypatch):
    pytest.importorskip('motoro')
    from motoro.mcp.client import MCP_DEFAULT_ALLOWED_ENV_VARS, build_subprocess_env
    from memstara.config import Settings

    settings = Settings(_env_file=None)
    expected = {
        'HF_HOME': str(tmp_path / 'fresh-hf'),
        'HF_HUB_CACHE': str(tmp_path / 'fresh-hub'),
        'HF_HUB_OFFLINE': '1',
        'XDG_CACHE_HOME': str(tmp_path / 'fresh-xdg'),
        'OMP_NUM_THREADS': '1',
        'OPENBLAS_NUM_THREADS': '1',
        'TOKENIZERS_PARALLELISM': 'false',
    }
    for key, value in expected.items():
        monkeypatch.setenv(key, value)
    for key in ('ANTHROPIC_FOUNDRY_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'MOTORO_DATABASE_URL'):
        monkeypatch.setenv(key, 'test-only-secret')
    allowed = MCP_DEFAULT_ALLOWED_ENV_VARS | frozenset(settings.mcp_allowed_env_vars.split(','))
    child_env = build_subprocess_env(allowed_env_vars=allowed)
    assert {key: child_env.get(key) for key in expected} == expected
    assert not {'ANTHROPIC_FOUNDRY_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY',
                'MOTORO_DATABASE_URL'} & child_env.keys()
    subprocess.run([sys.executable, '-c',
                    'import os; assert os.environ["HF_HOME"] == os.environ["EXPECTED_HF_HOME"]; '
                    'assert os.environ["OMP_NUM_THREADS"] == "1"; '
                    'assert "OPENAI_API_KEY" not in os.environ'],
                   env={**child_env, 'EXPECTED_HF_HOME': expected['HF_HOME']}, check=True,
                   cwd=tmp_path, timeout=10)
    assert os.environ['OPENAI_API_KEY'] == 'test-only-secret'
