"""Project-owned operational configuration, separate from saved research designs.

File mode never fills missing project settings from the calling shell. Environment
mode is an explicit contract for CI and process supervision. Neither reads a
sibling checkout. Resolution is pure so callers can validate before initialization.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from memstara.paths import REPO_ROOT

SELECTORS = {'MEMSTARA_CONFIG_MODE', 'MEMSTARA_ENV_FILE'}
PREFIXES = ('MEMSTARA_', 'MOTORO_', 'ANTHROPIC_', 'OPENAI_', 'OPENROUTER_', 'AZURE_', 'AGENTIC_')
EXTRA = {'AGENTIC_OKF_BUNDLE_DIR', 'CORE_VIEWER_DSN', 'VIEWER_CORS', 'HF_HOME',
         'HF_HUB_CACHE', 'HF_HUB_OFFLINE', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
         'MKL_NUM_THREADS', 'TOKENIZERS_PARALLELISM', 'POSTGRES_PASSWORD'}
PORT_DEFAULTS = {'MEMSTARA_WEB_PORT': 5173, 'MEMSTARA_API_PORT': 8071,
                 'MEMSTARA_CONTROL_PORT': 8072}
PATH_DEFAULTS = {'MEMSTARA_OUTPUT_DIR': 'outputs', 'HF_HOME': 'outputs/huggingface'}
PATH_KEYS = {*PATH_DEFAULTS, 'HF_HUB_CACHE', 'MEMSTARA_DATASET_PATH', 'AGENTIC_OKF_BUNDLE_DIR',
             'MEMSTARA_USER_SKILLS_DIR', 'MEMSTARA_SPECIALIST_SKILLS_DIR',
             'MEMSTARA_SHARED_SKILLS_DIR', 'MEMSTARA_RESULTS_SKILL_PATH',
             'MEMSTARA_ML_REFERENCE_PATH', 'MEMSTARA_SKILL_ALIASES_PATH',
             'MEMSTARA_LEAKAGE_RULES_PATH', 'MEMSTARA_EXPLANATION_SOURCES'}


def managed(name: str) -> bool:
    return name.startswith(PREFIXES) or name in EXTRA


def resolve(environ=None, *, file: Path | None = None):
    """Return validated values and safe provenance, without changing os.environ."""
    source = dict(os.environ if environ is None else environ)
    mode = source.get('MEMSTARA_CONFIG_MODE', 'project')
    if mode not in ('project', 'environment'):
        raise ValueError('MEMSTARA_CONFIG_MODE must be project or environment')
    path = Path(file or source.get('MEMSTARA_ENV_FILE') or REPO_ROOT / '.env').expanduser().resolve()
    if mode == 'project':
        if not path.is_file():
            raise ValueError('Project .env is missing; copy .env.example and configure this installation')
        raw = dotenv_values(path, interpolate=False)
        values = {k: v for k, v in raw.items() if v is not None and managed(k) and k not in SELECTORS}
        if any('${' in v for v in values.values()):
            raise ValueError('Project .env requires literal values; shell interpolation is not supported')
    else:
        values = {k: v for k, v in source.items() if managed(k) and k not in SELECTORS}
    root = path.parent if mode == 'project' else REPO_ROOT
    for name, default in PATH_DEFAULTS.items():
        values.setdefault(name, str(root / default))
    for name in PATH_KEYS:
        if values.get(name):
            p = Path(values[name]).expanduser()
            values[name] = str((p if p.is_absolute() else root / p).resolve())
    for name, default in PORT_DEFAULTS.items():
        value = values.get(name, str(default))
        if not value.isdecimal() or not 1 <= int(value) <= 65535:
            raise ValueError(f'{name} must be an integer port from 1 to 65535')
        values[name] = str(int(value))
    if len({values[k] for k in PORT_DEFAULTS}) != len(PORT_DEFAULTS):
        raise ValueError('Web, API and control ports must be distinct')
    # The default endpoint and resource must describe the same Foundry account.
    if values.get('MEMSTARA_LLM_PROVIDER') == 'azure_foundry':
        from memstara.stage_models import validate_endpoint
        resource = values.get('ANTHROPIC_FOUNDRY_RESOURCE', '').strip()
        endpoint = values.get('MEMSTARA_LLM_API_BASE', '').strip()
        if endpoint:
            validate_endpoint(endpoint)
            host = urlsplit(endpoint).hostname or ''
            suffix = '.services.ai.azure.com'
            if not host.endswith(suffix) or urlsplit(endpoint).path not in ('', '/'):
                raise ValueError('MEMSTARA_LLM_API_BASE must be a Foundry resource root URL')
            inferred = host[:-len(suffix)]
            if resource and resource != inferred:
                raise ValueError('Foundry resource and endpoint conflict')
            resource = inferred
        if resource:
            import re
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', resource):
                raise ValueError('ANTHROPIC_FOUNDRY_RESOURCE must be a resource name, not a URL')
            values['ANTHROPIC_FOUNDRY_RESOURCE'] = resource
            values['MEMSTARA_LLM_API_BASE'] = f'https://{resource}.services.ai.azure.com'
    values['MEMSTARA_CONFIG_MODE'] = mode
    values['MEMSTARA_ENV_FILE'] = str(path)
    return values, {'mode': mode, 'file': str(path) if mode == 'project' else None,
                    'inherited_project_file': (source.get('MEMSTARA_CONFIG_ORIGIN_FILE')
                                               if mode == 'environment' else None),
                    'restart_required_after_change': True}


def model_profiles(values=None):
    """Construct two public model profiles; credentials never enter the result."""
    values = os.environ if values is None else values
    base = {k: values.get('MEMSTARA_LLM_' + k.upper(), '').strip()
            for k in ('provider', 'model', 'api_base')}
    profiles = {}
    for family, prefix in (('non_explanation_agents', 'MEMSTARA_NON_EXPLANATION_'),
                           ('explanation_agent', 'MEMSTARA_EXPLANATION_')):
        profile = {k: values.get(prefix + k.upper(), '').strip() or v for k, v in base.items()}
        if profile['provider'] != base['provider'] and not values.get(prefix + 'API_BASE', '').strip():
            # A different provider must never inherit another provider's endpoint.
            profile['api_base'] = ''
        if not profile['provider'] or not profile['model']:
            raise ValueError('Set MEMSTARA_LLM_PROVIDER and MEMSTARA_LLM_MODEL in project .env before execution')
        for key, cast in (('temperature', float), ('max_tokens', int)):
            raw = values.get(prefix + key.upper(), '').strip() or values.get('MEMSTARA_LLM_' + key.upper(), '').strip()
            if raw:
                try:
                    profile[key] = cast(raw)
                except ValueError:
                    raise ValueError(f'{prefix}{key.upper()} has an invalid numeric value') from None
        effort = values.get(prefix + 'EFFORT', '').strip() or values.get('MEMSTARA_LLM_EFFORT', '').strip()
        if effort:
            profile['effort'] = effort
        if not profile['api_base']:
            profile.pop('api_base')
        profiles[family] = profile
    from memstara.stage_models import validate_profiles
    return validate_profiles(profiles)


def save_source(directory: Path) -> None:
    """Record source metadata once, without copying configuration or secrets."""
    from memstara.env import configuration_source
    from memstara.pipeline.checkpoint import atomic_json
    path = directory / 'operational_source.json'
    if not path.exists():
        atomic_json(path, configuration_source(), overwrite=False)


def migrate_models(path: Path, destination: Path) -> Path:
    """Explicitly import legacy profiles, preserving a restricted backup first."""
    import json
    import shutil
    import tempfile
    from dotenv import set_key, unset_key
    from memstara.stage_models import validate_profiles
    profiles = validate_profiles(json.loads(path.read_text()))
    if not destination.is_file():
        raise ValueError('Create project .env before importing legacy model settings')
    backup = Path(tempfile.mkdtemp(prefix='environment-', dir=destination.parent / 'outputs'))
    backup.chmod(0o700)
    for source in (destination, path):
        copied = backup / source.name
        shutil.copyfile(source, copied)
        copied.chmod(0o600)
    # Edit a restricted temporary copy; any validation/write failure leaves the
    # original installation configuration intact.
    fd, name = tempfile.mkstemp(prefix='.env-migration-', dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        shutil.copyfile(destination, temporary)
        existing = dotenv_values(temporary, interpolate=False)
        for family, prefix in (('non_explanation_agents', 'MEMSTARA_NON_EXPLANATION_'),
                               ('explanation_agent', 'MEMSTARA_EXPLANATION_')):
            for key in ('provider', 'model', 'api_base', 'temperature', 'max_tokens', 'effort'):
                if prefix + key.upper() in existing:
                    unset_key(str(temporary), prefix + key.upper())
                if key in profiles[family]:
                    set_key(str(temporary), prefix + key.upper(), str(profiles[family][key]))
        for key in ('provider', 'model', 'api_base', 'temperature', 'max_tokens', 'effort'):
            if 'MEMSTARA_LLM_' + key.upper() in existing:
                unset_key(str(temporary), 'MEMSTARA_LLM_' + key.upper())
            if key in profiles['non_explanation_agents']:
                set_key(str(temporary), 'MEMSTARA_LLM_' + key.upper(), str(profiles['non_explanation_agents'][key]))
        if 'MEMSTARA_STAGE_MODELS_PATH' in existing:
            unset_key(str(temporary), 'MEMSTARA_STAGE_MODELS_PATH')
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return backup


def check(values: dict) -> dict:
    """Static readiness, deliberately not a successful network or model probe."""
    errors = []
    for name in ('MEMSTARA_DATABASE_URL', 'MOTORO_DATABASE_URL', 'MOTORO_REDIS_URL'):
        if not values.get(name):
            errors.append(f'{name} is required')
    identities = []
    for name in ('MEMSTARA_DATABASE_URL', 'MOTORO_DATABASE_URL'):
        try:
            url = urlsplit(values.get(name, ''))
            if url.scheme not in ('postgresql', 'postgresql+asyncpg') or not url.hostname or not url.path.strip('/'):
                raise ValueError()
            host = '127.0.0.1' if url.hostname == 'localhost' else url.hostname
            identities.append((host, url.port or 5432, url.path))
        except ValueError:
            errors.append(f'{name} must identify a PostgreSQL database')
    if len(identities) == 2 and identities[0] == identities[1]:
        errors.append('Memstara and Motoro must use different databases')
    try:
        redis = urlsplit(values.get('MOTORO_REDIS_URL', ''))
        if redis.scheme not in ('redis', 'rediss') or not redis.hostname:
            raise ValueError()
        _ = redis.port
    except ValueError:
        errors.append('MOTORO_REDIS_URL must identify a Redis service')
    for name in PATH_KEYS - set(PATH_DEFAULTS) - {'HF_HUB_CACHE', 'MEMSTARA_USER_SKILLS_DIR'}:
        if values.get(name) and not Path(values[name]).exists():
            errors.append(f'{name} does not exist; correct the selected project .env')
    if values.get('MEMSTARA_STAGE_MODELS_PATH'):
        errors.append('Migrate legacy model JSON and unset MEMSTARA_STAGE_MODELS_PATH')
    profiles = {}
    try:
        profiles = model_profiles(values)
    except ValueError as exc:
        errors.append(str(exc))
    keys = {'azure_foundry': 'ANTHROPIC_FOUNDRY_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY',
            'openai': 'OPENAI_API_KEY', 'openrouter': 'OPENROUTER_API_KEY'}
    for role, profile in profiles.items():
        key = keys.get(profile['provider'])
        if key and (not values.get(key) or values[key].startswith(('YOUR_', 'REPLACE_'))):
            errors.append(f'{role}: configure {key} in the selected source')
    return {'configuration_valid': not errors, 'errors': errors,
            'models': profiles, 'ports': {k: values[k] for k in PORT_DEFAULTS},
            'database_connection': 'not_tested', 'model_call': 'not_tested'}


def main() -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'migrate-models'))
    parser.add_argument('--from-json', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'migrate-models':
            if not args.from_json:
                raise ValueError('Provide --from-json explicitly')
            file = Path(os.environ.get('MEMSTARA_ENV_FILE') or REPO_ROOT / '.env')
            (file.parent / 'outputs').mkdir(exist_ok=True)
            backup = migrate_models(args.from_json, file)
            print('Legacy model assignments imported. Restricted backup:', backup)
            print('Credentials are not imported. Restart services after validating .env.')
            return 0
        values, source = resolve()
        result = check(values)
        print(json.dumps({'source': source, **result}, indent=2))
        return 0 if result['configuration_valid'] else 1
    except (ValueError, OSError):
        # Parser/IO details may contain credential-bearing input: keep this generic.
        print('Configuration unavailable. Check selected .env, values and migration source; no values logged.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
