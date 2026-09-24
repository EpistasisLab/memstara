"""Recover ownership after a control-service restart without trusting a recycled PID."""
import json
import os
import subprocess
from pathlib import Path


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
            return 0 if status.get('status') == 'completed' else 1
        except (OSError, ValueError):
            return 1

    def send_signal(self, signal):
        if self.poll() is not None:
            raise RuntimeError('The original pipeline process is no longer running')
        os.kill(self.record['pid'], signal)


def save_record(record: dict):
    data = {k: v for k, v in record.items() if k != 'popen'}
    path = Path(data['run_dir']) / 'control_record.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(path)


def recover(root: Path, pipeline_id=None):
    live, finished = [], []
    for path in sorted(root.glob('**/control_record.json'), reverse=True):
        try:
            record = json.loads(path.read_text())
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
