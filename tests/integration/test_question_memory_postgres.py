"""Actual transactions and locks, exclusively in disposable test schemas."""

import json
import uuid

import pytest

from memstara.blackboard import BoardBusy, run_lock
from memstara.control import question_memory as memory
from memstara.mcp_servers import blackboard as tools

pytestmark = pytest.mark.integration


async def seed(db, text="Synthetic question"):
    return await db.fetchval(
        "INSERT INTO memstara_questions(text,text_key,okf_tags) VALUES($1,$2,'[\"tag\"]') RETURNING question_id",
        text,
        text.lower(),
    )


async def confirmation():
    return {
        "confirm": "CLEAR QUESTION MEMORY",
        "request_id": str(uuid.uuid4()),
        "token": (await memory.preview())["token"],
    }


async def test_clear_preserves_evidence_and_releases_duplicate_memory(database):
    qid = await seed(database)
    await database.execute(
        "INSERT INTO memstara_results(run_tag,trial,question_id,hypothesis) "
        "VALUES('history',0,$1,'Retained hypothesis')",
        qid,
    )
    before = dict(await database.fetchrow("SELECT * FROM memstara_results"))
    body = await confirmation()
    result = await memory.clear(body)
    assert result["cleared"] == 1
    assert (await memory.preview())["count"] == 0
    assert dict(await database.fetchrow("SELECT * FROM memstara_results")) == before
    assert (
        await database.fetchval("SELECT text FROM memstara_questions WHERE question_id=$1", qid) == "Synthetic question"
    )
    assert json.loads(await tools.read_questions(status=""))["questions"] == []
    assert json.loads(await tools.claim_question("new-run"))["question_id"] is None
    proposal = json.loads(
        await tools.propose_questions([{"text": "Synthetic question", "okf_tags": ["tag"], "rationale": "Synthetic"}])
    )
    assert len(proposal["added"]) == 1, proposal
    await tools.record_question_outcomes("history", retire_after=1)
    assert await database.fetchval("SELECT status FROM memstara_questions WHERE question_id=$1", qid) == "cleared"
    replay = await memory.clear(body)
    assert replay["replayed"] is True
    assert (await memory.preview())["count"] == 1  # Retry never clears later questions.
    audit = await database.fetchrow("SELECT * FROM memstara_question_memory_clears")
    assert audit["question_count"] == 1
    assert json.loads(audit["previous_keys_and_status"])[0]["status"] == "open"


async def test_stale_confirmation_makes_no_changes(database):
    await seed(database)
    body = await confirmation()
    await seed(database, "Another question")
    with pytest.raises(memory.MemoryConflict, match="changed"):
        await memory.clear(body)
    assert (await memory.preview())["count"] == 2


async def test_active_execution_and_clear_exclude_each_other(database):
    await seed(database)
    body = await confirmation()
    async with run_lock("synthetic-running-or-paused"):
        with pytest.raises(memory.MemoryConflict, match="End all"):
            await memory.clear(body)
    await database.execute("SELECT pg_advisory_lock(180947,54)")
    try:
        with pytest.raises(BoardBusy, match="memory"):
            async with run_lock("new-run"):
                pytest.fail("A pipeline started during a clear")
    finally:
        await database.execute("SELECT pg_advisory_unlock(180947,54)")
    assert (await memory.preview())["count"] == 1


async def test_audit_failure_rolls_back_all_changes(database):
    await seed(database)
    body = await confirmation()
    await database.execute(memory.AUDIT_SCHEMA)
    await database.execute("""CREATE FUNCTION reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'synthetic audit failure'; END $$;
      CREATE TRIGGER reject_audit BEFORE INSERT ON memstara_question_memory_clears
      FOR EACH ROW EXECUTE FUNCTION reject_audit();""")
    with pytest.raises(Exception, match="synthetic audit failure"):
        await memory.clear(body)
    assert (await memory.preview())["count"] == 1
    assert await database.fetchval("SELECT text_key FROM memstara_questions") == "synthetic question"
    assert await database.fetchval("SELECT count(*) FROM memstara_question_memory_clears") == 0


async def test_concurrent_confirmations_change_memory_once(database):
    import asyncio

    await seed(database)
    body = await confirmation()
    # Nonblocking exclusive gate may reject the competing request; retry is safe.
    outcomes = await asyncio.gather(memory.clear(body), memory.clear(body), return_exceptions=True)
    assert any(isinstance(result, dict) and result["cleared"] == 1 for result in outcomes)
    for result in outcomes:
        if isinstance(result, Exception):
            assert isinstance(result, memory.MemoryConflict)
    assert (await memory.clear(body))["replayed"]
    assert await database.fetchval("SELECT count(*) FROM memstara_question_memory_clears") == 1


async def test_legacy_execution_lock_blocks_clear(database):
    await seed(database)
    body = await confirmation()
    await database.execute("SELECT pg_advisory_lock(987654321::bigint)")
    try:
        with pytest.raises(memory.MemoryConflict, match="ownership"):
            await memory.clear(body)
    finally:
        await database.execute("SELECT pg_advisory_unlock(987654321::bigint)")
    assert (await memory.preview())["count"] == 1
