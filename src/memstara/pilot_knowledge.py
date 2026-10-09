"""Explicit read-only expert knowledge adapters for the experimental runner."""
from __future__ import annotations

from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import sqlite3


def validate_binding(binding: dict) -> None:
    if not isinstance(binding, dict) or not binding.get('database_id'):
        raise ValueError('An explicit expert database_id is required')
    kind = binding.get('kind')
    if kind == 'markdown':
        if not binding.get('path') or not Path(binding['path']).is_dir():
            raise ValueError('Knowledge directory is missing')
    elif kind in ('sqlite', 'postgres'):
        query = binding.get('query', '').strip()
        if not query.lower().startswith('select ') or ';' in query:
            raise ValueError('Knowledge query must be one SELECT returning id and text')
        if kind == 'sqlite' and (not binding.get('path') or not Path(binding['path']).is_file()):
            raise ValueError('Knowledge SQLite file is missing')
        if kind == 'postgres' and not os.environ.get(binding.get('dsn_env', '')):
            raise ValueError('Knowledge DSN environment binding is missing')
    else:
        raise ValueError('Choose an explicit markdown, sqlite or postgres knowledge adapter')


def _evidence(rows: list[dict], database_id: str) -> dict:
    records = []
    for row in rows[:10]:
        if row.get('id') is None or not isinstance(row.get('text'), str):
            raise ValueError('Knowledge records must have id and text fields')
        text = row['text']
        records.append({'id': str(row['id']), 'text': text[:6000],
                        'sha256': hashlib.sha256(text.encode()).hexdigest(),
                        'truncated': len(text) > 6000})
    return {'database_id': database_id, 'documents': records,
            'limit': 10, 'scope': 'retrieved evidence, not the entire knowledge database'}


async def retrieve(binding: dict, query_text: str) -> dict:
    """Query only the supplied expert store; there is no cross-expert fallback."""
    validate_binding(binding)
    kind = binding['kind']
    if kind == 'markdown':
        root = Path(binding['path']).resolve()
        terms = set(re.findall(r'[a-z0-9]+', query_text.lower()))
        ranked = []
        for path in sorted(root.rglob('*.md')):
            if not path.resolve().is_relative_to(root) or 'old' in {p.lower() for p in path.relative_to(root).parts}:
                continue
            text = path.read_text(encoding='utf-8')
            score = len(terms & set(re.findall(r'[a-z0-9]+', text.lower())))
            if score:
                ranked.append((score, path.relative_to(root).as_posix(), text))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        rows = [{'id': name, 'text': text} for _, name, text in ranked[:10]]
    elif kind == 'sqlite':
        uri = Path(binding['path']).resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as connection:
            connection.execute('PRAGMA query_only=ON')
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(binding['query'], (query_text,))
            rows = [dict(row) for row in cursor.fetchmany(10)]
    else:
        import asyncpg
        connection = await asyncpg.connect(os.environ[binding['dsn_env']], timeout=10)
        try:
            async with connection.transaction(readonly=True):
                rows = [dict(row) for row in await connection.fetch(
                    f"SELECT * FROM ({binding['query']}) AS pilot_knowledge LIMIT 10", query_text, timeout=15)]
        finally:
            await connection.close()
    return _evidence(rows, binding['database_id'])
