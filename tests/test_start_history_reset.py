"""Exercise startup ordering with fake Docker; never touch a real DB."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture
def startup(tmp_path):
    root = Path(__file__).resolve().parents[1]
    shutil.copyfile(root / "start.sh", tmp_path / "start.sh")
    (tmp_path / ".env").write_text("# synthetic settings\n")
    deployment = tmp_path / "deployment"
    deployment.mkdir()
    (deployment / "reset-execution-history.py").write_text("# fake cleanup\n")
    (deployment / "backup-execution-history.py").write_text(
        'import os, sys\n'
        'with open(os.environ["TEST_EVENTS"], "a") as f: f.write("backup\\n")\n'
        'sys.exit(int(os.environ.get("TEST_BACKUP_FAILURE", "0")))\n')
    (deployment / "mount_directories.py").write_text("# fake mount inspection\n")
    (deployment / "select-web-port.sh").write_text("#!/bin/sh\nexit 0\n")
    (deployment / "build-service.sh").write_text(
        '#!/bin/sh\necho "build $1" >> "$TEST_EVENTS"\n'
        'if [ "$1" = "--bootstrap" ]; then echo synthetic-image > "$2"; fi\n')
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text('''#!/bin/sh
echo "docker $*" >> "$TEST_EVENTS"
case "$*" in
  *reset-execution-history.py*--apply*) exit "${TEST_CLEANUP_FAILURE:-0}" ;;
  "compose config --format json") echo '{}' ;;
  "compose port web 80") echo '127.0.0.1:8070' ;;
esac
exit 0
''')
    docker.chmod(0o755)
    events = tmp_path / "events"
    env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
           "TEST_EVENTS": str(events)}
    return tmp_path, env, events


def test_normal_start_never_cleans_history(startup):
    root, env, events = startup
    result = subprocess.run(["sh", "start.sh"], cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "--apply" not in events.read_text()
    assert "backup\n" not in events.read_text()
    assert "compose up" in events.read_text()


@pytest.mark.parametrize("failure", [False, True])
def test_explicit_reset_follows_build_and_stops_on_failure(startup, failure):
    root, env, events = startup
    env["TEST_CLEANUP_FAILURE"] = "1" if failure else "0"
    result = subprocess.run(["sh", "start.sh", "--reset-execution-history"],
                            cwd=root, env=env, capture_output=True, text=True)
    log = events.read_text()
    assert log.index("build web") < log.index("compose stop control api web") < log.index("--apply")
    assert log.index("compose stop control api web") < log.index("backup\n") < log.index("--apply")
    if failure:
        assert result.returncode != 0
        assert "compose up" not in log
    else:
        assert result.returncode == 0, result.stderr
        assert log.index("--apply") < log.index("compose up")
        assert "compose exec -T control python /app/deployment/check_web.py" in log


def test_backup_failure_prevents_deletion_and_restart(startup):
    root, env, events = startup
    env['TEST_BACKUP_FAILURE'] = '1'
    result = subprocess.run(['sh', 'start.sh', '--reset-execution-history'],
                            cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert '--apply' not in events.read_text()
    assert 'compose up' not in events.read_text()
