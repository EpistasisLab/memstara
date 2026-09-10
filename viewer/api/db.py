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
   logger                the viewer's own log, so a failure outlives the poll that
                         overwrites it on screen
   Pools                 the container holding the two pools
   Pools._pool()         builds a pool at first use (lazily)
   Pools._discard()      the only way a pool is let go of — and only ever the pool the
                         caller itself held, never whichever one happens to be installed
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
   3. On failure the pool is **closed and then dropped to None.** Dropping it is so a
      dead socket is not reused and the next poll connects afresh — leave that out and
      the viewer keeps saying the DB is down after it has come back. Closing it first
      is so the connections do not outlive the pool: dropping the reference on its own
      leaks every backend the pool held, with no handle left to close them by.
   4. **There is code that puts health back to True** on success. Without it a DB
      that failed once stays marked dead forever.
==============================================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

import asyncpg

T = TypeVar("T")

#: The viewer's own log. Until this existed, `viewer/api/` wrote nothing at all — no
#: logging, no print — so the container's 99,608 log lines were pure uvicorn access log,
#: every one of them a 200. A `guarded` failure is the one event that explains a wrong
#: screen, and it left no trace: the health flag it sets is overwritten by the next
#: successful poll two seconds later. That is why intermittent faults here have had to
#: be diagnosed from scratch every time instead of read off the log.
#:
#: The name is a child of uvicorn's own error logger on purpose, and it is the only way
#: this line is worth writing. uvicorn configures `uvicorn`, `uvicorn.error` and
#: `uvicorn.access` and leaves the root logger with no handler at all, so a logger named
#: plainly `viewer` falls through to `logging.lastResort` and prints the bare message
#: with no level and no formatting — indistinguishable from a stray print in a log that
#: is otherwise entirely access lines. As a child of `uvicorn.error` it inherits that
#: handler and comes out marked `WARNING:` alongside everything else. Verified both ways
#: under uvicorn's real LOGGING_CONFIG.
logger = logging.getLogger("uvicorn.error.viewer")

MEMSTARA_DSN_DEFAULT = "postgresql://memstara_viewer:viewer@localhost:5463/memstara"
CORE_DSN_DEFAULT = "postgresql://memstara_viewer:viewer@localhost:5453/motoro"

