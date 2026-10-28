"""Immutable, encrypted model connections selected by an experiment.

Only opaque IDs enter designs/argv. Credentials are resolved into a dedicated
worker's environment, using Motoro's normal credential resolver. Never mutate
the control service environment or another experiment's model assignment.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import UTC, datetime

PROVIDERS = ('openai', 'anthropic', 'azure_foundry', 'openrouter', 'local', 'bedrock')
KEYS = {'openai': ('MEMSTARA_OPENAI_API_KEY', 'OPENAI_API_KEY'),
        'anthropic': ('MEMSTARA_ANTHROPIC_API_KEY', 'ANTHROPIC_API_KEY'),
        'azure_foundry': ('MEMSTARA_AZURE_FOUNDRY_API_KEY', 'ANTHROPIC_FOUNDRY_API_KEY'),
        'openrouter': ('MEMSTARA_OPENROUTER_API_KEY', 'OPENROUTER_API_KEY'),
        'local': ('MEMSTARA_LOCAL_API_KEY', 'LOCAL_LLM_API_KEY')}
AWS_FIELDS = ('AWS_REGION', 'AWS_DEFAULT_REGION', 'AWS_BEARER_TOKEN_BEDROCK',
              'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
              'AWS_PROFILE', 'AWS_DEFAULT_PROFILE', 'AWS_CONFIG_FILE',
              'AWS_SHARED_CREDENTIALS_FILE', 'AWS_WEB_IDENTITY_TOKEN_FILE',
              'AWS_ROLE_ARN', 'AWS_CONTAINER_CREDENTIALS_RELATIVE_URI',
              'AWS_CONTAINER_CREDENTIALS_FULL_URI')
_lock = threading.Lock()


def validate(value, *, stored=False):
    fields = {'provider', 'model', 'api_key', 'api_base', 'region', 'auth_type',
              'access_key_id', 'secret_access_key', 'session_token'}
    extra = {'settings', 'catalog_id'} | ({'resolved_capabilities'} if stored else set())
    if not isinstance(value, dict) or set(value) - fields - extra:
        raise ValueError('Unsupported connection fields')
    if any(not isinstance(v, str) or len(v) > 8192 or any(ord(c) < 32 for c in v)
           for k, v in value.items() if k in fields or k == 'catalog_id'):
        raise ValueError('Connection fields must be single-line text')
    data = {k: value.get(k, '').strip() for k in fields}
    provider = data['provider']
    if provider not in PROVIDERS:
        raise ValueError('Choose a supported provider')
    if not re.fullmatch(r'[A-Za-z0-9._:/-]{1,200}', data['model']):
        raise ValueError('Enter the exact model ID or deployment name')
    if provider in ('azure_foundry', 'local'):
        if not data['api_base']:
            raise ValueError('Enter the model endpoint URL')
        if provider == 'azure_foundry':
            from motoro.services.credentials import foundry_api_base
            data['api_base'] = foundry_api_base(data['api_base'])
        from memstara.stage_models import validate_endpoint
        validate_endpoint(data['api_base'], allow_http=provider == 'local')
    elif data['api_base']:
        raise ValueError('This provider uses its standard endpoint')
    if provider not in ('local', 'bedrock') and not data['api_key']:
        raise ValueError('Enter an API key')
    if provider == 'bedrock':
        if not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d+', data['region']):
            raise ValueError('Enter an AWS region, such as us-east-1')
        if data['auth_type'] == 'api_key':
            if not data['api_key']:
                raise ValueError('Enter a Bedrock API key')
            if any(data[k] for k in ('access_key_id', 'secret_access_key', 'session_token')):
                raise ValueError('Choose one Bedrock authentication method')
        elif data['auth_type'] == 'aws_credentials':
            if not data['access_key_id'] or not data['secret_access_key'] or data['api_key']:
                raise ValueError('Enter an AWS access key ID and secret access key')
        else:
            raise ValueError('Choose a Bedrock authentication method')
    elif any(data[k] for k in ('region', 'auth_type', 'access_key_id', 'secret_access_key', 'session_token')):
        raise ValueError('AWS fields apply only to Bedrock')
    if 'settings' in value or value.get('catalog_id') or (stored and 'resolved_capabilities' in value):
        from memstara.model_catalog import capabilities, validate_settings
        from motoro.services.model_capabilities import ModelCapabilities
        data['catalog_id'] = value.get('catalog_id', '')
        caps = (
            ModelCapabilities.model_validate(value['resolved_capabilities']).model_dump(mode='json')
            if stored and 'resolved_capabilities' in value
            else capabilities(provider, data['model'], data['catalog_id'])
        )
        data['settings'] = validate_settings(value.get('settings', {}), caps)
        data['resolved_capabilities'] = caps
    return data


def _directory():
    from memstara.paths import output_dir
    directory = output_dir() / 'private-model-connections'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def _cipher():
    from cryptography.fernet import Fernet, MultiFernet
    configured = os.environ.get('MOTORO_ENCRYPTION_KEY', '').strip()
    if configured:
        return MultiFernet([Fernet(k.strip().encode()) for k in configured.split(',') if k.strip()])
    # Persist once so a container restart or Resume can decrypt the same records.
    path = _directory() / 'encryption.key'
    with _lock:
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(Fernet.generate_key())
        return Fernet(path.read_bytes())


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise ValueError('Invalid model connection ID')
    return value


def load(connection_id):
    name = identifier(connection_id)
    try:
        record = json.loads(_cipher().decrypt((_directory() / (name + '.enc')).read_bytes()))
        data = validate(record['connection'], stored=True)
        return {**record, 'connection': data}
    except Exception:
        raise ValueError('Saved model connection is unavailable. Check and save a new connection.') from None


def public(record):
    data = record['connection']
    return {**{k: data[k] for k in ('provider', 'model', 'api_base', 'region')},
            'id': record['id'], 'checked_at': record['checked_at'],
            **({'settings': data['settings'], 'capabilities': data['resolved_capabilities']}
               if 'settings' in data else {})}


def profiles(data):
    from memstara.stage_models import AGENT_ROLES
    profile = {'provider': data['provider'], 'model': data['model']}
    if data['api_base']:
        profile['api_base'] = data['api_base']
    if 'settings' in data:
        profile.update(data['settings'], resolved_capabilities=data['resolved_capabilities'])
    return {role: dict(profile) for role in AGENT_ROLES}


def environment(data, source=None):
    """Pure construction; one worker gets one connection, including during retries."""
    from memstara.stage_models import AGENT_ROLES
    env = dict(os.environ if source is None else source)
    for key in list(env):
        if any(key.startswith(f'MEMSTARA_{role.upper()}_') for role in (*AGENT_ROLES, 'llm')):
            env.pop(key)
    for key in (*AWS_FIELDS, *(k for pair in KEYS.values() for k in pair),
                'ANTHROPIC_FOUNDRY_RESOURCE', 'LOCAL_LLM_API_BASE', 'MEMSTARA_STAGE_MODELS_PATH',
                'OPENAI_API_BASE', 'OPENAI_BASE_URL', 'ANTHROPIC_BASE_URL', 'AZURE_API_KEY',
                'AZURE_API_BASE', 'AZURE_API_VERSION'):
        env.pop(key, None)
    env.update(MEMSTARA_CONFIG_MODE='environment', MEMSTARA_LLM_PROVIDER=data['provider'],
               MEMSTARA_LLM_MODEL=data['model'], MEMSTARA_LLM_API_BASE=data['api_base'])
    if 'settings' in data:
        env.update({f'MEMSTARA_LLM_{key.upper()}': str(value) for key, value in data['settings'].items()})
        env['MEMSTARA_LLM_CAPABILITIES_JSON'] = json.dumps(data['resolved_capabilities'])
    if data['provider'] in KEYS:
        for key in KEYS[data['provider']]:
            env[key] = data['api_key']
    if data['provider'] == 'local':
        env['LOCAL_LLM_API_BASE'] = data['api_base']
    if data['provider'] == 'bedrock':
        env.update(AWS_REGION=data['region'], AWS_DEFAULT_REGION=data['region'], AWS_EC2_METADATA_DISABLED='true')
        if data['auth_type'] == 'api_key':
            env['AWS_BEARER_TOKEN_BEDROCK'] = data['api_key']
        else:
            env.update(AWS_ACCESS_KEY_ID=data['access_key_id'], AWS_SECRET_ACCESS_KEY=data['secret_access_key'])
            if data['session_token']:
                env['AWS_SESSION_TOKEN'] = data['session_token']
    return env


def execution_environment(connection_id='', source=None):
    if connection_id:
        return environment(load(connection_id)['connection'], source)
    return {**(os.environ if source is None else source), 'MEMSTARA_CONFIG_MODE': 'environment'}


def probe(data):
    """A short Motoro structured-output request in an isolated process. No CSV/KB."""
    try:
        result = subprocess.run([sys.executable, '-m', 'memstara.model_connection_probe'],
                                env=environment(data), stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=45, check=False)
    except subprocess.TimeoutExpired:
        raise ValueError('Connection timed out. Check the endpoint and try again.') from None
    if result.returncode:
        # Provider exceptions may echo keys/URLs; only expose our fixed codes.
        code = result.stdout.decode(errors='replace').strip().splitlines()[-1:] or ['']
        messages = {'auth': 'Authentication failed. Check the API key and model access.',
                    'model': 'Model unavailable. Check the exact model ID or deployment name.',
                    'quota': 'The provider rejected the request because of quota or rate limits.',
                    'network': 'Could not reach the model. Check the endpoint and network connection.'}
        raise ValueError(messages.get(code[0], 'Connection check failed. Check the provider, model and credentials.'))


def check_and_save(value):
    data = validate(value)
    # Verify storage before billing a model probe; write no unverified connection.
    cipher = _cipher()
    probe(data)
    record = {'id': uuid.uuid4().hex, 'checked_at': datetime.now(UTC).isoformat(), 'connection': data}
    path = _directory() / (record['id'] + '.enc')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(cipher.encrypt(json.dumps(record).encode()))
    return public(record)
