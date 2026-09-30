"""Confirmed archival reset of active question memory; historical IDs remain valid."""

import asyncio
import hashlib
import json
import uuid

import asyncpg

from memstara.blackboard import dsn

# Shared by every pipeline lease; clearing takes the exclusive transaction lock.
MEMORY_LOCK = (180947, 54)
AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS memstara_question_memory_clears (
    request_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    preview_token TEXT NOT NULL,
    question_count INTEGER NOT NULL,
    cleared_through INTEGER NOT NULL,
    previous_keys_and_status JSONB NOT NULL
)
"""


class MemoryConflict(ValueError):
    """No change was made; ask the user to review current state."""


def summarize(rows):
    ids = [int(row["question_id"]) for row in rows]
    return {
        "count": len(ids),
        "through": max(ids, default=0),
        "token": hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest(),
    }


async def preview():
    conn = await asyncpg.connect(dsn(), timeout=5, command_timeout=10)
    try:
        return summarize(
            await conn.fetch(
                "SELECT question_id FROM memstara_questions WHERE status <> 'cleared' ORDER BY question_id"
            )
        )
    finally:
        await conn.close()


def validate(body):
    if body.get("confirm") != "CLEAR QUESTION MEMORY":
        raise ValueError("Explicit confirmation is required.")
    try:
        request_id = uuid.UUID(body["request_id"])
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError("A valid confirmation request ID is required.") from None
    token = body.get("token")
    if not isinstance(token, str) or len(token) != 64:
        raise ValueError("Review the current question count before confirming.")
    return request_id, token


async def clear(body):
    request_id, token = validate(body)
    conn = await asyncpg.connect(dsn(), timeout=5, command_timeout=15)
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL lock_timeout = '3s'")
            if not await conn.fetchval("SELECT pg_try_advisory_xact_lock($1::integer, $2::integer)", *MEMORY_LOCK):
                raise MemoryConflict("End all running or paused executions before clearing question memory.")
            if await conn.fetchval("""SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objsubid=1
                    AND database=(SELECT oid FROM pg_database WHERE datname=current_database())
                    AND granted AND pid<>pg_backend_pid())"""):
                raise MemoryConflict("An execution still holds database ownership. End it before clearing memory.")
            # Also serialize against proposal deduplication and all direct table writers.
            await conn.execute("SELECT pg_advisory_xact_lock(180947, 53)")
            await conn.execute("LOCK TABLE memstara_questions IN SHARE ROW EXCLUSIVE MODE")
            await conn.execute(AUDIT_SCHEMA)
            previous = await conn.fetchrow(
                "SELECT question_count, cleared_through, preview_token "
                "FROM memstara_question_memory_clears WHERE request_id=$1",
                request_id,
            )
            if previous:
                if previous["preview_token"] != token:
                    raise MemoryConflict("This request ID was already used for a different confirmation.")
                return {
                    "cleared": previous["question_count"],
                    "cleared_through": previous["cleared_through"],
                    "replayed": True,
                }
            rows = await conn.fetch(
                "SELECT question_id, text_key, status FROM memstara_questions "
                "WHERE status <> 'cleared' ORDER BY question_id"
            )
            current = summarize(rows)
            if current["token"] != token:
                raise MemoryConflict("Question memory changed. Review the updated count and confirm again.")
            await conn.execute(
                """UPDATE memstara_questions
                SET status='cleared', text_key='memory-cleared:' || $1::text || ':' || question_id::text,
                    claimed_run='', claimed_by='', claimed_at=NULL
                WHERE status <> 'cleared'""",
                str(request_id),
            )
            await conn.execute(
                """INSERT INTO memstara_question_memory_clears
                (request_id, preview_token, question_count, cleared_through, previous_keys_and_status)
                VALUES ($1,$2,$3,$4,$5::jsonb)""",
                request_id,
                token,
                current["count"],
                current["through"],
                json.dumps([dict(row) for row in rows]),
            )
            return {"cleared": current["count"], "cleared_through": current["through"], "replayed": False}
    finally:
        await conn.close()


def handle(workspace, runs, body=None):
    """Control-plane mutation only; the viewer database role stays read-only."""
    if body is not None:
        validate(body)
    with workspace.lock:
        busy = bool(runs.running() or any(p.get("running") for p in workspace.list()))
        if body is not None and busy:
            raise MemoryConflict("End all running or paused executions before clearing question memory.")
        if body is None:
            return {**asyncio.run(preview()), "blocked": busy}
        return asyncio.run(clear(body))
