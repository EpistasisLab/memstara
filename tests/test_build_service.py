"""Exercise the real shell wrapper with an isolated fake Docker executable."""
from pathlib import Path
import os
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'deployment/build-service.sh'


@pytest.mark.parametrize('mode,expected_calls,success', [
    ('transient', 2, True), ('persistent', 3, False), ('compile', 1, False),
])
@pytest.mark.parametrize('bootstrap', [False, True])
def test_build_retry_classification(tmp_path, mode, expected_calls, success, bootstrap):
    docker = tmp_path / 'docker'
    docker.write_text('''#!/bin/sh
n=0
[ ! -f "$COUNT" ] || n=$(cat "$COUNT")
n=$((n + 1))
printf '%s' "$n" > "$COUNT"
if [ "$MODE" = compile ]; then echo 'TypeScript compilation failed'; exit 1; fi
if [ "$MODE" = transient ] && [ "$n" -gt 1 ]; then exit 0; fi
echo 'failed to dial gRPC: unable to upgrade to h2c, received 500'
exit 1
''')
    docker.chmod(0o755)
    sleep = tmp_path / 'sleep'
    sleep.write_text('#!/bin/sh\nexit 0\n')
    sleep.chmod(0o755)
    count = tmp_path / 'count'
    env = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'],
           'COUNT': str(count), 'MODE': mode}
    args = ['--bootstrap', str(tmp_path / 'image')] if bootstrap else ['control']
    result = subprocess.run(['sh', str(SCRIPT), *args], env=env, capture_output=True, text=True)
    assert (result.returncode == 0) == success
    assert int(count.read_text()) == expected_calls


def test_start_builds_before_recreating_services():
    text = (SCRIPT.parents[1] / 'start.sh').read_text()
    assert text.index('for service in control initialize api web') < text.index('compose up -d --no-build')
    assert 'compose up -d --build' not in text
