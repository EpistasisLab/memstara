"""Two connection pools, deliberately independent.

The board lives in Memstara's database, the agent run history in core's. They were
split apart on 2026-08-17 precisely so one going down does not take the other with
it — so the viewer must not undo that by treating them as one source. Each pool is
acquired separately and each query is wrapped by `guarded`, which turns an
unreachable database into a reported condition rather than a 500.

Read-only by permission, not by convention: the account is `memstara_viewer`, which
holds SELECT and nothing else. Verified — UPDATE and DELETE are refused. It is the
database that blocks it, not the carefulness of the code, so it cannot write even by
mistake.

==============================================================================
 How to read this file
==============================================================================

 What this file does
   It manages the connection pools to two independent PostgreSQL servers. So that one
   database going down does not take the whole viewer with it, a failure is turned
   into a "status report" called `Health` rather than an exception. Because it
   connects only with a read-only account, no query that goes out through this file
   can write.

 The cast
   MEMSTARA_DSN_DEFAULT  the DB with the board and the results table (memstara-postgres:5463)
   CORE_DSN_DEFAULT      the agent and run-history DB (motoro-postgres:5453)
   _dsn()                reads the connection string from the environment and strips
                         the SQLAlchemy prefix off it
   Health                which DB answered on the last attempt, or why it did not
   Pools                 the container holding the two pools
   Pools._pool()         builds a pool at first use (lazily)
   Pools.guarded()       ★ the heart of this file. Wraps a query and turns a failure
                         into a fallback
   pools                 the module-global instance. Every other file uses this one

 Easy things to miss
   1. The pool is built **at first use, not at import time.** Build it at import and
      the viewer cannot start at all while the core DB is switched off — which throws
      away the point of the split.
   2. `guarded` **swallows** the exception. That is right. A screen that shows the
      board and says "core is unreachable" is far more useful than a blank page
      because half the data is missing.
   3. On failure the pool is **dropped to None.** That is so a dead socket is not
      reused and the next poll connects afresh. Leave this out and the viewer keeps
      saying the DB is down after it has come back.
   4. **There is code that puts health back to True** on success. Without it a DB
      that failed once stays marked dead forever.
==============================================================================
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

import asyncpg

T = TypeVar("T")

MEMSTARA_DSN_DEFAULT = "postgresql://memstara_viewer:viewer@localhost:5463/memstara"
CORE_DSN_DEFAULT = "postgresql://memstara_viewer:viewer@localhost:5453/motoro"

#: Connections per pool. Two pools, so the servers see at most 2 x this.
POOL_MAX = 10
#: Seconds to wait for a free connection before calling the pool exhausted. Above the
#: slowest measured query (FLAT_CALLS at 2.7s on a loaded core DB) so that a slow answer
#: is not reported as a dead database, and far below nginx's 60s so a real jam surfaces
#: as "core is unreachable" on the screen rather than as a 504 with no explanation.
ACQUIRE_TIMEOUT = 5.0
# The default connection strings for the two DBs. That the ports differ is exactly what
# "completely different servers" means. 5463 = board and results table (memstara) /
# 5453 = agents and run history (motoro). Started under Docker, environment
# variables override these defaults.


def _dsn(env_name: str, default: str) -> str:
    # Read the connection string from the environment, but if it is empty or only
    # whitespace, use the default. `re.sub` turns a SQLAlchemy-style prefix such as
    # `postgresql+asyncpg://` back into `postgresql://`. That is a courtesy so a DSN
    # copied straight from somewhere else (the pipeline, say) is still one asyncpg
    # accepts.
    url = os.environ.get(env_name, "").strip() or default
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


@dataclass
class Health:
    """Which stores answered on the last attempt, and why not if they did not."""

    # Why this is a separate dataclass: so a failure can be **carried around as a value
    # instead of thrown as an exception.** The screen has to show a person "core:
    # unreachable", and for that the failure has to be recorded somewhere.
    # The default of True is deliberate too: if it has never connected yet, it is not
    # declared dead.

    memstara: bool = True
    core: bool = True
    memstara_error: str = ""
    core_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        # The shape that goes out as JSON unchanged. The front end reads it as
        # `health.core.up`.
        return {
            "memstara": {"up": self.memstara, "error": self.memstara_error},
            "core": {"up": self.core, "error": self.core_error},
        }


class Pools:
    # The container holding the two pools. There is only one instance, `pools` at the
    # bottom of this file, and main.py and scene.py both take that one.
    def __init__(self) -> None:
        self._memstara: asyncpg.Pool | None = None
        self._core: asyncpg.Pool | None = None
        self.health = Health()

    async def close(self) -> None:
        # Called when the app comes down (the lifespan in main.py). A pool that was
        # never built is None and is skipped. Putting it back to None after closing
        # matters — that is what lets `_pool` build a new one when it comes back up.
        for pool in (self._memstara, self._core):
            if pool is not None:
                await pool.close()
        self._memstara = self._core = None

    async def _pool(self, which: str) -> asyncpg.Pool:
        """Create the pool on first use and keep it.

        Lazily, because the viewer has to start even when a database is down — that is
        the whole point of the split. A pool built at import time would make an
        unreachable core database a startup crash.
        """
        attr = f"_{which}"
        pool = getattr(self, attr)
        if pool is None:
            dsn = (
                _dsn("MEMSTARA_VIEWER_DSN", MEMSTARA_DSN_DEFAULT)
                if which == "memstara"
                else _dsn("CORE_VIEWER_DSN", CORE_DSN_DEFAULT)
            )
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=POOL_MAX, timeout=5,
                                             command_timeout=10)
            # The create_pool above: timeout=5 is the limit on "getting connected",
            # command_timeout=10 the limit on "one query" — both are needed to stop a
            # slow DB from holding up the whole screen.
            #
            # POOL_MAX was 4, on the reasoning that a read-only app polling every 2
            # seconds needs few connections. That reasoning assumed one reader and a
            # snapshot faster than the interval, and both turned out to be false: a
            # snapshot measured 1.6-1.8s against a 2s poll, one browser tab per open
            # window, and each snapshot acquires four times (runs, board, results, core).
            # Overlapping polls then drained the pool.
            setattr(self, attr, pool)
        return pool

    async def guarded(self, which: str, fn: Callable[[asyncpg.Connection], Awaitable[T]],
                      fallback: T) -> T:
        """Run *fn* against one database; on any failure record it and return *fallback*.

        Swallowing the exception is right here: a viewer that shows the board and says
        "core is unreachable" is more useful than one that shows a blank page because
        half its data is missing. That is to say, this function is the device that
        **turns a partial failure into a partial screen.**
        """
        try:
            pool = await self._pool(which)
            # `timeout=` is the load-bearing argument, not a tidying detail. Without it
            # `acquire()` is the one unbounded wait in this file, and an exhausted pool
            # therefore never raises — so this `except` never runs, the screen never
            # degrades, and the request hangs until nginx gives up with a 504. That is
            # the opposite of what this function exists to do. With it, pool exhaustion
            # arrives here like any other failure: the DB is marked down, the pool is
            # dropped, and the next poll rebuilds it.
            async with pool.acquire(timeout=ACQUIRE_TIMEOUT) as conn:
                result = await fn(conn)
        except Exception as e:  # noqa: BLE001 - every failure is the same to a reader
            # The kind of exception is not distinguished. To the person looking, whether
            # it was "connection refused" or "authentication failed" or "query timed
            # out", the result is the same: "this DB cannot be read right now." So they
            # are lumped together. In exchange the type name and message are kept, up to
            # 200 characters, so the reason can be shown on screen.
            msg = f"{type(e).__name__}: {e}"[:200]
            if which == "memstara":
                self.health.memstara, self.health.memstara_error = False, msg
            else:
                self.health.core, self.health.core_error = False, msg
            # Drop the pool so the next tick reconnects instead of reusing dead sockets.
            # Keep reusing a dead socket and the viewer marks the DB down forever, even
            # after it comes back. Put back to None, `_pool` builds a new pool on the
            # next poll and it recovers by itself.
            setattr(self, f"_{which}", None)
            return fallback
        # Getting this far means success. health is **put back** to True. Without these
        # two lines a DB that failed once stays on a red light forever.
        if which == "memstara":
            self.health.memstara, self.health.memstara_error = True, ""
        else:
            self.health.core, self.health.core_error = True, ""
        return result


pools = Pools()
# One module-global instance. Every other file takes only this, with
# `from db import pools`. Holding the pools in one place is what makes the number of
# connections predictable.
