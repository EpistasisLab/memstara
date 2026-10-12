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
