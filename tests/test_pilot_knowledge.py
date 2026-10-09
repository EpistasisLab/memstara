import asyncio
import sqlite3

import pytest

from memstara.pilot_knowledge import retrieve, validate_binding


def test_markdown_retrieves_scoped_evidence_without_archive_or_external_symlink(tmp_path):
    root = tmp_path / 'knowledge'
    root.mkdir()
    (root / 'current.md').write_text('addiction knowledge')
    (root / 'old').mkdir()
    (root / 'old' / 'archived.md').write_text('addiction archive')
    outside = tmp_path / 'outside.md'
    outside.write_text('addiction outside')
    (root / 'linked.md').symlink_to(outside)
    result = asyncio.run(retrieve({'kind': 'markdown', 'path': str(root), 'database_id': 'addiction'}, 'addiction'))
    assert [item['id'] for item in result['documents']] == ['current.md']
    assert len(result['documents'][0]['sha256']) == 64


def test_sqlite_query_parameter_and_readonly_boundary(tmp_path):
    path = tmp_path / 'knowledge.sqlite'
    connection = sqlite3.connect(path)
    connection.execute('create table documents(id text, text text)')
    connection.execute('insert into documents values (?, ?)', ('one', 'hiv evidence'))
    connection.commit()
    connection.close()
    binding = {'kind': 'sqlite', 'path': str(path), 'database_id': 'hiv',
               'query': "SELECT id, text FROM documents WHERE text LIKE '%' || ? || '%'"}
    result = asyncio.run(retrieve(binding, 'hiv'))
    assert result['documents'][0]['id'] == 'one'
    assert asyncio.run(retrieve(binding, "' OR 1=1 --"))['documents'] == []
    binding['query'] = 'DELETE FROM documents'
    with pytest.raises(ValueError):
        validate_binding(binding)
