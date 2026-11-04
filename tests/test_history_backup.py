import importlib.util
import json
from pathlib import Path
import tarfile
import subprocess
import sys

import pytest


@pytest.fixture
def module(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('backup_history', Path(__file__).resolve().parents[1] / 'deployment/backup-execution-history.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.chdir(tmp_path)
    for name in ('outputs', 'user-inputs'):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'record.json').write_text('{"saved": true}')
    (tmp_path / '.env').write_text('PRIVATE=synthetic')
    config = {'services': {'control': {'volumes': [
        {'type': 'bind', 'target': '/app/' + name, 'source': str(tmp_path / name)}
        for name in ('outputs', 'user-inputs')]}}}
    monkeypatch.setattr(mod.subprocess, 'check_output', lambda args: json.dumps(config).encode())
    monkeypatch.setattr(mod.os, 'umask', lambda mode: None)
    return mod


def test_complete_backup_preserves_files_and_dumps(module, tmp_path, monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if 'run' in args:
            assert args[args.index('--user') + 1] == '0:0'
            assert args[args.index('--entrypoint') + 1] == 'python'
            assert '--no-deps' in args and '-T' in args
            mounts = {}
            for i, arg in enumerate(args):
                if arg == '-v':
                    source, target, mode = args[i + 1].rsplit(':', 2)
                    assert mode == 'ro'
                    mounts[target] = source
            sources = {k: mounts[v] for k, v in json.loads(args[-1]).items()}
            subprocess.run([sys.executable, '-c', args[-2], json.dumps(sources)],
                           check=True, stdout=kwargs['stdout'])
        elif 'stdout' in kwargs and hasattr(kwargs['stdout'], 'write'):
            kwargs['stdout'].write(b'fake database archive')
    monkeypatch.setattr(module, 'run', run)
    folder = module.backup(tmp_path / 'backups')
    manifest = json.loads((folder / 'COMPLETE.json').read_text())
    assert set(manifest['files']) == {'board.dump', 'runtime.dump', 'files.tar.gz'}
    assert sum('pg_restore' in c for c in calls) == 2
    with tarfile.open(folder / 'files.tar.gz') as archive:
        assert archive.extractfile('.env').read() == b'PRIVATE=synthetic'
        assert archive.extractfile('outputs/record.json').read() == b'{"saved": true}'
    assert (tmp_path / 'outputs/record.json').exists()


def test_failed_dump_has_no_complete_marker(module, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('dump failed')
    monkeypatch.setattr(module, 'run', fail)
    with pytest.raises(RuntimeError, match='dump failed'):
        module.backup(tmp_path / 'backups')
    assert not list((tmp_path / 'backups').rglob('COMPLETE.json'))


def test_backup_cannot_be_inside_outputs(module, tmp_path):
    with pytest.raises(RuntimeError, match='outside'):
        module.backup(tmp_path / 'outputs/backups')


def test_container_archive_failure_prevents_complete_marker(module, tmp_path, monkeypatch):
    def run(args, **kwargs):
        if 'run' in args:
            raise subprocess.CalledProcessError(1, args)
        if hasattr(kwargs.get('stdout'), 'write'):
            kwargs['stdout'].write(b'fake database archive')
    monkeypatch.setattr(module, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        module.backup(tmp_path / 'backups')
    assert not list((tmp_path / 'backups').rglob('COMPLETE.json'))
    assert (tmp_path / 'outputs/record.json').exists()
