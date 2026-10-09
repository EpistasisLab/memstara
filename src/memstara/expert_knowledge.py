"""Bounded, read-only retrieval from explicitly configured expert databases.

Bindings use id/text columns and optional enforced domain scopes. No model-supplied
SQL, database names, credentials or fallback corpus enter this adapter.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import time


class KnowledgeError(ValueError):
    """A safe configuration/availability error without connection secrets."""


def validate(binding, expert):
    if not isinstance(binding, dict) or binding.get("expert") != expert:
        raise KnowledgeError(f"{expert}: an explicit expert database binding is required")
    if binding.get('kind') == 'okf':
        from memstara.okf_expert import validate as validate_okf
        return validate_okf(binding,expert)
    required = {"expert", "database_id", "kind", "table", "id_column", "text_column"}
    optional = {"path", "dsn_env", "scope_column", "scope_value"}
    if set(binding) - required - optional or not required <= set(binding):
        raise KnowledgeError(f"{expert}: unsupported or incomplete database binding")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", str(binding["database_id"])):
        raise KnowledgeError("database_id must be a non-secret logical identifier")
    for key in ("table", "id_column", "text_column", "scope_column"):
        if key in binding and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", str(binding[key])):
            raise KnowledgeError("Database identifiers must be simple unqualified names")
    if ("scope_column" in binding) != ("scope_value" in binding):
        raise KnowledgeError("Both scope_column and scope_value are required")
    if "scope_value" in binding and (not isinstance(binding["scope_value"], str) or not binding["scope_value"]):
        raise KnowledgeError("The database scope must be a nonempty string")
    if binding["kind"] == "sqlite":
        if "dsn_env" in binding or not binding.get("path") or not Path(binding["path"]).is_file():
            raise KnowledgeError(f"{expert}: SQLite database is missing")
    elif binding["kind"] == "postgres":
        name = binding.get("dsn_env", "")
        if "path" in binding or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name) or not os.environ.get(name):
            raise KnowledgeError(f"{expert}: PostgreSQL connection environment setting is missing")
    else:
        raise KnowledgeError("Supported database kinds are sqlite and postgres")


def query(binding, text):
    """Return application-generated parameterized SQL, never execute caller SQL."""
    terms = list(dict.fromkeys(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())))[:24]
    if not terms:
        raise KnowledgeError("No searchable terms in the Interpretation context")
    params = []
    postgres = binding["kind"] == "postgres"

    def parameter(value):
        params.append(value)
        return f"${len(params)}" if postgres else "?"

    clauses = []
    if "scope_column" in binding:
        clauses.append(f'"{binding["scope_column"]}" = {parameter(binding["scope_value"])}')
    matches = []
    for term in terms:
        escaped = term.replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%")
        matches.append(f"LOWER(\"{binding['text_column']}\") LIKE {parameter('%' + escaped + '%')} ESCAPE '\\'")
    clauses.append("(" + " OR ".join(matches) + ")")
    expression = f'LEFT("{binding["text_column"]}",6001)' if postgres else f'SUBSTR("{binding["text_column"]}",1,6001)'
    sql = (
        f'SELECT "{binding["id_column"]}" AS id, {expression} AS text '
        f'FROM "{binding["table"]}" WHERE ' + " AND ".join(clauses) + f' ORDER BY "{binding["id_column"]}" LIMIT 10'
    )
    return sql, params


def _sqlite(binding, sql, params):
    path = Path(binding["path"]).resolve()
    before = path.stat()
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + 10
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(sql, params).fetchmany(10)]
        version = {
            "sqlite_version": sqlite3.sqlite_version,
            "file_size": before.st_size,
            "mtime_ns": before.st_mtime_ns,
            "snapshot": "retrieved excerpts retained; not a whole-database snapshot",
        }
        return rows, version
    finally:
        connection.close()


async def retrieve(binding, text):
    if binding.get('kind') == 'okf':
        from memstara.okf_expert import retrieve as retrieve_okf
        return await retrieve_okf(binding,text)
    validate(binding, binding.get("expert"))
    sql, params = query(binding, text)
    try:
        if binding["kind"] == "sqlite":
            rows, version = await asyncio.wait_for(asyncio.to_thread(_sqlite, binding, sql, params), 15)
        else:
            import asyncpg

            connection = await asyncpg.connect(os.environ[binding["dsn_env"]], timeout=10)
            try:
                async with connection.transaction(readonly=True, isolation="repeatable_read"):
                    rows = [dict(row) for row in await connection.fetch(sql, *params, timeout=10)]
                    version = {
                        "server_version": str(connection.get_server_version()),
                        "transaction_snapshot": str(
                            await connection.fetchval("SELECT txid_current_snapshot()", timeout=5)
                        ),
                        "snapshot": "retrieved excerpts retained; not a whole-database backup",
                    }
            finally:
                await connection.close(timeout=5)
    except Exception as exc:
        raise KnowledgeError(f"{binding['expert']}: database retrieval failed ({type(exc).__name__})") from None
    documents = []
    for row in rows:
        if row.get("id") is None or not isinstance(row.get("text"), str) or not row["text"].strip():
            raise KnowledgeError("Knowledge records require non-null id and text")
        excerpt = row["text"][:6000]
        documents.append(
            {
                "id": str(row["id"]),
                "text": excerpt,
                "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                "truncated": len(row["text"]) > 6000,
            }
        )
    if not documents:
        raise KnowledgeError(f"{binding['expert']}: no matching knowledge evidence; no fallback source was used")
    return {
        "database_id": binding["database_id"],
        "expert": binding["expert"],
        "binding": {k: v for k, v in binding.items() if k not in ("path", "dsn_env")},
        "query": {"text": text, "sql": sql, "parameters": params},
        "version": version,
        "documents": documents,
        "retrieval_policy": "bounded lexical matching; at most 10 excerpts; not an exhaustive review",
    }


async def probe(binding):
    """Check actual read-only connectivity, schema and scoped availability before LLM work."""
    if binding.get('kind') == 'okf':
        from memstara.okf_expert import probe as probe_okf
        return await probe_okf(binding)
    validate(binding, binding.get("expert"))
    sql = f'SELECT "{binding["id_column"]}" AS id, "{binding["text_column"]}" AS text FROM "{binding["table"]}"'
    params = []
    if "scope_column" in binding:
        placeholder = "$1" if binding["kind"] == "postgres" else "?"
        sql += f' WHERE "{binding["scope_column"]}"={placeholder}'
        params.append(binding["scope_value"])
    # Do not load large documents during connection preflight.
    sql = (
        sql.replace(f'"{binding["text_column"]}" AS text', f'SUBSTR("{binding["text_column"]}",1,1) AS text')
        + " LIMIT 1"
    )
    try:
        if binding["kind"] == "sqlite":
            rows, version = await asyncio.wait_for(asyncio.to_thread(_sqlite, binding, sql, params), 15)
        else:
            import asyncpg

            connection = await asyncpg.connect(os.environ[binding["dsn_env"]], timeout=10)
            try:
                async with connection.transaction(readonly=True):
                    rows = [dict(row) for row in await connection.fetch(sql, *params, timeout=10)]
                    version = {"server_version": str(connection.get_server_version())}
            finally:
                await connection.close(timeout=5)
        if not rows or rows[0].get("id") is None or not isinstance(rows[0].get("text"), str):
            raise KnowledgeError("Configured database scope is empty or lacks id/text records")
    except Exception as exc:
        raise KnowledgeError(f"{binding['expert']}: database preflight failed ({type(exc).__name__})") from None
    return {
        "status": "readable",
        "database_id": binding["database_id"],
        "expert": binding["expert"],
        "version": version,
        "scope": "read-only connection/schema check; not proof of evidence relevance",
    }
