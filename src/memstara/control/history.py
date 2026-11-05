"""Explicit, installation-wide history reset jobs. Never run at import/startup.

Configuration lives outside the deletion allowlist. A verified backup is a
precondition in backup mode, and a partial destructive job blocks new launches
until a subsequent explicit reset succeeds. Current jobs survive browser reloads.
"""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tarfile
import threading
import time
from uuid import uuid4

from memstara.paths import REPO_ROOT, output_dir
from memstara.pipeline.checkpoint import atomic_json
from memstara.control.history_gate import epoch, epoch_path, maintenance_guard, quiescent_ml

CONFIRMATION = 'CLEAR ALL HISTORY'
ACTIVE = {'stopping', 'validating', 'backing_up', 'clearing_databases', 'clearing_files', 'verifying'}


def cleanup_module():
    spec = importlib.util.spec_from_file_location('memstara_history_cleanup',
                                                REPO_ROOT / 'deployment/reset-execution-history.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


async def utility(args, *, env=None, timeout=600):
    """Use installed PostgreSQL clients; never mount a Docker socket or log DSNs."""
    process = await asyncio.create_subprocess_exec(*args, env=env,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        code = await asyncio.wait_for(process.wait(), timeout)
        if code:
            raise RuntimeError('PostgreSQL backup verification failed')
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def backup_history(root, job_id, paths):
    folder = Path(root) / 'history-backups' / job_id
    if folder.parent.is_symlink():
        raise RuntimeError('Unsafe backup directory')
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    for key, name in [('MEMSTARA_DATABASE_URL', 'board.dump'), ('MOTORO_DATABASE_URL', 'runtime.dump')]:
        archive = folder / name
        # libpq reads the connection string from the child environment. It never
        # appears in process arguments, HTTP responses or diagnostic messages.
        env = {**os.environ, 'PGDATABASE': os.environ[key].replace('postgresql+asyncpg://', 'postgresql://', 1)}
        await utility(['pg_dump', '--format=custom', '--no-password', '--file', str(archive)], env=env)
        if not archive.is_file() or archive.stat().st_size == 0:
            raise RuntimeError('Database backup is empty')
        archive.chmod(0o600)
        await utility(['pg_restore', '--list', str(archive)])
    files = folder / 'execution-files.tar.gz'
    with tarfile.open(files, 'w:gz', dereference=False) as archive:
        for path in paths:
            archive.add(path, arcname=str(path.relative_to(root)))
    files.chmod(0o600)
    with tarfile.open(files, 'r:gz') as archive:
        for member in archive:
            if member.isfile():
                with archive.extractfile(member) as stream:
                    while stream.read(1024 * 1024):
                        pass
    names = ['board.dump', 'runtime.dump', 'execution-files.tar.gz']
    manifest = {'id': job_id, 'files': {name: {'sha256': digest(folder/name),
        'bytes': (folder/name).stat().st_size} for name in names},
        'scope': 'Both application databases and deleted execution files; input/settings files remain in place.',
        'validation': 'PostgreSQL archive listing, full execution archive read and SHA256 verification; restore not rehearsed'}
    atomic_json(folder / 'manifest.json', manifest)
    bundle = folder / 'backup.tar.gz'
    with tarfile.open(bundle, 'w:gz') as archive:
        for name in [*names, 'manifest.json']:
            archive.add(folder/name, arcname=name)
    bundle.chmod(0o600)
    # Validate the downloadable bundle, not just the inner file headers.
    with tarfile.open(bundle, 'r:gz') as archive:
        for name, expected in manifest['files'].items():
            checksum = hashlib.sha256()
            with archive.extractfile(name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    checksum.update(block)
            if checksum.hexdigest() != expected['sha256']:
                raise RuntimeError('Backup checksum verification failed')
    atomic_json(folder / 'COMPLETE.json', {'sha256': digest(bundle), 'bytes': bundle.stat().st_size})
    return {'id': job_id, 'location': f'outputs/history-backups/{job_id}',
            'download': f'/control/history-reset/backups/{job_id}/download'}


class HistoryReset:
    def __init__(self, workspace, standalone, *, root=None, stop_timeout=120):
        self.workspace, self.standalone = workspace, standalone
        self.root = Path(root or output_dir())
        self.stop_timeout = stop_timeout
        self.lock = threading.RLock()
        self.thread = None

    @property
    def state_path(self):
        return self.root / 'history-reset-state.json'

    def _read(self):
        try:
            value = json.loads(self.state_path.read_text())
        except FileNotFoundError:
            return {'state': 'idle', 'revision': epoch(self.root)['revision'], 'blocked': False}
        if not isinstance(value,dict) or value.get('state') not in ACTIVE | {'idle','completed','failed'}:
            raise ValueError('History reset state is invalid; review it before another reset')
        return value

    def status(self):
        with self.lock:
            record = self._read()
            # A service restart must not masquerade as a completed or active job.
            from memstara.control.recovery import identity
            if record.get('state') in ACTIVE and record.get('owner_identity') != identity(record.get('owner_pid', 0)):
                record.update(state='failed', error_code='reset_controller_interrupted',
                              message='History clearing was interrupted. Review the saved state and retry explicitly.',
                              blocked=bool(record.get('deletion_started')))
                self._save(record)
            public = {key: value for key, value in record.items() if key not in ('owner_identity', 'owner_pid', 'exceptions')}
            return public

    def _save(self, record):
        record['updated_at'] = time.time()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root/'runs').mkdir(exist_ok=True)
        atomic_json(self.state_path, record)
        previous = epoch(self.root)
        atomic_json(epoch_path(self.root), {'revision': record.get('revision', previous['revision']),
            'busy': record['state'] in ACTIVE or record.get('blocked', False),
            'last_reset_id': record['id'] if record['state'] == 'completed' else previous.get('last_reset_id')})

    def begin(self, body):
        if (not isinstance(body, dict) or set(body) != {'mode', 'confirmation', 'request_id'}
                or body.get('mode') not in ('backup', 'no_backup') or body.get('confirmation') != CONFIRMATION):
            raise ValueError('Choose a backup option and type CLEAR ALL HISTORY to confirm clearing every pipeline.')
        request_id = body.get('request_id')
        from uuid import UUID
        if not isinstance(request_id, str) or str(UUID(request_id)) != request_id:
            raise ValueError('A valid reset request ID is required')
        with self.workspace.lock, self.lock:
            current = self.status()
            if current.get('request_id') == request_id:
                if current.get('mode') != body['mode']:
                    raise ValueError('This request ID already refers to a different backup choice')
                return current
            if current.get('state') in ACTIVE:
                raise RuntimeError('History clearing is already in progress')
            from memstara.control.recovery import identity
            record = {'id': str(uuid4()), 'request_id': request_id, 'mode': body['mode'],
                      'state': 'stopping', 'revision': current.get('revision', 'initial'),
                      'started_at': time.time(), 'deletion_started': False, 'blocked': False,
                      'owner_pid': os.getpid(), 'owner_identity': identity(os.getpid())}
            self._save(record)
            self.thread = threading.Thread(target=self._worker, args=(record,), daemon=True)
            self.thread.start()
            return self.status()

    def phase(self, record, state):
        with self.lock:
            record['state'] = state
            if state in ('clearing_databases', 'clearing_files'):
                record['deletion_started'] = True
            self._save(record)

    def _worker(self, record):
        try:
            asyncio.run(self.perform(record))
        except Exception as error:
            from memstara.pipeline.board_reads import exception_details
            with self.lock:
                failed_phase = record['state']
                record.update(state='failed', failed_phase=failed_phase, error_type=type(error).__name__,
                              error_code='history_reset_failed', exceptions=exception_details(error),
                              blocked=bool(record.get('deletion_started')), ended_at=time.time(),
                              message=('History clearing did not finish. Some history may already be removed; '
                                       'new executions remain blocked. Retry clearing after correcting the error.'
                                       if record.get('deletion_started') else
                                       'History clearing did not start. No history was deleted. Review the reset diagnostics.'))
                self._save(record)

    async def stop_all(self):
        from memstara.control.recovery import records
        with self.workspace.lock:
            managers = [self.standalone, *(self.workspace.manager(p['id']) for p in self.workspace.items)]
            known = {manager.pipeline_id for manager in managers}
            for _, record in records(self.root/'runs'):
                key = record.get('pipeline_id')
                if key not in known:
                    managers.append(self.workspace.factory(key))
                    known.add(key)
            for manager in managers:
                active = manager.running()
                if active:
                    manager.terminate(active['run_tag'])
        deadline = time.monotonic() + self.stop_timeout
        while any(manager.running() for manager in managers):
            if time.monotonic() >= deadline:
                raise RuntimeError('Executions did not stop within the safe deadline; nothing deleted')
            await asyncio.sleep(.2)

    async def perform(self, record):
        await self.stop_all()
        with maintenance_guard(self.root), quiescent_ml(self.root):
            module = cleanup_module()
            self.phase(record, 'validating')
            keep = module.preserved(self.root)
            paths = module.targets(self.root)
            await module.main(False, root=self.root)
            if record['mode'] == 'backup':
                self.phase(record, 'backing_up')
                record['backup'] = await backup_history(self.root, record['id'], paths)
                self._save(record)
            await module.main(True, root=self.root, on_phase=lambda state: self.phase(record, state))
            self.phase(record, 'verifying')
            if module.targets(self.root) or module.preserved(self.root) != keep:
                raise RuntimeError('History removal or settings preservation could not be verified')
            # Remove in-memory finished-run pointers only after durable verification.
            with self.workspace.lock:
                for manager in [self.standalone, *self.workspace.managers.values()]:
                    with manager._lock:
                        manager._live, manager._done = None, []
            record.update(state='completed', revision=record['id'], blocked=False, ended_at=time.time(),
                          message='All experiment history cleared. Settings and research inputs were preserved.')
            self._save(record)

    def backup_file(self, identifier):
        from uuid import UUID
        if str(UUID(identifier)) != identifier:
            raise ValueError('Invalid backup ID')
        folder = self.root / 'history-backups' / identifier
        if folder.is_symlink() or not folder.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('Invalid backup directory')
        complete = json.loads((folder/'COMPLETE.json').read_text())
        path = folder/'backup.tar.gz'
        if path.is_symlink() or path.stat().st_size != complete['bytes'] or digest(path) != complete['sha256']:
            raise ValueError('Backup verification failed')
        return path
