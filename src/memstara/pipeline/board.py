#!/usr/bin/env python3
"""The same four stages, driven by a shared board instead of a supervisor.

In `src/memstara/pipeline/mvp.py` a Python function calls the stages in order and carries each
output to the next by variable. Here nobody carries anything: the hypothesis stage puts
work on a board, and the other stages take work off it. Each task says which stage
should pick it up next, so an agent only has to know its own type.

**That file is untouched.** Both paths exist so they can be compared — a board that
produces different answers than the supervisor did would be worth knowing about, and
only one of them can be the reason.

Why a driving script rather than agents that watch the board: core runs an agent once
and returns. There is no pattern that keeps one alive waiting for work, so something
has to look at the board and call whoever is needed. That something is deterministic
and cheap, which is what the 2026-08-12 alignment concluded ("this doesn't have to be
an agent, it could be just a deterministic script").

A task whose agent dies goes back to waiting and is retried. Retries used to be
unlimited, which meant a task that always failed kept the board from draining and the
report never ran — the only thing that could end such a run was a person watching the
console. `--max-attempts` (default 5) now closes a task that keeps coming back, marks
it failed, and lets the rest of the run finish; the trial it belonged to is reported as
lost rather than quietly dropped. `--max-attempts 0` restores the old behaviour. The
retry count is still printed every round, because the cap ends a stuck run without
explaining it. `--report-only` writes the report from whatever has accumulated, for
when a run is interrupted.

Setup is the same as 02, plus the board::

    python -m memstara.blackboard --create

Run::

    python -m memstara.pipeline.board --trials 3
    python -m memstara.pipeline.board --report-only --run-tag <tag>


==============================================================================
 How to read this file
==============================================================================

 - Think of it as one laboratory

 There are five people, and one board on the wall.

   hypothesis    reads the papers and proposes "these variables look like the answer"
   data          cuts just those variables out of the original
   ml            runs a model on what was cut and produces a score
   interpreter   puts the score that came out into words
   reporter      gathers it all and writes it up on one page

 **Nobody hands anything to the next person directly.** Work is pinned to the board and
 the next person takes it down themselves. Each sheet says "whose turn is next", so each
 person only has to know their own type.

 There are three reasons it was built that way.
   · what each person did **stays on paper**
   · if one of them dies the sheet is still on the board — restart and it carries on
   · adding more people later is easy


 - What happens when this file is started

   (1) call the five people          provision_board_agents()
       fetch the role description that says what kind of work each of them does.
       If it is the first time, write it fresh.

   (2) switch on the four machines   setup_tools()
       people cannot work bare-handed. The paper store, the data machine, the learning
       machine, the board window — these four go on.

   (3) decide who gets which button  tools_for()
       the hypothesis person is **not given** the "cut it out" button. Give it to them
       and they will do the whole thing themselves, and then whose judgement produced
       the result can no longer be told.

   (4) pin the first instruction to the board     (seeding)
       call the hypothesis person and say "think about it from this perspective and pin
       it to the board". Repeat once per trial.

   (5) run until the board is empty               (the work loop)
       look at the board -> if there is somebody to do it, call them -> if not, wait a
       moment. Repeat until the board is empty.

   (6) wrap up at the end                          (the report)
       the reporter gathers what finished and writes it on one page.

 Run with `--report-only` and it skips (4) and (5) and does **only (6)**. It is
 gathering the results of a run that already finished, so it calls only one person —
 which is why it is cheap.

 `--waves` is **a ceiling, not a target.** The knowledge source is finite, so the
 questions dry up eventually, and at that point the program starts recycling questions
 out of the bank. If no new question comes out for `--stop-after-dry` rounds in a row
 (default 2) it does not start the remaining waves; it stops right there and says so.
 `--stop-after-dry 0` never stops. While this was absent, a dried-out run was
 indistinguishable on screen from a run making progress — both just kept going.

 **Carrying on without a person.** This program has no daemon and no cron. An infinite
 loop is not the answer for a finite knowledge source, and if you want to run it several
 times a shell loop is safer (state stays in the DB even if it dies mid-way). What this
 file and the window do instead is keep three things so that **the place one run left
 off passes cleanly to the next**:

   · `run_tag` is sent along with `claim_task` — a task another run left behind is never
     picked up. Without it the oldest is picked first, so a dead run's tasks catch
     **first of all**.
   · at startup it reclaims its own tag's stalled tasks once — running again with the
     same `--run-tag` becomes "carry on".
   · `--max-attempts` closes a task that never comes right — it ends with nobody watching.

 Clearing up somebody else's orphans that are already there is what
 `blackboard.py --orphans / --reclaim / --close` does. This file looks only at its own run.


 - One thing that is easy to miss

 **Five programs are running.** This file is one, and the four machines switched on in
 (2) are each a separate program. So attaching a debugger to this file will not stop
 inside `tools_*.py` — those are somebody else's program.

 There are two ways to stop in there:
   · `python -m memstara.debug_harness data`  — pull the machine into this program and use it here
   · turn on `MEMSTARA_DEBUGPY=data` and attach a debugger to that machine separately




 - Code structure

   main()             reads the arguments, checks the environment, takes the lock,
                      calls run()
     └ run()          holds (1) through (6) above, in that order
"""

from __future__ import annotations

# ---- standard library -------------------------------------------------------
import argparse   # command-line arguments (things like --trials 3)
import asyncio    # async execution. Most functions in this file are async
import csv        # used to read only the dataset's first line (the column names)
import json       # the JSON strings the tools return, turned into Python values
import os         # reading environment variables
import re         # used for exactly one password-masking regex
import sys        # sys.executable (the path of this Python) and stderr output
import time       # used only to measure how long each stage took
import uuid       # turns the run_id string back into a UUID when writing trace files
from datetime import datetime
from pathlib import Path
from typing import Any

# ---- outside packages -------------------------------------------------------
import asyncpg    # PostgreSQL async driver. Used only to query the board directly

# ---- the rest of the package -------------------------------------------------
# LITELLM_LOG has to be set before litellm is imported, and `memstara.pipeline.core`
# below drags litellm in. There used to be a bare `import` of the env module here to force
# that order. It is gone: reaching this module at all runs `memstara/__init__.py`
# first, and that is where the variable is now set. See its docstring.
from memstara.env import load_env

# memstara/blackboard.py — the board table's definition and connection details
from memstara.blackboard import BoardBusy, dsn, release_questions, run_lock
# memstara/logging_setup.py — makes a directory per run and also keeps the log in a file
from memstara.logging_setup import drain_llm_requests, new_run_dir, setup_logging, tee_console
# memstara/pipeline/core.py — the part the two pipelines (mvp, board) share
from memstara.pipeline.core import (
    BOARD_AGENT_NAMES,       # stage -> the durable agent's name in motoro's database
    BOARD_SERVERS,           # the tool servers each stage is allowed to reach
    BOARD_TOOLS,             # the individual tool names each stage is allowed
    QUESTION_SERVERS,        # ...and the same two, for the hypothesis agent's other job
    QUESTION_TOOLS,          # (writing the wave's questions). Not a stage — see core.py
    perspective_for,         # trial number -> perspective wording
    provision_board_agents,  # creates or fetches the five agents
    temperature_for,         # trial number -> temperature
    tools_for,               # picks out of the registry only the tools to be used
)
# memstara/pipeline/prompts.py — what each agent is told, and its fingerprint
from memstara.pipeline.prompts import prompt_digest
# memstara/mcp_servers/frontmatter.py — the same reader the okf server uses for --skill.
# Imported so a malformed skill is refused here, by the same code that will enforce it,
# rather than a second parser that could come to disagree with it.
from memstara.mcp_servers.frontmatter import parse_field_filter
from memstara.config import Settings   # the settings object that reads .env and hands it to core

# memstara/paths.py, memstara/servers.py — where things are, and how the five tool
# servers are launched. One copy each, for both pipelines and for preflight.
from memstara.paths import DEFAULT_OUTPUT_DIR
from memstara.servers import launch_table
# The function that writes one run out in a form a person can read. render is used
# rather than dump_all — dump_all presumes the todo_rows.json shape of the 02 path.
# See write_traces().
from memstara.trace.run import render

# ---- motoro (the repo next door, installed editable) ------------------
from motoro import configure
from motoro.mcp.registry import MCPServerRegistry
from motoro.runner import create_run, execute_run
from motoro.services.mcp_service import (
    get_server_by_name,
    hydrate_registry,
    register_server,
    update_server,
)

OUT_DIR = DEFAULT_OUTPUT_DIR

# The stages that take work off the board, in the order a task passes through them.
#
#
# There are five people but only three here. The two that are missing are missing for
# **different reasons.**
#
#   ┌ why the hypothesis person is missing
#   │   they do not take work off, they **put it on.** When the board is empty they
#   │   make the first sheet and pin it up. So there is no reason to ask them "is there
#   │   anything to take" — ask and the answer is always no.
#   │
#   │   the timing of the pinning is different too. The hypothesis person is called in
#   │   (4) below **a fixed number of times** (three trials, three calls). These three,
#   │   by contrast, are called in (5) only when needed, **after looking at the board.**
#   │
#   └ why the reporter is missing
#       they do not look at the board at all. They read the **finished drawer** (where
#       only the completed ones collect). Whether sheets are left on the board makes no
#       difference to them, which is why they are called exactly once, at the very end,
#       in (6) after the (5) loop finishes.
#
#   The order is not just a listing either. It is the order one sheet actually travels
#   in, and the loop in (5) sweeps **in this order every lap.** So with luck, in one lap
#   a single sheet can pass straight through data -> ml -> interpretation. Reverse the
#   order and that never happens; only the lap count goes up.
CLAIMING_STAGES = ("data", "ml", "interpreter")

# How long to wait when every remaining task is in progress and none is stale yet.
# Staring at the board without a pause keeps the computer busy for no gain.
POLL_SECONDS = 15

# **The person's name -> the name written on the sheet.**
#
#   Why such a table is needed — the two names are not always the same.
#
#       person's name      name on the sheet
#       data          ->   data          same
#       ml            ->   ml            same
#       interpreter   ->   interpret     **different**  <- the table exists for this one
#
#   Only the last one differs. But because of that one, looking up
#   `counts["interpreter/ready"]` always gives 0 and the interpreter is never called.
#   With no error at all. So it is nailed down in a table to leave no room for confusion.
#
#   There are only three here for the same reason as CLAIMING_STAGES above — the
#   hypothesis person and the reporter do not take sheets off the board, so there is
#   never anything to look up for them.
#
#   For reference, four names can appear on a sheet on the board (TASK_TYPES in
#   blackboard.py: hypothesis · data · ml · interpret). `hypothesis` is used only as a
#   sheet's **first state** and moves straight on to `data`.
STAGE_TASK_TYPE = {"data": "data", "ml": "ml", "interpreter": "interpret"}


