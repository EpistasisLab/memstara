"""Offline recovery rehearsal for a disposable schema and synthetic artifacts."""

import asyncio
import hashlib
import json
import os
import re
import shutil
from urllib.parse import unquote, urlsplit

import asyncpg
import pytest

from memstara.experiment_registry import SCHEMA, register_experiment

pytestmark = pytest.mark.integration


async def test_dump_restore_preserves_evidence_and_constraints(database, tmp_path):
    schema = await database.fetchval('SELECT current_schema()')
    assert re.fullmatch(r'test_[0-9a-f]{32}', schema)
    parts = urlsplit(os.environ['MEMSTARA_TEST_DATABASE_URL'])
    assert parts.path.endswith('_test')
    env = dict(os.environ, PGHOST=parts.hostname or 'localhost',
               PGPORT=str(parts.port or 5432), PGUSER=unquote(parts.username or ''),
               PGPASSWORD=unquote(parts.password or ''), PGDATABASE=parts.path.lstrip('/'))
    env.pop('PGOPTIONS', None)

    async def run(tool, *args):
        executable = shutil.which(tool)
        assert executable, f'{tool} must be installed for the backup/restore rehearsal'
        process = await asyncio.create_subprocess_exec(
            executable, *args, env=env, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        assert process.returncode == 0, stderr.decode()
        return stdout

    await database.execute(SCHEMA)
    await register_experiment(database, 'synthetic', {'planned_runs': 1}, {'C01': {}})
    artifacts = tmp_path / 'outputs'
    artifacts.mkdir()
    report = artifacts / 'report.md'
    report.write_text('Synthetic proposal; no measured clinical findings.\n')
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    await database.execute(
        "INSERT INTO memstara_executions VALUES "
        "('run', 'synthetic', 'C01', NULL, $1, 'completed', '{}', '{}', $2, '{}', now())",
        str(artifacts), report.read_text())
    await database.execute(
        "INSERT INTO memstara_execution_artifacts VALUES ('run', $1, $2, $3, 'report')",
        str(report), digest, report.stat().st_size)
    await database.execute(
        "INSERT INTO memstara_execution_costs VALUES ('run', 'request-1', $1::jsonb)",
        json.dumps({'actual_cost': None, 'status': 'unavailable'}))
    task_id = await database.fetchval(
        "INSERT INTO memstara_blackboard(run_tag,trial,status,task_type) "
        "VALUES ('run',0,'ready','data') RETURNING task_id")

    async def snapshot():
        tables = await database.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname=$1 ORDER BY tablename", schema)
        return {row['tablename']: await database.fetchval(
            f'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), '\
            f"'[]'::jsonb)::text FROM {schema}.{row['tablename']} t") for row in tables}

    before = await snapshot()
    archive = tmp_path / 'database.dump'
    await run('pg_dump', '--format=custom', '--no-owner', '--no-privileges',
              f'--schema={schema}', f'--file={archive}')
    file_backup = tmp_path / 'artifact-backup'
    shutil.copytree(artifacts, file_backup)
    # Only the UUID schema created by the fixture is removed; never public/live tables.
    await database.execute(f'DROP SCHEMA {schema} CASCADE')
    report.unlink()
    await run('pg_restore', '--exit-on-error', '--single-transaction', '--no-owner',
              '--no-privileges', '--dbname', parts.path.lstrip('/'), str(archive))
    shutil.copytree(file_backup, artifacts, dirs_exist_ok=True)
    assert await snapshot() == before
    assert hashlib.sha256(report.read_bytes()).hexdigest() == digest
    assert report.stat().st_size == await database.fetchval(
        "SELECT bytes FROM memstara_execution_artifacts WHERE run_tag='run'")
    next_id = await database.fetchval(
        "INSERT INTO memstara_blackboard(run_tag,trial,status,task_type) "
        "VALUES ('run',1,'ready','data') RETURNING task_id")
    assert next_id > task_id
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await database.execute(
            "INSERT INTO memstara_execution_costs VALUES ('missing-run','bad','{}')")
    with pytest.raises(asyncpg.CheckViolationError):
        await database.execute(
            "UPDATE memstara_blackboard SET status='invalid' WHERE task_id=$1", next_id)


async def test_motoro_dump_restore_retains_runs_steps_and_readonly_acl(database, tmp_path):
    """Use installed upstream models without configuring or editing upstream."""
    import importlib
    import uuid

    from sqlalchemy.ext.asyncio import create_async_engine

    for module in ('agent', 'run'):
        importlib.import_module(f'motoro.models.{module}')
    from motoro.models.agent import Agent
    from motoro.models.base import Base
    from motoro.models.run import AgentRun, RunStep

    schema = await database.fetchval('SELECT current_schema()')
    assert re.fullmatch(r'test_[0-9a-f]{32}', schema)
    parts = urlsplit(os.environ['MEMSTARA_TEST_DATABASE_URL'])
    assert parts.path.endswith('_test')
    reader = 'reader_' + uuid.uuid4().hex
    engine = create_async_engine(
        parts._replace(scheme='postgresql+asyncpg').geturl(),
        connect_args={'server_settings': {'search_path': schema}})
    agent_id, run_id = uuid.uuid4(), uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync: Base.metadata.create_all(
                sync, tables=[Agent.__table__, AgentRun.__table__, RunStep.__table__]))
            await conn.execute(Agent.__table__.insert().values(
                id=agent_id, name='Synthetic recovery agent', goal='Recovery test'))
            await conn.execute(AgentRun.__table__.insert().values(
                id=run_id, agent_id=agent_id, status='completed', input='Synthetic input',
                output='Synthetic output', token_usage={'input': 10, 'output': 2}))
            await conn.execute(RunStep.__table__.insert().values(
                run_id=run_id, sequence=1, phase='act',
                input_data={'synthetic': True}, output_data={'saved': True}))
    finally:
        await engine.dispose()

    env = dict(os.environ, PGHOST=parts.hostname or 'localhost',
               PGPORT=str(parts.port or 5432), PGUSER=unquote(parts.username or ''),
               PGPASSWORD=unquote(parts.password or ''), PGDATABASE=parts.path.lstrip('/'))
    env.pop('PGOPTIONS', None)

    async def run(tool, *args):
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

    async def snapshot():
        tables = await database.fetch(
            'SELECT tablename FROM pg_tables WHERE schemaname=$1 ORDER BY tablename', schema)
        return {row['tablename']: await database.fetchval(
            f'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), '
            f"'[]'::jsonb)::text FROM {schema}.{row['tablename']} t") for row in tables}

    await database.execute(f'CREATE ROLE {reader} NOLOGIN')
    try:
        await database.execute(f'GRANT USAGE ON SCHEMA {schema} TO {reader}')
        await database.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {reader}')
        await database.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {reader}')
        before = await snapshot()
        archive = tmp_path / 'motoro-with-acl.dump'
        # Keep ACLs. Owner remains the dedicated test administrator on this same cluster.
        await run('pg_dump', '--format=custom', f'--schema={schema}', f'--file={archive}')
        await database.execute(f'DROP SCHEMA {schema} CASCADE')
        await database.execute(f'DROP ROLE {reader}')
        # Roles are cluster objects; a database archive cannot create them.
        await database.execute(f'CREATE ROLE {reader} NOLOGIN')
        await run('pg_restore', '--exit-on-error', '--single-transaction',
                  '--dbname', parts.path.lstrip('/'), str(archive))
        assert await snapshot() == before
        await database.execute('CREATE TABLE recovery_new_table (id integer)')
        await database.execute(f'SET ROLE {reader}')
        try:
            assert await database.fetchval('SELECT output FROM agent_runs WHERE id=$1', run_id) == 'Synthetic output'
            assert await database.fetchval('SELECT count(*) FROM run_steps WHERE run_id=$1', run_id) == 1
            assert await database.fetchval('SELECT count(*) FROM recovery_new_table') == 0
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await database.execute('DELETE FROM agent_runs WHERE id=$1', run_id)
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await database.execute('INSERT INTO recovery_new_table VALUES (1)')
        finally:
            await database.execute('RESET ROLE')
    finally:
        await database.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
        await database.execute(f'DROP ROLE IF EXISTS {reader}')
