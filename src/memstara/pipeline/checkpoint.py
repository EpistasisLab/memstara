"""Durable driver checkpoints. Unknown external effects are never replayed blindly."""
import json
import hashlib
import os
from pathlib import Path


class RecoveryBlocked(RuntimeError):
    pass


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Checkpoint:
    def __init__(self, root, *, resume=False):
        self.path = Path(root) / 'checkpoint.json'
        if resume:
            self.state = json.loads(self.path.read_text())
            if not isinstance(self.state, dict) or self.state.get('version') != 1:
                raise RecoveryBlocked('Unsupported checkpoint version')
            if type(self.state.get('next_wave')) is not int or self.state['next_wave'] < 0:
                raise RecoveryBlocked('Invalid saved Loop position')
            if not isinstance(self.state.get('phases'), dict) or not isinstance(self.state.get('calls'), dict):
                raise RecoveryBlocked('Invalid checkpoint operations')
            expected = self.state.get('code_hash')
            if expected and expected != code_hash():
                raise RecoveryBlocked('Memstara code changed since this execution; '
                                      'restore the matching version before recovery')
            problem = self.problem()
            if problem:
                raise RecoveryBlocked(problem)
        else:
            if self.path.exists():
                raise RecoveryBlocked('Existing checkpoint: use Resume instead of restarting this execution')
            self.state = {'version': 1, 'next_wave': 0, 'waves_run': 0,
                          'seeded_total': 0, 'missing_trials': [], 'dry_streak': 0,
                          'phases': {}, 'calls': {}, 'finished': False, 'code_hash': code_hash()}
            self.save()

    def save(self):
        atomic_json(self.path, self.state)

    def problem(self):
        if self.state.get('finished'):
            return 'This execution has ended; start a new execution instead.'
        if any(v == 'active' for v in self.state.get('calls', {}).values()):
            return ('An agent call was interrupted. Its external effects require review before recovery; '
                    'no call will be replayed automatically.')
        if any(v.get('status') != 'done' for v in self.state.get('phases', {}).values()):
            return ('A checkpoint operation was interrupted before its result was saved. '
                    'Review persisted artifacts before recovery.')
        return None

    def call_started(self, key):
        self.state['calls'][key] = 'active'
        self.save()

    def call_finished(self, key):
        self.state['calls'].pop(key, None)
        self.save()

    async def phase(self, key, operation):
        previous = self.state['phases'].get(key)
        if previous:
            if previous['status'] != 'done':
                raise RecoveryBlocked('Interrupted checkpoint operation requires review: ' + key)
            return previous['result']
        self.state['phases'][key] = {'status': 'active'}
        self.save()
        result = await operation()
        self.state['phases'][key] = {'status': 'done', 'result': result}
        self.save()
        return result

    def advance(self, wave, **values):
        self.state.update(values, next_wave=wave + 1)
        self.save()

    def finish(self):
        self.state['finished'] = True
        self.save()


def recovery_status(root):
    root = Path(root)
    if not (root / 'checkpoint.json').exists():
        return {'recoverable': False}
    try:
        state = json.loads((root / 'checkpoint.json').read_text())
        if isinstance(state, dict) and state.get('finished'):
            return {'recoverable': False}
        checkpoint = Checkpoint(root, resume=True)
        arguments = json.loads((root / 'resume_arguments.json').read_text())
        if not isinstance(arguments, dict) or not arguments.get('run_tag'):
            raise RecoveryBlocked('Saved launch settings are unavailable')
        return {'recoverable': True, 'recovery_wave': checkpoint.state['next_wave'] + 1}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecoveryBlocked) as exc:
        return {'recoverable': False, 'recovery_blocked': str(exc)}


def code_hash():
    """Fail closed on changed driver/tool behavior; no Motoro sources are modified."""
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parents[1]
    for path in sorted(root.rglob('*.py')):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    import sys
    from importlib.metadata import version, PackageNotFoundError
    digest.update(sys.version.encode())
    for package in ('motoro', 'litellm'):
        try:
            digest.update((package + version(package)).encode())
        except PackageNotFoundError:
            digest.update((package + ':unavailable').encode())
    return digest.hexdigest()
