"""Port collision handling keeps other apps and private installation values intact."""
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('web_port', ROOT / 'deployment/web_port.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_resolved_binding_and_private_env_preserved(tmp_path):
    assert module.requested({'services': {'web': {'ports': [
        {'target': 80, 'host_ip': '127.0.0.1', 'published': '5173'}]}}}) == '5173'
    env = tmp_path / '.env'
    env.write_text('# Keep this comment\nAPI_KEY=private-sentinel\nMEMSTARA_WEB_PORT=5173\n')
    module.save(tmp_path, '49155')
    assert env.read_text() == '# Keep this comment\nAPI_KEY=private-sentinel\nMEMSTARA_WEB_PORT=49155\n'


@pytest.mark.parametrize('value', ['0', '65536', '-1', 'abc'])
def test_invalid_port_does_not_change_env(tmp_path, value):
    env = tmp_path / '.env'
    env.write_text('MEMSTARA_WEB_PORT=5173\n')
    with pytest.raises(ValueError):
        module.save(tmp_path, value)
    assert env.read_text() == 'MEMSTARA_WEB_PORT=5173\n'


def selector(tmp_path, case):
    binary = tmp_path / 'docker'
    binary.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$CALLS"
case "$*" in
  *"web_port.py requested") echo 5173 ;;
  "compose ps --status running -q web") [ "$CASE" != own ] || echo own-web ;;
  "compose port web 80") echo 127.0.0.1:5173 ;;
  "ps --format "*) [ "$CASE" != published ] || echo '0.0.0.0:5173->80/tcp' ;;
  "create "*)
    cidfile=$3
    case "$*" in
      *127.0.0.1::80*) echo fallback > "$cidfile" ;;
      *) echo preferred > "$cidfile" ;;
    esac ;;
  "start preferred")
    case "$CASE" in
      occupied) echo 'bind: address already in use' >&2; exit 1 ;;
      failure) echo 'Docker engine is unavailable' >&2; exit 1 ;;
    esac ;;
  "port fallback 80/tcp") echo 127.0.0.1:49155 ;;
  *) exit 0 ;;
esac
''')
    binary.chmod(0o755)
    environment = {**os.environ, 'PATH': str(tmp_path) + ':' + os.environ['PATH'],
                   'CALLS': str(tmp_path / 'calls'), 'CASE': case}
    result = subprocess.run(['sh', str(ROOT / 'deployment/select-web-port.sh'), 'test-preparer'],
                            cwd=tmp_path, env=environment, text=True, capture_output=True)
    return result, (tmp_path / 'calls').read_text()


@pytest.mark.parametrize('case', ['own', 'free', 'occupied', 'published', 'failure'])
def test_docker_publisher_selection_and_cleanup(tmp_path, case):
    result, calls = selector(tmp_path, case)
    assert result.returncode == (1 if case == 'failure' else 0), result.stderr
    assert 'compose stop' not in calls and 'compose down' not in calls
    if case == 'own':
        assert 'create ' not in calls
    elif case != 'published':
        assert 'rm -f preferred' in calls
    if case in ('occupied', 'published'):
        assert '127.0.0.1::80' in calls
        assert 'web_port.py save /project 49155' in calls
        assert 'rm -f fallback' in calls
        assert 'Port 5173 is in use' in result.stdout
    else:
        assert 'web_port.py save' not in calls
        assert '127.0.0.1::80' not in calls
