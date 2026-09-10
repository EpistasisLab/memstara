"""Read-only live scene check; only temporary tables are created."""
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewer" / "api"))
import db
import queries
import scene


async def main():
    conn = await asyncpg.connect(db.CORE_DSN_DEFAULT)
    try:
        async with conn.transaction():
            await conn.execute(queries.FLAT_TEMP_TABLE)
            core = {}
            for key, query, args in (
                ("open", queries.OPEN_RUNS, (str(scene.RUN_ALIVE_SECONDS),)),
                ("roster", queries.LAST_ROSTER, (str(scene.RUN_ALIVE_SECONDS),)),
                ("touches", queries.TASK_TOUCHES, (str(scene.RUN_ALIVE_SECONDS),)),
                ("last_call", queries.LAST_CALL, ()),
                ("recent", queries.RECENT_CALLS, (str(scene.FLASH_SECONDS),)),
            ):
                core[key] = [dict(r) for r in await conn.fetch(query, *args)]
            result = scene._build_scene(core, True)
            print("Live hypothesis telemetry:", [
                (a["playbook"], a["state"]) for a in result["agents"] if a["stage"] == "hypothesis"
            ])
            assert len({a["id"] for a in result["agents"]}) == len(result["agents"])
            print("PASS: live SQL and scene assembly, unique figure IDs")
    finally:
        await conn.close()


asyncio.run(main())
