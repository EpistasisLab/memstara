#!/usr/bin/env python3
"""The shared work board — table definitions and creation.

The 2026-08-12 alignment settled that this is a **table**, living in **Memstara's own
database** — its own Postgres server, its own volume, its own account. See
``docker-compose.yml`` next to this file; nothing here touches core's database.

That independence is the point, and it is worth being blunt about why. These tables
first lived inside core's `motoro` database, separated only by an `memstara_` name
prefix. Everything worked, but the arrangement was wrong: Memstara is meant to be an
application that owns its store, not a guest in core's. Sharing a server means core's
container going down takes Memstara's results with it, a `docker volume rm` aimed at
core destroys data that has nothing to do with core, and backing up one backs up the
other. A prefix is a naming convention, not a boundary. So the server, the volume and the
account were separated outright.

**core's migrations are not touched** — they cannot be, since they run against a
different server entirely.

Two tables, deliberately separate:

- ``memstara_blackboard`` — work that is not finished yet, and its state. Changes
  constantly while a run is going.
- ``memstara_results``   — what the interpretation stage produced. Only accumulates.

Keeping them apart means "what is left to do" never gets mixed with "what we have
found", which is what that separation was for.

    memstara_blackboard  the **work surface**, holding work that is not finished and
                         its state. It changes constantly while a run is going, and
                         it may be cleared away once it has served its purpose.
    memstara_results     the **record** the interpretation stage produced. It only
                         accumulates, never shrinks.

Usage::

    python -m memstara.blackboard --create      # idempotent
    python -m memstara.blackboard --show
    python -m memstara.blackboard --drop        # asks first
    python -m memstara.blackboard --drop-questions   # the bank, which --drop leaves alone

 The three below deal with **one run only**, not the whole board. They are for
 clearing away tasks left on the board by a run that was interrupted or died.

    python -m memstara.blackboard --orphans   which run left how many unfinished tasks
    python -m memstara.blackboard --reclaim TAG
                                     put that run's 'in progress' back in the queue
    python -m memstara.blackboard --close TAG close that run's unfinished tasks as failed.
                                     **The rows are not deleted** — they record why
                                     there is no result.

==============================================================================
 How to read this file
==============================================================================

 This file is **the blueprint for the board and the results table.** It writes down
 which columns the tables get (in SQL), settles the address the database is reached
 at, and makes creating, viewing and dropping them possible from the command line.
 No work actually happens here — it only lays out the place where work happens.

 The main names
 --------------
 STATUSES / TASK_TYPES  the four states a task can be in and the four stages.
 SCHEMA                 the full definition (SQL) of the tables. Written to be safe
                        to run more than once.
 dsn()                  the address of Memstara's own database. Not core's.
 BoardBusy              the exception raised when another run already holds this run_tag.
 run_lock(run_tag)      one run at a time per run_tag — a Postgres advisory lock.
 create / drop / show   create the tables / drop them / see what state things are in.
 orphans()              counts, per tag, the tasks left unfinished on the board. Reads only.
 reclaim / close_run    reverse or close one run only. Other tags are untouched.
 main()                 reads the command-line arguments and calls one of the above.

 Easy things to miss
 -------------------
 1. There are two tables. `memstara_blackboard` is a work surface, so **it is fine
    for it to disappear when cleared**; `memstara_results` is a record, so **it has
    to stay.**
 2. The link from the results table to the board is `ON DELETE SET NULL`. That is,
    **dropping the board does not delete the results** — only the link is broken.
    Back when it was CASCADE, cleaning the board took the results with it, which
    removes the point of having two tables.
 3. `run_lock` is a PostgreSQL advisory lock, so **it is tied to the connection.**
    Even a `kill -9` closes the connection and releases the lock with it. Had it been
    a pid file, the file a dead process left behind would have blocked every later run.
"""

from __future__ import annotations

import argparse      # reads the command-line arguments (--create, --drop, --show)
import asyncio        # asyncpg is async, so the CLI wraps calls in asyncio.run
import contextlib     # what makes run_lock usable with `with`
import os             # reads the database address from the environment
import re             # tidies up the postgresql+asyncpg:// form
import zlib           # holds crc32, which turns a run_tag into a lock number (an integer)
from collections.abc import AsyncIterator

import asyncpg        # the async PostgreSQL driver