#: Connections per pool. Two pools, so the servers see at most 2 x this.
POOL_MAX = 10
#: Seconds to wait for a free connection before calling the pool exhausted. Above the
#: slowest measured query (FLAT_CALLS at 2.7s on a loaded core DB) so that a slow answer
#: is not reported as a dead database, and far below nginx's 60s so a real jam surfaces
#: as "core is unreachable" on the screen rather than as a 504 with no explanation.
ACQUIRE_TIMEOUT = 3.0
#: Failures that say "the pool this read was holding went away", never "the database is
#: unreachable" — a connection cut from under an in-flight request, or a pool terminated
#: by `_discard` while another request was inside `acquire()`. `guarded` retries these
#: once against a fresh pool and reports them only if the second attempt fails too.
#:
#: Treating them as evidence is what turned one slow query into a self-sustaining outage:
#: the teardown produced `InterfaceError: pool is closed`, that counted as a failure,
#: that discarded the next pool, and with more than one poller the loop never settled.
#: `InterfaceError` is asyncpg's client side; `PostgresConnectionError` is the server
#: saying the connection is gone (class 08, `connection_does_not_exist` among them).
#: The two are separate hierarchies, so both have to be named.
_TEARDOWN_ERRORS = (asyncpg.InterfaceError, asyncpg.exceptions.PostgresConnectionError)
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
        #: Consecutive failed reads per store, reset to 0 by any success. Not a retry
        #: count and nothing here acts on it — it exists so the caller can tell a single
        #: dropped read from a database that is actually gone. See `hiccup`.
        self.fails: dict[str, int] = {"memstara": 0, "core": 0}
        #: Held while a pool is being built, one per store. Without it, every request
        #: that finds `None` builds its own pool and only the last `setattr` survives;
        #: the rest are unreachable and keep `min_size` backends open for the life of
        #: the process. See `_pool`.
        self._creating: dict[str, asyncio.Lock] = {
            "memstara": asyncio.Lock(), "core": asyncio.Lock(),
        }

    async def close(self) -> None:
        # Called when the app comes down (the lifespan in main.py). A pool that was
        # never built is None and is skipped. Putting it back to None after closing
        # matters — that is what lets `_pool` build a new one when it comes back up.
        for which in ("memstara", "core"):
            await self._discard(which, getattr(self, f"_{which}"))

    async def _discard(self, which: str, pool: asyncpg.Pool | None) -> None:
        """Let go of *pool*, closing it, but only if it is still the installed one.

        The only way a pool is ever released, whether at shutdown or after a failure.
        Dropping the reference on its own closes nothing: asyncpg owns the sockets, so
        an unclosed pool leaves up to POOL_MAX backends open on a server that nothing
        will read from again, and once the attribute is None there is no longer any
        handle to close them with.

        **Which pool is discarded is the whole correctness of this function.** It used
        to take only `which` and throw away whatever was installed at the moment it ran.
        `guarded` binds its pool once and then crosses several awaits, so a request that
        failed slowly would tear down the pool a *different* request had built in the
        meantime and was actively reading from. Those requests then failed with
        `InterfaceError: pool is closed`, which is itself a failure, which discarded the
        next pool — with more than one poller there is always a request in flight, so the
        loop sustained itself indefinitely and no database was involved in any of it.
        Comparing identity is what stops a failure from being contagious: a request may
        only throw away the pool it actually used.
        """
        # Detached first, and deliberately. Whatever happens below, the next poll must
        # find None here and build itself a fresh pool — recovery cannot be made to wait
        # on the tidying up of the thing that already failed.
        if pool is None or getattr(self, f"_{which}") is not pool:
            return
        setattr(self, f"_{which}", None)
        # A failed query can still have a connection in asyncpg's reset/release path.
        # Awaiting ``pool.close()`` here waits for every connection to be handed back,
        # and the failure that makes us throw a pool away is very often a connection that
        # is never coming back. Terminate it synchronously instead. The next request
        # builds a fresh pool; no request is allowed to wait for cleanup.
        pool.terminate()

    def hiccup(self) -> bool:
        """True when a store has just failed for the first time in a row.

        The distinction this draws is between a database that dropped one read and a
        database that is gone, and the caller needs it because the two deserve opposite
        answers. `guarded` returns an empty fallback either way, and a snapshot composed
        from that fallback does not say "unknown" — it says the board has no tasks and
        every agent is idle. For a real outage that is fine, because health goes down
        alongside it and `_build_scene` draws `unknown` instead. For one dropped read it
        is a fabrication, and at a 2s poll it is the flicker of six characters going
        blank and coming straight back.

        So this is not a threshold before believing a failure — health is still marked
        down on the first one, immediately and honestly. It only lets `scene.snapshot`
        prefer the previous picture, plainly flagged stale, for the single tick that a
        hiccup lasts. If the second read fails too this is False and the degraded
        snapshot goes out as it always did.
        """
        return any(n == 1 for n in self.fails.values())

    async def _pool(self, which: str) -> asyncpg.Pool:
        """Create the pool on first use and keep it.

        Lazily, because the viewer has to start even when a database is down — that is
        the whole point of the split. A pool built at import time would make an
        unreachable core database a startup crash.

        **Building it is behind a lock, and that is not a tidying detail.** `create_pool`
        is awaited, so without one every request that finds `None` builds a pool of its
        own and only the last `setattr` is reachable afterwards. The others are never
        closed and never will be — nothing holds a handle to them — so each strands
        `min_size` backends for the life of the process. Two pools of ten were seen as
        38 idle `memstara_viewer` backends on the server, the oldest sitting for ten
        days. The lock plus the second check below means N concurrent misses build one
        pool between them.
        """
        attr = f"_{which}"
        pool = getattr(self, attr)
        if pool is not None:
            return pool
        async with self._creating[which]:
            # Checked again inside the lock: whoever held it before us has very likely
            # just built the pool this call was going to build.
            pool = getattr(self, attr)
            if pool is not None:
                return pool
            dsn = (
                _dsn("MEMSTARA_VIEWER_DSN", MEMSTARA_DSN_DEFAULT)
                if which == "memstara"
                else _dsn("CORE_VIEWER_DSN", CORE_DSN_DEFAULT)
            )
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=POOL_MAX, timeout=5,
                                             command_timeout=4)
            # The create_pool above: timeout=5 is the limit on "getting connected",
            # command_timeout=4 the limit on "one query" — both are needed to stop a
            # slow DB from holding up the whole screen. The query ceiling sits under
            # SNAPSHOT_DEADLINE so a slow store is reported by the snapshot rather than
            # by the socket.
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
        last: Exception | None = None
        # Two attempts, and only ever for the one kind of failure listed in
        # `_TEARDOWN_ERRORS`. Everything else is reported the first time it happens.
        for attempt in (1, 2):
            pool = None
            try:
                pool = await self._pool(which)
                # `timeout=` is the load-bearing argument, not a tidying detail. Without
                # it `acquire()` is the one unbounded wait in this file, and an exhausted
                # pool therefore never raises — so this `except` never runs, the screen
                # never degrades, and the request hangs until nginx gives up with a 504.
                # That is the opposite of what this function exists to do. With it, pool
                # exhaustion arrives here like any other failure: the DB is marked down,
                # the pool is dropped, and the next poll rebuilds it.
                async with pool.acquire(timeout=ACQUIRE_TIMEOUT) as conn:
                    result = await fn(conn)
            except Exception as e:  # noqa: BLE001 - every failure is the same to a reader
                # Drop the pool so the next tick reconnects instead of reusing dead
                # sockets. Keep reusing a dead socket and the viewer marks the DB down
                # forever, even after it comes back. `_discard` throws away only the pool
                # this attempt actually held, so a failure here cannot take down a pool
                # another request is reading from.
                last = e
                await self._discard(which, pool)
                if attempt == 1 and isinstance(e, _TEARDOWN_ERRORS):
                    # Not evidence about the database. The pool this request was holding
                    # was terminated underneath it — by our own `_discard`, on some other
                    # request's failure, or by a server that closed the socket. Reporting
                    # it would put a red light on a store that was never asked. Ask once
                    # more, against a pool built after the one that went.
                    logger.debug("%s pool was replaced mid-read, retrying: %s",
                                 which, type(e).__name__)
                    continue
                break
            # Getting this far means success. health is **put back** to True. Without
            # these two lines a DB that failed once stays on a red light forever.
            self.fails[which] = 0
            if which == "memstara":
                self.health.memstara, self.health.memstara_error = True, ""
            else:
                self.health.core, self.health.core_error = True, ""
            return result

        # Both attempts spent, or one failure that a retry could not have fixed.
        #
        # The kind of exception is not distinguished from here on. To the person looking,
        # whether it was "connection refused" or "authentication failed" or "query timed
        # out", the result is the same: "this DB cannot be read right now." So they are
        # lumped together. In exchange the type name and message are kept, up to 200
        # characters, so the reason can be shown on screen.
        msg = f"{type(last).__name__}: {last}"[:200]
        self.fails[which] = self.fails.get(which, 0) + 1
        # Say it out loud as well as on screen. The screen forgets on the next successful
        # poll; the log does not, and an intermittent fault is only ever solvable from a
        # record that outlives it. `which` and the exception are all that goes out —
        # never the DSN, which carries the password.
        logger.warning("%s database query failed (%d in a row): %s",
                       which, self.fails[which], msg)
        if which == "memstara":
            self.health.memstara, self.health.memstara_error = False, msg
        else:
            self.health.core, self.health.core_error = False, msg
        return fallback


pools = Pools()
# One module-global instance. Every other file takes only this, with
# `from db import pools`. Holding the pools in one place is what makes the number of
# connections predictable.
