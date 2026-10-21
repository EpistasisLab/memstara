"""Offline Compose backup and isolated restore drill; never stops the application.

Archives retain symlink metadata without following or extracting links.
"""
import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import uuid
from typing import Any


class PreservationError(ValueError):
    pass


def command(args, *, stdout=None, stdin=None, timeout=600):
    result = subprocess.run(args, stdin=stdin, stdout=stdout or subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, check=False)
    if result.returncode:
        # Provider configuration and database errors can contain credentials.
        raise PreservationError(f'{args[0]} command failed (exit {result.returncode}); no credentials logged')
    return result.stdout


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def compose_ids():
    return command(['docker', 'compose', 'ps', '--all', '--quiet']).decode().split()


def inspect_installation():
    ids = compose_ids()
    if not ids:
        raise PreservationError('No existing Compose installation found in this directory')
    records = json.loads(command(['docker', 'inspect', *ids]))
    services = {}
    for record in records:
        name = record['Config']['Labels']['com.docker.compose.service']
        if name in services:
            raise PreservationError('Multiple containers for a service are not supported')
        services[name] = record
    return services


def require_quiet(services):
    for name, record in services.items():
        if name not in ('board', 'runtime', 'redis') and record['State']['Running']:
            raise PreservationError('Stop application services and finish all writers before backup; '
                                    'Pause is insufficient')
    for name in ('board', 'runtime'):
        if name not in services or not services[name]['State']['Running']:
            raise PreservationError('Both database services must be running')


def database_command(container, action, *, stdout=None):
    actions = {
        'dump': 'exec pg_dump -Fc --no-owner --no-acl -U "$POSTGRES_USER" "$POSTGRES_DB"',
        'clients': ('exec psql -X -At -U "$POSTGRES_USER" "$POSTGRES_DB" -c "SELECT count(*) FROM pg_stat_activity '
                    'WHERE datname=current_database() AND backend_type=\'client backend\' AND pid<>pg_backend_pid()"'),
    }
    return command(['docker', 'exec', container, 'sh', '-ec',
                    '. /settings/postgres.env; ' + actions[action]], stdout=stdout,
                   timeout=3600 if action == 'dump' else 600)


def assert_no_clients(services):
    require_quiet(services)
    for name in ('board', 'runtime'):
        if database_command(services[name]['Id'], 'clients').strip() != b'0':
            raise PreservationError('Database clients remain connected; finish all external writers before backup')


def inventory(root):
    files = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            files[p.relative_to(root).as_posix()] = 'symlink:' + os.readlink(p)
            continue
        if p.is_file():
            files[p.relative_to(root).as_posix()] = digest(p)
        elif not p.is_dir():
            raise PreservationError('Special files are not accepted in preserved trees')
    return files


def archive_tree(source, destination):
    before = inventory(source)
    with tarfile.open(destination, 'w:gz') as tar:
        tar.add(source, arcname='data', recursive=True)
    if before != inventory(source):
        raise PreservationError('Source changed during backup; backup is incomplete')
    return before


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('version') != 1 or manifest.get('status') != 'complete':
        raise PreservationError('Backup is incomplete or unsupported')
    expected = manifest['files']
    if not {'board.dump', 'runtime.dump', 'outputs.tar.gz', 'installation.tar.gz'} <= expected.keys():
        raise PreservationError('Required backup files missing from manifest')
    actual = {p.name for p in root.iterdir() if p.name != 'manifest.json'}
    if actual != set(expected):
        raise PreservationError('Backup file set differs from manifest')
    for name, sha in expected.items():
        p = root / name
        if Path(name).name != name or p.is_symlink() or not p.is_file() or digest(p) != sha:
            raise PreservationError('Backup checksum or path validation failed')
    if set(manifest['trees']) != {n for n in expected if n.endswith('.tar.gz')}:
        raise PreservationError('Archive inventory is incomplete')
    for name, tree in manifest['trees'].items():
        observed = {}
        with tarfile.open(root / name, 'r:gz') as tar:
            for member in tar:
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts or path.parts[0] != 'data':
                    raise PreservationError('Unsafe archive path')
                if member.issym():
                    key = Path(*path.parts[1:]).as_posix()
                    if key in observed:
                        raise PreservationError('Duplicate archive member')
                    observed[key] = 'symlink:' + member.linkname
                    continue
                if not (member.isfile() or member.isdir()):
                    raise PreservationError('Unsafe archive member')
                if member.isfile():
                    key = Path(*path.parts[1:]).as_posix()
                    if key in observed:
                        raise PreservationError('Duplicate archive member')
                    stream = tar.extractfile(member)
                    if stream is None:
                        raise PreservationError('Archive file content is unavailable')
                    h = hashlib.sha256()
                    while chunk := stream.read(1024 * 1024):
                        h.update(chunk)
                    observed[key] = h.hexdigest()
        if observed != tree:
            raise PreservationError('Archived file inventory differs')
    return manifest


