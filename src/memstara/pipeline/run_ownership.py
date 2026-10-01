"""Fail closed when the database session that owns an execution is lost."""
import asyncio
import time
from datetime import datetime, UTC
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
    def __init__(self, connection, *, on_lost=None, on_health=None, lock_key=None,
                 interval=2.0, timeout=10.0, failure_limit=3):
        self.connection = connection
        self.owner = asyncio.current_task()
        self.on_lost = on_lost
        self.on_health = on_health
        self.lock_key = lock_key
        self.failure_limit = failure_limit
        self.failures = 0
        self.last_success = time.monotonic()
        self.ready = asyncio.Event()
        self.ready.set()
        self.interval, self.timeout = interval, timeout
        self.lost = False
        self.stopping = False
        self.monitor = None
        self.reason = None

    def lose(self, reason, *, cancel_owner=True):
        if self.lost or self.stopping:
            return
        self.lost, self.reason = True, reason
        self.ready.set()
        self.health("lost", reason=reason)
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

    def health(self, state, **details):
        if self.on_health:
            try:
                self.on_health({'state': state, 'at': datetime.now(UTC).isoformat(),
                                'consecutive_failures': self.failures,
                                'seconds_since_verified': round(time.monotonic() - self.last_success, 3),
                                **details})
            except Exception:
                import logging
                logging.getLogger(__name__).warning('Could not save connection health diagnostics')

    async def wait_verified(self):
        self.check()
        await self.ready.wait()
        self.check()

    async def watch(self):
        while True:
            before = time.monotonic()
            await asyncio.sleep(self.interval)
            loop_delay = max(0, time.monotonic() - before - self.interval)
            try:
                if self.lock_key is None:
                    verified = await self.connection.fetchval('SELECT 1', timeout=self.timeout)
                else:
                    verified = await self.connection.fetchval(
                        """SELECT EXISTS (SELECT 1 FROM pg_locks
                           WHERE locktype='advisory' AND pid=pg_backend_pid()
                             AND objsubid=1 AND classid=0 AND objid=$1::oid
                             AND mode='ExclusiveLock' AND granted)""",
                        self.lock_key, timeout=self.timeout)
                if not verified:
                    self.lose('execution_lock_missing')
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.connection.is_closed():
                    self.lose('lock_connection_closed')
                    return
                self.failures += 1
                self.ready.clear()
                self.health('verifying', error_type=type(exc).__name__,
                            event_loop_delay_seconds=round(loop_delay, 3))
                if self.failures >= self.failure_limit:
                    self.lose('lock_connection_unresponsive')
                    return
                continue
            if self.failures:
                self.health('recovered', event_loop_delay_seconds=round(loop_delay, 3))
            self.failures = 0
            self.last_success = time.monotonic()
            self.ready.set()

    def start(self):
        self.health('healthy')
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
    import json
    # The outer exception handler must not erase the first diagnostic cause.
    if reason == 'execution_ownership_lost':
        try:
            previous = json.loads((root/'infrastructure_status.json').read_text())
            if previous.get('status') == 'interrupted' and previous.get('reason'):
                atomic_json(root/'pipeline_status.json', previous)
                return
        except (OSError, ValueError):
            pass
    messages = {
        'lock_connection_closed': 'The database execution connection closed.',
        'lock_connection_unresponsive': 'Execution ownership could not be verified after repeated database checks.',
        'execution_lock_missing': 'The database session no longer holds the execution lock.',
    }
    payload = {'status': 'interrupted', 'reason': reason, 'results_preserved': True,
               'message': (messages.get(reason, 'Database execution ownership could not be confirmed.') +
                           ' Saved results are retained. Recovery requires a verified checkpoint.')}
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
    out = {}
    for filename, field in [('infrastructure_status.json', 'infrastructure_status'),
                            ('connection_health.json', 'connection_health')]:
        try:
            value = json.loads((Path(root)/filename).read_text())
            if isinstance(value, dict):
                out[field] = {k: v for k, v in value.items() if k != 'history'}
        except (ValueError, OSError):
            pass
    return out


async def await_ownership():
    lease = _current.get()
    if lease:
        await lease.wait_verified()


def record_health(root, value):
    import json
    from pathlib import Path
    from memstara.pipeline.checkpoint import atomic_json
    path = Path(root) / 'connection_health.json'
    try:
        history = json.loads(path.read_text()).get('history', [])
    except (OSError, ValueError):
        history = []
    atomic_json(path, {**value, 'history': [*history[-19:], value]})
