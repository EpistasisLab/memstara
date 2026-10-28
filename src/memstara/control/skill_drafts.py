"""Bounded, asynchronous role-specific skill drafting; never starts a pipeline."""
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
    stage = body.get('stage', 'hypothesis')
    if stage == 'explanation':
        stage = 'report'
    if stage in ('interpreter', 'report'):
        raise ValueError('Interpretation and Explanation use the supplied skills from the library.')
    if not isinstance(stage, str) or stage not in ('hypothesis', 'data', 'ml'):
        raise ValueError('Choose a Hypothesis, Data or ML agent role.')
    data = {'stage': stage}
    from memstara.skill_bases import CHOICES, validate as validate_base
    if stage in CHOICES:
        data['base_skill'] = validate_base(stage, body.get('base_skill', CHOICES[stage][0]))
    elif body.get('base_skill'):
        raise ValueError('Hypothesis skills do not select a Data or ML policy.')
    if body.get('model_connection_id'):
        from memstara.model_connections import identifier
        data['model_connection_id'] = identifier(body['model_connection_id'])
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


def models(connection_id='') -> dict:
    from memstara.stage_models import deployment_profiles, public_profiles
    from memstara import model_connections
    if not connection_id:
        current = model_connections.current_default()
        connection_id = current['id'] if current else ''
    profiles = (model_connections.profiles(model_connections.load(connection_id)['connection'])
                if connection_id else deployment_profiles())
    return {'agents': public_profiles(profiles), 'model_connection_id': connection_id}


def start(body: dict) -> dict:
    data = validate(body)
    from memstara.operational import agent_profile
    from memstara.model_connections import execution_environment
    from memstara.control.model_policy import require_provider
    selected = models(data.get('model_connection_id', ''))
    data['model_connection_id'] = selected['model_connection_id']
    profile = agent_profile(data['stage'], execution_environment(data['model_connection_id']))
    require_provider(profile['provider'])
    if data['model'] != profile['model']:
        raise ValueError('Skill draft model differs from the selected agent configuration; refresh settings')
    data['provider'] = profile['provider']
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
        from memstara.model_connections import execution_environment
        # A separate event loop/process avoids sharing Motoro DB pools with the control server.
        result = subprocess.run(
            [sys.executable, '-m', 'memstara.control.skill_draft_worker'],
            input=json.dumps(data), capture_output=True, text=True, timeout=150,
            cwd=Path(__file__).resolve().parents[3],
            env=execution_environment(
                data.get('model_connection_id', '')),
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
