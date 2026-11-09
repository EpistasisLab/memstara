"""Exercise real public-schema deletion in two disposable PostgreSQL databases."""

import json
import os
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from memstara.blackboard import SCHEMA
from memstara.experiment_registry import SCHEMA as REGISTRY_SCHEMA
from memstara.control import history, history_scope

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def pair(monkeypatch, tmp_path):
    url = os.environ.get("MEMSTARA_TEST_DATABASE_URL", "")
    parts = urlsplit(url)
    if not parts.path.endswith("_test"):
        pytest.fail("A dedicated MEMSTARA_TEST_DATABASE_URL ending in _test is required")
    admin = await asyncpg.connect(url)
    names = ["history_" + uuid4().hex + "_test" for _ in range(2)]
    connections = []
    try:
        for name, key in zip(names, ["MEMSTARA_DATABASE_URL", "MOTORO_DATABASE_URL"], strict=True):
            await admin.execute(f'CREATE DATABASE "{name}"')
            endpoint = urlunsplit(parts._replace(path="/" + name))
            monkeypatch.setenv(key, endpoint)
            connections.append(await asyncpg.connect(endpoint))
        board, runtime = connections
        await board.execute(SCHEMA)
        await board.execute(REGISTRY_SCHEMA)
        await runtime.execute("""
            CREATE TABLE agents(id uuid PRIMARY KEY, name text, configuration jsonb);
            CREATE TABLE agent_runs(id uuid PRIMARY KEY, agent_id uuid REFERENCES agents(id));
            CREATE TABLE messages(id serial PRIMARY KEY, run_id uuid REFERENCES agent_runs(id), text text);
            CREATE TABLE run_steps(id uuid PRIMARY KEY, run_id uuid REFERENCES agent_runs(id));
            CREATE TABLE memory_entries(id serial PRIMARY KEY, agent_id uuid REFERENCES agents(id),
                source_run_id uuid REFERENCES agent_runs(id), step_id uuid REFERENCES run_steps(id), text text);
        """)
        root = tmp_path / "outputs"
        (root / "runs").mkdir(parents=True)
        (root / "runs/pipeline_workspace.json").write_text("preserved configuration")
        yield board, runtime, root
    finally:
        for conn in connections:
            await conn.close()
        for name in names:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()


