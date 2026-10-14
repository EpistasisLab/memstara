"""Start local services from project .env without shell sourcing or model JSON."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from urllib.parse import unquote, urlsplit

from memstara.operational import PORT_DEFAULTS, check, managed, resolve
from memstara.paths import REPO_ROOT


def child_environment(values, service):
    """Only workers/control need provider credentials; web never receives DB keys."""
    generic = {key: value for key, value in os.environ.items()
               if key in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER', 'SHELL', 'SYSTEMROOT')}
    if service == 'web':
        return {**generic, **{k: values[k] for k in PORT_DEFAULTS}}
    if service == 'api':
        names = ('MEMSTARA_VIEWER_DSN', 'CORE_VIEWER_DSN', 'MEMSTARA_OUTPUT_DIR')
        return {**generic, **{k: values[k] for k in names if k in values},
                'VIEWER_CORS': f"http://localhost:{values['MEMSTARA_WEB_PORT']},http://127.0.0.1:{values['MEMSTARA_WEB_PORT']}"}
    return {**{k: v for k, v in os.environ.items() if not managed(k)},
            **values, 'MEMSTARA_CONFIG_MODE': 'environment',
            **({'MEMSTARA_CONFIG_ORIGIN_FILE': values['MEMSTARA_ENV_FILE']}
               if values.get('MEMSTARA_CONFIG_MODE') == 'project' else {})}


def assert_free(ports):
    sockets = []
    try:
        for port in ports:
            sock = socket.socket()
            sockets.append(sock)
            try:
                sock.bind(('127.0.0.1', int(port)))
            except OSError:
                raise ValueError(f'Port {port} is unavailable; choose a free port in project .env') from None
    finally:
        for sock in sockets:
            sock.close()


def compose_definition(values):
    """Construct a new local stack from database URLs; refuse remote destinations."""
    import re
    project = values.get('MEMSTARA_COMPOSE_PROJECT', 'memstara-local')
    if not re.fullmatch('[a-z0-9][a-z0-9_-]*', project):
        raise ValueError('MEMSTARA_COMPOSE_PROJECT must be a lowercase Compose project identifier')
    services = {}
    ports = []
    for name, key, image in (('board', 'MEMSTARA_DATABASE_URL', 'postgres:16-alpine'),
                             ('runtime', 'MOTORO_DATABASE_URL', 'pgvector/pgvector:pg16')):
        url = urlsplit(values.get(key, ''))
        if (url.hostname not in ('localhost', '127.0.0.1') or not url.port
                or not url.username or not url.password or not url.path.strip('/')):
            raise ValueError(f'{key}: local provisioning requires explicit localhost port, user, password and database')
        ports.append(url.port)
        user, password, db = unquote(url.username), unquote(url.password), unquote(url.path.strip('/'))
        services[name] = {'image': image, 'ports': [f'127.0.0.1:{url.port}:5432'],
                          'environment': {k: v.replace('$', '$$') for k, v in
                                          {'POSTGRES_USER': user, 'POSTGRES_PASSWORD': password,
                                           'POSTGRES_DB': db}.items()},
                          'volumes': [f'{name}-data:/var/lib/postgresql/data'],
                          'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'],
                                          'interval': '2s', 'timeout': '5s', 'retries': 30}}
    redis = urlsplit(values.get('MOTORO_REDIS_URL', ''))
    if redis.hostname not in ('localhost', '127.0.0.1') or not redis.port or redis.password or redis.username:
        raise ValueError('Local Redis provisioning requires a localhost URL with an explicit port and no credentials')
    ports.append(redis.port)
    if len(set(ports)) != len(ports):
        raise ValueError('Database and Redis host ports must be distinct')
    if set(ports) & {int(values.get(k, default)) for k, default in PORT_DEFAULTS.items()}:
        raise ValueError('Database/Redis ports must differ from web, API and control ports')
    services['redis'] = {'image': 'redis:7-alpine', 'ports': [f'127.0.0.1:{redis.port}:6379']}
    return {'name': project, 'services': services, 'volumes': {'board-data': {}, 'runtime-data': {}}}, ports


async def probe_connections(values):
    """Probe only selected services; never infer model success from credentials."""
    import asyncpg
    import redis.asyncio as redis
    results = {}
    for key in ('MEMSTARA_DATABASE_URL', 'MOTORO_DATABASE_URL',
                'MEMSTARA_VIEWER_DSN', 'CORE_VIEWER_DSN'):
        connection = None
        try:
            if not values.get(key):
                results[key] = 'not_configured'
                continue
            connection = await asyncpg.connect(
                values[key].replace('postgresql+asyncpg://', 'postgresql://', 1), timeout=5)
            await connection.fetchval('SELECT 1')
            if key.endswith('DSN'):
                unsafe = await connection.fetchval("""
                    SELECT EXISTS (SELECT 1 FROM pg_roles
                      WHERE rolname=current_user AND (rolsuper OR rolcreaterole OR rolcreatedb))
                    OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                      WHERE n.nspname='public' AND c.relkind IN ('r','p')
                      AND has_table_privilege(c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE'))
                """)
                if unsafe:
                    results[key] = 'unsafe_write_privileges'
                    continue
            results[key] = 'connected'
        except Exception:
            # Driver errors can include passwords/DSNs. Do not serialize them.
            results[key] = 'connection_failed'
        finally:
            if connection:
                await connection.close()
    client = None
    try:
        client = redis.from_url(values.get('MOTORO_REDIS_URL', ''), socket_timeout=5,
                                socket_connect_timeout=5)
        results['MOTORO_REDIS_URL'] = 'connected' if await client.ping() else 'connection_failed'
    except Exception:
        results['MOTORO_REDIS_URL'] = 'connection_failed'
    finally:
        if client:
            await client.aclose()
    return {'services': results, 'model_call': 'not_tested'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'connections', 'services', 'init', 'control', 'api', 'web'))
    args = parser.parse_args()
    try:
        values, source = resolve()
        environment = child_environment(values, args.command)
        if args.command == 'connections':
            import asyncio
            result = asyncio.run(probe_connections(values))
            print(json.dumps(result, indent=2))
            return 0 if all(v == 'connected' for v in result['services'].values()) else 1
        if args.command == 'check':
            result = check(values)
            print(json.dumps({'source': source, **result}, indent=2))
            return 0 if result['configuration_valid'] else 1
        if args.command == 'services':
            definition, ports = compose_definition(values)
            assert_free(ports)
            project = definition['name']
            for kind in ('container', 'volume'):
                command = ['docker', 'ps', '-aq'] if kind == 'container' else ['docker', 'volume', 'ls', '-q']
                found = subprocess.check_output(
                    [*command, '--filter', f'label=com.docker.compose.project={project}'], text=True)
                if found.strip():
                    raise ValueError('Compose project already has containers or volumes; '
                                     'inspect it explicitly, do not overwrite or reuse it')
            folder = Path(values['MEMSTARA_OUTPUT_DIR']) / 'local-runtime'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / 'compose.json'
            with path.open('w') as stream:
                os.chmod(path, 0o600)
                json.dump(definition, stream, indent=2)
            return subprocess.call(['docker', 'compose', '-f', str(path), 'up', '-d'], env=environment)
        if args.command == 'init':
            if not values.get('MOTORO_DATABASE_URL') or not values.get('MEMSTARA_DATABASE_URL'):
                raise ValueError('Configure both database URLs in project .env first')
            subprocess.run([sys.executable, '-m', 'motoro.migrations', 'upgrade',
                            '--url', values['MOTORO_DATABASE_URL']],
                           env=environment, cwd=REPO_ROOT, check=True)
            return subprocess.call([sys.executable, '-m', 'memstara.blackboard', '--create'],
                                   env=environment, cwd=REPO_ROOT)
        if args.command == 'control':
            port = values['MEMSTARA_CONTROL_PORT']
            argv = [sys.executable, '-m', 'memstara.control', '--port', port]
        elif args.command == 'api':
            if not all(values.get(k) for k in ('MEMSTARA_VIEWER_DSN', 'CORE_VIEWER_DSN')):
                raise ValueError('Configure both read-only viewer DSNs in project .env')
            import asyncio
            checks = asyncio.run(probe_connections({k: values[k] for k in
                                                   ('MEMSTARA_VIEWER_DSN', 'CORE_VIEWER_DSN')}))
            if any(checks['services'][k] != 'connected' for k in ('MEMSTARA_VIEWER_DSN', 'CORE_VIEWER_DSN')):
                raise ValueError('Viewer database access failed or has write privileges; '
                                 'run local_setup connections and fix read-only grants')
            port = values['MEMSTARA_API_PORT']
            argv = [str(REPO_ROOT / 'viewer/.venv/bin/python'), '-m', 'uvicorn', 'main:app',
                    '--app-dir', str(REPO_ROOT / 'viewer/api'), '--host', '127.0.0.1', '--port', port]
        else:
            port = values['MEMSTARA_WEB_PORT']
            argv = ['npm', '--prefix', str(REPO_ROOT / 'viewer/web'), 'run', 'dev', '--',
                    '--host', '127.0.0.1', '--port', port, '--strictPort']
        assert_free([port])
        return subprocess.call(argv, cwd=REPO_ROOT, env=environment)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        if isinstance(exc, ValueError):
            print(str(exc))
        else:
            print('Local setup operation failed; check service tools and file permissions')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
