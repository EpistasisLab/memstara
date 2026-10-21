"""Exercise the user entrypoint without Docker, providers, or project secrets."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def launcher(tmp_path, *, env=True):
    shutil.copy(ROOT / 'start.sh', tmp_path / 'start.sh')
    (tmp_path / 'deployment').mkdir()
    for name in ('build-service.sh', 'mount_directories.py'):
        shutil.copy(ROOT / 'deployment' / name, tmp_path / 'deployment' / name)
    (tmp_path / '.env.example').write_text('OPENAI_API_KEY=REPLACE_ME\n')
    if env:
        (tmp_path / '.env').write_text('OPENAI_API_KEY=PRIVATE_TEST_SENTINEL\n')
    binary = tmp_path / 'bin'
    binary.mkdir()
    docker = binary / 'docker'
    docker.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$CALLS"
case "$*" in
  "info") [ "$FAIL" != daemon ] ;;
  "compose run "*) [ "$FAIL" != preflight ] ;;
  "compose up "*) [ "$FAIL" != startup ] ;;
  "compose exec "*) [ "$FAIL" != readiness ] ;;
  "compose port web 80") echo '127.0.0.1:15999' ;;
  *) exit 0 ;;
esac
''')
    docker.chmod(0o755)
    sleeper = binary / 'sleep'
    sleeper.write_text('#!/bin/sh\nexit 0\n')
    sleeper.chmod(0o755)
    return {**os.environ, 'PATH': str(binary) + ':' + os.environ['PATH'],
            'CALLS': str(tmp_path / 'calls'), 'FAIL': ''}


def run(tmp_path, environment):
    return subprocess.run(['sh', str(tmp_path / 'start.sh')], cwd=tmp_path.parent,
                          env=environment, capture_output=True, text=True)


def test_missing_env_creates_private_template_and_never_starts(tmp_path):
    environment = launcher(tmp_path, env=False)
    result = run(tmp_path, environment)
    assert result.returncode == 1
    assert (tmp_path / '.env').stat().st_mode & 0o777 == 0o600
    assert not (tmp_path / 'calls').exists()
    assert 'Edit the model deployment' in result.stdout


def test_start_preserves_env_and_checks_proxy_before_reporting_url(tmp_path):
    environment = launcher(tmp_path)
    before = (tmp_path / '.env').read_bytes()
    result = run(tmp_path, environment)
    assert result.returncode == 0
    assert (tmp_path / '.env').read_bytes() == before
    calls = (tmp_path / 'calls').read_text()
    assert 'compose up -d --no-build --force-recreate' in calls
    for service in ('control', 'initialize', 'api', 'web'):
        assert calls.index('compose build ' + service) < calls.index('compose up')
    assert '/api/discovery/questions' in calls and '/control/health' in calls
    assert 'http://127.0.0.1:15999/' in result.stdout
    assert 'PRIVATE_TEST_SENTINEL' not in result.stdout + result.stderr + calls
    assert 'down' not in calls


@pytest.mark.parametrize('failure', ['daemon', 'startup'])
def test_failures_never_report_ready(tmp_path, failure):
    environment = launcher(tmp_path)
    environment['FAIL'] = failure
    result = run(tmp_path, environment)
    assert result.returncode != 0
    assert 'Memstara is ready' not in result.stdout
    assert 'compose exec' not in (tmp_path / 'calls').read_text()


def test_readiness_failure_is_not_reported_as_success(tmp_path):
    environment = launcher(tmp_path)
    environment['FAIL'] = 'readiness'
    result = run(tmp_path, environment)
    assert result.returncode == 1
    assert 'readiness could not be confirmed' in result.stderr
    assert 'Memstara is ready' not in result.stdout
    calls = (tmp_path / 'calls').read_text()
    assert calls.count('compose exec') == 30
    assert 'compose port' not in calls


def test_preflight_failure_does_not_build_or_restart_application(tmp_path):
    environment = launcher(tmp_path)
    environment['FAIL'] = 'preflight'
    result = run(tmp_path, environment)
    assert result.returncode == 1
    assert 'Preflight failed' in result.stderr
    calls = (tmp_path / 'calls').read_text()
    assert 'compose build configure' in calls
    assert '--check' in calls
    assert 'compose up' not in calls
    assert 'compose exec' not in calls
