"""Preservation must fail closed without touching an operational installation."""
import json

import pytest

from memstara import preservation as p


def bundle(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'checkpoint.json').write_text('{"completed": true}')
    root = tmp_path / 'backup'
    root.mkdir()
    trees = {name: p.archive_tree(source, root / name)
             for name in ('outputs.tar.gz', 'installation.tar.gz')}
    for name in ('board.dump', 'runtime.dump'):
        (root / name).write_bytes(b'synthetic dump')
    manifest = {'version': 1, 'status': 'complete', 'trees': trees,
                'files': {f.name: p.digest(f) for f in root.iterdir()}}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    return root


def test_complete_bundle_verifies(tmp_path):
    assert p.verify(bundle(tmp_path))['status'] == 'complete'


@pytest.mark.parametrize('change', ['corrupt', 'missing', 'extra', 'incomplete', 'inventory'])
def test_corrupt_bundle_is_rejected(tmp_path, change):
    root = bundle(tmp_path)
    if change == 'corrupt':
        (root / 'board.dump').write_bytes(b'changed')
    elif change == 'missing':
        (root / 'runtime.dump').unlink()
    elif change == 'extra':
        (root / 'extra').touch()
    else:
        path = root / 'manifest.json'
        value = json.loads(path.read_text())
        if change == 'incomplete':
            value['status'] = 'incomplete'
        else:
            value['trees']['outputs.tar.gz'] = {}
        path.write_text(json.dumps(value))
    with pytest.raises(p.PreservationError):
        p.verify(root)


def test_symlink_target_is_recorded_without_reading_external_content(tmp_path):
    (tmp_path / 'link').symlink_to('/nonexistent/old-installation')
    assert p.inventory(tmp_path) == {'link': 'symlink:/nonexistent/old-installation'}


@pytest.mark.parametrize('service', ['control', 'initialize', 'web', 'api'])
def test_active_application_refuses_backup(service):
    services = {n: {'State': {'Running': True}} for n in ('board', 'runtime', service)}
    with pytest.raises(p.PreservationError, match='Stop application'):
        p.require_quiet(services)


@pytest.mark.parametrize('host_storage', [False, True])
def test_drill_cleans_owned_container_on_restore_failure(tmp_path, monkeypatch, host_storage):
    root = bundle(tmp_path)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if 'pg_restore' in args:
            raise p.PreservationError('synthetic restore failure')
        return b''
    monkeypatch.setattr(p, 'command', run)
    with pytest.raises(p.PreservationError):
        p.drill(root, storage_parent=tmp_path if host_storage else None)
    assert calls[-1][:4] == ['docker', 'rm', '--force', '--volumes']
    assert calls[-1][-1].startswith('memstara-restore-drill-')
    assert not any('compose' in args for args in calls)
    assert any('pg_isready -h 127.0.0.1' in arg for args in calls for arg in args)
    create = next(args for args in calls if args[:2] == ['docker', 'create'])
    assert any('dst=/var/lib/postgresql/data' in arg for arg in create) == host_storage
    assert not list(tmp_path.glob('memstara-restore-*'))


def test_host_restore_data_is_retained_if_container_removal_fails(tmp_path, monkeypatch):
    root = bundle(tmp_path)
    def run(args, **kwargs):
        if args[:2] == ['docker', 'rm']:
            raise p.PreservationError('container may still be running')
        return b''
    monkeypatch.setattr(p, 'command', run)
    with pytest.raises(p.PreservationError, match='still be running'):
        p.drill(root, storage_parent=tmp_path)
    assert len(list(tmp_path.glob('memstara-restore-*'))) == 1


@pytest.mark.parametrize('state', ['intact', 'missing', 'changed', 'outside'])
def test_registry_audit_detects_missing_or_changed_artifacts(tmp_path, monkeypatch, state):
    root = tmp_path / 'outputs'
    root.mkdir()
    saved = root / 'result.json'
    saved.write_text('saved')
    row = {'run_tag': 'synthetic', 'path': '/app/outputs/result.json',
           'sha256': p.digest(saved), 'bytes': saved.stat().st_size}
    if state == 'missing':
        saved.unlink()
    elif state == 'changed':
        saved.write_text('other')
    elif state == 'outside':
        row['path'] = '/unrelated/result.json'
    monkeypatch.setattr(p, 'inspect_installation', lambda: {
        'control': {'Mounts': [{'Type': 'bind', 'Source': str(root), 'Destination': '/app/outputs'}]},
        'board': {'Id': 'synthetic-board'},
    })
    monkeypatch.setattr(p, 'command', lambda *a, **k: json.dumps([row]).encode())
    result = p.audit_records()
    assert result['status'] == ('passed' if state == 'intact' else 'issues_found')
    assert len(result['problems']) == (0 if state == 'intact' else 1)


def test_backup_refuses_active_app_before_creating_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(p, 'inspect_installation', lambda: {'control': {'State': {'Running': True}}})
    with pytest.raises(p.PreservationError):
        p.backup(tmp_path / 'backup')
    assert not (tmp_path / 'backup').exists()


def test_backup_preserves_complete_set_and_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.memstara').mkdir()
    (tmp_path / '.memstara' / 'installation.json').write_text('{"synthetic": true}')
    outputs = tmp_path / 'outputs'
    outputs.mkdir()
    (outputs / 'checkpoint.json').write_text('{"completed": true}')
    services = {n: {'Id': n, 'Image': 'synthetic-image', 'State': {'Running': True}}
                for n in ('board', 'runtime')}
    services['control'] = {'Id': 'control', 'Image': 'synthetic-image', 'State': {'Running': False},
                           'Mounts': [{'Type': 'bind', 'Source': str(outputs), 'Destination': '/app/outputs'}]}
    monkeypatch.setattr(p, 'inspect_installation', lambda: services)
    monkeypatch.setattr(p, 'command', lambda *a, **k: b'synthetic')
    def db(container, action, stdout=None):
        if action == 'clients':
            return b'0'
        stdout.write(b'synthetic dump')
    monkeypatch.setattr(p, 'database_command', db)
    root = p.backup(tmp_path / 'backup')
    assert p.verify(root)['status'] == 'complete'
    assert root.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        p.backup(root)


def test_explicit_old_root_mapping_is_read_only(tmp_path, monkeypatch):
    (tmp_path / 'result').write_text('saved')
    row = {'run_tag': 'old', 'path': '/old/outputs/result', 'bytes': 5,
           'sha256': p.digest(tmp_path / 'result')}
    monkeypatch.setattr(p, 'inspect_installation', lambda: {
        'control': {'Mounts': [{'Type': 'bind', 'Source': str(tmp_path), 'Destination': '/app/outputs'}]},
        'board': {'Id': 'synthetic'},
    })
    calls = []
    def cmd(args):
        calls.append(args)
        return json.dumps([row]).encode()
    monkeypatch.setattr(p, 'command', cmd)
    assert p.audit_records()['status'] == 'issues_found'
    assert p.audit_records('/old/outputs')['status'] == 'passed'
    assert all('SELECT' in call[-1] for call in calls)
