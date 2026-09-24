"""Fail closed when the database session that owns an execution is lost."""
import asyncio
from contextvars import ContextVar


class RunOwnershipLost(RuntimeError):
    pass


class RunLockCleanupError(RuntimeError):
    pass


_current = ContextVar('memstara_run_ownership', default=None)


def ownership_lost():
    lease = _current.get()
    return bool(lease and lease.lost)


def require_ownership():
    lease = _current.get()
    if lease:
        lease.check()


class RunLease:
    def __init__(self, connection, *, on_lost=None, interval=1.0, timeout=3.0):
        self.connection = connection
        self.owner = asyncio.current_task()
        self.on_lost = on_lost
        self.interval, self.timeout = interval, timeout
        self.lost = False
        self.stopping = False
        self.monitor = None
        self.reason = None

    def lose(self, reason, *, cancel_owner=True):
        if self.lost or self.stopping:
            return
        self.lost, self.reason = True, reason
        try:
            if self.on_lost:
                self.on_lost(reason)
        finally:
            if cancel_owner:
                self.owner.cancel('Database execution ownership lost')

    def terminated(self, connection):
        self.lose('lock_connection_closed')

    def check(self):
        if not self.lost and self.connection.is_closed():
            self.lose('lock_connection_closed', cancel_owner=False)
        if self.lost:
            raise RunOwnershipLost('Database execution ownership was lost; saved work requires safe recovery.')

    async def watch(self):
        while True:
            await asyncio.sleep(self.interval)
            try:
                await self.connection.fetchval('SELECT 1', timeout=self.timeout)
            except Exception:
                self.lose('lock_connection_unresponsive')
                return

    def start(self):
        self.connection.add_termination_listener(self.terminated)
        self.monitor = asyncio.create_task(self.watch())

    async def stop(self):
        self.stopping = True
        self.connection.remove_termination_listener(self.terminated)
        if self.monitor:
            self.monitor.cancel()
            await asyncio.gather(self.monitor, return_exceptions=True)


def record_interruption(root, reason):
    from pathlib import Path
    from memstara.pipeline.checkpoint import atomic_json
    root = Path(root)
    payload = {'status': 'interrupted', 'reason': reason, 'results_preserved': True,
               'message': ('Database connection interrupted. Saved results are retained. '
                           'Resume is available only at a verified checkpoint; uncertain work requires review.')}
    atomic_json(root/'infrastructure_status.json', payload)
    atomic_json(root/'pipeline_status.json', payload)


def record_cleanup_warning(root):
    import json
    from pathlib import Path
    from memstara.pipeline.checkpoint import atomic_json
    root = Path(root)
    payload = {'status': 'cleanup_warning', 'results_preserved': True,
               'message': ('Execution ended, but connection cleanup could not be verified. '
                           'Saved analysis results are retained.')}
    atomic_json(root/'infrastructure_status.json', payload)
    try:
        status = json.loads((root/'pipeline_status.json').read_text())
    except (ValueError, OSError):
        status = {}
    if not status:
        atomic_json(root/'pipeline_status.json', payload)
    return 0 if status.get('status') == 'completed' else 1


def infrastructure_status(root):
    import json
    from pathlib import Path
    try:
        value = json.loads((Path(root)/'infrastructure_status.json').read_text())
        return {'infrastructure_status': value} if isinstance(value, dict) else {}
    except (ValueError, OSError):
        return {}
