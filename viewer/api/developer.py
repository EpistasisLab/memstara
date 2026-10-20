"""Read-only, execution-scoped developer inspection; payloads load on demand."""

import asyncio
import json
import uuid
from fastapi import HTTPException
from db import pools
import run_artifacts
from loop_history import call_loops


async def execution(tag, loop=None):
    artifact = await asyncio.to_thread(run_artifacts.lookup, tag)
    if not artifact:
        raise HTTPException(404, "Execution archive not found")
    calls = [c for c in call_loops(artifact.get("calls", [])) if loop is None or c["loop"] == loop]
    return {
        "run_tag": tag,
        "loop": loop,
        "calls": calls,
        "pipeline": artifact.get("pipeline"),
        "note": "Recorded invocations, not a complete network trace. Select a call to inspect stored steps.",
    }


async def steps(tag, run_id, offset=0, detail=False):
    archive = await execution(tag)
    if not any(c.get("run_id") == str(run_id) for c in archive["calls"]):
        raise HTTPException(404, "Invocation does not belong to this execution")

    # Metadata lists never transfer model/tool payloads. Full payloads are fetched
    # one step at a time, after an explicit selection, and are not logged here.
    async def read(conn):
        if detail:
            rows = await conn.fetch(
                """SELECT row_to_json(s)::text AS record FROM run_steps s
                WHERE run_id=$1 ORDER BY sequence ASC, id ASC
                OFFSET $2 LIMIT 1""",
                uuid.UUID(str(run_id)),
                offset,
            )
            from motoro_records import redacted
            return [redacted(json.loads(r["record"])) for r in rows]
        rows = await conn.fetch(
            """SELECT id, sequence, iteration, phase, started_at, completed_at FROM run_steps
            WHERE run_id=$1 ORDER BY sequence ASC, id ASC
            OFFSET $2 LIMIT 51""",
            uuid.UUID(str(run_id)),
            offset,
        )
        return [dict(r) for r in rows]

    try:
        async with asyncio.timeout(10):
            records = await pools.guarded("core", read, None)
    except TimeoutError:
        raise HTTPException(503, "Trace read timed out; retry is safe") from None
    if records is None:
        raise HTTPException(503, "Trace database unavailable")
    return {
        "run_tag": tag,
        "run_id": str(run_id),
        "offset": offset,
        "steps": records[:50],
        "next_offset": offset + 50 if len(records) > 50 else None,
    }
