"""Recover ownership after a control-service restart without trusting a recycled PID."""
import json
import os
import subprocess
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from memstara.pipeline.checkpoint import atomic_json


_record_cache: ContextVar[dict | None] = ContextVar('control_record_cache', default=None)


@contextmanager
def record_snapshot():
    """Share disk discovery within one response, never across requests or threads."""
    token = _record_cache.set({})
    try:
        yield
    finally:
        _record_cache.reset(token)


def records(root: Path):
    cache = _record_cache.get()
    key = root.resolve()
    if cache is not None and key in cache:
        return cache[key]
    found = []
    for path in sorted(root.glob('**/control_record.json'), reverse=True):
        try:
            record = json.loads(path.read_text())
            if isinstance(record, dict):
                found.append((path, record))
        except (OSError, ValueError):
            continue
    if cache is not None:
        cache[key] = found
    return found


def identity(pid: int) -> str:
    try:
        return subprocess.check_output(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'command='],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        return ''


class RecoveredProcess:
    def __init__(self, record: dict):
        self.record = record

    def poll(self):
        current = identity(self.record['pid'])
        expected = self.record.get('process_identity')
        if current and expected and current == expected:
            return None
        try:
            root = Path(self.record['run_dir'])
            status_path = root / ('report_status.json' if self.record.get('report_only') else 'pipeline_status.json')
            status = json.loads(status_path.read_text())
            terminal = {'completed'} if self.record.get('report_only') else {'completed', 'completed_with_skips', 'no_findings'}
            return 0 if status.get('status') in terminal else 1
        except (OSError, ValueError):
            return 1

    def send_signal(self, signal):
        if self.poll() is not None:
            raise RuntimeError('The original pipeline process is no longer running')
        os.kill(self.record['pid'], signal)


def save_record(record: dict):
    data = {k: v for k, v in record.items() if k != 'popen'}
    path = Path(data['run_dir']) / 'control_record.json'
    atomic_json(path, data)


def recover(root: Path, pipeline_id=None):
    live, finished = [], []
    for path, saved in records(root):
        try:
            record = dict(saved)
            if record.get('pipeline_id') != pipeline_id:
                continue
            record['run_dir'] = str(path.parent.resolve())
            if record.get('exit_code') is not None:
                finished.append(record)
                continue
            process = RecoveredProcess(record)
            code = process.poll()
            if code is None:
                live.append({**record, 'popen': process})
            else:
                finished.append({**record, 'exit_code': code})
        except (OSError, ValueError, KeyError):
            continue
    if len(live) > 1:
        raise RuntimeError('Multiple surviving pipelines detected; refusing ambiguous ownership')
    return (live[0] if live else None), finished[:10]