# --------------------------------------------------------------------------- #
#  The things that show the stages on screen
# --------------------------------------------------------------------------- #
#
# Why they are needed — following along in a debugger, the screen fills with logs and
# finding by eye which stage it is in is hard. These make (1) through (6) of "How to
# read this file" at the top visible on the screen as well.
#
# They go out on stdout. That is fine because this is the parent process — what the MCP
# protocol travels over is the children's stdout.

_STEP_STARTED: dict[str, float] = {}


def step(number: str, title: str, detail: str = "") -> None:
    """Mark the start of a stage boldly.

    e.g.
        ══════════════════════════════════════════════════════════
         (2) switch on the four machines
        ══════════════════════════════════════════════════════════
    """
    print()
    print("=" * 74)
    print(f" {number} {title}" + (f"   —   {detail}" if detail else ""))
    print("=" * 74)
    _STEP_STARTED[number] = time.monotonic()


def done(number: str, result: str = "") -> None:
    """The result of the stage just finished and how long it took, on one line.

    Why the time is printed with it — where the time goes has to be visible. Usually the
    stage that calls the LLM takes longer than all the rest put together.
    """
    took = time.monotonic() - _STEP_STARTED.get(number, time.monotonic())
    print(f"   ✓ {result}" + f"   ({took:.1f}s)" if result else f"   ✓ ({took:.1f}s)")


def note(text: str) -> None:
    """Report progress within a stage on one line. The indent shows it belongs to the stage."""
    print(f"   · {text}")


def _redacted_dsn() -> str:
    """The board's address with the password removed, safe to print in an error."""
    # postgresql://user:password@host/db  ->  postgresql://user:***@host/db
    # The connection address has to appear in the error message, but the password
    # must not go with it.
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", dsn())


