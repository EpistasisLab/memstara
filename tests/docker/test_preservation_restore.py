"""Actual pg_dump/pg_restore in isolated synthetic containers; no app databases."""
import json
import uuid

import pytest

from memstara import preservation as p

pytestmark = pytest.mark.docker


def test_paired_dump_and_isolated_restore(tmp_path):
    name = 'memstara-backup-source-' + uuid.uuid4().hex
    created = False
    image = 'pgvector/pgvector:pg16'
    p.command(['docker', 'image', 'inspect', image])
    try:
        p.command(['docker', 'create', '--name', name, '--network', 'none', '--memory', '768m',
                   '--cpus', '1', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', image])
        created = True
        p.command(['docker', 'start', name])
        p.command(['docker', 'exec', name, 'sh', '-ec',
                   'i=0; until pg_isready -U postgres; do i=$((i+1)); [ "$i" -lt 60 ]; sleep 1; done'])
        root = tmp_path / 'backup'
        root.mkdir()
        for db in ('board', 'runtime'):
            p.command(['docker', 'exec', name, 'createdb', '-U', 'postgres', db])
            p.command(['docker', 'exec', name, 'psql', '-U', 'postgres', '-d', db, '-v', 'ON_ERROR_STOP=1',
                       '-c', "CREATE TABLE evidence(id integer PRIMARY KEY, value text); "
                       "INSERT INTO evidence VALUES(1, 'saved result');"])
            with (root / f'{db}.dump').open('wb') as stream:
                p.command(['docker', 'exec', name, 'pg_dump', '-Fc', '-U', 'postgres', db], stdout=stream)
        source = tmp_path / 'artifacts'
        source.mkdir()
        (source / 'checkpoint.json').write_text('{"saved": true}')
        trees = {file: p.archive_tree(source, root / file)
                 for file in ('outputs.tar.gz', 'installation.tar.gz')}
        (root / 'manifest.json').write_text(json.dumps({
            'version': 1, 'status': 'complete', 'trees': trees,
            'files': {file.name: p.digest(file) for file in root.iterdir()},
        }))
        result = p.drill(root)
        assert result['databases_restored'] == ['board', 'runtime']
        assert result['application_resume'] == 'not_tested'
    finally:
        if created:
            p.command(['docker', 'rm', '--force', '--volumes', name])
