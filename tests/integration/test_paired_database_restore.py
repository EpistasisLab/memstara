"""Quiescent two-database recovery with synthetic cross-database references."""

import asyncio
import hashlib
import json
import os
import shutil
import uuid
from urllib.parse import unquote, urlsplit

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from memstara.experiment_registry import SCHEMA, register_experiment

pytestmark = pytest.mark.integration


async def test_quiescent_database_pair_and_artifacts_restore(tmp_path):
    from motoro.models.agent import Agent
    from motoro.models.base import Base
    from motoro.models.run import AgentRun, RunStep

    parts = urlsplit(os.environ.get('MEMSTARA_TEST_DATABASE_URL', ''))
    assert parts.path.endswith('_test'), 'A dedicated test database is required'
    admin = await asyncpg.connect(parts.geturl(), timeout=10)
    names = {key: f'restore_{uuid.uuid4().hex}_test'
             for key in ('app_source', 'core_source', 'app_target', 'core_target')}
    created = []
    env = dict(os.environ, PGHOST=parts.hostname or 'localhost',
               PGPORT=str(parts.port or 5432), PGUSER=unquote(parts.username or ''),
               PGPASSWORD=unquote(parts.password or ''))
    env.pop('PGOPTIONS', None)

    def url(key):
        return parts._replace(path='/' + names[key], query='').geturl()

    async def cli(tool, *args):
        executable = shutil.which(tool)
        assert executable, f'{tool} is required'
        proc = await asyncio.create_subprocess_exec(
            executable, *args, env=env, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), 60)
        except BaseException:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            raise
        assert proc.returncode == 0, stderr.decode()

    async def snapshot(key):
        conn = await asyncpg.connect(url(key))
        try:
            tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            return {r['tablename']: await conn.fetchval(
                f'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), '
                f"'[]'::jsonb)::text FROM public.{r['tablename']} t") for r in tables}
        finally:
            await conn.close()

    try:
        for name in names.values():
            await admin.execute(f'CREATE DATABASE {name}')
            created.append(name)
        agent_id, run_id = uuid.uuid4(), uuid.uuid4()
        engine = create_async_engine(url('core_source').replace('postgresql://', 'postgresql+asyncpg://'))
        try:
            async with engine.begin() as conn:
                await conn.run_sync(lambda sync: Base.metadata.create_all(
                    sync, tables=[Agent.__table__, AgentRun.__table__, RunStep.__table__]))
                await conn.execute(Agent.__table__.insert().values(
                    id=agent_id, name='Synthetic pair', goal='Recovery evidence'))
                await conn.execute(AgentRun.__table__.insert().values(
                    id=run_id, agent_id=agent_id, status='completed', input='Synthetic input',
                    output='Synthetic report'))
                await conn.execute(RunStep.__table__.insert().values(
                    run_id=run_id, sequence=1, phase='act', output_data={'saved': True}))
        finally:
            await engine.dispose()
        outputs = tmp_path / 'outputs'
        outputs.mkdir()
        report = outputs / 'report.txt'
        report.write_text('Synthetic report')
        digest = hashlib.sha256(report.read_bytes()).hexdigest()
        app = await asyncpg.connect(url('app_source'))
        try:
            await app.execute(SCHEMA)
            await register_experiment(app, 'pair', {'planned_runs': 1}, {'C01': {}})
            await app.execute(
                "INSERT INTO memstara_executions VALUES "
                "('pair-run','pair','C01',NULL,$1,'completed','{}','{}',$2,'{}',now())",
                str(outputs), report.read_text())
            await app.execute(
                "INSERT INTO memstara_execution_agents VALUES "
                "('pair-run',$1,'report',1,2,'{}',$2::jsonb)",
                run_id, json.dumps({'core_run_id': str(run_id)}))
            await app.execute(
                "INSERT INTO memstara_execution_artifacts VALUES ('pair-run',$1,$2,$3,'report')",
                str(report), digest, report.stat().st_size)
        finally:
            await app.close()

        # All synthetic writers/connections are closed before either dump or file copy.
        before = {key: await snapshot(key) for key in ('app_source', 'core_source')}
        bundle = tmp_path / 'bundle'
        bundle.mkdir()
        for key in ('app_source', 'core_source'):
            await cli('pg_dump', '--dbname', names[key], '--format=custom',
                      '--no-owner', '--no-privileges', '--file', str(bundle / f'{key}.dump'))
        shutil.copytree(outputs, bundle / 'outputs')
        manifest = {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in bundle.rglob('*') if p.is_file()}
        (bundle / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True))
        # Sources are made unavailable; successful assertions must use restored databases.
        for key in ('app_source', 'core_source'):
            await admin.execute(f'DROP DATABASE {names[key]}')
            created.remove(names[key])
        report.unlink()
        assert all(hashlib.sha256((bundle / name).read_bytes()).hexdigest() == sha
                   for name, sha in manifest.items())
        for source, target in (('app_source', 'app_target'), ('core_source', 'core_target')):
            await cli('pg_restore', '--dbname', names[target], '--exit-on-error',
                      '--single-transaction', '--no-owner', '--no-privileges',
                      str(bundle / f'{source}.dump'))
            assert await snapshot(target) == before[source]
        shutil.copytree(bundle / 'outputs', outputs, dirs_exist_ok=True)
        app = await asyncpg.connect(url('app_target'))
        core = await asyncpg.connect(url('core_target'))
        try:
            linked_id = await app.fetchval(
                "SELECT agent_run_id FROM memstara_execution_agents WHERE run_tag='pair-run'")
            assert linked_id == run_id
            assert await core.fetchval('SELECT output FROM agent_runs WHERE id=$1', linked_id) == report.read_text()
            assert await core.fetchval('SELECT count(*) FROM run_steps WHERE run_id=$1', linked_id) == 1
            artifact = await app.fetchrow('SELECT * FROM memstara_execution_artifacts')
            assert artifact['path'] == str(report)
            assert artifact['sha256'] == hashlib.sha256(report.read_bytes()).hexdigest()
            assert artifact['bytes'] == report.stat().st_size
        finally:
            await app.close()
            await core.close()
    finally:
        for name in reversed(created):
            await admin.execute(f'DROP DATABASE {name} WITH (FORCE)')
        await admin.close()