# Every state a task can be in.
#
# `failed` and the `attempts` column below are present but **not yet used by any
# policy**. What happens to a task whose agent claimed it and then died is still open
# (see the 2026-08-17 blackboard design document, §2 "the five to decide") — it might be
# returned to `ready` for another attempt, or closed as `failed`. Carrying both now
# means whichever way that
# lands, the table does not have to be rebuilt. **This is not a decision; it is leaving
# both doors open.**
#
#   ready        nobody has taken it yet — anyone may
#   in_progress  somebody took it and is working on it now
#   done         finished
#   failed       closed as a failure
STATUSES = ("ready", "in_progress", "done", "failed")

# The four stages: form a hypothesis -> cut the data -> train -> interpret. A task
# carries the stage that should pick it up next, which is how an agent answers "is this
# mine?" without anyone telling it — it decides from the board alone.
TASK_TYPES = ("hypothesis", "data", "ml", "interpret")

# What follows is an f-string. The tuples settled above go straight into the {STATUSES}
# and {TASK_TYPES} slots and become SQL IN lists. Writing the state names out separately
# in Python and in SQL would drift apart sooner or later, so they are written once and
# interpolated.
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS memstara_blackboard (
    -- The board (the work surface). Work that is not finished and its state live here.
    -- A table that may be cleared away once a run is over.
    -- task_id is BIGSERIAL — a number that increments by 1 with every row inserted.
    task_id            BIGSERIAL PRIMARY KEY,

    -- which pipeline run this row belongs to, and which trial within it.
    -- perspective records the angle that trial was built from.
    run_tag            TEXT        NOT NULL,
    trial              INTEGER     NOT NULL,
    perspective        TEXT        NOT NULL DEFAULT '',

    -- The two columns that turn a ledger into a board. status says what state it is in
    -- now, task_type says who should pick it up next. Without the two this is just a
    -- table that accumulates records; with them the agents can divide the work up among
    -- themselves. CHECK is what stops anything but the settled values getting in.
    status             TEXT        NOT NULL
                       CHECK (status IN {STATUSES}),
    task_type          TEXT        NOT NULL
                       CHECK (task_type IN {TASK_TYPES}),

    -- Filled by the hypothesis stage: what it claims (hypothesis), which columns it
    -- means to use (columns), and which evidence documents it read (okf_concept_ids).
    -- JSONB is the column type that holds a whole list or table.
    hypothesis         TEXT        NOT NULL DEFAULT '',
    columns            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    okf_concept_ids    JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- What the matcher was asked and what it offered back, including the candidates
    -- that were not chosen. The driver harvests this from the run trace after the
    -- hypothesis stage; the agent does not report it. Asking the agent would mean
    -- trusting it to hand-copy hundreds of candidate rows with no way to check the
    -- copy, and the trace already holds every call verbatim.
    --
    -- Without this the row records which columns were picked but not what they were
    -- picked over, so "why this column" is answerable only while the run directory
    -- survives.
    match_trace        JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- What the chosen columns are meant to predict. On the board rather than in a
    -- prompt: a task has to carry everything its stage needs, or the board is not the
    -- source of truth it claims to be. Before this, the driving script told each agent
    -- the outcome column in the prompt text, so a finished row recorded an AUC without
    -- recording what it was an AUC *of*.
    y_column           TEXT        NOT NULL DEFAULT '',

    -- Filled by the data stage: where the small CSV it cut lives (subset_path), the
    -- columns it actually used (columns_used) and the ones it could not because they
    -- were absent (columns_missing). The absent ones are recorded separately because
    -- when what the hypothesis asked for differs from what was actually used, the
    -- interpretation stage has to read the result knowing that difference.
    subset_path        TEXT        NOT NULL DEFAULT '',
    columns_used       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    columns_missing    JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- Filled by the ml stage: the performance number (auc) and how much each variable
    -- contributed (feature_importance). auc alone is not NOT NULL, because before
    -- training has happened the right value is "none", not "0".
    -- The doubled braces in the default are because this SCHEMA is an f-string; doubled
    -- here, they arrive in the real SQL singled, as an empty JSON object.
    auc                DOUBLE PRECISION,
    feature_importance JSONB       NOT NULL DEFAULT '{{}}'::jsonb,

    -- Filled by the interpretation stage: the numbers put into human words.
    interpretation     TEXT        NOT NULL DEFAULT '',

    -- See the note on STATUSES above. How many attempts were made and the last error.
    -- They are only in place; no policy yet decides anything from them.
    attempts           INTEGER     NOT NULL DEFAULT 0,
    error              TEXT        NOT NULL DEFAULT '',

    -- When and by whom it was claimed / when it was created / when it last changed.
    -- TIMESTAMPTZ is the type that stores the time zone along with the time.
    claimed_at         TIMESTAMPTZ,

    -- Who is holding it. Empty means nobody claimed it, or a claimer that did not say
    -- who it was. This comment used to promise "and by whom" one line up while no such
    -- column existed, and the cost of that was concrete: submit_result could ask "is
    -- this in_progress?" and never "is this still mine?", so a worker whose task had
    -- been reclaimed out from under it could still submit and overwrite whoever now
    -- held it. With one worker per stage that never happened. With two it is the
    -- ordinary case.
    --
    -- TEXT, and deliberately not a foreign key to any agents table — the same reasoning
    -- as question_id further down. The board is cleared and the identities outlive it,
    -- so a key pointing from the short-lived table at the long-lived one would make
    -- dropping the board require dropping them first.
    claimed_by         TEXT        NOT NULL DEFAULT '',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- An index is a table of contents that makes looking things up fast. claim_task()
-- always asks for exactly this — the oldest ready row of one type — so the index is
-- built in that same order.
CREATE INDEX IF NOT EXISTS memstara_blackboard_claim_idx
    ON memstara_blackboard (task_type, status, task_id);

-- The index used when gathering the rows of one run (run_tag).
CREATE INDEX IF NOT EXISTS memstara_blackboard_run_idx
    ON memstara_blackboard (run_tag);

CREATE TABLE IF NOT EXISTS memstara_results (
    -- The results table (the record). Unlike the board it only accumulates and never
    -- shrinks. The reporting stage reads **this table only.**
    result_id      BIGSERIAL PRIMARY KEY,
    -- Nullable, and SET NULL rather than CASCADE. The whole reason this table is
    -- separate from the board is that the board is a work queue you can clean out
    -- while findings stay — and CASCADE made cleaning the board delete the findings
    -- with it, which quietly removed the point of having two tables. SET NULL keeps
    -- the link honest while the task row lives and breaks it cleanly once it is gone.
    -- A result row describes itself without the id: run_tag, trial, perspective,
    -- hypothesis, columns_used, y_column, auc and the write-up are all here.
    --
    -- **This is the most important line in the file.**
    task_id        BIGINT      REFERENCES memstara_blackboard (task_id)
                   ON DELETE SET NULL,
    run_tag        TEXT        NOT NULL,
    trial          INTEGER     NOT NULL,
    perspective    TEXT        NOT NULL DEFAULT '',
    hypothesis     TEXT        NOT NULL DEFAULT '',
    columns_used   JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- Why those columns, copied over from the board when the task finishes. The board
    -- is a work surface that gets cleared and this table is the record that stays, so
    -- evidence left only on the board is evidence with an expiry date: clearing the
    -- board took "why this column" with it and left a result asserting a conclusion it
    -- could no longer support.
    --
    -- okf_concept_ids is which corpus documents the hypothesis was built from;
    -- match_trace is what the matcher offered, chosen and rejected alike.
    okf_concept_ids JSONB      NOT NULL DEFAULT '[]'::jsonb,
    match_trace     JSONB      NOT NULL DEFAULT '[]'::jsonb,

    -- What was asked for, against columns_used above, which is what arrived. When the
    -- two differ the reason is columns_missing, and without both a reader of this table
    -- cannot tell a column that was never wanted from one that was wanted and absent.
    columns         JSONB      NOT NULL DEFAULT '[]'::jsonb,
    columns_missing JSONB      NOT NULL DEFAULT '[]'::jsonb,

    -- Carried over from the board. The reporting stage reads only this table, so
    -- without it a report would state an AUC without stating what it is an AUC *of* —
    -- exactly the gap that putting y_column on the board was meant to close.
    y_column       TEXT        NOT NULL DEFAULT '',

    auc            DOUBLE PRECISION,

    -- Which columns actually carried that AUC, copied over from the board. Feedback
    -- needs this and nothing else does: a later run can only avoid what did not work
    -- if the number saying so outlives the run that produced it. While this lived only
    -- on the board, a hypothesis agent reading finished results could see that a trial
    -- scored 0.72 but not which of its columns contributed nothing.
    feature_importance JSONB   NOT NULL DEFAULT '{{}}'::jsonb,

    interpretation TEXT        NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The index used when gathering one run's results.
CREATE INDEX IF NOT EXISTS memstara_results_run_idx
    ON memstara_results (run_tag);

CREATE TABLE IF NOT EXISTS memstara_questions (
    -- The question bank. Neither a board nor a results table: it holds what the
    -- pipeline decided to ASK, where the other two hold what it did and what it found.
    --
    -- There is deliberately no run_tag. A run_tag column would make this a per-run
    -- scratch list, and then the second run would re-ask everything the first run had
    -- already exhausted. The bank spans runs so that "what has this project already
    -- looked at" is a question the database can answer.
    question_id  SERIAL      PRIMARY KEY,

    -- The perspective phrase itself, handed to the hypothesis agent verbatim. text_key
    -- is the same string lowercased and whitespace-collapsed; UNIQUE sits on the key,
    -- not on text, so two proposals differing only in capitalisation collide as they
    -- should while the wording the agent chose is preserved.
    text         TEXT        NOT NULL,
    text_key     TEXT        NOT NULL UNIQUE,

    -- Which corpus branches this question is grounded in. This column is the whole
    -- point of the table: a question that cannot name a tag the corpus actually carries
    -- is a question the knowledge source cannot answer, and asking it anyway is what
    -- forced the agent to invent citations. Empty here means the generator failed.
    okf_tags     JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- Why this question was proposed — which corpus gap, or which prior result. On the
    -- second wave onward this is where the feedback loop becomes readable by a person.
    rationale    TEXT        NOT NULL DEFAULT '',

    origin_run   TEXT        NOT NULL DEFAULT '',
    origin_wave  INTEGER     NOT NULL DEFAULT 0,

    -- Filled in after a wave finishes, by joining the results table on question_id.
    -- times_used counts trials, not runs: one question can seed several trials.
    times_used   INTEGER     NOT NULL DEFAULT 0,
    best_auc     DOUBLE PRECISION,

    status       TEXT        NOT NULL DEFAULT 'open',   -- 'open' | 'exhausted'
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Who is working this question right now, and since when. The same pair the board
    -- carries, for the same reason and with the same vocabulary: with two hypothesis
    -- agents seeding one wave, something has to stop both of them setting out from the
    -- question. Without it the only thing keeping them apart is the driver handing each
    -- a different one out of its own memory, which is not written down anywhere and
    -- therefore not true of a second driver, a resumed run, or a crash mid-wave.
    --
    -- **These two are temporary in a way the board's are not, and that difference is the
    -- whole design.** There is deliberately no run_tag on this table (see above): the
    -- bank spans runs so the project can answer "what have we already asked". A claim
    -- that is never released would therefore drain the bank permanently — the second run
    -- would find every question taken by the first and have nothing to ask. So a claim
    -- lives only as long as the seeding window it exists to protect, and it is ended two
    -- ways: release_questions() clears the run's claims the moment its wave has finished
    -- seeding, and claim_question treats a claim older than the staleness window as free,
    -- which is what recovers a run that died between the two.
    --
    -- claimed_run is which run is holding it, not which agent — release_questions works a
    -- run at a time, and the worker name alone ('hypothesis#1') is reused by every run
    -- there has ever been. claimed_by is kept beside it anyway, because "run X is holding
    -- this" does not tell a person reading the bank which of X's two workers had it.
    claimed_run  TEXT        NOT NULL DEFAULT '',
    claimed_by   TEXT        NOT NULL DEFAULT '',
    claimed_at   TIMESTAMPTZ
);

-- read_questions() asks for open rows newest-first; this is that order.
CREATE INDEX IF NOT EXISTS memstara_questions_status_idx
    ON memstara_questions (status, question_id DESC);

-- CREATE TABLE IF NOT EXISTS does nothing to a table that already exists, so a column
-- added later has to be stated separately. Two tables and one column do not justify a
-- migration tool; this line is correct both for a fresh database and an existing one.
ALTER TABLE memstara_blackboard ADD COLUMN IF NOT EXISTS y_column TEXT NOT NULL DEFAULT '';
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS y_column TEXT NOT NULL DEFAULT '';

-- The evidence columns, added for the same reason and in the same way. Without these
-- lines the CREATE TABLE above is silently a no-op on any database that already exists,
-- which is every database this code has ever run against — the fix would appear to be
-- applied and change nothing.
ALTER TABLE memstara_blackboard ADD COLUMN IF NOT EXISTS match_trace JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS okf_concept_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS match_trace JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS feature_importance JSONB NOT NULL DEFAULT '{{}}'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS columns JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS columns_missing JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Which bank question seeded this row. A plain INTEGER and deliberately not a foreign
-- key: memstara_questions outlives the board and the results table, and a foreign key
-- would point from the short-lived tables at the long-lived one, so dropping the bank
-- would require dropping them first. The link is nice to have, not load-bearing —
-- `perspective` already carries the question text on both tables, so a row still says
-- what it was asked even if the bank is gone.
ALTER TABLE memstara_blackboard ADD COLUMN IF NOT EXISTS question_id INTEGER;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS question_id INTEGER;

-- Who is holding a claimed row, added the same way and for the same reason. Every
-- database this code has ever run against already has memstara_blackboard, so without
-- this line the column exists only on a database nobody has — the ownership check would
-- read a column that is not there and the fix would look applied while changing nothing.
ALTER TABLE memstara_blackboard ADD COLUMN IF NOT EXISTS claimed_by TEXT NOT NULL DEFAULT '';

-- The question bank's own claim, added the same way. The bank is the oldest table here
-- and the one most certain to already exist, so of every ALTER in this block these are
-- the three least safe to leave out.
ALTER TABLE memstara_questions ADD COLUMN IF NOT EXISTS claimed_run TEXT NOT NULL DEFAULT '';
ALTER TABLE memstara_questions ADD COLUMN IF NOT EXISTS claimed_by  TEXT NOT NULL DEFAULT '';
ALTER TABLE memstara_questions ADD COLUMN IF NOT EXISTS claimed_at  TIMESTAMPTZ;

-- Same reason as the ADD COLUMN above: an existing table keeps whatever constraint it
-- was created with, so the change has to be stated for databases made before it.
-- The order: drop NOT NULL -> remove the old foreign key -> attach the SET NULL one.
ALTER TABLE memstara_results ALTER COLUMN task_id DROP NOT NULL;
ALTER TABLE memstara_results DROP CONSTRAINT IF EXISTS memstara_results_task_id_fkey;
ALTER TABLE memstara_results ADD CONSTRAINT memstara_results_task_id_fkey
    FOREIGN KEY (task_id) REFERENCES memstara_blackboard (task_id) ON DELETE SET NULL;
"""

#: The table names this file is responsible for. --drop shows this list when it asks.
#: `memstara_questions` is deliberately absent — `--drop` does not delete that table, so
#: listing it here would make the prompt say "dropping these" and then not (see
#: drop_questions).
TABLES = ("memstara_blackboard", "memstara_results")


#: The address used when nothing has been configured. It points at the container the
#: docker-compose.yml beside this file brings up. Port 5463 was chosen so as not to
#: collide with core's Postgres (5432 and the like).
MEMSTARA_DATABASE_URL_DEFAULT = "postgresql://memstara:memstara@localhost:5463/memstara"


def dsn() -> str:
    """Postgres address for Memstara's own database.

    Deliberately **not** ``MOTORO_DATABASE_URL``. Reading core's variable is how the
    board ended up inside core's database in the first place: the address was there, it
    worked, and nothing ever forced the question of whose store this is.

    The default points at the container in ``docker-compose.yml``, so a fresh checkout
    runs after ``docker compose up -d`` with nothing else set. Override with
    ``MEMSTARA_DATABASE_URL`` to point somewhere else.

    SQLAlchemy's ``postgresql+asyncpg://`` form is accepted and reduced, because the
    value often gets copied from a core-style .env and asyncpg rejects the ``+driver``.
    """
    url = os.environ.get("MEMSTARA_DATABASE_URL", "").strip() or MEMSTARA_DATABASE_URL_DEFAULT
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


class BoardBusy(RuntimeError):
    """Raised when another driver already holds this run_tag.

    Not a program error but a notice that says "not right now".
    """


@contextlib.asynccontextmanager
async def run_lock(run_tag: str) -> AsyncIterator[None]:
    """Hold an exclusive claim on *run_tag* for as long as this block runs.

    Only one driver may work a given run_tag at a time. The board itself is safe
    under concurrency — `claim_task` uses FOR UPDATE SKIP LOCKED, so two claimers
    never take the same row — but the *driver* is not. It decides "nothing is
    waiting for me, so anything still in_progress must be abandoned" and returns
    those tasks to the queue. That inference is only sound if it is the only driver.
    With two, one sees an empty queue merely because the other took the work, and
    then reclaims tasks that are actively being worked on.

    This happened, on 2026-08-17: a run believed dead was still alive, and a second
    was started 39 seconds later against the same tag. Nothing broke — the row-level
    locking held — but four interpretation agents and two reporting agents ran, and
    the numbers were unusable.

    A Postgres advisory lock rather than a pid file, because it is tied to the
    connection: kill the process and the lock is gone with it. A pid file left by a
    killed process blocks every later run until someone deletes it by hand.

    Raises:
        BoardBusy: another driver holds this run_tag. It is raised immediately rather
            than waited on.
    """
    # crc32 gives a stable 32-bit key from the tag. hashtext() would also work but is
    # an internal function with no compatibility promise across versions.
    # An advisory lock is taken on a **number**, not on a name.
    key = zlib.crc32(run_tag.encode("utf-8"))
    # A connection dedicated to this lock. The lock is tied to the connection, so the
    # moment the block ends — or the process dies and the connection closes — the lock
    # is released with it.
    conn = await asyncpg.connect(dsn())
    try:
        # The try_ form, so it does not wait. If somebody already holds it, false at once.
        if not await conn.fetchval("SELECT pg_try_advisory_lock($1)", key):
            raise BoardBusy(
                f"run_tag '{run_tag}' is already being worked by another process.\n"
                "  Two drivers on one tag reclaim each other's tasks — see run_lock().\n"
                "  Use a different --run-tag, or wait for the other run to finish."
            )
        try:
            # This is where the work inside the `with` block happens. The lock is held
            # throughout.
            yield
        finally:
            # Whatever happens inside, the lock is released.
            await conn.execute("SELECT pg_advisory_unlock($1)", key)
    finally:
        # The connection is always closed too. Even if it were not, losing the
        # connection releases the lock anyway.
        await conn.close()


async def create() -> None:
    """Create the tables. Nothing happens if they already exist (safe to run repeatedly)."""
    conn = await asyncpg.connect(dsn())
    try:
        await conn.execute(SCHEMA)   # run the whole SCHEMA above
    finally:
        await conn.close()


async def drop() -> None:
    """Drop the two tables. The data goes with them.

    `memstara_questions` is **not dropped here.** The question bank accumulates across
    runs, so if it vanished whenever the board was cleaned, "what has this project
    already asked" would be lost every time. Emptying the bank takes a separate
    `--drop-questions`.
    """
    conn = await asyncpg.connect(dsn())
    try:
        # results first — it references the board, so the referring side has to be
        # cleared away first for the order to be right.
        await conn.execute("DROP TABLE IF EXISTS memstara_results, memstara_blackboard CASCADE;")
    finally:
        await conn.close()


async def drop_questions() -> None:
    """Drop the question bank. Why it is kept apart from `drop()` is in that docstring."""
    conn = await asyncpg.connect(dsn())
    try:
        await conn.execute("DROP TABLE IF EXISTS memstara_questions CASCADE;")
    finally:
        await conn.close()


async def show() -> None:
    """Print what is in the database now and what state the board is in.

    Our tables and core's are shown apart. In practice the servers are entirely
    separate, so seeing no core tables is the normal outcome — they are still shown
    apart so that looking at an old-style mixed database is obvious at a glance.
    """
    conn = await asyncpg.connect(dsn())
    try:
        # pg_tables is the "list of tables" table PostgreSQL keeps for itself.
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        names = [r["tablename"] for r in rows]
        ours = [n for n in names if n.startswith("memstara_")]
        theirs = [n for n in names if not n.startswith("memstara_")]

        print(f"our tables: {len(ours)}")
        for n in ours:
            # A table name cannot be passed as a bound value, so it is joined into the
            # string. It is safe because the name came out of the list above and no
            # outside input can find its way in (the noqa comment tells the checker so).
            count = await conn.fetchval(f"SELECT count(*) FROM {n}")  # noqa: S608 - fixed names
            print(f"   {n:24} {count} rows")
        print(f"\ncore tables: {len(theirs)} — left alone")
        for n in theirs:
            print(f"   {n}")

        # If the board exists, count how many rows there are per stage x status. It is
        # for seeing at a glance how far a run got and where it is stuck.
        if "memstara_blackboard" in ours:
            by = await conn.fetch(
                "SELECT task_type, status, count(*) AS n FROM memstara_blackboard "
                "GROUP BY task_type, status ORDER BY task_type, status"
            )
            if by:
                print("\nstate of the board")
                for r in by:
                    print(f"   {r['task_type']:10} {r['status']:12} {r['n']}")
    finally:
        await conn.close()


async def orphans() -> int:
    """Count the tasks a finished run left on the board, per tag. Read-only.

    A run that is killed, or that dies before its board drains, leaves rows behind.
    Nothing removes them: the driver's `reclaim_stalled` only looks at its own run_tag
    and only runs inside the work loop, so a fresh run with a fresh tag never sees them.
    Until `claim_task` was scoped by run_tag those leftovers were also the *first* thing
    the next run would claim.

    Returns:
        How many leftover tasks there are, so the caller can use it as an exit code.
    """
    conn = await asyncpg.connect(dsn())
    try:
        # `ready` and `in_progress` only. `done` is finished and `failed` is **already
        # closed**, so nobody is waiting on either. Counting `failed` here would leave
        # the list non-empty even after --close cleared it, which would make "the board
        # is clean" impossible to confirm with this command.
        rows = await conn.fetch(
            "SELECT run_tag, task_type, status, count(*) AS n, "
            "       max(updated_at) AS last "
            "  FROM memstara_blackboard WHERE status IN ('ready', 'in_progress') "
            " GROUP BY run_tag, task_type, status "
            " ORDER BY run_tag, task_type, status"
        )
    finally:
        await conn.close()

    if not rows:
        print("no tasks left over — the board is clean")
        return 0
    total = sum(r["n"] for r in rows)
    print(f"unfinished tasks: {total}")
    for r in rows:
        print(f"   {r['run_tag']:<22} {r['task_type']:<10} {r['status']:<12} "
              f"{r['n']:>3}   last {r['last']:%Y-%m-%d %H:%M}")
    print("\n   put them back in the queue with --reclaim TAG, or close them with --close TAG")
    return total


async def reclaim(run_tag: str) -> int:
    """Return every `in_progress` task of one tag to `ready`.

    The same UPDATE as `reclaim_stalled` in `src/memstara/pipeline/board.py`, but **with no time
    condition.** There it waits stale_after seconds so as not to snatch a task somebody
    is working on right now; here a person is calling it knowing "that run is over", so
    there is no reason to wait.

    Args:
        run_tag: tag of the run to return. No other tag is touched.

    Returns:
        How many were returned.
    """
    conn = await asyncpg.connect(dsn())
    try:
        return await conn.fetchval(
            """
            WITH returned AS (
                UPDATE memstara_blackboard
                   -- claimed_by is cleared with claimed_at. Not for the next claimer's
                   -- sake — claim_task overwrites the name anyway — but because a row
                   -- reading 'ready' while still naming a holder says two contradictory
                   -- things at once to whoever reads the board next.
                   SET status = 'ready', claimed_at = NULL, claimed_by = '',
                       updated_at = now()
                 WHERE run_tag = $1 AND status = 'in_progress'
             RETURNING 1
            ) SELECT count(*) FROM returned
            """,
            run_tag,
        )
    finally:
        await conn.close()


async def release_questions(run_tag: str) -> int:
    """Give back every bank question one run is holding. **The bank itself is untouched.**

    The counterpart to `claim_question` in `src/memstara/mcp_servers/blackboard.py`, and the
    reason a question claim is safe to make at all. `memstara_questions` has no run_tag
    (`src/memstara/blackboard.py:292-295`) — the bank spans runs so the project can answer
    "what have we already asked". A claim left behind would therefore not expire with the
    run that made it; it would take that question out of circulation for every run after,
    and the bank would look exhausted while being full.

    So a claim is meant to be short. It exists to keep two hypothesis workers of **one
    wave** off one question, and the driver calls this the moment that wave has finished
    seeding — long before the wave's tasks are done, because by then the question's job is
    over and the work it produced is on the board under its own question_id.

    This is the normal ending. The other one is in `claim_question`, which treats a claim
    older than the staleness window as free; that is what recovers a run that died between
    claiming and this call, and it is the only thing that does.

    Not an MCP tool, deliberately. An agent claims; releasing is the driver's business,
    the same split `reclaim` above already keeps. Adding it to the tool server would give
    a model a way to hand somebody else's question back mid-wave.

    Args:
        run_tag: which run's claims to give back. No other run's are touched.

    Returns:
        How many were released.
    """
    conn = await asyncpg.connect(dsn())
    try:
        return await conn.fetchval(
            """
            WITH freed AS (
                UPDATE memstara_questions
                   -- All three, together. A row naming a holder with no claimed_at could
                   -- never go stale, so it would be the one kind of leak the staleness
                   -- rule cannot clean up afterwards.
                   SET claimed_run = '', claimed_by = '', claimed_at = NULL
                 WHERE claimed_run = $1
             RETURNING 1
            ) SELECT count(*) FROM freed
            """,
            run_tag,
        )
    finally:
        await conn.close()


async def close_run(run_tag: str) -> int:
    """Close the unfinished tasks of one tag as `failed`. **They are not deleted.**

    The row stays so that "why is there no result for trial 3" is answerable later. A
    DELETE would make the board look clean and the results look complete, which is the
    same lie by omission the run report is built to avoid.

    `claimed_by` is **not** cleared here, unlike in `reclaim` above. The asymmetry is
    deliberate: a reclaimed row goes back into the queue and must name nobody, while a
    closed row is a record of work that did not finish, and who was holding it when the
    run was closed is part of that record.

    Args:
        run_tag: tag of the run to close. No other tag is touched.

    Returns:
        How many were closed.
    """
    conn = await asyncpg.connect(dsn())
    try:
        return await conn.fetchval(
            """
            WITH closed AS (
                UPDATE memstara_blackboard
                   SET status = 'failed',
                       error  = CASE WHEN error = '' THEN 'closed by blackboard.py --close'
                                     ELSE error END,
                       updated_at = now()
                 -- What is already failed is not counted again. Called twice it would
                 -- say "closed 2" while nothing was newly closed, and that is a false
                 -- report.
                 WHERE run_tag = $1 AND status IN ('ready', 'in_progress')
             RETURNING 1
            ) SELECT count(*) FROM closed
            """,
            run_tag,
        )
    finally:
        await conn.close()


def main() -> int:
    """The entry point when called from the command line. Returning 0 means fine, 1 means cancelled."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # **Exactly one** of these has to be chosen. Choosing none is not allowed either.
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true", help="create the tables (idempotent)")
    g.add_argument("--drop", action="store_true", help="drop them — asks first")
    g.add_argument("--show", action="store_true", help="what exists and what is on the board")
    g.add_argument("--drop-questions", action="store_true",
                   help="empty the question bank — separate from --drop on purpose")
    # The three below handle **one run's worth only**, not the whole board. Unlike the
    # --drop family they do not touch rows belonging to another tag.
    g.add_argument("--orphans", action="store_true",
                   help="list tasks left unfinished by runs that ended, per run_tag")
    g.add_argument("--reclaim", metavar="TAG",
                   help="put that run's in_progress tasks back in the queue")
    g.add_argument("--close", metavar="TAG",
                   help="mark that run's unfinished tasks failed — the rows stay")
    ap.add_argument("--yes", action="store_true", help="skip the question on --drop")
    args = ap.parse_args()

    if args.create:
        # Show the state right after creating — so it can be seen by eye that it worked.
        asyncio.run(create())
        print("created (or already there)")
        asyncio.run(show())
    elif args.drop:
        # Dropping cannot be undone, so by default it asks once. With --yes it does not
        # ask (that is for calling from a script). "yes" has to be typed **exactly**.
        if not args.yes:
            print(f"these tables will be dropped: {', '.join(TABLES)}")
            if input("really drop them? (yes) ").strip() != "yes":
                print("cancelled")
                return 1
        asyncio.run(drop())
        print("dropped")
    elif args.drop_questions:
        # The bank accumulates across runs, so more is lost here than with --drop. It
        # asks the same way.
        if not args.yes:
            print("the whole question bank (memstara_questions) will be dropped.")
            if input("really drop it? (yes) ").strip() != "yes":
                print("cancelled")
                return 1
        asyncio.run(drop_questions())
        print("dropped questions")
    elif args.orphans:
        # It only reads, so it does not ask.
        asyncio.run(orphans())
    elif args.reclaim:
        # Returning is an undoable act (someone can just pick them up again), so it does
        # not ask.
        n = asyncio.run(reclaim(args.reclaim))
        print(f"returned {n} tasks of '{args.reclaim}' to the queue")
    elif args.close:
        # Closing makes that run finished. The rows stay but are never processed again,
        # so it asks once, the same way --drop does.
        if not args.yes:
            print(f"every unfinished task of '{args.close}' will be closed as failed (the rows stay).")
            if input("really close them? (yes) ").strip() != "yes":
                print("cancelled")
                return 1
        n = asyncio.run(close_run(args.close))
        print(f"closed {n} tasks of '{args.close}' as failed")
    else:
        asyncio.run(show())
    return 0


if __name__ == "__main__":
    # The returned value is used as the exit code as it stands. A cancel ends with 1.
    raise SystemExit(main())