# The credentials each provider needs. Only the one chosen with `--provider` is checked.
#
# While this table was absent, empty credentials did not blow up **until the first LLM
# call.** By then one seeding had already been spent and a row was left on the board.
# Stopping before anything starts is better — the board stays clean, and what has to be
# filled in is known right there.
_PROVIDER_KEYS = {
    "azure_foundry": ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


async def check_environment(provider: str = "", y_column: str = "") -> list[str]:
    """Everything missing, reported at once, before anything starts.

    What is missing is collected **all together** rather than reported one at a time.
    Fix one, run again, find another one missing — that is what this removes.

    An empty list coming back means "ready".

    Args:
        provider: the value chosen with `--provider`. Only the credentials matching it
            are checked. An empty string skips the credential check.
        y_column: the outcome variable chosen with `--y-column`. Checks that the name
            really is in the dataset. An empty string skips it.
    """
    problems: list[str] = []   # if there is even one thing in here, it does not run

    # Two databases, and they are not interchangeable. core keeps its agents and run
    # history in MOTORO_DATABASE_URL; the board and the results table live in Memstara's
    # own server (MEMSTARA_DATABASE_URL, docker-compose.yml). Only the first is required
    # here — the second has a working default pointing at the compose container.
    #
    #   MOTORO_DATABASE_URL  : core's  — the people's role descriptions and run history (5453)
    #   MEMSTARA_DATABASE_URL : ours    — the board and the finished drawer              (5463)
    for name, hint in (
        ("AGENTIC_OKF_BUNDLE_DIR", "the knowledge source folder"),
        ("MEMSTARA_DATASET_PATH", "the dataset csv"),
        ("MEMSTARA_OUTPUT_DIR", "where sub-datasets go"),
        ("MOTORO_DATABASE_URL", "core's own database — agents and run history"),
    ):
        value = os.environ.get(name, "").strip()   # empty string if unset
        if not value:
            problems.append(f"{name} is not set — {hint}")

    # LLM credentials. Empty, and the first agent call dies with "Azure Anthropic
    # requests require an api_base" — after one seeding has already been spent. Caught
    # here, it stops without spending anything.
    #
    # These values live in `motoro/.env`. main() reads that file, so if they are
    # still empty by the time execution gets here, they really are not in it.
    for name in _PROVIDER_KEYS.get(provider, ()):
        if not os.environ.get(name, "").strip():
            problems.append(
                f"{name} is not set — needed for --provider {provider}. "
                "Check motoro/.env."
            )

    # Reachability, not just presence. An unreachable board fails later as an opaque
    # tool error inside an agent, which reads like a prompt problem — and then the wrong
    # place gets fixed.
    try:
        conn = await asyncpg.connect(dsn())
        await conn.close()
    except Exception as e:  # noqa: BLE001 - any failure to reach it is the same problem
        problems.append(
            f"Memstara's database is not reachable at {_redacted_dsn()} — {type(e).__name__}. "
            "Start it with `docker compose up -d` in this folder."
        )

    # The outcome column has to exist in the dataset, and nothing checked that until
    # now. A wrong `--y-column` was caught in src/memstara/mcp_servers/data.py, deep inside the data stage,
    # after every hypothesis agent had already been paid for — and the run still ended
    # "successfully" and wrote a report full of nulls. The default is `outcome`, which
    # is not a column in this cohort, so the default path always went that way.
    dataset = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    if y_column and dataset:
        try:
            # Only the header row is read. The file is large and the answer is on line 1.
            with open(dataset, newline="", encoding="utf-8") as fh:
                header = next(csv.reader(fh))
        except Exception as e:  # noqa: BLE001 - unreadable and absent are the same problem here
            problems.append(
                f"MEMSTARA_DATASET_PATH cannot be read at {dataset} — {type(e).__name__}."
            )
        else:
            if y_column not in header:
                # Near-misses only, never the whole column list. src/memstara/mcp_servers/data.py hides the
                # outcome column from its error for a reason (an agent that learns the
                # name can use it as a feature); a console message is safer but the same
                # restraint keeps 1,393 names out of the terminal.
                near = [c for c in header if y_column.upper() in c.upper()][:5]
                hint = f" Did you mean: {', '.join(near)}?" if near else ""
                problems.append(
                    f"--y-column '{y_column}' is not a column in the dataset."
                    f"{hint} ({len(header)} columns in {Path(dataset).name})"
                )

    return problems


async def setup_tools() -> MCPServerRegistry:
    """Connect the five tool servers, including the board.

    This is where there come to be six programs. Each of the five lines below starts a
    separate program. They talk to each other by passing characters — not down anything
    like a phone line, just one side writing and the other reading.

    **Which is why attaching a debugger to this file will not stop inside them.** They
    are somebody else's program.
    """
    # Turns off the warning each child emits when running under a debugger:
    #
    #     Debugger warning: It seems that frozen modules are being used ...
    #
    # **It has to be set here.** debugpy checks the moment the child Python starts, so
    # turning it off inside the child's code is already too late. The parent has to put
    # it in beforehand, and it has to be on the allowlist in `src/memstara/config.py` to reach the
    # child at all.
    #
    # The warning itself is about the **inside** of the standard library and has nothing
    # to do with our code.
    os.environ.setdefault("PYDEVD_DISABLE_FILE_VALIDATION", "1")

    registry = MCPServerRegistry()   # the vessel holding the connected servers and their tools

    # The same five 02 starts, from the same table — memstara/servers.py. That the two
    # pipelines start an identical set is not a coincidence to be maintained by hand:
    # if 03's matcher went missing, its hypothesis agent would pick column names by eye
    # off `describe_dataset`, the two pipelines would choose columns by different means,
    # and their AUCs would stop being comparable without anything failing.
    #
    # `Server.command()` builds each command from `sys.executable` — the very Python
    # running this file — so the five machines come up in the same environment as
    # whatever started them.
    for name, command in launch_table():
        existing = await get_server_by_name(name)   # already registered in core's DB?
        if existing is None:
            # A server never seen before — register it
            await register_server(name=name, transport="stdio", command=command, registry=registry)
        elif existing.command != command:
            # Already registered, but **the command that starts it has changed** (the
            # Python path moved, say). It gets updated. This one line is why changing
            # environments is followed automatically.
            await update_server(existing.id, command=command, registry=registry)

    # Actually connect to the registered servers and fetch their tool lists.
    failed = await hydrate_registry(registry=registry)
    if failed:
        # Say so if even one would not attach. It does not stop here — going as far as
        # the rest allow is better for finding out what is broken.
        print(f"!! MCP reconnect failed: {failed}", file=sys.stderr)
    return registry


# Collects the agents called in this run, in the order they were called.
#
# Why a list and why not per trial — on the 02 path one trial passes through the four
# stages in turn, so it groups by `TodoRow.run_ids[stage]` (src/memstara/pipeline/core.py:184). The
# board path is different. **Which task a single `call_agent(data, ...)` picks up is
# decided by the board at that moment.** So it cannot be grouped by trial, and keeping
# the order they were called in is what matches the facts.
#
# The run_ids collected here are what the trace files are written from at the end of the
# run. Those files hold exactly what the agent asked each tool and what came back — which
# a debugger cannot show. Without collecting them, the records stay in core's DB but
# **which run was which stage cannot be told.**
_CALLS: list[dict[str, Any]] = []


async def call_agent(
    agent_id,
    prompt: str,
    *,
    tools,
    registry,
    temperature: float | None = None,
    stage: str = "",
) -> tuple[str, dict[str, Any]]:
    """Run one agent once and return its text, or "" if the run did not complete.

    Call one person, set them to work, and take back what they said.

    **This is the only place in this file that calls a model.** It is the only place
    that costs money and time. Everything else is looking at the board or writing files,
    which is free.

    Args:
        stage: the label used in the trace file's name ("hypothesis" · "data" ·
            "report" …). Left empty, only the sequence number is used.

    Returns:
        ``(text, entry)``. `entry` is this call's own row in `_CALLS`, handed back rather
        than looked up. A caller that wants the record of the call it just made used to
        read `_CALLS[-1]`, which is only the right row while exactly one call is in
        flight — with two, the other one's append moves it. Returning it removes the
        assumption instead of documenting it.
    """
    # Overridden only if a temperature was given. None uses the agent's own default.
    overrides = {"temperature": temperature} if temperature is not None else None

    # core creates a "run" first and executes it afterwards. Being split in two is what
    # leaves the record in the DB, so it can be retraced later with src/memstara/trace/run.py.
    run = await create_run(agent_id=agent_id, user_input=prompt, model_config_overrides=overrides)

    # Written down **before** executing. The run_id has to survive even if it dies
    # mid-execution — a run that died is exactly the one worth retracing.
    #
    # Bound to a local, and every line below writes through that local rather than
    # through `_CALLS[-1]`. The two are the same row only while this is the only call in
    # flight. The moment a second call runs alongside, its append moves the end of the
    # list, and this call's status, error and trace file all land on the other one's row
    # — a mis-labelled trace being the worst of the three, because it looks like evidence.
    entry: dict[str, Any] = {
        "seq": len(_CALLS),
        "stage": stage or "?",
        "run_id": str(run.id),
        "prompt": prompt,
        "status": "started",
    }
    _CALLS.append(entry)

    # ── this is where the LLM runs ─────────────────────────────────────────
    # `execute_run` is a function of motoro. Inside, it repeats reason -> act
    # (calling a tool) -> observe. **We do not go inside it** — `justMyCode: true` in
    # launch.json steps F11 over it here. What we see is only the result.
    #
    # What happened inside is what _trace_one() below pulls out into a file.
    result = await execute_run(run_id=run.id, registry=registry, available_tools=tools)
    entry["status"] = getattr(result.status, "value", str(result.status))
    if result.error:
        entry["error"] = str(result.error)

    # The trace file for **this one call** is written the moment the run finishes.
    #
    # Why write it here — writing them all at the end is useless while debugging,
    # because the file does not exist until the whole run is over. Written here, the
    # instant you stop at a breakpoint on the line after `await call_agent(...)` you can
    # open `trace/00_hypothesis0.txt` and read what just happened — which tool was
    # called with which arguments and what came back.
    await _trace_one(entry)

    # Spell out on screen what that person actually did. The untruncated version is in
    # the file under trace/.
    #
    # Everything this prints happens after its two awaits above, with no await in
    # between, so one call's block reaches the screen in a single slice. Two calls
    # running together interleave block by block, never line by line.
    await show_what_agent_did(entry)

    # An empty string on failure. The caller usually re-reads the result off the board,
    # so rather than throwing here it quietly empties out and leaves it to the next lap.
    if result.error or result.status != "completed":
        return "", entry

    # Agent output is usually JSON shaped like {"result": "..."}. Failing that, the raw text.
    try:
        return str(json.loads(result.output or "").get("result", "")), entry
    except (json.JSONDecodeError, TypeError, AttributeError):
        return result.output or "", entry


# The folder the trace files go to. run() sets it when it starts.
#
# Why it is global — `call_agent` does not know the run directory. Passed as an
# argument, all four call sites would have to carry it around, and that is baggage
# unrelated to what this file is trying to do.
_TRACE_DIR: Path | None = None


def _short(value: Any, width: int = 88) -> str:
    """Shorten one value to a single line. Line breaks are laid flat into spaces."""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= width else s[:width] + " …"


async def show_what_agent_did(call: dict[str, Any]) -> None:
    """Spell out on screen **what the person just called actually did.**

    Why this is needed — if the screen says only "called the reporter", which tool that
    person called with which values and what they got back is invisible. All of it
    happens inside core, and a debugger does not show it either (core was left as a
    black box on purpose).

    It reads what core left in `run_steps` and shortens it into something readable. The
    **untruncated version** of the same content is written separately to
    `trace/NN_stage.txt` — this one is for skimming.

    One person's turn looks like this:

        sense    the instruction received
        reason   thinking —— "here is what I will do"
        act      acting —— call a tool, or give the final answer
        reason   thinking again (having seen the tool's result)
        act      ...
    """
    from motoro.runner import get_run, get_run_steps

    try:
        rid = uuid.UUID(call["run_id"])
        run = await get_run(rid)
        steps = await get_run_steps(rid)
    except Exception as e:  # noqa: BLE001 - showing it must not block the run
        note(f"(could not read what it did: {type(e).__name__})")
        return

    tokens = (getattr(run, "token_usage", None) or {}) if run else {}
    cost = float(getattr(run, "cost_estimate", 0) or 0) if run else 0.0
    print(f"   ┌─ what {call['stage']} did "
          f"({len(steps)} steps · tokens {tokens.get('prompt_tokens', 0)}/"
          f"{tokens.get('completion_tokens', 0)} · ${cost:.4f})")

    for s in steps:
        phase = getattr(s.phase, "value", str(s.phase))
        # The field is called `output`. The DB column is `output_data` but the Python
        # side exposes it as `output` — go by the column name and it is an AttributeError.
        out = s.output or {}

        if phase == "reason":
            # What it made up its mind to do.
            thought = out.get("thought") if isinstance(out, dict) else None
            if thought:
                print(f"   │  think   {_short(thought)}")

        elif phase == "act":
            # If a tool was actually called, show its arguments and result. This is the
            # important part.
            tc = s.tool_call
            for one in _flatten_calls(tc):
                server = one.get("server", "?")
                tool = one.get("tool", "?")
                args = one.get("arguments", {})
                result = one.get("result", "")
                print(f"   │  tool    {server}.{tool}({_short(args, 70)})")
                print(f"   │          → {_short(result, 86)}")
            # A turn that gave only a final answer, with no tool.
            if not _flatten_calls(tc) and isinstance(out, dict):
                for r in (out.get("results") or []):
                    if r.get("action") == "final_answer":
                        print(f"   │  answer  {_short(r.get('result', ''), 86)}")

    # For the requests sent to the model, **only the count and size** go on screen. One
    # request runs to tens of thousands of characters, and printing the raw text here
    # would make the screen unusable — the raw text is in the trace file.
    n_req = call.get("llm_requests", 0)
    if n_req:
        print(f"   │  req     {n_req} LLM calls — what was sent is in "
              f"trace/{call['seq']:02d}_{call['stage']}.llm.txt")
    print("   └─")


def _flatten_calls(tool_call: Any) -> list[dict[str, Any]]:
    """Flatten the **three shapes** `tool_call` can arrive in into one.

    core may call several tools in one turn, so the shape splits:

        None or JSON's null      no tool was called
        {"server":…, "tool":…}   one was called
        {"calls":[{…},{…}]}      several were called

    Fail to reconcile this and a turn that called them in a batch is invisible
    altogether, or, the other way, an empty one gets counted as a call.
    """
    if not tool_call or tool_call == "null":
        return []
    if isinstance(tool_call, str):
        try:
            tool_call = json.loads(tool_call)
        except json.JSONDecodeError:
            return []
    if not isinstance(tool_call, dict):
        return []
    if "calls" in tool_call:
        return [c for c in tool_call["calls"] if isinstance(c, dict)]
    return [tool_call] if tool_call.get("tool") else []


async def _trace_one(call: dict[str, Any]) -> None:
    """Write the trace file for one run. A failure here does not stop the pipeline.

    What goes in the file: status · tokens · cost · the thinking and acting of each step
    · **the arguments and results of the tool calls.** The last one is the point — it
    happens inside motoro, so a breakpoint cannot show it.
    """
    if _TRACE_DIR is None:
        return

    # **What has already been written is not written again.**
    #
    # The net at the end (write_traces) sweeps every call once more, and writing again
    # then creates the file afresh and **the LLM requests disappear** — requests are
    # drained as they are taken, so the second time there are 0 of them. That is how it
    # was actually lost and then found.
    if call.get("traced"):
        return

    stem = f"{call['seq']:02d}_{call['stage']}"
    path = _TRACE_DIR / f"{stem}.txt"
    llm_path = _TRACE_DIR / f"{stem}.llm.txt"
    try:
        with path.open("w", encoding="utf-8") as fh:
            # readable=True — it is printed for a person to read. Nothing is truncated.
            # The only thing left out is **what another line already said** (see the
            # explanation of memstara.trace.run.render).
            await render(call["stage"], uuid.UUID(call["run_id"]),
                         full=True, summary=False, stream=fh, readable=True)

        # The requests that were **sent to the model.** core does not store these, so
        # they are intercepted from litellm's log (see logging_setup). Draining empties
        # as it takes, so only what that agent called goes in — it does not get mixed up
        # with the next person's.
        #
        # **Why a file off to the side** — every call carries the whole conversation so
        # far all over again. Call it 6 times and the same content is stacked six deep
        # (261KB, measured). Appended to the trace file above, the body you actually
        # came to read would be buried underneath it.
        requests = drain_llm_requests()
        call["llm_requests"] = len(requests)
        if requests:
            with llm_path.open("w", encoding="utf-8") as lf:
                print("=" * 100, file=lf)
                print(f"{len(requests)} requests {call['stage']} sent to the model", file=lf)
                print("the later ones carry the earlier conversation again — "
                      "the last is the biggest.", file=lf)
                print("=" * 100, file=lf)
                for i, body in enumerate(requests, 1):
                    print(f"\n[{i}/{len(requests)}] " + "-" * 88, file=lf)
                    print(body, file=lf)
        call["traced"] = True
    except Exception as e:  # noqa: BLE001 - a failure to record must not wreck the run
        print(f"  trace failed {call['seq']:02d} {call['stage']}: {type(e).__name__}: {e}",
              file=sys.stderr)


async def write_traces(run_dir: Path) -> int:
    """The net that sweeps once more at the end. Returns how many were written.

    Normally `_trace_one` has already written each call as it happened, and what is
    already written is **skipped.** The reason this is kept is the **died halfway**
    case — if an exception is raised mid-run or Ctrl-C comes in, the last one may not
    have reached `_trace_one`.

    Without the skip, the file is written afresh and the LLM requests disappear (see
    the comment above).

    Why `memstara.trace.run.dump_all` is not used — that function assumes the per-trial
    `run_ids` shape of `todo_rows.json` (src/memstara/trace/run.py:162). The board path is not that
    shape, so `render()`, one layer below, is called directly.
    """
    if not _CALLS:
        return 0

    out_dir = run_dir / "trace"
    out_dir.mkdir(parents=True, exist_ok=True)

    # The list itself is left behind too. It is what src/memstara/trace/board.py, or a person
    # retracing by hand, reads later.
    (run_dir / "runs.json").write_text(
        json.dumps(_CALLS, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for call in _CALLS:
        await _trace_one(call)
    return len(_CALLS)


async def board_state(registry: MCPServerRegistry, run_tag: str) -> dict:
    """What is on the board right now, straight from the tool the agents use.

    The database is not searched directly; the board is read through **the same window
    the people use.** That way the board on my screen cannot drift out of step with the
    board they see.
    """
    server = await get_server_by_name("memstara-blackboard")
    from motoro.services.mcp_service import call_server_tool

    raw = await call_server_tool(server.id, "read_board", {"run_tag": run_tag}, registry=registry)
    # Sometimes the return is a (metadata, body) tuple, sometimes only the body.
    text = raw[1] if isinstance(raw, tuple) else raw
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # If it cannot be read, treat it as "the board is empty". The loop ends on this
        # value, which is better than spinning forever because a read failed.
        return {"count": 0, "tasks": []}


#: Matcher tools whose calls are worth keeping. Both live on the semantic-matcher
#: server; nothing else it exposes produces candidate lists.
_MATCHER_TOOLS = ("match_concepts", "match_concept")


def _matcher_call_failed(result: Any) -> bool:
    """Did this matcher call actually answer, or did it come back an error?

    This has to be asked before anything is filed as evidence. The 2026-08-30 run
    filed 27 calls into the results table whose every result was "Not authorized:
    Tool 'match_concepts' is not in this run's allowed tool set" — a dead server
    registration meant the matcher never ran, and the durable table recorded the
    refusals as if they were candidate lists. This is the check that stops that.
    """
    if isinstance(result, dict):
        return "error" in result
    if isinstance(result, str):
        # Core refuses a tool outside the run's allowed set with a plain sentence,
        # not JSON — so it survives the parse above untouched and has to be read here.
        text = result.strip()
        return text.startswith("Not authorized") or "is not in this run's allowed tool set" in text
    return False


async def harvest_match_trace(
    registry: MCPServerRegistry, call: dict[str, Any]
) -> tuple[int, int]:
    """Lift one agent run's matcher calls out of the trace and file them on the board.

    The matcher answers inside the hypothesis agent's turn and writes nothing down.
    Only the chosen columns reach the board, so the candidates that lost — and the
    scores that made them lose — existed nowhere except this run's trace, which is
    deleted whenever the run directory is. That is the gap this closes.

    Why the driver does it rather than the agent or the matcher: the agent would
    have to hand-copy hundreds of candidate rows with nothing checking the copy,
    and the matcher would need board access it is deliberately built without. The
    trace already holds every call verbatim, so nobody has to be trusted.

    Both halves come out of the same run. The matcher calls are the ones worth
    keeping; the ``create_task`` calls in the same turn say which task they belong
    to, because the agent matched and then filed in one continuous turn.

    **Only calls that answered are filed.** `match_trace` is a record of candidates
    the matcher actually returned, never a count of attempts — a refused call proves
    nothing about the cohort and must not sit in the results table looking like it
    does. Refusals are counted and reported instead, because silently dropping them
    would make "the matcher was never called" and "every call was refused" look
    identical, and those need entirely different fixes.

    Args:
        registry: the live server registry, used to reach the board tool.
        call: one entry of `_CALLS` — the run whose trace is read.

    Returns:
        `(annotated, refused)` — how many tasks were annotated, and how many matcher
        calls came back an error and were left out. `(0, 0)` is normal for a stage that
        never matched, and also what a failure returns: a missing trace must not stop
        the pipeline, since the pipeline's actual work already succeeded by the time
        this runs.
    """
    from motoro.runner import get_run_steps
    from motoro.services.mcp_service import call_server_tool

    try:
        steps = await get_run_steps(uuid.UUID(call["run_id"]))
    except Exception as e:  # noqa: BLE001 - bookkeeping must not fail the run
        note(f"(could not read the matcher record: {type(e).__name__})")
        return 0, 0

    matcher_calls: list[dict[str, Any]] = []
    task_ids: list[int] = []
    refused = 0                    # calls that came back an error and were left out

    for s in steps:
        for one in _flatten_calls(s.tool_call):
            tool = one.get("tool") or ""
            if tool in _MATCHER_TOOLS:
                # The result is a JSON string on the wire. Parse it so the board holds
                # a real object; a string of JSON inside JSONB is readable only by
                # parsing twice, and whoever reads it later will not know to.
                result = one.get("result") or ""
                try:
                    result = json.loads(result) if isinstance(result, str) else result
                except json.JSONDecodeError:
                    pass
                if _matcher_call_failed(result):
                    refused += 1
                    continue
                matcher_calls.append({
                    "tool": tool,
                    "arguments": one.get("arguments") or {},
                    "result": result,
                })
            elif tool == "create_task":
                # create_task answers {"task_id": N}. That is the only link between a
                # matcher call and the row it ended up justifying.
                try:
                    tid = json.loads(one.get("result") or "{}").get("task_id")
                except (json.JSONDecodeError, AttributeError):
                    tid = None
                if isinstance(tid, int):
                    task_ids.append(tid)

    if not matcher_calls or not task_ids:
        return 0, refused

    server = await get_server_by_name("memstara-blackboard")
    written = 0
    for tid in task_ids:
        try:
            await call_server_tool(
                server.id,
                "attach_match_trace",
                {"task_id": tid, "match_trace": json.dumps(matcher_calls, ensure_ascii=False)},
                registry=registry,
            )
            written += 1
        except Exception as e:  # noqa: BLE001 - same reason as above
            note(f"(could not attach the matcher record to task {tid}: {type(e).__name__})")
    return written, refused


async def call_board_tool(registry: MCPServerRegistry, tool: str, args: dict[str, Any]) -> Any:
    """Call one board tool from the driver rather than through an agent.

    Bookkeeping the pipeline knows about and no agent does — that a wave has ended, that
    a trace is ready to file — has to be written by whoever knows it. These tools are
    kept out of BOARD_TOOLS so no agent can reach them.
    """
    from motoro.services.mcp_service import call_server_tool

    server = await get_server_by_name("memstara-blackboard")
    raw = await call_server_tool(server.id, tool, args, registry=registry)
    # Sometimes the return is an (is-it-an-error, body) tuple, sometimes only the body —
    # read_board_via_tool already does the same thing in the same place.
    text = raw[1] if isinstance(raw, tuple) else raw
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


async def questions_for_wave(
    registry: MCPServerRegistry,
    agents: dict[str, Any],
    by_stage: dict[str, Any],
    *,
    run_tag: str,
    wave: int,
    want: int,
    skill: str = "",
) -> tuple[list[dict[str, Any]], bool]:
    """Ask for this wave's questions, then read back what was banked.

    The agent called here is the **hypothesis agent**, doing the other of its two jobs.
    It is handed `by_stage["question"]` rather than `by_stage["hypothesis"]`, and that
    difference is the whole separation: this call cannot reach `create_task`, so it
    cannot answer its own question, and the answering call cannot reach
    `propose_questions`, so it cannot write itself an easier one
    (`src/memstara/pipeline/core.py:448-466`).

    Read back rather than trust the return value: the agent answers in prose, and
    what matters is what actually landed in the bank. propose_questions is also the
    only thing that can reject a question, so its verdict is the one to read.

    Returns fewer than `want` without complaint. A wave that can only ground three
    questions in the corpus should propose three; padding to a target is exactly the
    habit that produced questions nothing could answer.

    Returns:
        ``(rows, recycled)``. `rows` is bank entries, newest first, at most `want`; an
        empty list means the caller should fall back to the built-in perspective list.
        `recycled` is True when the call produced nothing new and this wave is about
        to re-run questions the bank already had — the caller decides what that means.
        It is returned rather than only printed because the run is otherwise unable to
        tell "investigated something new" from "investigated the same thing again".
    """
    before = await call_board_tool(registry, "read_questions", {"status": "open", "limit": 200})
    known = {q["question_id"] for q in (before or {}).get("questions", [])}

    # The first sentence says which of the agent's two jobs this call is. Its system
    # prompt describes both, so without it the agent has to infer from the tools it was
    # handed which half of its own instructions applies — and inferring is exactly what
    # the per-call message exists to make unnecessary.
    ask = (
        "This call is the question-writing half of your work: decide what gets asked, "
        "and do not investigate anything. "
        f"Propose {want} question(s) for wave {wave} of run '{run_tag}'. "
        f"Call propose_questions once, with origin_run='{run_tag}' and origin_wave={wave}. "
    )
    ask += (
        "This is the first wave, so read_results has nothing yet — work from the corpus."
        if wave == 0
        else f"Call read_results with run_tag='{run_tag}' first and let those results "
             "decide what is worth asking next."
    )
    # This is the first call of the wave to touch the corpus, and under a skill it is
    # reading one branch of it. Left unsaid, "work from the corpus" asks it to ground
    # questions in what looks like a very small literature, and the reasonable response
    # to that is to search wider — which the server will refuse, call after call.
    if skill:
        ask += (
            f" The corpus is confined to {skill} for this run; okf_search and okf_read "
            f"return that branch and nothing else, so ask what that branch can answer."
        )
    try:
        # Neither half of what call_agent returns is wanted here. What the call did is
        # read back off the bank below, not taken from what it said — that is the whole
        # point of the docstring above.
        #
        # `stage=` is the console and trace label only (`:502-503`); the run is recorded
        # against the agent id. "question" rather than the agent's own name because the
        # label's job is to say which of the two jobs a line is about, and the Log panel
        # is the one place a reader sees these strings.
        await call_agent(
            agents["hypothesis"], ask,
            tools=by_stage["question"], registry=registry, stage=f"question{wave}",
        )
    except Exception as e:  # noqa: BLE001 - the fallback below is the point
        note(f"(the question step failed: {type(e).__name__} — going with the built-in "
             "perspective list)")
        # Not recycling: a call that crashed says nothing about whether the corpus
        # still has questions in it. Those are different situations with different fixes.
        return [], False

    after = await call_board_tool(registry, "read_questions", {"status": "open", "limit": 200})
    rows = (after or {}).get("questions", [])
    fresh = [q for q in rows if q["question_id"] not in known]

    # Falling back to already-banked questions when the call only produced duplicates
    # keeps the wave running, and a repeat of a known question is still grounded in the
    # corpus — which the built-in list is not.
    #
    # But it is reported upward as well as printed. Silently recycling is how a run that
    # has nothing left to ask keeps spending money looking exactly like a run that is
    # still making progress.
    if not fresh:
        note("(no new questions — reusing what was already in the bank)")
        return rows[:want], True
    return fresh[:want], False


def summarise(tasks: list[dict]) -> tuple[dict[str, int], list[tuple[int, int]]]:
    """Counts per (type, status), and which tasks have actually been retried.

    `attempts` counts *claims*, not failures. A task that goes data -> ml -> interpret
    is claimed three times and finishes with attempts=3, having failed nothing. Reading
    that number as a retry count made a clean run print "retried up to 3 times", which is
    the opposite of the truth.

    That matters more here than it would elsewhere: retries are unlimited by decision,
    so this display is the only thing telling a person whether to stop. A false alarm
    makes it useless.

    A task is being retried when it has been claimed more times than the stages it has
    passed through. `stage_index` gives how many claims a healthy task would have had
    by now.

    Two things come back:

        counts   {"data/ready": 2, ...}   who has how many sheets waiting — this is printed
        retried  [(sheet number, extra), ...]   **only the sheets that came back.** To see
                                                whether anything is stuck
    """
    # If a sheet had come this far normally, **how many times should it have been torn
    # off?** Once by the data person, once more by the ml person, once more by the
    # interpreter.
    stage_index = {"data": 1, "ml": 2, "interpret": 3}
    counts: dict[str, int] = {}
    retried: list[tuple[int, int]] = []

    for t in tasks:
        status, ttype = t["status"], t["task_type"]

        # Only what is not finished is counted. What is done stays out of the status line.
        if status in ("ready", "in_progress"):
            counts[f"{ttype}/{status}"] = counts.get(f"{ttype}/{status}", 0) + 1

        # 'ready' means that person has not torn it off **yet**, so one is subtracted.
        expected = stage_index.get(ttype, 0) - (1 if status == "ready" else 0)
        # times actually torn off - times it would have been if all went well = extra.
        # Greater than 0 means the sheet **came back because someone tried and failed.**
        extra = (t.get("attempts") or 0) - max(expected, 0)
        if extra > 0:
            retried.append((t["task_id"], extra))

    return counts, retried


def report_skill_note(skill: str) -> str:
    """What the report agent is told about the branch this run was confined to.

    A function rather than a variable because the report agent is called from two
    places — `--report-only`, which rescues a run that was interrupted, and the end of a
    full run — and the rescue path is the one that is used when something has already
    gone wrong. A note written into only one of them would be missing exactly then.

    Empty when there is no skill, which is every run made before `--skill` existed.
    """
    if not skill:
        return ""
    return (
        f" The knowledge bundle is confined to {skill} for this run. okf_search and "
        f"okf_read return that branch and nothing else, so use them to check a claim "
        f"against what that branch says — and say plainly that the reading was that "
        f"branch, not the whole corpus."
    )


async def run(args: argparse.Namespace, run_dir: Path) -> int:
    """The body of the run. (1) through (6) of "How to read this file" at the top are
    here, in that order."""
    configure(Settings())   # read .env and hand it to core (DB address, API keys, ...)
    log_path = setup_logging(level="DEBUG" if args.verbose else "INFO", log_file=run_dir / "run.jsonl")

    # Decide where the trace files go first. It has to be made **before** the first agent
    # is called, so a file appears the moment that call ends — that is why it can be read
    # while debugging.
    global _TRACE_DIR
    _TRACE_DIR = run_dir / "trace"
    _TRACE_DIR.mkdir(parents=True, exist_ok=True)
    print()
    print("=" * 74)
    print(f" board pipeline — run named '{args.run_tag}'")
    print("=" * 74)
    print(f"   trials      {args.trials if not args.report_only else '(report only)'}")
    print(f"   outcome     {args.y_column}")
    print(f"   data        {os.environ.get('MEMSTARA_DATASET_PATH','(none)')}")
    print(f"   knowledge   {os.environ.get('AGENTIC_OKF_BUNDLE_DIR','(none)')}")
    print(f"   skill       {args.skill or '(whole bundle)'}")
    print(f"   record dir  {run_dir}")
    print(f"   trace files {_TRACE_DIR.name}/  (one more each time a person is called)")

    # -- (1) call the five people ----------------------------------------
    #
    # Fetch the role description that says what each of them does. If this is the first
    # time, write it. Running it again and again only finds the same people back; it
    # does not multiply them.
    step("(1)", "call the five people", "fetch the role descriptions")
    agents = await provision_board_agents(provider=args.provider, model=args.model)
    done("(1)", f"{len(agents)} ready — {' · '.join(agents)}")

    # What each of them was told is a file now, and files change between runs. The run
    # directory does not answer *which wording produced this* by being looked at:
    # `report.md` is the answer and `board.json` the work; `src/memstara/trace/run.py:344`
    # records the system prompt's **length** and no more. The text itself is not lost —
    # it is inside `trace/NN_stage.llm.txt`, written by `_trace_one` — but that file is
    # the whole request stacked once per call, and it exists only where litellm's log was
    # intercepted. Comparing two runs there is reading; comparing two digests is looking.
    # So write the fingerprints down here, right after provisioning and before the first
    # model call, while what was sent is exactly what was just read.
    #
    # Keyed off `agents` rather than off `BOARD_AGENT_NAMES` so the record cannot come
    # to describe a stage that was not provisioned; the prompt path is the stage name
    # by construction (`provision_board_agents`).
    #
    # `_run` is not a stage, and the underscore is what says so. The skill belongs in
    # this file rather than in a new one because it answers the same question the
    # digests answer — *what produced this run* — and a branch of the corpus decides
    # what could be found at least as much as a wording decides what was asked.
    (run_dir / "prompts.json").write_text(
        json.dumps(
            {
                "_run": {"run_tag": args.run_tag, "skill": args.skill or None},
                **{
                    stage: {
                        "agent": BOARD_AGENT_NAMES[stage],
                        "agent_id": str(agent_id),
                        "file": f"src/memstara/prompts/board/{stage}.md",
                        **prompt_digest(f"board/{stage}"),
                    }
                    for stage, agent_id in agents.items()
                },
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    note("prompts.json — the sha256 of what each of them was told")

    # -- (2) switch on the four machines ---------------------------------
    #
    # This is where there come to be five programs. This one file + four machines.
    step("(2)", "switch on the four machines", "this is where there come to be five programs")
    registry = await setup_tools()
    done("(2)", "paper store · data machine · learning machine · board window")
    try:
        # -- (3) decide who gets which button ----------------------------
        #
        # Each person is handed **only the buttons they may use.** Give them all of them
        # and they do other people's work too, and then there is no telling afterwards
        # whose judgement a result was.
        by_stage = {
            stage: tools_for(registry, BOARD_SERVERS[stage], only=BOARD_TOOLS[stage])
            for stage in BOARD_TOOLS
        }
        # `question` is not a sixth person — it is the hypothesis agent's other set of
        # buttons, handed to it when it is writing the wave's questions instead of
        # answering one (`src/memstara/pipeline/core.py:448-466`). It is a separate entry
        # here because the buttons are handed out per call, and this is the table the
        # calls read from.
        by_stage["question"] = tools_for(
            registry, QUESTION_SERVERS, only=QUESTION_TOOLS,
        )
        # Print who got what. Later it can be confirmed from the log alone.
        step("(3)", "decide who gets which button", "cut them off from other people's work")
        _ROLE = {"hypothesis": "hypothesis agent (answering)", "data": "data agent",
                 "ml": "ml agent", "interpreter": "interpreter agent",
                 "report": "report agent", "question": "hypothesis agent (asking)"}
        for stage, ts in by_stage.items():
            names = sorted(x["tool_name"] for x in ts)
            print(f"   {_ROLE.get(stage, stage):<30} {len(names)}  {' · '.join(names)}")
        # Sets of buttons, not people. There are more sets than agents because the
        # hypothesis agent gets two, and saying "handed out to 6" about 5 agents is the
        # kind of number someone would later quote.
        done("(3)", f"{len(by_stage)} sets of buttons for "
                    f"{len(BOARD_TOOLS)} agents")

        # -- report only ------------------------------------------------
        # -- the path that does only (6) (--report-only) ------------------
        #
        # (4) and (5) are skipped and it **only wraps up.** It gathers the results of a
        # run that already finished and writes them as one page. Only one person (the
        # report agent) is called, so it is cheap.
        #
        # It also makes a report for a run that was interrupted or only partly finished,
        # out of whatever had piled up by then.
        if args.report_only:
            step("(6)", "wrap up at the end",
                 f"read the finished drawer of '{args.run_tag}' — (4) and (5) are skipped")
            note("call the report agent once (the only LLM call of this run)")
            text, _ = await call_agent(
                agents["report"],
                f"Write the report for run '{args.run_tag}'. Call read_results with that "
                f"run_tag.{report_skill_note(args.skill)}",
                tools=by_stage["report"], registry=registry, stage="report",
            )
            (run_dir / "report.md").write_text(text, encoding="utf-8")
            done("(6)", f"report {len(text.splitlines())} lines → report.md")
            print()
            print(text)
            return 0

        # -- waves ------------------------------------------------------
        # (4) and (5) are wrapped in **waves.** One wave = make the questions → seed the
        # board → work it all off.
        #
        # The wave boundary is what makes feedback possible at all. Seeding every trial
        # up front means the questions are all written before a single result exists,
        # so nothing any trial finds can affect what gets asked. A wave ends with
        # results on the table, and the next wave's question step reads them.
        #
        # Trial numbers that were seeded but left nothing on the board. They accumulate
        # across waves, and at the end they are handed to the report agent too.
        missing_trials: list[int] = []

        # Before the first wave, take back anything this tag left in_progress last time.
        # `reclaim_stalled` is also called inside the work loop, but only once that loop
        # has decided it has nothing to do — so re-running a tag that died mid-wave would
        # seed a whole new wave before noticing the old task was still there. Calling it
        # here is what makes "same --run-tag again" mean "carry on where it stopped".
        # stale_after still applies: a run that is genuinely still alive holds the
        # advisory lock above, so we cannot get here while one is.
        recovered = await reclaim_stalled(registry, args.run_tag, args.stale_after)
        if recovered:
            note(f"returned {recovered} tasks left by the last run to the queue — "
                 "carrying on")

        # How many waves in a row produced no new question. It stops when it reaches
        # `--stop-after-dry`.
        #
        # The corpus is finite — 333 documents across 37 tags — so the bank runs dry by
        # construction, not by accident. `--waves N` is a count, and a count cannot know
        # when there is nothing left to ask; this is the part that can.
        dry_streak = 0
        waves_run = 0        # waves actually seeded. If it stops early this differs from args.waves
        seeded_total = 0     # hypothesis agents actually called. This number goes to the report agent
        for wave in range(args.waves):
            base = wave * args.trials          # trial numbers carry on across waves
            if args.waves > 1:
                print(f"\n{'─' * 68}\n wave {wave + 1}/{args.waves}\n{'─' * 68}")

            # -- (3') decide what to ask --------------------------------
            questions: list[dict] = []
            recycled = False
            if not args.no_curator:
                step("(3')", "decide what to ask",
                     "the question step reads the corpus"
                     + ("" if wave == 0 else " and the previous wave's results")
                     + f" and makes {args.trials} questions")
                questions, recycled = await questions_for_wave(
                    registry, agents, by_stage,
                    run_tag=args.run_tag, wave=wave, want=args.trials, skill=args.skill,
                )
                for q in questions:
                    note(f"question #{q['question_id']} {q['text']}"
                         f"  [{'·'.join(q.get('okf_tags') or []) or 'no tags'}]")
                done("(3')", f"{len(questions)} questions"
                     + (" · all of them already in the bank" if recycled else ""))

            # -- stop when it runs dry -----------------------------------
            #
            # Two consecutive dry waves, not one. The question step can come back
            # empty-handed once by mistake, and that is not the same thing as a corpus
            # with nothing left in it. The break happens *before* seeding, so a run that
            # has run dry pays for one more question call and not for a whole wave of
            # trials it has already done.
            dry_streak = dry_streak + 1 if recycled else 0
            if args.stop_after_dry and dry_streak >= args.stop_after_dry:
                note(f"the questions have run dry — {dry_streak} waves in a row produced "
                     f"no new question. Stopping without starting wave "
                     f"{wave + 1}/{args.waves}")
                break
            waves_run += 1

            # If question generation was switched off or failed, fall back to the
            # perspective list hard-coded here. It is a list that does not line up with the corpus, but that
            # is better than the run stopping.
            if not questions:
                questions = [{"question_id": 0, "text": perspective_for(base + k)}
                             for k in range(args.trials)]
            # Counted here rather than as waves × trials: the question step is allowed to
            # ground fewer questions than asked for, and the loop above is allowed to
            # stop early. Both make the multiplication a number no run actually seeded.
            seeded_total += len(questions)

            # -- seed -------------------------------------------------------
            # -- (4) pin the first instruction to the board -------------------
            #
            # The hypothesis agent is called once per trial. Each time it is given a
            # **different perspective**, and the width of its answer is varied a little
            # too, because three identical answers leave nothing to compare.
            #
            # Only by shaking the perspective does an overlap come to mean "they set out
            # from different angles and arrived at the same place".
            step("(4)", "pin the first instruction to the board",
                 f"call the hypothesis agent {len(questions)} times — a different question "
                 f"each time"
                 + (f", {args.hypothesis_agents} at a time"
                    if args.hypothesis_agents > 1 else ""))

            # Whether the question comes from the bank or from the built-in list decides
            # how the workers are told what to ask, and the two are genuinely different.
            #
            #   from the bank  — the worker calls claim_question and is handed one. The
            #       bank row records who took it, so two workers cannot set out from one
            #       question even if this driver is not the only thing reading the bank.
            #   the fallback   — the question step grounded nothing (questions_for_wave
            #       returned empty) and these perspectives are not in the bank at all,
            #       so there is nothing to claim. Worker k is handed perspectives[k] directly, which
            #       is distinct by construction because the driver deals them out itself.
            #
            # The fallback keeps the old prompt exactly. It is the degraded path and it
            # already prints a warning; giving it a second, subtly different failure mode
            # to reason about would buy nothing.
            from_bank = any(q["question_id"] for q in questions)

            # The branch is enforced in the okf server whether or not this sentence is
            # written, so saying it buys nothing in safety — it buys the agent an
            # explanation. Without it, a search that returns 52 documents where the
            # bundle holds 312 reads as a thin literature, and the sensible response to a
            # thin literature is to search again more broadly. Told what it is looking
            # at, it spends those calls on the branch instead.
            #
            # It is written here, in the driver's per-call message, and not into
            # `prompts/board/hypothesis.md`: a prompt file is the same for every run, and
            # the branch is the one thing about this run that the user chose

            skill_note = (
                f" The knowledge bundle is confined to {args.skill} for this run; "
                f"okf_search and okf_read return that branch and nothing else."
                if args.skill else ""
            )

            async def seed_one(i: int, q: dict[str, Any], *, from_bank: bool = from_bank,
                               skill_note: str = skill_note):
                """Call one hypothesis worker and attach what its matcher calls saw."""
                text = q["text"]
                wid = f"hypothesis#{i}"
                # Both branches open by naming which of the agent's two jobs this is —
                # the counterpart of the sentence in `questions_for_wave`. The system
                # prompt covers writing questions as well as answering them, so a call
                # that does not say which it is leaves the agent to guess.
                if from_bank:
                    ask = (
                        f"This call is the answering half of your work: investigate the "
                        f"question you are handed and put the work on the board. "
                        f"You are worker '{wid}'. Call claim_question with "
                        f"run_tag='{args.run_tag}' and worker='{wid}' to be given your "
                        f"question; if it hands you nothing, stop. The outcome column is "
                        f"'{args.y_column}'. Choose the columns that will predict it from "
                        f"the perspective of the question you were handed. Then put the "
                        f"task on the board with run_tag='{args.run_tag}', trial={i}, "
                        f"perspective set to that question's text, and question_id set to "
                        f"the question_id you were handed.{skill_note}"
                    )
                else:
                    # question_id travels with the task so a finished result can be traced
                    # back to what was asked. 0 means the fallback list was used.
                    ask = (
                        f"This call is the answering half of your work: investigate the "
                        f"question below and put the work on the board. "
                        f"The outcome column is '{args.y_column}'. Choose the columns that will predict it, "
                        f"{text}. Then put the task on the board with "
                        f"run_tag='{args.run_tag}', trial={i}, perspective='{text}', "
                        f"question_id={q['question_id']}.{skill_note}"
                    )
                _, call = await call_agent(
                    agents["hypothesis"], ask,
                    tools=by_stage["hypothesis"], registry=registry, temperature=temperature_for(i),
                    stage=f"hypothesis{i}",
                )
                # Has to happen here, not at the end of the run. `submit_result` copies a
                # row from the board to the results table the moment it turns done, so a
                # trace attached after stage (5) would land on a board row whose result had
                # already been written without it — recorded in the place that gets cleared
                # and missing from the place that is kept.
                return i, await harvest_match_trace(registry, call)

            # A trial that never calls `create_task` leaves nothing behind: no board row,
            # no result, no error. On 2026-08-30 one of four trials spent 31 steps and
            # $1.88 that way and the run ended looking successful — the only thing that
            # noticed was the report agent, in prose, by luck. The count was already
            # being printed below; it was never compared, so nothing could notice.
            #
            # **How that is caught changed with this loop.** It used to read the whole
            # board's count before and after each call and blame the current trial for the
            # difference. Attributing a delta to one worker only works while exactly one
            # worker is running, and it was never quite right even then — any row from
            # anywhere would have counted as this trial's. The board carries the trial
            # number, so what is asked below is the direct question: is there a row for
            # trial i? That is concurrency-safe and strictly more truthful.
            for chunk_start in range(0, len(questions), args.hypothesis_agents):
                chunk = questions[chunk_start:chunk_start + args.hypothesis_agents]
                outcomes = await asyncio.gather(
                    *(seed_one(base + chunk_start + k, q) for k, q in enumerate(chunk)),
                    return_exceptions=True,
                )
                state = await board_state(registry, args.run_tag)
                for outcome in outcomes:
                    if isinstance(outcome, BaseException):
                        # Reported, not swallowed, and not fatal to the wave. The other
                        # workers in this chunk finished; their trials are on the board and
                        # the missing one is found by the presence test below like any
                        # other trial that produced nothing.
                        note(f"⚠ a hypothesis worker died: {type(outcome).__name__}: {outcome}")
                        continue
                    i, (attached, refused) = outcome
                    extra = ""
                    if attached:
                        extra += f" · attached the matcher record to {attached} sheets"
                    if refused:
                        # Reported, not hidden. All-refused and never-called are different
                        # failures with different fixes, and they look the same if this is
                        # silent.
                        extra += (f" · {refused} matcher calls were refused and left out of "
                                  f"the evidence")
                    note(f"trial {i} → {state['count']} sheets on the board" + extra)

            # The presence test. One read of the board, and a trial with no row of its own
            # is one whose worker never called create_task.
            state = await board_state(registry, args.run_tag)
            on_board = {t["trial"] for t in state["tasks"]}
            for k in range(len(questions)):
                i = base + k
                if i not in on_board:
                    note(f"⚠ trial {i} left nothing on the board "
                         f"— create_task was never called")
                    missing_trials.append(i)

            # Give the wave's questions back to the bank now that seeding is over. Not at
            # the end of the run: the claim exists to keep two workers of *this* wave off
            # one question, and the moment they have all called create_task that job is
            # done — what they produced is on the board under its own question_id and no
            # longer needs the bank row held. Held any longer, and because
            # memstara_questions has no run_tag to scope a cleanup by, the questions this
            # run used would be missing from the next run's bank.
            if from_bank:
                freed = await release_questions(args.run_tag)
                if freed:
                    note(f"gave {freed} question(s) back to the bank")

            # -- work it down ----------------------------------------------
            # -- (5) run until the board is empty ----------------------------
            #
            # This loop's only exit is an empty board, so something has to close a task
            # that can never succeed. `--max-attempts` does, below. It still prints what
            # it sees every round: the cap ends a stuck run, it does not explain it, and
            # the person reading is the one who decides whether the cap was the right
            # answer or the stage needs fixing.
            lost_here = [i for i in missing_trials if base <= i < base + len(questions)]
            done("(4)", f"{state['count']} sheets on the board"
                 + (f" · {len(lost_here)} of {len(questions)} trials ended empty-handed "
                    f"({', '.join(str(i) for i in lost_here)})" if lost_here else ""))
            step("(5)", "run until the board is empty",
                 "stop it with Ctrl-C and the board is still there")
            rounds = 0
            while True:
                state = await board_state(registry, args.run_tag)      # look at the board
                counts, retried = summarise(state["tasks"])            # status · what came back

                # If nothing is left on the board, that is the end.
                if not counts:
                    done("(5)", f"the board is empty — after {rounds} laps")
                    break

                rounds += 1
                desc = " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))

                # Named, not aggregated: "somewhere retried 5 times" does not tell a person
                # which task is stuck, and stuck-ness is what they are deciding about.
                #
                # Naming this `note` would shadow the note() function defined above, and
                # then calling note(...) inside this loop would die with a TypeError.
                stuck = ""
                if retried:
                    worst = sorted(retried, key=lambda p: -p[1])[:3]   # the worst three only
                    stuck = "  ← came back: " + ", ".join(f"#{tid} ×{n}" for tid, n in worst)
                print(f"   [lap {rounds:>3}] {desc}{stuck}")

                # Give up on tasks that keep coming back. `retried` already counts the
                # extra claims, so this is a decision on a number that was being printed
                # and otherwise acted on by nobody. Closing one task does not stop the
                # run — the others keep going, and the trial is recorded as lost so the
                # report says so rather than quietly describing fewer results as all.
                if args.max_attempts:
                    doomed = [tid for tid, n in retried if n >= args.max_attempts]
                    if doomed:
                        lost = await give_up_on(doomed)
                        missing_trials.extend(t for t in lost if t not in missing_trials)
                        note(f"gave up on task {', '.join(f'#{t}' for t in doomed)} — "
                             f"it came back more than {args.max_attempts} times. That trial "
                             f"stays empty-handed")
                        # Go round again so what was closed drops out of the status line.
                        continue

                # Was anyone called at all this lap? If nobody was, fall through below.
                #
                # The calls are collected first and started together, rather than awaited
                # one at a time as they were before. Two consequences worth being explicit
                # about:
                #
                #   * Stages overlap as well as workers. data#1, data#2 and ml#1 all run
                #     at once. There is nothing to serialise for — each one claims only
                #     its own task_type, and claim_task takes its row in a single
                #     FOR UPDATE SKIP LOCKED statement, so two claimers cannot take one
                #     row (proved under 12-for-8 contention in scripts/check_blackboard.py).
                #   * The sweep order in CLAIMING_STAGES no longer decides anything within
                #     a lap. It still decides the order the launches are built in, which
                #     is what keeps the printed output roughly in pipeline order.
                worked = False
                launches = []
                for stage in CLAIMING_STAGES:                 # data → ml → interpreter order
                    ttype = STAGE_TASK_TYPE[stage]
                    waiting = counts.get(f"{ttype}/ready", 0)
                    if not waiting:
                        continue                              # no sheet for this person to take

                    # Never more workers than there are sheets. An extra worker claims
                    # nothing, is told "nothing to claim", and reaches that conclusion at
                    # the price of a whole model call. The flag is a ceiling on how many
                    # may run, not an instruction to run that many.
                    #
                    # `interpreter` is the stage's name and `interpret` is the name on the
                    # sheet; the flag is spelled --interpret-agents, after the sheet, which
                    # is what STAGE_TASK_TYPE is for.
                    for k in range(1, min(waiting, getattr(args, f"{ttype}_agents")) + 1):
                        # The worker's name. It goes in the prompt because the guard on the
                        # board compares names, and a name the agent was never given is a
                        # comparison that cannot fire — submit_result treats an empty
                        # worker as "no opinion", not as a failure.
                        wid = f"{ttype}#{k}"

                        # No outcome column in this message on purpose. It is on the task,
                        # put there by the hypothesis stage, and a task has to carry
                        # everything its stage needs. Saying it here as well would leave two
                        # sources for one fact — and the one in the prompt is the one that
                        # goes unrecorded, so if the two ever disagree there is no way to
                        # check.
                        #
                        # The run_tag is the exception, and not a contradiction of the rule
                        # above: it does not describe the task, it decides *which* task to
                        # pick. That has to come from the prompt because the agent is
                        # choosing before it holds a task to read it from. The worker name
                        # is here for the same reason — it is not a property of the task,
                        # it is who is asking.
                        launches.append(call_agent(
                            agents[stage],
                            f"You are worker '{wid}'. Claim a '{ttype}' task from run_tag "
                            f"'{args.run_tag}' and do your part. Pass worker='{wid}' to "
                            f"both claim_task and submit_result.",
                            tools=by_stage[stage], registry=registry,
                            # Each worker gets its own trace file. Left as `stage`, two
                            # workers of one type would write trace/NN_data.txt over each
                            # other and the losing one's record would simply be absent.
                            stage=wid,
                        ))
                    worked = True

                if launches:
                    # return_exceptions=True, deliberately. Before this, one call_agent
                    # raising ended the whole run. With N workers in flight that would
                    # throw away the other N-1's finished work for one crash. Here the
                    # failure is printed and the lap goes on: the crashed worker's task
                    # stays in_progress and --stale-after takes it back, which is the
                    # mechanism that already exists for a worker that stops answering.
                    #
                    # It is reported rather than swallowed. A crash that only shows up as
                    # a task quietly reclaimed 600 seconds later is a crash nobody can
                    # attribute to anything.
                    for outcome in await asyncio.gather(*launches, return_exceptions=True):
                        if isinstance(outcome, BaseException):
                            note(f"⚠ a worker died: {type(outcome).__name__}: {outcome} "
                                 f"— its task stays in progress until --stale-after "
                                 f"({args.stale_after}s) takes it back")

                if not worked:
                    # Nothing is waiting for any stage, so what is left is in_progress.
                    # Either its agent died without submitting, or it is simply still
                    # running. Only the first kind may be taken back, which is what the
                    # staleness window decides.
                    n = await reclaim_stalled(registry, args.run_tag, args.stale_after)
                    if n:
                        print(f"       {n} had been stuck for more than {args.stale_after}s "
                              f"and were returned to waiting")
                    else:
                        # Everything still in progress is young enough to be presumed
                        # alive. Waiting is correct; looping without waiting would spin
                        # the CPU and hammer the board for no reason.
                        print(f"       waiting on what is in progress ({POLL_SECONDS}s)")
                        await asyncio.sleep(POLL_SECONDS)

            # -- (6') write this wave's score into the question bank ------
            #
            # Has to be here, not after the last wave: the next wave's question step
            # reads the bank, so a score written after the loop is a score no question
            # ever used.
            try:
                folded = await call_board_tool(
                    registry, "record_question_outcomes", {"run_tag": args.run_tag})
                if folded.get("questions_updated"):
                    note(f"wrote this score onto {folded['questions_updated']} questions"
                         + (f" · {folded['questions_retired']} were used up and retired"
                            if folded.get("questions_retired") else ""))
            except Exception as e:  # noqa: BLE001 - bookkeeping must not fail the run
                note(f"(could not write the score into the question bank: {type(e).__name__})")


        # -- report -----------------------------------------------------
        # -- (6) wrap up at the end -------------------------------------
        #
        # The report agent reads **the finished drawer, not the board.** The board is a
        # workbench and disappears when it is cleared; the finished drawer is the record
        # that stays.
        step("(6)", "wrap up at the end", "the report agent reads the finished drawer")
        # How many trials were seeded is told to the reporter, because the results table
        # cannot say it. read_results only returns rows that exist, so a trial that died
        # before create_task is invisible there — and a report that silently describes
        # three results as if three were all that were attempted is a false report.
        lost_note = (
            f" Trials {', '.join(str(i) for i in missing_trials)} produced no result at all "
            f"(the hypothesis agent never called create_task); they will be absent from "
            f"read_results. Say so explicitly."
            if missing_trials else ""
        )
        text, _ = await call_agent(
            agents["report"],
            f"Write the report for run '{args.run_tag}'. Call read_results with that run_tag. "
            f"{seeded_total} trials were seeded across {waves_run} wave(s)"
            + (f" (of {args.waves} requested; the run stopped early because the question "
               f"bank ran dry)" if waves_run < args.waves else "")
            + f". State how many of those {seeded_total} produced a result.{lost_note}"
            + report_skill_note(args.skill),
            tools=by_stage["report"], registry=registry, stage="report",
        )
        (run_dir / "report.md").write_text(text, encoding="utf-8")

        # The last state of the board is saved whole as well. It is what a later retrace
        # reads.
        final = await board_state(registry, args.run_tag)
        (run_dir / "board.json").write_text(
            json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        run_ids = [t.get("task_id") for t in final["tasks"]]
        print(f"\n{'=' * 68}\n{text}\n{'=' * 68}")
        print(f"\nrun directory: {run_dir}")
        print(f"  report.md · board.json ({len(run_ids)} tasks) · prompts.json")
        if log_path:
            print(f"  {log_path.name}")
        return 0
    finally:
        # The trace files are written **inside finally.** Even if it dies partway or is
        # cut short with Ctrl-C, the record of the runs called up to that point has to
        # survive — a run that died is precisely the one worth retracing. It is written
        # before the tool servers are disconnected: what is read here is core's DB and has
        # nothing to do with the tool servers, but reversing the order would break quietly
        # the day somebody changes this to use a tool.
        try:
            n = await write_traces(run_dir)
            if n:
                print(f"  {n} files in trace/ · runs.json — what the agents asked the "
                      f"tools and what they got back is in here")
        except Exception as e:  # noqa: BLE001 - a failure to record must not wreck the run
            print(f"!! could not write the trace files: {type(e).__name__}: {e}",
                  file=sys.stderr)

        # Success or failure, the four child processes are always cleaned up.
        await registry.disconnect_all()


async def reclaim_stalled(registry: MCPServerRegistry, run_tag: str, stale_after: int) -> int:
    """Put tasks nobody is working on back into the queue.

    An agent that finished without submitting leaves its task marked in_progress
    forever. Since retries are unlimited, these go back to waiting rather than being
    closed — that is the decision, and this is where it is enforced.

    **Only rows untouched for *stale_after* seconds.** Without that condition this
    reclaims work that is in progress right now, one second after it was claimed. A
    single driver mostly gets away with it, because it only calls this when it has
    nothing else to do — but "nothing waiting for me" and "nothing being worked on"
    are different statements, and the gap between them is where a stage that simply
    takes a long time gets its task yanked away mid-run. It then submits against a
    task somebody else has since claimed — which `submit_result` now refuses by name,
    provided both workers identified themselves when they claimed. That refusal turns
    a silent overwrite into a visible error; it does not make the reclaim above any
    less premature, so *stale_after* still has to be right.

    Returns:
        How many were returned to the queue. Zero means everything still in progress
        is young enough to be presumed alive — the caller should wait, not spin.
    """
    # This is the one place that touches the board directly. It does not go through the
    # window because this is not a worker's job but **the caretaker's** — it is not a
    # button to hand to anybody.
    conn = await asyncpg.connect(dsn())
    try:
        n = await conn.fetchval(
            """
            WITH returned AS (
                UPDATE memstara_blackboard
                -- claimed_by is released with claimed_at. Not for the next claimer's
                -- sake — claim_task overwrites the name anyway — but for the window
                -- in between, which is exactly the window somebody looks at when a
                -- run is behaving oddly. A row reading 'ready' while still naming a
                -- holder says two contradictory things at once, and this reclaim is
                -- the only thing that ever produces that state.
                SET status = 'ready', claimed_at = NULL, claimed_by = '',
                    updated_at = now()
                WHERE run_tag = $1 AND status = 'in_progress'
                  AND claimed_at IS NOT NULL
                  -- only what was claimed more than stale_after seconds ago. This line
                  -- is the safeguard.
                  AND claimed_at < now() - make_interval(secs => $2::double precision)
                RETURNING 1
            ) SELECT count(*) FROM returned
            """,
            run_tag,
            float(stale_after),
        )
    finally:
        await conn.close()
    return int(n)


async def give_up_on(task_ids: list[int]) -> list[int]:
    """Close tasks that will not succeed, so the board can drain.

    Retries were unlimited, which is defensible for a stage that fails on a hiccup and
    indefensible for one that fails on the same thing every time: the work loop's only
    exit is an empty board, so one such task keeps a run from ever reaching its report.
    Somebody has to decide "this will not work", and before this it was the person
    watching the console — which means an unattended run had no end.

    Failed, not deleted. The row is the only record of what was attempted, and the trial
    it belongs to is returned so the caller can report it as lost rather than let a
    shorter results table pass for a complete one.

    Args:
        task_ids: the board rows to close.

    Returns:
        The trial numbers those rows belonged to.
    """
    # It does not go through the window, for the same reason as reclaim_stalled — this is
    # the caretaker's job, not a button to hand to an agent.
    conn = await asyncpg.connect(dsn())
    try:
        rows = await conn.fetch(
            """
            UPDATE memstara_blackboard
               SET status = 'failed',
                   error  = CASE WHEN error = '' THEN 'gave up: too many retries'
                                 ELSE error END,
                   updated_at = now()
             WHERE task_id = ANY($1::bigint[])
               AND status IN ('ready', 'in_progress')
         RETURNING trial
            """,
            task_ids,
        )
    finally:
        await conn.close()
    return [r["trial"] for r in rows]


async def main() -> int:
    """The door in from the command line. Reads the arguments, checks them, takes the
    lock and calls run()."""
    # This project has **two** `.env` files, and they hold different things.
    #
    #     memstara/.env   the MEMSTARA_* paths
    #     motoro/.env           LLM credentials · MOTORO_DATABASE_URL
    #
    # But `env_file=".env"` in `src/memstara/config.py:27` reads **only the current folder.** So
    # unless core's file is read separately the LLM credentials never arrive, and the
    # result is this error, which blows up on the first call:
    #
    #     ValueError: Azure Anthropic requests require an api_base.
    #
    # `source` both in a shell and it does not happen, but VS Code's `envFile` takes only
    # one file, so starting with F5 does hit it. That amounts to behaving differently
    # depending on how it was started, so **the program reads them itself** and comes out
    # the same wherever it was launched from.
    #
    # The sandbox one is read first. `load_dotenv` does not overwrite a value that is
    # already there (override=False is the default), so whichever is read first wins, and
    # a value given by the shell or by launch.json comes ahead of both — which keeps the
    # intent of "a different bundle for this run only" working.
    #
    # `load_env` is `memstara.env`'s, and it is now the only reader of those two files. This
    # was one of four hand-written copies of the same pair, and they had already drifted:
    # debug_harness.py read core's first, giving it priority over the sandbox's.
    load_env()

    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3, help="how many hypotheses to seed per wave")
    ap.add_argument("--waves", type=int, default=1,
                    help="how many question-then-investigate rounds; wave 2 onward reads "
                         "the results of the one before it. This is a ceiling, not a "
                         "target — see --stop-after-dry")
    ap.add_argument("--stop-after-dry", type=int, default=2,
                    help="stop early after this many consecutive waves in which the "
                         "question step produced no new question, so the wave would only "
                         "re-run ones already banked. 0 never stops early (default 2)")
    # Kept under this name although there is no curator agent any more: it is an
    # argument people already type and its meaning has not changed. Renaming it would
    # break every saved command line to make a flag agree with an implementation detail.
    ap.add_argument("--no-curator", action="store_true",
                    help="skip the question-writing call and use the built-in "
                         "perspective list instead")
    ap.add_argument("--y-column", default="outcome")
    # The user's chosen skill: one branch of the knowledge bundle, named the way the
    # bundle files it. This flag does not ask the agents to stay inside it — it sets
    # MEMSTARA_OKF_FIELDS, which the okf server reads and enforces on every search and
    # every read (src/memstara/mcp_servers/okf.py). Empty is the whole bundle, which is
    # how every run before this flag existed behaved.
    ap.add_argument(
        "--skill", default="",
        help="confine the knowledge bundle to one branch for this run, as front matter "
             "equalities: \"terminus_kind=sud\" or "
             "\"mechanism_family=treatment-toxicity,terminus_kind=sud\". Empty (the "
             "default) leaves the whole bundle readable",
    )
    ap.add_argument("--provider", default="azure_foundry", choices=["anthropic", "azure_foundry", "openai"])
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--run-tag", default=None, help="names this run on the board")
    ap.add_argument("--report-only", action="store_true", help="write the report from what has finished")
    ap.add_argument(
        "--stale-after", type=int, default=600,
        help="seconds a task may sit in_progress before it is presumed abandoned (default 600)",
    )
    ap.add_argument(
        "--max-attempts", type=int, default=5,
        help="give up on a task once it has come back this many extra times, mark it "
             "failed and go on without it. 0 retries forever, which means only a person "
             "watching can end a run whose task can never succeed (default 5)",
    )
    # How many workers of each claiming stage run at once.
    #
    # One flag per stage rather than a single --agents N, because the right number is not
    # the same for all three. A `data` worker spends its time in the model and in a CSV
    # slice; a second one genuinely doubles throughput. An `ml` worker ends in
    # train_and_score, which is a **sync** tool, and FastMCP calls sync tools straight on
    # the server's event loop (mcp/server/fastmcp/utilities/func_metadata.py:93-96) — so
    # two ml workers overlap their reasoning turns and their fits still run one after the
    # other. Rolling the three into one number would hide that.
    #
    # Default 1 everywhere: that is exactly the behaviour before this flag existed, so a
    # command line that does not mention them runs as it always did.
    for stage_flag, what in (("data", "data"), ("ml", "ml"), ("interpret", "interpretation")):
        ap.add_argument(
            f"--{stage_flag}-agents", type=int, default=1,
            help=f"how many {what} workers claim from the board at once (default 1)",
        )
    # The seeding stage's own count. It is separate from the three above because it is not
    # the same kind of number: those three are how many workers stand at the board through
    # a whole run, this is how many of a wave's trials are seeded at once. --trials still
    # decides how many trials there are; this only decides how many are in flight.
    ap.add_argument(
        "--hypothesis-agents", type=int, default=1,
        help="how many hypothesis workers seed the board at once. Each claims its own "
             "question out of the bank, so two never set out from one question (default 1)",
    )
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--run-dir", default=None)
    args = ap.parse_args()

    # Rejected here rather than clamped. A run started with --data-agents 0 asked for
    # something specific; quietly turning it into 1 gives back a run that is not the one
    # that was asked for, and quietly turning it into 0 workers hangs on a board that
    # never empties.
    bad = [f"--{s}-agents={getattr(args, f'{s}_agents')}"
           for s in ("hypothesis", "data", "ml", "interpret")
           if getattr(args, f"{s}_agents") < 1]
    if bad:
        ap.error("a stage needs at least one worker: " + ", ".join(bad))

    # The skill is read here, before Postgres is touched or a server is started, so a
    # mistyped branch costs a second rather than a provisioned run. It is then written
    # into the environment the tool servers inherit — the same route
    # AGENTIC_OKF_BUNDLE_DIR already takes to the okf child.
    #
    # Written **unconditionally**, so that the flag is the whole answer: with a value
    # left over in a shell or in .env, an unflagged run would otherwise be confined to a
    # branch that nothing on screen and nothing in the run directory mentions.
    if args.skill:
        try:
            parse_field_filter(args.skill)
        except ValueError as e:
            ap.error(f"--skill {args.skill!r}: {e}")
    os.environ["MEMSTARA_OKF_FIELDS"] = args.skill

    # If the prerequisites are missing it ends **without doing anything.** Stopping
    # before the start leaves the board cleaner than dying halfway through.
    #
    # `--report-only` does not use the outcome column. It only reads and tidies what has
    # already finished, so it never opens the dataset. Check the outcome column anyway
    # and the default `outcome` blocks **the very path meant for rescuing an interrupted
    # run** — the means of rescue failing only when rescue is needed.
    problems = await check_environment(
        provider=args.provider,
        y_column="" if args.report_only else args.y_column,
    )
    if problems:
        print("Environment is not ready:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    started = datetime.now()
    # If no run name is given, one is made from the clock. This name is what ties the
    # sheets on the board together.
    args.run_tag = args.run_tag or started.strftime("board_%Y%m%dT%H%M%S")
    run_dir = Path(args.run_dir) if args.run_dir else new_run_dir(
        f"board_{args.trials}trials", started.strftime("%Y-%m-%dT%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    # Whatever is printed to the screen is left in console.log as well.
    with tee_console(run_dir / "console.log"):
        try:
            # Refuse to be the second driver on this tag. Held for the whole run and
            # released with the connection, so a killed process leaves nothing behind.
            # Two of them once ran at the same time, taking each other's sheets, and the
            # board ended up scrambled.
            async with run_lock(args.run_tag):
                return await run(args, run_dir)
        except BoardBusy as e:
            # Somebody is already running under this name.
            print(f"\n{e}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            # The board is a database; whatever was written stays written. Say what to
            # do next rather than leaving a bare traceback.
            print("\n\ninterrupted. the board is still there.")
            print("  see the state:  python -m memstara.blackboard --show")
            print(f"  report only:    python -m memstara.pipeline.board --report-only --run-tag {args.run_tag}")
            return 130


if __name__ == "__main__":
    # asyncio.run drives main() to the end, and its return value (0/1/2/130) becomes the
    # exit code.
    raise SystemExit(asyncio.run(main()))
