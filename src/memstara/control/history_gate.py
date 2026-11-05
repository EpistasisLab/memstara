"""Installation-wide exclusion between execution and history maintenance."""
import fcntl
import json
from contextlib import contextmanager, ExitStack
from pathlib import Path

from memstara.paths import output_dir


def epoch_path(root=None):
    return Path(root or output_dir()) / 'runs' / 'history_epoch.json'


def epoch(root=None):
    path = epoch_path(root)
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return {'revision': 'initial', 'busy': False}
    if not isinstance(value, dict) or type(value.get('busy')) is not bool:
        raise RuntimeError('History maintenance state is invalid; review it before starting')
    return value


def ensure_idle(root=None):
    if epoch(root).get('busy'):
        raise RuntimeError('Experiment history is being cleared. Wait for completion before starting or editing.')


@contextmanager
def execution_guard(root=None):
    """A driver holds a shared lock until its cleanup and reconciliation finish."""
    root = Path(root or output_dir())
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.history-maintenance.lock').open('a') as lock:
        ensure_idle(root)
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('History maintenance is active; no experiment was started') from None
        try:
            ensure_idle(root)
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@contextmanager
def maintenance_guard(root):
    """Refuse deletion while even an unlisted CLI driver still holds a lease."""
    with (Path(root) / '.history-maintenance.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('An execution is still active; nothing was deleted') from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@contextmanager
def quiescent_ml(root):
    """Child ML workers inherit this existing lease even if their driver exits."""
    root = Path(root)
    paths = [root/'.paired-ml.lock', *root.glob('research_inputs/prepared/*/derived/.paired-ml.lock')]
    with ExitStack() as stack:
        for path in paths:
            if not path.exists():
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise RuntimeError('Unsafe ML lease path; nothing deleted')
            lock = stack.enter_context(path.open('r'))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('An ML child is still active; nothing deleted') from None
        yield
