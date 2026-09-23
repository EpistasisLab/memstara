"""Bounded, asynchronous Hypothesis skill drafting; never starts a pipeline."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

FIELDS = ('domain', 'population', 'features', 'constraints')
_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def validate(body: dict) -> dict:
    if body.get('stage', 'hypothesis') != 'hypothesis':
        raise ValueError('AI skill drafting is available only for the Hypothesis Agent.')
    data = {}
    for field in FIELDS:
        value = body.get(field, '')
        if not isinstance(value, str) or not value.strip() or len(value) > 4000 or '\0' in value:
            raise ValueError(f'Provide {field} (1–4000 characters); use "None" if not applicable.')
        data[field] = value.strip()
    model = body.get('model', '')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}', model):
        raise ValueError('Choose a valid model or deployment name.')
    data['model'] = model
    return data


def models() -> dict:
    from memstara.control.request import configured_llm
    provider, model = configured_llm()
    return {'provider': provider, 'default_model': model, 'models': [model]}


def start(body: dict) -> dict:
    data = validate(body)
    data['provider'] = models()['provider']
    with _lock:
        now = time.monotonic()
        for key in list(_jobs):
            if now - _jobs[key]['created'] > 3600 and _jobs[key]['status'] != 'generating':
                del _jobs[key]
        if sum(j['status'] == 'generating' for j in _jobs.values()) >= 2:
            raise ValueError('Two skills are already being generated. Wait for one to finish.')
        if len(_jobs) >= 100:
            raise ValueError('Draft capacity reached. Please try again later.')
        key = uuid.uuid4().hex
        _jobs[key] = {'id': key, 'status': 'generating', 'created': now}
    threading.Thread(target=_generate, args=(key, data), daemon=True).start()
    return {'id': key, 'status': 'generating'}


def get(key: str) -> dict | None:
    with _lock:
        job = _jobs.get(key)
        return {k: v for k, v in job.items() if k != 'created'} if job else None


def _generate(key: str, data: dict) -> None:
    try:
        # A separate event loop/process avoids sharing Motoro DB pools with the control server.
        result = subprocess.run(
            [sys.executable, '-m', 'memstara.control.skill_draft_worker'],
            input=json.dumps(data), capture_output=True, text=True, timeout=150,
            cwd=Path(__file__).resolve().parents[3],
        )
        if result.returncode:
            raise RuntimeError('Generation failed. Check the selected deployment and model connection, then retry.')
        lines = [line[12:] for line in result.stdout.splitlines() if line.startswith('SKILL_DRAFT:')]
        draft = json.loads(lines[-1]) if lines else {}
        content = draft.get('content')
        if not isinstance(content, str) or not content.strip() or len(content.encode()) > 48000:
            raise RuntimeError('The model did not return a usable Markdown skill. Please retry.')
        update = {'status': 'ready', **draft}
    except subprocess.TimeoutExpired:
        update = {'status': 'failed', 'error': 'Generation timed out. No skill was saved. Please retry.'}
    except Exception:
        # Do not expose provider exception text, credentials, or subprocess output to browsers.
        update = {'status': 'failed', 'error': ('Could not generate a skill. Check the model connection '
                                               'or deployment name and retry. No skill was saved.')}
    with _lock:
        _jobs[key].update(update)