def backup(destination):
    services = inspect_installation()
    assert_no_clients(services)
    control = services.get('control')
    if not control:
        raise PreservationError('Existing control container required to resolve storage mounts')
    mounts = {m['Destination']: Path(m['Source']) for m in control['Mounts'] if m['Type'] == 'bind'}
    if '/app/outputs' not in mounts:
        raise PreservationError('Outputs bind mount is missing')
    sources = {'outputs.tar.gz': mounts['/app/outputs'], 'installation.tar.gz': Path('.memstara').resolve()}
    if '/app/user-inputs' in mounts:
        sources['inputs.tar.gz'] = mounts['/app/user-inputs']
    destination = Path(destination).resolve()
    for source in sources.values():
        if not source.is_dir() or destination.is_relative_to(source.resolve()):
            raise PreservationError('Source missing or destination is inside a preserved tree')
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    old_umask = os.umask(0o077)
    try:
        manifest: dict[str, Any] = {'version': 1, 'status': 'incomplete', 'created_at': datetime.now(UTC).isoformat(),
                    'trees': {}, 'files': {}, 'containers': {n: r['Image'] for n, r in services.items()},
                    'scope': 'Quiescent installation; external writers must remain stopped; no model call',
                    'excluded': ['.env (store separately)', 'external inputs outside mounted inputs']}
        manifest['git_commit'] = command(['git', 'rev-parse', 'HEAD']).decode().strip()
        manifest['git_dirty'] = bool(command(['git', 'status', '--porcelain', '--untracked-files=no']).strip())
        for name in ('board', 'runtime'):
            with (destination / f'{name}.dump').open('wb') as stream:
                database_command(services[name]['Id'], 'dump', stdout=stream)
        for name, source in sources.items():
            manifest['trees'][name] = archive_tree(source, destination / name)
        current = inspect_installation()
        assert_no_clients(current)
        if {n: r['Id'] for n, r in services.items()} != {n: r['Id'] for n, r in current.items()}:
            raise PreservationError('Installation changed during backup')
        for name, source in sources.items():
            if inventory(source) != manifest['trees'][name]:
                raise PreservationError('Files changed before backup completed')
        manifest['files'] = {p.name: digest(p) for p in destination.iterdir()}
        manifest['status'] = 'complete'
        (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        verify(destination)
    finally:
        os.umask(old_umask)
    return destination


def drill(root, image='pgvector/pgvector:pg16'):
    """Restore dumps only in an owned, network-isolated ephemeral container."""
    root = Path(root).resolve()
    verify(root)
    command(['docker', 'image', 'inspect', image])  # No implicit downloads.
    name = 'memstara-restore-drill-' + uuid.uuid4().hex
    created = False
    try:
        command(['docker', 'create', '--name', name, '--network', 'none', '--memory', '768m',
                 '--cpus', '1', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
                 '--mount', f'type=bind,src={root},dst=/backup,readonly', image])
        created = True
        command(['docker', 'start', name])
        command(['docker', 'exec', name, 'sh', '-ec',
                 'i=0; until pg_isready -U postgres; do i=$((i+1)); [ "$i" -lt 60 ]; sleep 1; done'])
        for database in ('board', 'runtime'):
            command(['docker', 'exec', name, 'createdb', '-U', 'postgres', database])
            command(['docker', 'exec', name, 'pg_restore', '--exit-on-error', '--no-owner', '--no-acl',
                     '-U', 'postgres', '-d', database, f'/backup/{database}.dump'], timeout=3600)
        return {'status': 'passed', 'databases_restored': ['board', 'runtime'],
                'artifacts': 'checksums verified', 'application_resume': 'not_tested'}
    finally:
        if created:
            command(['docker', 'rm', '--force', '--volumes', name])


def audit_records(previous_output_root=None):
    """Read-only comparison of indexed artifacts with the current outputs mount."""
    services = inspect_installation()
    control = services.get('control', {})
    mounts = {m['Destination']: Path(m['Source']).resolve()
              for m in control.get('Mounts', []) if m['Type'] == 'bind'}
    root = mounts.get('/app/outputs')
    if root is None or 'board' not in services:
        raise PreservationError('Board database and outputs mount are required')
    sql = ("SELECT coalesce(json_agg(t), '[]'::json) FROM "
           "(SELECT run_tag,path,sha256,bytes FROM memstara_execution_artifacts) t")
    raw = command(['docker', 'exec', services['board']['Id'], 'sh', '-ec',
                   '. /settings/postgres.env; exec psql -X -At -v ON_ERROR_STOP=1 '
                   '-U "$POSTGRES_USER" "$POSTGRES_DB" -c "$1"', 'audit', sql])
    rows = json.loads(raw)
    problems = []
    hash_cache = {}
    for row in rows:
        path = Path(row['path'])
        if previous_output_root and path.is_relative_to(Path(previous_output_root)):
            path = root / path.relative_to(Path(previous_output_root))
        if path.is_relative_to('/app/outputs'):
            path = root / path.relative_to('/app/outputs')
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or path.is_symlink():
            reason = 'outside_current_outputs'
        elif not path.is_file():
            reason = 'missing'
        else:
            stat = path.stat()
            key = (str(resolved), stat.st_size, stat.st_mtime_ns)
            if key not in hash_cache:
                hash_cache[key] = digest(path)
            if stat.st_size == row['bytes'] and hash_cache[key] == row['sha256']:
                continue
            reason = 'changed'
        problems.append({'run_tag': row['run_tag'], 'path': row['path'], 'reason': reason})
    return {'status': 'issues_found' if problems else ('passed' if rows else 'no_indexed_artifacts'),
            'indexed_artifacts': len(rows), 'problems': problems,
            'previous_output_root': str(previous_output_root) if previous_output_root else None,
            'scope': 'Registry-indexed files only; live writes may change this read-only observation; '
                     'unindexed traces and cross-database references are not certified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'audit', 'backup', 'verify', 'drill'])
    parser.add_argument('path', nargs='?')
    parser.add_argument('--previous-output-root', help='Explicit old absolute outputs root for read-only audit')
    args = parser.parse_args()
    try:
        if args.action == 'audit':
            if args.previous_output_root and not Path(args.previous_output_root).is_absolute():
                parser.error('--previous-output-root must be absolute')
            result = audit_records(args.previous_output_root)
            print(json.dumps(result, indent=2))
            return 0 if result['status'] == 'passed' else 1
        if args.action == 'inspect':
            services = inspect_installation()
            print(json.dumps({n: {'running': r['State']['Running'], 'mounts': [
                {'destination': m['Destination'], 'source': m['Source'], 'type': m['Type']}
                for m in r['Mounts']]} for n, r in services.items()}, indent=2))
        else:
            if not args.path:
                parser.error('path is required')
            result = {'backup': backup, 'verify': verify, 'drill': drill}[args.action](args.path)
            print(json.dumps({'status': 'passed', 'action': args.action,
                              'result': str(result) if isinstance(result, Path) else result}, indent=2))
    except (PreservationError, OSError, ValueError, subprocess.TimeoutExpired, tarfile.TarError) as exc:
        print(f'Preservation failed: {type(exc).__name__}. No backup/restore success claimed.')
        if isinstance(exc, PreservationError):
            print(str(exc))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
