"""Each test uses a disposable schema and genuine, independent connections."""

import os
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio

from memstara.blackboard import SCHEMA


@pytest_asyncio.fixture
async def database(monkeypatch, tmp_path):
    url = os.environ.get("MEMSTARA_TEST_DATABASE_URL", "")
    parts = urlsplit(url)
    if not url or not parts.path.endswith("_test"):
        pytest.fail("Set MEMSTARA_TEST_DATABASE_URL to a dedicated database ending in _test")
    schema = "test_" + uuid.uuid4().hex
    connection = await asyncpg.connect(url, timeout=10)
    try:
        await connection.execute(f"CREATE SCHEMA {schema}")
        await connection.execute(f"SET search_path TO {schema}")
        await connection.execute(SCHEMA)
        query = dict(parse_qsl(parts.query))
        query["search_path"] = schema
        monkeypatch.setenv("MEMSTARA_DATABASE_URL", urlunsplit(parts._replace(query=urlencode(query))))
        monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(tmp_path))
        # Integration evidence must not depend on a developer's local engine default.
        monkeypatch.setenv("MEMSTARA_ML_ENGINE", "xgboost")
        monkeypatch.delenv("MEMSTARA_RUN_CONFIG", raising=False)
        yield connection
    finally:
        await connection.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await connection.close()