async def test_selected_sql_clears_resumes_costs_outputs_and_preserves_other_experiment(pair):
    board, runtime, root = pair
    agent = uuid4()
    run_a, run_retry, run_b, shared = [uuid4() for _ in range(4)]
    await runtime.execute("INSERT INTO agents VALUES($1,'memstara-shared-agent','{}')", agent)
    for run in [run_a, run_retry, run_b, shared]:
        await runtime.execute("INSERT INTO agent_runs VALUES($1,$2)", run, agent)
        await runtime.execute("INSERT INTO messages(run_id,text) VALUES($1,'keep exact text')", run)
        await runtime.execute(
            "INSERT INTO memory_entries(agent_id,source_run_id,text) VALUES($1,$2,'run memory')", agent, run
        )
    await runtime.execute("INSERT INTO memory_entries(agent_id,text) VALUES($1,'shared unattributed memory')", agent)
    await board.execute("INSERT INTO memstara_experiments(id,definition) VALUES('design','{}')")
    await board.execute("INSERT INTO memstara_experiment_combinations VALUES('design','C01','{}')")
    for tag, owner, calls in [
        ("a-first", "a", [run_a, shared]),
        ("a-retry", "a", [run_retry]),
        ("b-first", "b", [run_b, shared]),
    ]:
        directory = root / "runs" / tag
        directory.mkdir()
        (directory / "control_record.json").write_text(json.dumps({"run_tag": tag, "pipeline_id": owner}))
        (directory / "execution.json").write_text(json.dumps({"calls": [{"run_id": str(run)} for run in calls]}))
        await board.execute(
            "INSERT INTO memstara_executions VALUES($1,'design','C01',$2,$3,'completed','{}','{}','report','{}',now())",
            tag,
            owner,
            str(directory),
        )
        for run in calls:
            await board.execute("INSERT INTO memstara_execution_agents VALUES($1,$2,'ml',1,2,'{}','{}')", tag, run)
        await board.execute("INSERT INTO memstara_execution_costs VALUES($1,'cost','{\"usd\":3}')", tag)
    q_a = await board.fetchval(
        "INSERT INTO memstara_questions(text,text_key,origin_run) VALUES('a','a','a-first') RETURNING question_id"
    )
    q_shared = await board.fetchval(
        "INSERT INTO memstara_questions(text,text_key,origin_run) "
        "VALUES('shared','shared','a-first') RETURNING question_id"
    )
    for tag, q in [("a-first", q_a), ("a-retry", q_shared), ("b-first", q_shared)]:
        task = await board.fetchval(
            "INSERT INTO memstara_blackboard(run_tag,trial,status,task_type,question_id) "
            "VALUES($1,1,'done','ml',$2) RETURNING task_id",
            tag,
            q,
        )
        await board.execute(
            "INSERT INTO memstara_results(run_tag,trial,task_id,question_id) VALUES($1,1,$2,$3)", tag, task, q
        )
    derived = root / "research_inputs/prepared/study/derived"
    derived.mkdir(parents=True)
    for name, owners in [("only-a.json", ["a-first"]), ("shared.json", ["a-first", "b-first"])]:
        path = derived / name
        path.write_text("preserve exact shared artifact")
        for tag in owners:
            await board.execute(
                "INSERT INTO memstara_execution_artifacts VALUES($1,$2,'hash',1,'file')", tag, str(path)
            )
    scoped = await history_scope.plan(root, "a")
    assert scoped["run_tags"] == ["a-first", "a-retry"]
    module = history.cleanup_module()
    await module.main(False, root=root, scope=scoped)
    assert await board.fetchval("SELECT count(*) FROM memstara_results") == 3
    await module.main(True, root=root, scope=scoped)
    assert [r["run_tag"] for r in await board.fetch("SELECT run_tag FROM memstara_results")] == ["b-first"]
    for table in ("memstara_blackboard", "memstara_execution_costs", "memstara_executions"):
        assert [r["run_tag"] for r in await board.fetch(f"SELECT run_tag FROM {table}")] == ["b-first"]
    assert await board.fetchval("SELECT count(*) FROM memstara_experiments") == 1
    assert [r["question_id"] for r in await board.fetch("SELECT question_id FROM memstara_questions")] == [q_shared]
    assert {r["id"] for r in await runtime.fetch("SELECT id FROM agent_runs")} == {run_b, shared}
    assert await runtime.fetchval("SELECT count(*) FROM messages") == 2
    assert await runtime.fetchval("SELECT count(*) FROM memory_entries") == 3
    assert await runtime.fetchval("SELECT count(*) FROM agents") == 1
    assert (root / "runs/b-first/execution.json").is_file() and not (root / "runs/a-first").exists()
    assert (derived / "shared.json").read_text() == "preserve exact shared artifact"
    assert not (derived / "only-a.json").exists()
    assert (root / "runs/pipeline_workspace.json").read_text() == "preserved configuration"
    # An exact durable plan is idempotent after files and registry rows disappear.
    await module.main(True, root=root, scope=scoped)
    assert await board.fetchval("SELECT count(*) FROM memstara_results") == 1
    # The original installation-wide reset still clears the remaining history.
    await module.main(True, root=root)
    for table in module.BOARD_TABLES:
        assert await board.fetchval(f"SELECT count(*) FROM {table}") == 0
    assert await runtime.fetchval("SELECT count(*) FROM agent_runs") == 0
    assert await runtime.fetchval("SELECT count(*) FROM memory_entries") == 0
    assert await runtime.fetchval("SELECT count(*) FROM agents") == 1
    assert (root / "runs/pipeline_workspace.json").read_text() == "preserved configuration"


async def test_active_database_owner_blocks_selected_deletion(pair):
    import zlib

    board, _, root = pair
    scoped = {"run_tags": ["active"], "paths": [], "runtime_run_ids": [], "experiment_ids": []}
    key = zlib.crc32(b"active")
    await board.execute("SELECT pg_advisory_lock($1::bigint)", key)
    try:
        with pytest.raises(RuntimeError, match="still owns"):
            await history.cleanup_module().main(True, root=root, scope=scoped)
    finally:
        await board.execute("SELECT pg_advisory_unlock($1::bigint)", key)
