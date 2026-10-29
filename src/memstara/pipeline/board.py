#!/usr/bin/env python3
"""The same four stages, driven by a shared board instead of a supervisor."""

from __future__ import annotations

# ---- standard library -------------------------------------------------------
from contextvars import ContextVar
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
from memstara.env import load_env, model_environment_errors

# memstara/blackboard.py — the board table's definition and connection details
from memstara.blackboard import BoardBusy, dsn, release_questions, run_lock
from memstara.pipeline.run_ownership import (RunOwnershipLost, RunLockCleanupError,
    ownership_lost, require_ownership, record_interruption, record_cleanup_warning)
# memstara/logging_setup.py — makes a directory per run and also keeps the log in a file
from memstara.logging_setup import drain_llm_requests, new_run_dir, setup_logging, tee_console
# memstara/pipeline/core.py — the part the two pipelines (mvp, board) share
from memstara.pipeline.core import (
    BOARD_SERVERS,           # the tool servers each stage is allowed to reach
    BOARD_TOOLS,             # the individual tool names each stage is allowed
    QUESTION_SERVERS,        # ...and the same two, for the hypothesis agent's other job
    QUESTION_TOOLS,          # (writing the wave's questions). Not a stage — see core.py
    board_workers,           # the roster: worker key -> (agent name, its playbook)
    perspective_for,         # trial number -> perspective wording
    provision_board_agents,  # creates or fetches the agents on that roster
    stage_of,                # worker key -> stage; "hypothesis#2" is not a sixth stage
    temperature_for,         # trial number -> temperature
    tools_for,               # picks out of the registry only the tools to be used
)
# memstara/pipeline/prompts.py — what each agent is told, and its fingerprint
from memstara.pipeline.prompts import load_prompt, prompt_digest
from memstara.pipeline.failures import PipelineExecutionFailure
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
# There are five processing roles but only three queue consumers here.
# Hypothesis and report are outside this queue for
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
#   TASK_TYPES contains data, ml and interpret. Hypothesis generation creates a
#   data task directly; it never claims a hypothetical queue state.
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


async def check_environment(provider: str = "", y_column: str = "", *,
                            use_okf: bool = True, use_data: bool = True,
                            prepare_matcher: bool = False, run_dir: Path | None = None,
                            stage_models: dict | None = None) -> list[str]:
    """Everything missing, reported at once, before anything starts.

    What is missing is collected **all together** rather than reported one at a time.
    Fix one, run again, find another one missing — that is what this removes.

    An empty list coming back means "ready".

    Args:
        provider: legacy CLI model metadata. Credentials follow the selected profiles.
            Omit both provider and stage_models to skip model checks in data-only diagnostics.
        stage_models: frozen assignments, or current deployment profiles when omitted.
        y_column: the outcome variable chosen with `--y-column`. Checks that the name
            really is in the dataset. An empty string skips it.
    """
    problems: list[str] = []   # if there is even one thing in here, it does not run

    # Two databases, and they are not interchangeable. core keeps its agents and run
    # history in MOTORO_DATABASE_URL; the board and the results table live in Memstara's
    # own server (MEMSTARA_DATABASE_URL, compose.yml). Only the first is required
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
        if name == "AGENTIC_OKF_BUNDLE_DIR" and not use_okf:
            continue
        if name == "MEMSTARA_DATASET_PATH" and not use_data:
            continue
        value = os.environ.get(name, "").strip()   # empty string if unset
        if not value:
            problems.append(f"{name} is not set — {hint}")

    # LLM credentials. Empty, and the first agent call dies with "Azure Anthropic
    # requests require an api_base" — after one seeding has already been spent. Caught
    # here, it stops without spending anything.
    #
    # main() loads optional environment files before checking effective values.
    if provider or stage_models is not None:
        problems.extend(model_environment_errors(provider, stage_models))

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

    # Fresh registered inputs and legacy CSV runs share the same semantic-index
    # lifecycle. Repair derived artifacts BEFORE requiring their readiness.
    if prepare_matcher and use_data and not problems:
        from memstara.predictor_cache import ensure
        from memstara.pipeline.checkpoint import atomic_json
        def preparation_status(status, message):
            print(message, flush=True)
            if run_dir is not None:
                run_dir.mkdir(parents=True, exist_ok=True)
                progress_path = run_dir / "progress.json"
                try:
                    progress = json.loads(progress_path.read_text())
                    if not isinstance(progress, dict):
                        progress = {}
                except (OSError, ValueError):
                    progress = {}
                atomic_json(progress_path, {**progress,
                    "preparation": {"status": status, "message": message}})
        preparation_status("running", "Preparing predictor search for the selected dataset.")
        try:
            receipt = ensure()
        except Exception as exc:
            message = f"Predictor search preparation failed ({type(exc).__name__}): {exc}"
            preparation_status("failed", message)
            problems.append(message)
            return problems
        preparation_status("completed", f"Predictor search ready ({receipt['action']}).")

    # Question generation calls the semantic matcher before any data/ML stage.
    # Verify its cohort catalog and embedding stamps here, before spending LLM
    # calls on hypotheses that cannot be mapped. This is header/hash metadata
    # validation only; it does not load the embedding model or rebuild artifacts.
    if use_data and dataset and Path(dataset).is_file():
        try:
            from memstara.matcher import config as matcher_config
            from memstara.matcher.catalog import load_catalog, verify_catalog
            from memstara.matcher.embedder import embeddings_stale
            from memstara.matcher.service import build_run_config, current_fingerprint

            matcher_run_config = build_run_config()
            fingerprint = current_fingerprint(matcher_run_config)
            stale_catalog = verify_catalog(matcher_config.CATALOG_JSON, fingerprint)
            if stale_catalog:
                problems.append(
                    "Predictor-mapping cache is not ready: " + stale_catalog
                )
            else:
                entries = load_catalog(matcher_config.CATALOG_JSON)
                stale_embeddings = embeddings_stale(
                    matcher_config.CATALOG_JSON,
                    match_texts=[entry.match_text for entry in entries],
                    cfg=matcher_run_config.embedding,
                )
                if stale_embeddings:
                    problems.append(
                        "Predictor-mapping embeddings are not ready: " + stale_embeddings
                    )
        except Exception as e:  # noqa: BLE001 - fail before paid/model work
            problems.append(
                "Predictor-mapping cache preflight could not be completed: "
                f"{type(e).__name__}. Check MEMSTARA_DATASET_PATH and "
                "MEMSTARA_OUTCOME_COLUMN, then run `python -m memstara.preflight --quick`."
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
    try:
        from memstara.evaluation import active_plan
        from memstara.pipeline.ablation import enabled
        if enabled(active_plan()):
            # Do not hydrate persisted servers: that would reconnect OKF too.
            from motoro.services.mcp_service import reconnect_server
            for name, command in launch_table():
                if name == 'okf':
                    continue
                # Tool dispatch checks persisted registration IDs. Reconnect only
                # selected non-OKF entries through the public service API.
                server = await get_server_by_name(name)
                if server is None:
                    server = await register_server(name=name, transport="stdio", command=command, registry=registry)
                elif server.command != command:
                    server = await update_server(server.id, command=command, registry=registry)
                else:
                    server = await reconnect_server(server.id, registry=registry)
                entry = registry.servers.get(server.id) if server is not None else None
                if entry is None or entry.error:
                    raise RuntimeError(f'Ablation MCP startup failed: {name}')
            return registry
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
    except BaseException:
        # Cancellation during startup still owns partially opened tool sessions.
        try:
            await registry.disconnect_all()
        except Exception:
            pass  # Preserve the original startup/ownership failure.
        raise



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
_CURRENT_LOOP: ContextVar[int | None] = ContextVar("memstara_loop", default=None)
_CALLS: list[dict[str, Any]] = []
_CURRENT_FLAVORS: ContextVar[dict | None] = ContextVar("memstara_flavors", default=None)


_EXECUTION_GATE = None


async def call_agent(*args, **kwargs):
    try:
        if _EXECUTION_GATE is None:
            return await _call_agent_uncontrolled(*args, **kwargs)
        return await _EXECUTION_GATE.call(_call_agent_uncontrolled, *args, **kwargs)
    except PipelineExecutionFailure:
        raise
    except Exception as exc:
        from memstara.pipeline.failures import stop_execution
        stop_execution(_TRACE_DIR.parent if _TRACE_DIR else None,
                       kwargs.get('stage', ''), _CURRENT_LOOP.get(), exc)


async def _call_agent_uncontrolled(
    agent_id,
    prompt: str,
    *,
    tools,
    registry,
    temperature: float | None = None,
    stage: str = "",
) -> tuple[str, dict[str, Any]]:
    """Run one agent once; stop the execution if the agent fails.

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
    from memstara.pipeline.failures import ensure_not_failed, stop_execution
    ensure_not_failed(_TRACE_DIR.parent if _TRACE_DIR else None)
    from memstara.pipeline.scientific_policy import check_primary_tools
    require_ownership()
    from memstara.evaluation import active_plan
    from memstara.pipeline.ablation import enabled, filter_tools, INSTRUCTIONS
    plan = active_plan()
    from memstara.research_inputs import instructions as research_instructions
    skill_authored_stage = stage.split('#', 1)[0] in ('interpret', 'interpreter', 'report')
    if skill_authored_stage:
        # Supply input metadata, not a second set of report-writing rules.
        configuration = ((plan or {}).get('research_profile') or {}).get('configuration')
        if configuration:
            prompt += '\n\nResearch input metadata:\n' + json.dumps({
                key: configuration[key] for key in (
                    'target', 'data_mode', 'knowledge_mode', 'missing_policy', 'predictor_types'
                ) if key in configuration
            }, ensure_ascii=False)
    else:
        prompt += research_instructions((plan or {}).get('research_profile'))
    if stage.startswith(("hypothesis", "question")):
        from memstara.pipeline.feature_selection import scoped, hypothesis_tools, instructions as selection_instructions
        wave = max(0, (_CURRENT_LOOP.get() or 1) - 1)
        prompt += selection_instructions(plan, wave)
        tools = hypothesis_tools(tools, plan, wave)
        plan = scoped(plan, wave)
    tools = filter_tools(tools, plan)
    if enabled(plan) and not skill_authored_stage:
        prompt += '\n' + INSTRUCTIONS
    check_primary_tools(stage, tools)

    from memstara.stage_models import call_overrides
    overrides = call_overrides((plan or {}).get('stage_models'), stage, temperature)

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
        "loop": _CURRENT_LOOP.get(),
        "stage": stage or "?",
        "run_id": str(run.id),
        "prompt": prompt,
        "status": "started", "agent_id": str(agent_id), "started_at": time.time(),
        "allowed_tools": sorted({t[k] for t in tools for k in ("tool_name", "name") if t.get(k)}),
    }
    flavors = _CURRENT_FLAVORS.get()
    if flavors:
        entry['combination'] = flavors['combination']
        entry['repetition'] = flavors['repetition']
        entry['skill'] = next((a for a in flavors['agents'] if a.get('agent_id') == str(agent_id)), None)
    _CALLS.append(entry)
    write_execution_manifest()

    # ── this is where the LLM runs ─────────────────────────────────────────
    # `execute_run` is a function of motoro. Inside, it repeats reason -> act
    # (calling a tool) -> observe. **We do not go inside it** — `justMyCode: true` in
    # launch.json steps F11 over it here. What we see is only the result.
    #
    # What happened inside is what _trace_one() below pulls out into a file.
    from memstara.pipeline.diagnostics import call_context, call_loop
    context_token = call_context.set((str(_TRACE_DIR.parent), str(run.id), stage)) if _TRACE_DIR else None
    loop_token = call_loop.set(_CURRENT_LOOP.get())
    try:
        from memstara.pipeline.pause_runtime import active_timeout
        async with active_timeout((plan or {}).get('runtime_timeouts', {}).get('agent_timeout_seconds', 600),
                                  _TRACE_DIR.parent if _TRACE_DIR else None):
            from memstara.pipeline.llm import PipelineLLMService
            result = await execute_run(run_id=run.id, registry=registry, available_tools=tools,
                                       llm_service=PipelineLLMService(principal_id=run.owner_id))
    except BaseException as exc:
        entry["status"] = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
        entry["error"] = type(exc).__name__
        write_execution_manifest()
        if isinstance(exc, Exception):
            stop_execution(_TRACE_DIR.parent if _TRACE_DIR else None, stage, _CURRENT_LOOP.get(), exc)
        raise
    finally:
        call_loop.reset(loop_token)
        if context_token is not None:
            call_context.reset(context_token)
        entry["duration_seconds"] = time.time() - entry["started_at"]
        write_execution_manifest()
    entry["status"] = getattr(result.status, "value", str(result.status))
    if result.error:
        entry["error"] = str(result.error)
    write_execution_manifest()
    # Latch immediately, before trace reads or another worker can start a new request.
    if result.error or result.status != "completed":
        stop_execution(_TRACE_DIR.parent if _TRACE_DIR else None, stage, _CURRENT_LOOP.get(),
                       result.error or result.status)

    # The trace file for **this one call** is written the moment the run finishes.
    #
    # Why write it here — writing them all at the end is useless while debugging,
    # because the file does not exist until the whole run is over. Written here, the
    # instant you stop at a breakpoint on the line after `await call_agent(...)` you can
    # open `trace/00_hypothesis0.txt` and read what just happened — which tool was
    # called with which arguments and what came back.
    await _trace_one(entry)
    from memstara.experiment_registry import sync_after_agent as sync_registry
    if _TRACE_DIR:
        await sync_registry(_TRACE_DIR.parent)

    # Spell out on screen what that person actually did. The untruncated version is in
    # the file under trace/.
    #
    # Everything this prints happens after its two awaits above, with no await in
    # between, so one call's block reaches the screen in a single slice. Two calls
    # running together interleave block by block, never line by line.
    from memstara.pipeline.reporting import show_console_summary
    await show_console_summary(show_what_agent_did, entry, _TRACE_DIR)

    # Agent output is usually JSON shaped like {"result": "..."}. Failing that, the raw text.
    try:
        return str(json.loads(result.output or "").get("result", "")), entry
    except (json.JSONDecodeError, TypeError, AttributeError):
        return result.output or "", entry


def write_execution_manifest() -> None:
    """Publish call identities and states atomically for the run-scoped viewer."""
    if _TRACE_DIR is None:
        return
    root = _TRACE_DIR.parent
    temporary = root / "execution.json.tmp"
    temporary.write_text(json.dumps({"calls": [
        {k: c.get(k) for k in ("stage", "run_id", "status", "started_at", "duration_seconds", "error",
                              "loop", "seq", "skill", "combination", "repetition", "step_evidence", "trace_status")}
        for c in _CALLS
    ]}), encoding="utf-8")
    temporary.replace(root / "execution.json")
    from memstara.pipeline.checkpoint import atomic_json
    atomic_json(root / "calls_checkpoint.json", _CALLS)


async def settle_finished_workers(registry: MCPServerRegistry, run_tag: str,
                                  finished_workers: set[str] | None = None,
                                  interpretation_outputs: dict[str, tuple] | None = None) -> None:
    """Reconcile only returned workers; other pipeline paths may still be running."""
    refreshed = await board_state(registry, run_tag)
    for task in refreshed.get("tasks", []):
        if finished_workers is not None and task.get("claimed_by") not in finished_workers:
            continue
        if task["status"] == "in_progress" and task["task_type"] == "interpret":
            from memstara.evaluation import active_plan
            if (active_plan() or {}).get("recovery_policy"):
                from memstara.pipeline.recovery import complete_interpretation
                worker = task.get("claimed_by", "")
                output = (interpretation_outputs or {}).get(worker)
                owned = [t for t in refreshed.get("tasks", [])
                         if t.get("claimed_by") == worker and t.get("status") == "in_progress"]
                if (output and len(owned) == 1 and output[1].get("status") == "completed"
                        and complete_interpretation(output[0])):
                    saved = await call_board_tool(registry, "submit_result", {
                        "task_id": task["task_id"], "worker": worker, "interpretation": output[0]})
                    if saved.get("ok"):
                        note(f"Controller saved the returned interpretation for task {task['task_id']}.")
                        if _TRACE_DIR:
                            with (_TRACE_DIR.parent / "controller_handoffs.jsonl").open("a") as audit:
                                audit.write(json.dumps({"task_id": task["task_id"], "worker": worker,
                                                        "agent_run_id": output[1].get("run_id"),
                                                        "source": "completed_agent_response"}) + "\n")
                        continue
                    if saved.get("error"):
                        raise RuntimeError("Returned interpretation could not be committed safely")
                recovered = await call_board_tool(registry, "recover_interpretation", {
                    "task_id": task["task_id"], "worker": task.get("claimed_by", "")})
                if recovered.get("error"):
                    raise RuntimeError("Could not safely recover the unfinished interpretation")
                if recovered.get("ok"):
                    note(f"Interpretation task {task['task_id']} will retry once using the saved ML result.")
                    continue
        if (finished_workers is not None and task["status"] == "in_progress"
                and task["task_type"] == "data"):
            recovered = await call_board_tool(registry, "recover_data_handoff", {
                "task_id": task["task_id"], "worker": task.get("claimed_by", "")})
            if recovered.get("error"):
                raise RuntimeError("Could not safely recover the unfinished data handoff")
            if recovered.get("ok"):
                note(f"Data task {task['task_id']} returned without submission; retrying the handoff.")
                continue
        if task["status"] == "in_progress" and task["task_type"] in ("data", "interpret"):
            finalized = await call_board_tool(registry, "submit_result", {
                "task_id": task["task_id"], "worker": task.get("claimed_by", ""),
                "error": "Worker finished without handing off a valid stage result. "
                         "Review the trace before retrying this trial."})
        if task["task_type"] == "ml" and task["status"] == "in_progress":
            finalized = await call_board_tool(registry, "submit_result", {
                "task_id": task["task_id"], "worker": task.get("claimed_by", "")})
            if finalized.get("error"):
                finalized = await call_board_tool(registry, "submit_result", {
                    "task_id": task["task_id"], "worker": task.get("claimed_by", ""),
                    "error": "ML worker ended without a valid measured evaluation. "
                             "Review the tool trace and rerun this trial."})
            if finalized.get("status") == "failed":
                note(f"ML task {task['task_id']} failed: "
                     f"{finalized.get('reason', 'evaluation failed')}")
        if task["status"] == "in_progress" and task["task_type"] in ("data", "ml", "interpret"):
            if finalized.get("error") or not finalized.get("ok"):
                raise RuntimeError("Could not reconcile a finished worker with its task state")


async def call_report(*args, **kwargs) -> tuple[str, dict[str, Any]]:
    """Run a scoped specialist when frozen; preserve historical report behavior."""
    from memstara.evaluation import active_plan
    from memstara.specialist_explanation import execute
    plan = active_plan() or {}
    if not plan.get("specialist_explanation_policy"):
        if plan.get("run_tag") and _TRACE_DIR is not None:
            from memstara.report_inputs import execute as execute_scoped_report
            return await execute_scoped_report(
                plan, _CURRENT_LOOP.get(), _TRACE_DIR.parent, args, kwargs,
                _call_report_default, call_board_tool)
        return await _call_report_default(*args, **kwargs)
    run_dir = _TRACE_DIR.parent if _TRACE_DIR else None
    text, entry = await execute(plan, _CURRENT_LOOP.get(), run_dir,
                                args, kwargs, _call_report_default, call_board_tool)
    if entry.get("status") != "completed":
        if run_dir:
            save_report(run_dir, text, entry)
        from memstara.pipeline.failures import stop_execution
        stop_execution(run_dir, "report", _CURRENT_LOOP.get(),
                       RuntimeError(entry.get("error", "Specialist Explanation failed")))
    return text, entry


async def _call_report_default(*args, **kwargs) -> tuple[str, dict[str, Any]]:
    """Retry the read-only reporting stage once; never replay data/ML writes."""
    for attempt in range(2):
        try:
            text, entry = await call_agent(*args, **kwargs)
        except PipelineExecutionFailure:
            raise
        except Exception as exc:
            text, entry = "", {"status": "failed", "error": type(exc).__name__}
        if entry.get("status") == "completed" and text.strip():
            return text, entry
        if attempt == 0:
            note("Report did not complete; retrying the read-only report once using saved results.")
    return text, entry


def save_report(run_dir: Path, text: str, entry: dict[str, Any]) -> bool:
    """An empty or failed agent response must never become a successful report."""
    complete = entry.get("status") == "completed" and bool(text.strip())
    status = {"status": "completed" if complete else "failed", "agent_run_id": entry.get("run_id"),
              "error": None if complete else entry.get("error", "Explanation agent returned no report text")}
    if entry.get("specialist_explanation"):
        status["specialist_explanation"] = entry["specialist_explanation"]
    (run_dir / "report_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    if complete:
        temporary = run_dir / "report.md.tmp"
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(run_dir / "report.md")
    return complete


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

    call["actual_tools"] = [item.get("tool", "") for step in steps for item in _flatten_calls(step.tool_call)]
    call["tool_policy_violations"] = sorted(set(call["actual_tools"]) - set(call.get("allowed_tools", [])))
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
        from motoro.runner import get_run, get_run_steps
        from memstara.pipeline.request_evidence import write_private
        identifier = uuid.UUID(call['run_id'])
        run = await get_run(identifier)
        steps = await get_run_steps(identifier)
        if run is None or not steps:
            raise ValueError('Agent step evidence unavailable')
        relative = f'trace/{identifier}.steps.json'
        call['step_evidence'] = {'path': relative, **write_private(_TRACE_DIR.parent / relative, {
            'schema_version': 1, 'run_id': str(identifier), 'stage': call['stage'], 'loop': call.get('loop'),
            'input': call.get('prompt'), 'allowed_tools': call.get('allowed_tools', []),
            'run': run, 'steps': steps,
        })}
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
        requests = drain_llm_requests(call["run_id"])
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
        call['trace_status'] = 'exported'
    except Exception as e:  # noqa: BLE001 - a failure to record must not wreck the run
        call['trace_status'] = 'unavailable'
        print(f"  trace failed {call['seq']:02d} {call['stage']}: {type(e).__name__}",
              file=sys.stderr)
    finally:
        try:
            write_execution_manifest()
        except (OSError, TypeError, ValueError):
            print('Trace manifest write failed; audit evidence is incomplete', file=sys.stderr)


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
    roster_path = run_dir / "prompts.json"
    roster = json.loads(roster_path.read_text()) if roster_path.exists() else {}
    # Combination agents are provisioned per combination; the initial roster is
    # only a template and must not falsely report that those agents never ran.
    manifests = sorted(run_dir.glob("loop_*_flavors.json"))
    if manifests:
        roster = {}
        for path in manifests:
            for agent in json.loads(path.read_text())["agents"]:
                roster[agent["agent_id"]] = {
                    "stage": agent["stage"], "agent_id": agent["agent_id"],
                    "playbook": agent["id"], "skill_hash": agent["hash"],
                }
    factors = []
    for key, agent in roster.items():
        if key.startswith("_"):
            continue
        actual = [c for c in _CALLS if c.get("agent_id") == agent.get("agent_id")]
        factors.append({"agent": agent.get("stage", key), "agent_id": agent.get("agent_id"),
                        "enabled": True, "skill": agent.get("playbook"),
                        "called": bool(actual), "calls": len(actual),
                        "investigated": any(c.get("stage", "").startswith("hypothesis") for c in actual),
                        "completed": sum(c.get("status") == "completed" for c in actual)})
    (run_dir / "factors.json").write_text(json.dumps({"agents": factors, "calls": _CALLS}, indent=2))
    print("Execution factors: " + json.dumps(factors))
    return len(_CALLS)


def board_tool_text(raw) -> str:
    """Validate transport evidence without exposing the provider's error content."""
    if isinstance(raw, tuple):
        if len(raw) != 2 or raw[0] is not False:
            raise RuntimeError("Blackboard tool failed or returned an invalid response envelope")
        raw = raw[1]
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError("Blackboard tool returned no response text")
    return raw


async def board_state(registry: MCPServerRegistry, run_tag: str) -> dict:
    """What is on the board right now, straight from the tool the agents use.

    The database is not searched directly; the board is read through **the same window
    the people use.** That way the board on my screen cannot drift out of step with the
    board they see.
    """
    server = await get_server_by_name("memstara-blackboard")
    if server is None:
        raise RuntimeError("Blackboard server is not registered")
    from motoro.services.mcp_service import call_server_tool

    from memstara.pipeline.board_reads import verified_read, BoardReadError
    async def read_once():
        async with asyncio.timeout(30):
            raw = await call_server_tool(server.id, "read_board", {"run_tag": run_tag}, registry=registry)
        return decode_board_state(board_tool_text(raw))
    directory = _TRACE_DIR.parent if _TRACE_DIR else None
    try:
        return await verified_read(read_once, directory=directory)
    except BoardReadError as exc:
        from memstara.pipeline.failures import stop_execution
        stop_execution(directory, "board", _CURRENT_LOOP.get(), exc,
                       code="board_read_unavailable",
                       message=f"Execution state could not be read ({exc.code}). Saved results are retained; "
                               "see board_read_events.jsonl for recovery attempts.")


def decode_board_state(text: str) -> dict:
    """An unavailable board is never evidence that all work is finished."""
    try:
        state = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("Blackboard returned invalid JSON; pipeline cannot establish task state") from exc
    if isinstance(state, dict) and "error" in state:
        from memstara.pipeline.board_reads import response_error
        raise response_error(state)
    if (not isinstance(state, dict) or
            not isinstance(state.get("tasks"), list) or type(state.get("count")) is not int):
        raise RuntimeError("Blackboard read failed or returned an invalid task collection")
    if state["count"] != len(state["tasks"]):
        raise RuntimeError("Blackboard task count is inconsistent")
    return state


#: Matcher tools whose calls are worth keeping. Both live on the semantic-matcher
#: server; nothing else it exposes produces candidate lists.
_MATCHER_TOOLS = ("match_concepts", "match_concept")


def _matcher_call_failed(result: Any) -> bool:
    """Did this matcher call actually answer, or did it come back an error?"""
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
    if server is None:
        note("(could not attach matcher records: blackboard server is not registered)")
        return written, refused
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
    if server is None:
        raise RuntimeError("Blackboard server is not registered")
    async with asyncio.timeout(30):
        raw = await call_server_tool(server.id, tool, args, registry=registry)
    # Sometimes the return is an (is-it-an-error, body) tuple, sometimes only the body —
    # read_board_via_tool already does the same thing in the same place.
    text = board_tool_text(raw)
    try:
        response = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Blackboard tool returned invalid JSON") from exc
    if not isinstance(response, dict):
        raise RuntimeError("Blackboard tool response must be a JSON object")
    return response


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
        empty list means no experiment can be started. `recycled` is True after
        bounded attempts produced no executable question. Unused questions from
        this exact run and wave can be recovered; older waves are never reassigned.
        It is returned rather than only printed because the run is otherwise unable to
        tell "investigated something new" from "investigated the same thing again".
    """

    if want <= 0:
        return [], True

    # The first sentence says which of the agent's two jobs this call is. Its system
    # prompt describes both, so without it the agent has to infer from the tools it was
    # handed which half of its own instructions applies — and inferring is exactly what
    # the per-call message exists to make unnecessary.
    ask = (
        "This call is the question-writing half of your work: decide what gets asked, "
        "and do not investigate anything. "
        f"Propose {want} question(s) for wave {wave} of run '{run_tag}'. "
        "Call propose_questions, repair any rejection using its feedback, "
        f"with origin_run='{run_tag}' and origin_wave={wave}. "
    )
    from memstara.evaluation import active_plan
    from memstara.pipeline.question_contract import generation_instructions
    from memstara.pipeline.iteration_learning import enabled as learning_enabled, summarize, save_feedback, instructions
    snapshot = active_plan()
    from memstara.pipeline.feature_selection import scoped
    snapshot = scoped(snapshot, wave)
    if learning_enabled(snapshot):
        history = await call_board_tool(registry, "read_board", {"run_tag": run_tag}) if wave else {"tasks": []}
        if not isinstance(history, dict) or "tasks" not in history or history.get("error"):
            raise RuntimeError("Cannot read prior iteration evidence; refusing to silently generate without feedback")
        context = summarize(history["tasks"], snapshot, wave)
        save_feedback(context)
        ask += instructions(context)
    else:
        ask += ("Generate a primary, knowledge-driven hypothesis using only KG/OKF evidence. "
                "Use read_question_catalog only to avoid duplicate questions. Do not use previous "
                "AUC, feature importance, successful features or failed features to choose the question. "
                "Keep any evidence-informed refinement separate from this primary hypothesis.")
    from memstara.pipeline.combination_questions import (
        enabled as independent_questions, instructions as combination_instructions)
    if independent_questions(snapshot):
        ask += combination_instructions()
    ask += generation_instructions(snapshot)
    from memstara.pipeline.feature_context import instructions as feature_instructions
    ask += feature_instructions(snapshot)
    from memstara.pipeline.feature_selection import instructions as selection_instructions
    ask += selection_instructions(snapshot, wave)
    if snapshot and snapshot.get("question"):
        ask += " Research question: " + snapshot["question"]
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
        #
        # Each configured hypothesis standard writes a share of the total budget.
        # Writers execute concurrently; a budget smaller than the roster activates
        # only the first `want` workers. This avoids multiplying question volume.
        writers = [(k, agent) for k, agent in agents.items() if k.startswith("hypothesis")]
        async def write_one(slot, key, agent):
            allocation = want // len(writers) + (slot < want % len(writers))
            if not allocation:
                return
            from memstara.pipeline.question_repair import retry_instructions, prior_failure_instructions
            repair = (retry_instructions(snapshot or {}, wave, key)
                      + ("" if independent_questions(snapshot) else
                         prior_failure_instructions(snapshot or {}, wave, key)))
            await call_agent(
                agent, ask + repair + f" Your writer identity is '{key}'. Pass writer='{key}' to propose_questions. "
                f"Propose exactly up to {allocation} grounded questions; this replaces the total requested above.",
                tools=by_stage["question"], registry=registry, stage=f"question{wave}-{slot + 1}",
            )
        for attempt in range(2):
            # Recover a saved but not yet executed question from THIS wave only.
            # Never reassign an older question to a different feedback context.
            current = await call_board_tool(registry, "read_questions", {"status": "open", "limit": 200})
            if not isinstance(current, dict) or current.get("error") or "questions" not in current:
                raise RuntimeError("Question bank unavailable; generation cannot safely be replayed")
            fresh = [q for q in current["questions"] if q.get("origin_run") == run_tag
                     and q.get("origin_wave") == wave and not q.get("times_used", 0)]
            if fresh:
                return fresh[:want], False
            if attempt:
                ask += (" Recovery attempt: no valid question was persisted. Check tool rejection reasons. "
                        "Use concrete clinical entities from Instances, source_ids from okf_read, "
                        "an array of okf_tags, and "
                        "parent_task_ids plus learning_goal when prior evidence is supplied. "
                        + ("A supported question from an earlier Loop is permitted; submit it for this Loop. "
                           if independent_questions(snapshot) else
                           "Do not repeat an already banked question from an earlier wave.")
                        + "Search relevant domains and read source documents before declaring no support; "
                        "do not infer corpus exhaustion from title search alone.")
            tasks = [asyncio.create_task(write_one(i, k, a)) for i, (k, a) in enumerate(writers)]
            try:
                await asyncio.gather(*tasks)
            finally:
                # A rejected provider request is not an empty question bank. Stop
                # sibling writers promptly instead of waiting for another paid turn.
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        after = await call_board_tool(registry, "read_questions", {"status": "open", "limit": 200})
        if not isinstance(after, dict) or after.get("error") or "questions" not in after:
            raise RuntimeError("Question bank unavailable after generation")
        fresh = [q for q in after["questions"] if q.get("origin_run") == run_tag
                 and q.get("origin_wave") == wave and not q.get("times_used", 0)]
        if fresh:
            return fresh[:want], False
        note("No executable question after two attempts; no fallback or completed iteration is claimed.")
        return [], True
    except PipelineExecutionFailure:
        raise
    except Exception as exc:
        # Do not hide infrastructure failures as a depleted corpus or restart a
        # mutation when the read-back itself is unavailable.
        raise RuntimeError("Question generation could not be verified") from exc


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

        if status not in ("ready", "in_progress"):
            continue

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
    """What the explanation agent is told about the branch this run was confined to.

    A function rather than a variable because the explanation agent is called from two
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


#: The stages `--playbook-*` exists for. Not `BOARD_AGENT_NAMES` and not `stores.HOME`,
#: although it happens to hold the same five names: this list answers *which prompts may
#: be given a behavioural standard*, and a stage could be added to the pipeline without
#: being one. Written out so that adding a stage does not silently add a flag.
PLAYBOOK_STAGES = ("hypothesis", "data", "ml", "interpreter", "report")


def chosen_playbooks(args: argparse.Namespace) -> dict[str, list[str]]:
    """Stage -> the standards this run gave it, in worker order."""
    out: dict[str, list[str]] = {}
    for stage in PLAYBOOK_STAGES:
        field = "playbook_explanation" if stage == "report" else f"playbook_{stage}"
        selected = getattr(args, field, getattr(args, f"playbook_{stage}", ""))
        names = [b.strip() for b in selected.split(",") if b.strip()]
        if names:
            out[stage] = names
    return out


async def run(args: argparse.Namespace, run_dir: Path) -> int:
    """The body of the run. (1) through (6) of "How to read this file" at the top are
    here, in that order."""
    from memstara.control.catalog import ensure_explanation_enabled, ensure_hypothesis_enabled
    ensure_hypothesis_enabled(chosen_playbooks(args).get('hypothesis', []))
    ensure_explanation_enabled(chosen_playbooks(args).get('report', []))
    schedule = json.loads(getattr(args, 'combination_plan', '') or 'null')
    if schedule:
        ensure_hypothesis_enabled([item['id'] for item in schedule.get('skills', {}).get('hypothesis', [])])
        ensure_explanation_enabled([item['id'] for item in schedule.get('skills', {}).get('report', [])])
    if getattr(args, 'data_mode', 'dataset') == 'proposal':
        from memstara.pipeline.proposal import run as run_proposal
        return await run_proposal(args, run_dir)
    from memstara.pipeline.exploration import ExecutionGate
    global _EXECUTION_GATE
    _EXECUTION_GATE = ExecutionGate(run_dir)
    from memstara.pipeline.preparation import prepare_execution
    prepared = await prepare_execution(args, run_dir, chosen_playbooks(args))
    combination_plan = prepared.combination_plan
    stage_models = prepared.stage_models
    from memstara.pipeline.checkpoint import Checkpoint, atomic_json
    checkpoint = None if args.report_only else Checkpoint(run_dir, resume=args.resume)
    _EXECUTION_GATE.checkpoint = checkpoint
    if checkpoint and not args.resume:
        first_loop = getattr(args, 'start_loop', 1)
        if not 1 <= first_loop <= args.waves:
            raise ValueError('Retry position exceeds the frozen schedule')
        checkpoint.state['next_wave'] = first_loop - 1
        checkpoint.save()
        if getattr(args, 'retry_source_run', ''):
            atomic_json(run_dir / 'retry_lineage.json', {
                'source_run_tag': args.retry_source_run, 'first_loop': first_loop,
                'last_loop': args.waves, 'mode': 'new_attempt_from_failed_loop',
                'prior_results': 'retained_in_source_execution',
                'validation_reserve': 'new_execution_partition',
            })
        atomic_json(run_dir / "resume_arguments.json", vars(args))
    from memstara.blackboard import create
    await create()  # Apply additive result/provenance columns before the first tool call.
    from memstara.experiment_registry import sync as sync_registry
    await sync_registry(run_dir, evidence=False)
    log_path = setup_logging(level="DEBUG" if args.verbose else "INFO", log_file=run_dir / "run.jsonl")

    # Decide where the trace files go first. It has to be made **before** the first agent
    # is called, so a file appears the moment that call ends — that is why it can be read
    # while debugging.
    global _TRACE_DIR
    _TRACE_DIR = run_dir / "trace"
    _TRACE_DIR.mkdir(parents=True, exist_ok=True)
    if args.resume and (run_dir / "calls_checkpoint.json").exists():
        _CALLS[:] = json.loads((run_dir / "calls_checkpoint.json").read_text())
    print()
    print("=" * 74)
    print(f" board pipeline — run named '{args.run_tag}'")
    print("=" * 74)
    print(f"   trials      {args.trials if not args.report_only else '(report only)'}")
    print(f"   outcome     {args.y_column}")
    print(f"   data        {os.environ.get('MEMSTARA_DATASET_PATH','(none)')}")
    print(f"   knowledge   {os.environ.get('AGENTIC_OKF_BUNDLE_DIR','(none)')}")
    print(f"   skill       {args.skill or '(whole bundle)'}")
    # One line per stage, and a stage with several standards prints all of them —
    # "hypothesis=a,b,c" is the thing worth seeing before a run of three workers starts.
    _books = ' · '.join(f"{s}={','.join(b)}" for s, b in chosen_playbooks(args).items())
    print(f"   playbooks   {_books or '(none)'}")
    print(f"   record dir  {run_dir}")
    print(f"   trace files {_TRACE_DIR.name}/  (one more each time a person is called)")

    # -- (1) provision the configured agents ----------------------------------------
    #
    # Fetch the role description that says what each of them does. If this is the first
    # time, write it. Running it again and again only finds the same people back; it
    # does not multiply them.
    step("(1)", "provision the configured agents", "fetch the role descriptions")
    playbooks = chosen_playbooks(args)
    # The worker roster reflects the selected hypothesis and interpretation standards.
    # `workers` is the roster —
    # provisioning builds the agents from it and `prompts.json` below is written from it.
    workers = board_workers(playbooks, args.run_tag if args.pipeline_id else "")
    agents = await provision_board_agents(
        provider=args.provider, model=args.model, playbooks=playbooks,
        namespace=args.run_tag if args.pipeline_id else "", stage_models=stage_models or None
    )
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
    # to describe a stage that was not provisioned. The names and the standards come from
    # `board_workers`, which is the same function provisioning built the agents from —
    # deriving them here a second time is how a record comes to describe a run that did
    # not happen.
    #
    # **The keys are workers, not stages.** A run with several hypothesis standards has
    # `hypothesis`, `hypothesis#2`, … and each carries its own playbook name and its own
    # digest, which is what makes "which file went to which worker" answerable from the
    # run directory. `file` is the stage's prompt and is therefore the same for all of
    # them; the digests differ because the standard spliced into it differs.
    #
    # `_run` is not a stage, and the underscore is what says so. The skill belongs in
    # this file rather than in a new one because it answers the same question the
    # digests answer — *what produced this run* — and a branch of the corpus decides
    # what could be found at least as much as a wording decides what was asked.
    #
    # The playbook is recorded **per stage and by name**, beside the digest that already
    # covers it. The digest alone would say *this stage was told something different* and
    # not *which standard it was told to work to*; the name alone would not survive the
    # file being edited afterwards. Null where a stage was given none, rather than absent,
    # so a reader can tell "no standard" from "written before playbooks existed".
    (run_dir / "prompts.json").write_text(
        json.dumps(
            {
                "_run": {"run_tag": args.run_tag, "skill": args.skill or None},
                **{
                    key: {
                        "agent": name,
                        "agent_id": str(agents[key]),
                        "file": f"src/memstara/prompts/board/{stage_of(key)}.md",
                        "playbook": book or None,
                        **prompt_digest(f"board/{stage_of(key)}", book),
                    }
                    for key, (name, book) in workers.items()
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
    from memstara.pipeline.scheduler import StageWorkers
    live_workers = StageWorkers()
    seed_task = None
    # Startup is not user-paused work and must retain a finite connection cap.
    async with asyncio.timeout(300):
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
        from memstara.pipeline.failures import require_tools
        from memstara.pipeline.ablation import enabled as ablation_enabled
        from memstara.evaluation import active_plan
        required = {**BOARD_TOOLS, "question": QUESTION_TOOLS}
        if args.report_only:
            required = {"report": BOARD_TOOLS["report"]}
        elif args.no_curator:
            required.pop("question")
        if ablation_enabled(active_plan()):
            required = {stage: {name for name in names if not name.startswith('okf_')}
                        for stage, names in required.items()}
        require_tools(by_stage, required, run_dir)
        # Print who got what. Later it can be confirmed from the log alone.
        step("(3)", "decide who gets which button", "cut them off from other people's work")
        _ROLE = {"hypothesis": "hypothesis agent (answering)", "data": "data agent",
                 "ml": "ml agent", "interpreter": "interpreter agent",
                 "report": "explanation agent", "question": "hypothesis agent (asking)"}
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
        # explanation agent) is called, so it is cheap.
        #
        # It also makes a report for a run that was interrupted or only partly finished,
        # out of whatever had piled up by then.
        if args.report_only:
            _CURRENT_LOOP.set(None)
            step("(6)", "wrap up at the end",
                 f"read the finished drawer of '{args.run_tag}' — (4) and (5) are skipped")
            note("call the explanation agent once (the only LLM call of this run)")
            text, report_entry = await call_report(
                agents["report"],
                f"Write the report for run '{args.run_tag}'. Call read_results with that "
                f"run_tag.{report_skill_note(args.skill)}",
                tools=by_stage["report"], registry=registry, stage="report",
            )
            if not save_report(run_dir, text, report_entry):
                note("Report failed; see report_status.json and the report trace. Analysis results are preserved.")
                return 1
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
        # across waves, and at the end they are handed to the explanation agent too.
        if checkpoint is None:
            raise RuntimeError("Empirical execution requires a durable checkpoint")
        missing_trials: list[int] = list(checkpoint.state["missing_trials"])

        # Before the first wave, take back anything this tag left in_progress last time.
        # `reclaim_stalled` is also called inside the work loop, but only once that loop
        # has decided it has nothing to do — so re-running a tag that died mid-wave would
        # seed a whole new wave before noticing the old task was still there. Calling it
        # here is what makes "same --run-tag again" mean "carry on where it stopped".
        # stale_after still applies: a run that is genuinely still alive holds the
        # advisory lock above, so we cannot get here while one is.
        if args.resume:
            if checkpoint.state.get('calls') or any(p['status'] != 'done' for p in checkpoint.state['phases'].values()):
                from memstara.pipeline.paused_recovery import reconcile
                await reconcile(checkpoint, args.run_tag, asyncpg.connect, dsn())
            recovery_board = await board_state(registry, args.run_tag)
            if recovery_board.get("error") or "tasks" not in recovery_board:
                raise RuntimeError("Cannot verify saved task state for recovery")
            if any(t.get("status") == "in_progress" for t in recovery_board["tasks"]):
                from memstara.pipeline.checkpoint import RecoveryBlocked
                raise RecoveryBlocked("Uncommitted task ownership requires review before recovery")
        recovered = 0 if args.resume else await reclaim_stalled(registry, args.run_tag, args.stale_after)
        if recovered:
            note(f"returned {recovered} tasks left by the last run to the queue — "
                 "carrying on")

        # How many waves in a row produced no new question. It stops when it reaches
        # `--stop-after-dry`.
        #
        # The corpus is finite — 333 documents across 37 tags — so the bank runs dry by
        # construction, not by accident. `--waves N` is a count, and a count cannot know
        # when there is nothing left to ask; this is the part that can.
        dry_streak = checkpoint.state["dry_streak"]
        waves_run = checkpoint.state["waves_run"]  # Seeded waves may be fewer than args.waves.
        seeded_total = checkpoint.state["seeded_total"]  # Actual hypotheses requested; used by Explanation.
        from memstara.pipeline.exploration import (rounds, wait_for_new_questions, write_progress,
                                                    record_round, round_summary, finalize_rounds)
        async for wave in rounds(args.waves, args.continuous, run_dir, start=checkpoint.state["next_wave"]):
            from memstara.combinations import execution_label
            note(execution_label(wave + 1, combination_plan) + " · starting research process")
            _CURRENT_LOOP.set(wave + 1)
            if combination_plan:
                from memstara.combinations import prepare_loop
                agents, flavors, playbooks, namespace = await prepare_loop(
                    combination_plan, wave + 1, provider=args.provider, model=args.model,
                    run_tag=args.run_tag, provision=provision_board_agents, stage_models=stage_models or None,
                )
                _CURRENT_FLAVORS.set(flavors)
                workers = board_workers(playbooks, namespace)
                atomic_json(run_dir / f"loop_{wave + 1}_flavors.json", flavors)
            record_round(run_dir, wave + 1, "running")
            write_progress(run_dir, wave + 1, "hypothesis")
            base = wave * args.trials          # trial numbers carry on across waves
            if args.continuous or args.waves > 1:
                print(f"\n{'─' * 68}\n round {wave + 1}/"
                      f"{'continuous' if args.continuous else args.waves}\n{'─' * 68}")

            # -- (3') decide what to ask --------------------------------
            questions: list[dict] = []
            recycled = False
            if not args.no_curator:
                step("(3')", "decide what to ask",
                     "the question step follows the frozen knowledge/iteration-feedback policy"
                     + f" and makes {args.trials} questions")
                questions, recycled = await checkpoint.phase(
                    f"{wave}:questions", lambda agents=agents, wave=wave: questions_for_wave(
                    registry, agents, by_stage,
                    run_tag=args.run_tag, wave=wave, want=args.trials, skill=args.skill,
                ))
                for q in questions:
                    note(f"question #{q['question_id']} {q['text']}"
                         f"  [{'·'.join(q.get('okf_tags') or []) or 'no tags'}]")
                done("(3')", f"{len(questions)} questions"
                     + (" · no executable question saved" if recycled else ""))

            # -- stop when it runs dry -----------------------------------
            #
            # Two consecutive dry waves, not one. The question step can come back
            # empty-handed once by mistake, and that is not the same thing as a corpus
            # with nothing left in it. The break happens *before* seeding, so a run that
            # has run dry pays for one more question call and not for a whole wave of
            # trials it has already done.
            if not questions and not args.no_curator:
                from memstara.pipeline.combination_questions import skip_unavailable
                from memstara.evaluation import active_plan
                if skip_unavailable(active_plan(), run_dir, wave, checkpoint,
                                    dry_streak=dry_streak, waves_run=waves_run,
                                    seeded_total=seeded_total, missing_trials=missing_trials):
                    dry_streak += 1
                    note("This combination has no executable question; recorded as skipped. Continuing the schedule.")
                    continue
                record_round(run_dir, wave + 1, "blocked",
                             "No executable question after bounded recovery; no analysis was completed.")
                write_progress(run_dir, wave + 1, "hypothesis")
                from memstara.pipeline.question_repair import require_executable_questions
                require_executable_questions(questions, run_dir, wave)
            dry_streak = dry_streak + 1 if recycled else 0
            # Workspace exploration keeps searching until the configured Loop ceiling
            # or an explicit stop; two rejected candidates must not silently end it.
            dry_limit = 0 if args.continuous or args.pipeline_id else args.stop_after_dry
            if dry_limit and dry_streak >= dry_limit:
                note(f"the questions have run dry — {dry_streak} waves in a row produced "
                     f"no new question. Stopping without starting wave "
                     f"{wave + 1}/{args.waves}")
                break
            if args.continuous and not questions and not args.no_curator:
                note("No new grounded questions; waiting before exploring again. Stop remains available.")
                checkpoint.advance(wave, dry_streak=dry_streak, waves_run=waves_run,
                               seeded_total=seeded_total, missing_trials=missing_trials)
                await wait_for_new_questions(run_dir, dry_streak)
                continue
            waves_run += 1

            if not questions and not args.no_curator:
                note("No grounded primary question was produced; skipping this wave without a fallback hypothesis.")
                checkpoint.advance(wave, dry_streak=dry_streak, waves_run=waves_run,
                               seeded_total=seeded_total, missing_trials=missing_trials)
                continue

            # If question generation was explicitly switched off, fall back to the
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

            skill_note = (
                f" The knowledge bundle is confined to {args.skill} for this run; "
                f"okf_search and okf_read return that branch and nothing else."
                if args.skill else ""
            )

            async def seed_one(i: int, q: dict[str, Any], slot: int, *,
                               from_bank: bool = from_bank, skill_note: str = skill_note, agents=agents):
                """Call one hypothesis worker and attach what its matcher calls saw.

                `slot` is the position inside the concurrent chunk, and it is what
                chooses the agent. With one standard (or none) every slot resolves to
                the same agent and this is the loop it always was; with several,
                slot k carries the k-th standard for the whole run, so a column that
                two workers agreed on is two standards agreeing rather than one
                standard asked twice.
                """
                text = q["text"]
                # Trial identity and configured-agent identity are separate. Reusing
                # a slot in a later trial must not create another visible agent.
                worker_key = "hypothesis" if slot == 0 else f"hypothesis#{slot + 1}"
                writer = q.get("writer")
                if isinstance(writer, str) and writer in agents and writer.startswith("hypothesis"):
                    worker_key = writer
                wid = worker_key
                agent_id = agents.get(worker_key, agents["hypothesis"])
                # Both branches open by naming which of the agent's two jobs this is —
                # the counterpart of the sentence in `questions_for_wave`. The system
                # prompt covers writing questions as well as answering them, so a call
                # that does not say which it is leaves the agent to guess.
                if from_bank:
                    ask = (
                        f"This call is the answering half of your work: investigate the "
                        f"question you are handed and put the work on the board. "
                        f"You are worker '{wid}'. Call claim_question with "
                        f"run_tag='{args.run_tag}', worker='{wid}', question_id={q['question_id']} to be given your "
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
                from memstara.pipeline.question_contract import enabled, hypothesis_text, validate_saved
                from memstara.evaluation import active_plan
                plan = active_plan()
                if enabled(plan):
                    contract = validate_saved(q.get("question_contract"), text, plan)
                    if contract.get("source_ids"):
                        ask += (" The question was derived from these source document IDs: "
                                + json.dumps(contract["source_ids"]) + ". Open them directly with okf_read "
                                "section='auto' BEFORE searching. A metadata/title search returning zero hits "
                                "does not mean a clinical entity is absent from their Instances tables. "
                                "Use these document IDs as okf_concept_ids and source_id in feature_mapping. ")
                    ask += (" Preserve the assigned question exactly. Pass perspective exactly as the question text "
                            f"and hypothesis exactly as {hypothesis_text(contract)!r} to create_task. "
                            "Map only the question's predictor concepts; the target cannot change. "
                            "Supply feature_mapping entries with concept (the exact assigned name), column, "
                            "source_id (one of okf_concept_ids), and clinical rationale. Cover every assigned "
                            "concept and selected column. Read actual Instances and pass clinical entities "
                            "to match_concepts, never relation labels. "
                            "If those concepts cannot be mapped, stop without creating an unrelated task.")
                from memstara.pipeline.feature_selection import instructions as selection_instructions
                ask += selection_instructions(plan, i)
                _, call = await call_agent(
                    agent_id, ask,
                    tools=by_stage["hypothesis"], registry=registry, temperature=temperature_for(i),
                    stage=f"hypothesis{i}",
                )
                # Has to happen here, not at the end of the run. `submit_result` copies a
                # row from the board to the results table the moment it turns done, so a
                # trace attached after stage (5) would land on a board row whose result had
                # already been written without it — recorded in the place that gets cleared
                # and missing from the place that is kept.
                return i, await harvest_match_trace(registry, call)

            async def produce_hypotheses(questions=questions, base=base, from_bank=from_bank, seed_one=seed_one):
                # Keep each question with its author, serializing that author's
                # calls even when question-bank order differs from slot order.
                assignments: list[list[int]] = [[] for _ in range(args.hypothesis_agents)]
                writer_slots = {("hypothesis" if slot == 0 else f"hypothesis#{slot + 1}"): slot
                                for slot in range(args.hypothesis_agents)}
                for index, question in enumerate(questions):
                    slot = writer_slots.get(question.get("writer"), index % args.hypothesis_agents)
                    assignments[slot].append(index)
                async def produce_slot(slot):
                    for index in assignments[slot]:
                        from memstara.pipeline.recovery import ensure_artifact
                        trial = base + index
                        async def present(trial=trial):
                            current = await board_state(registry, args.run_tag)
                            if not isinstance(current, dict) or current.get("error") or "tasks" not in current:
                                raise RuntimeError("Cannot verify whether hypothesis work was committed")
                            return any(t["trial"] == trial for t in current["tasks"])
                        async def invoke(attempt, trial=trial, index=index):
                            if attempt:
                                note(f"Retrying hypothesis trial {trial}; no task was persisted.")
                            await seed_one(trial, questions[index], slot)
                        ok, reason = await ensure_artifact(invoke, present)
                        if not ok:
                            note(f"Hypothesis trial {trial} blocked: {reason}")
                async with asyncio.TaskGroup() as group:
                    for slot in range(args.hypothesis_agents):
                        group.create_task(produce_slot(slot))
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


            async def durable_seed():
                await produce_hypotheses()
                return list(missing_trials)
            async def restore_seed(wave=wave):
                saved_missing = await checkpoint.phase(f"{wave}:seed", durable_seed)
                missing_trials[:] = saved_missing
            seed_task = asyncio.create_task(restore_seed())
            state = await board_state(registry, args.run_tag)

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
            polling_laps = 0
            while True:
                state = await board_state(registry, args.run_tag)
                current_tasks = [t for t in state["tasks"] if base <= t["trial"] < base + args.trials]
                from memstara.pipeline.failures import ensure_tasks_not_failed
                ensure_tasks_not_failed(run_dir, wave + 1, current_tasks)
                current_stage = live_workers.progress_stage(
                    current_tasks, seed_done=seed_task.done())
                write_progress(run_dir, wave + 1,
                               current_stage, current_tasks)
                # Observe this run only.
                counts, retried = summarise(state["tasks"])            # status · what came back

                outcomes = await live_workers.completed()
                for _, outcome in outcomes:
                    if isinstance(outcome, PipelineExecutionFailure):
                        raise outcome
                    if isinstance(outcome, BaseException):
                        note(f"Worker failed: {type(outcome).__name__}: {outcome}")
                if outcomes:
                    await settle_finished_workers(registry, args.run_tag, {
                        f"{STAGE_TASK_TYPE[stage]}#{slot}" for (stage, slot), _ in outcomes},
                        {f"interpret#{slot}": outcome for (stage, slot), outcome in outcomes
                         if stage == "interpreter" and isinstance(outcome, tuple) and len(outcome) == 2})
                if seed_task.done():
                    await seed_task  # propagate producer/cleanup errors
                # Work can arrive while hypotheses are still being generated.
                if not counts and seed_task.done() and not live_workers.active:
                    done("(5)", f"the board is empty — after {polling_laps} laps")
                    break

                polling_laps += 1
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
                print(f"   [lap {polling_laps:>3}] {desc}{stuck}")

                # Give up on tasks that keep coming back. `retried` already counts the
                # extra claims. A terminal failure is observed on the next board read
                # and stops the execution before any further worker is launched.
                if args.max_attempts:
                    ready_ids = {t["task_id"] for t in state["tasks"] if t["status"] == "ready"}
                    doomed = [tid for tid, n in retried if n >= args.max_attempts and tid in ready_ids]
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
                    from memstara.interpretation_fanout import pending_slots
                    eligible = pending_slots(state["tasks"]) if stage == "interpreter" else None
                    for k in live_workers.available(stage, getattr(args, f"{ttype}_agents"), waiting, eligible):
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
                        live_workers.launch(stage, k, call_agent(
                            agents.get(stage if k == 1 else f"{stage}#{k}", agents[stage]),
                            f"You are worker '{wid}'. Claim a '{ttype}' task from run_tag "
                            f"'{args.run_tag}' and do your part. Pass worker='{wid}' to "
                            f"both claim_task and submit_result. A final text answer does not save results. "
                            "Call submit_result and verify its ok response before finishing.",
                            tools=by_stage[stage], registry=registry,
                            # Each worker gets its own trace file. Left as `stage`, two
                            # workers of one type would write trace/NN_data.txt over each
                            # other and the losing one's record would simply be absent.
                            stage=wid,
                        ))
                    worked = True

                # Reclaim only when no live worker can still own a task. A busy stage
                # does not prevent free stages from picking up newly ready work.
                if not live_workers.active and seed_task.done() and not worked:
                    await reclaim_stalled(registry, args.run_tag, args.stale_after)
                await live_workers.wait()

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


            verified_state = await board_state(registry, args.run_tag)
            verified_tasks = [t for t in verified_state["tasks"] if base <= t["trial"] < base + args.trials]
            analysis_complete = (bool(questions) and len(verified_tasks) == len(questions)
                                 and all(t["status"] == "done" for t in verified_tasks))
            record_round(run_dir, wave + 1, "analysis_complete" if analysis_complete else "blocked",
                         "" if analysis_complete else "One or more hypotheses produced no task or an analysis failed.")

            # Scoped final reports aggregate existing explanations; even a single
            # ordinary Loop must create its explanation before aggregation.
            scoped_report = bool((active_plan() or {}).get("run_tag")) and not (
                active_plan() or {}).get("specialist_explanation_policy")
            if combination_plan or args.continuous or args.waves > 1 or scoped_report:
                write_progress(run_dir, wave + 1, "report")
                text, report_entry = await checkpoint.phase(
                    f"{wave}:report",
                    lambda agents=agents, seeded_total=seeded_total, waves_run=waves_run: call_report(
                    agents["report"],
                    f"Write an interim report for run '{args.run_tag}'. Call read_results "
                    f"with that run_tag. {seeded_total} trials were requested across "
                    f"{waves_run} rounds. Exploration is ongoing. Identify missing and "
                    "failed results explicitly. Rank useful hypotheses by evidence and "
                    "limitations; interpretations are not independent experiments.",
                    tools=by_stage["report"], registry=registry, stage="report",
                ))
                report_saved = save_report(run_dir, text, report_entry)
                wave_state = await board_state(registry, args.run_tag)
                wave_tasks = [t for t in wave_state["tasks"] if base <= t["trial"] < base + args.trials]
                successful = (report_saved and len(wave_tasks) >= len(questions) and bool(questions)
                              and all(t["status"] == "done" for t in wave_tasks))
                record_round(run_dir, wave + 1, "completed" if successful else "blocked",
                             "" if successful else "Analysis or report incomplete; saved results remain available.")
                write_progress(run_dir, wave + 1, "report", wave_tasks, completed=successful)
            checkpoint.advance(wave, dry_streak=dry_streak, waves_run=waves_run,
                               seeded_total=seeded_total, missing_trials=missing_trials)


        # -- report -----------------------------------------------------
        # -- (6) wrap up at the end -------------------------------------
        #
        # The explanation agent reads **the finished drawer, not the board.** The board is a
        # workbench and disappears when it is cleared; the finished drawer is the record
        # that stays.
        _CURRENT_LOOP.set(None)
        summary = round_summary(run_dir)
        if not seeded_total and (summary or {}).get('skipped', 0):
            atomic_json(run_dir / 'pipeline_status.json', {
                'status': 'no_findings', 'report_completed': False,
                'unfinished_task_ids': [], 'missing_trials': [], 'exploration': summary,
                'message': ('All attempted combinations lacked an executable question; '
                            'no analysis or report was produced.'),
            })
            checkpoint.finish()
            return 0
        step("(6)", "wrap up at the end", "the explanation agent reads the finished drawer")
        # How many trials were seeded is told to the reporter, because the results table
        # cannot say it. read_results only returns rows that exist, so a trial that died
        # before create_task is invisible there — and a report that silently describes
        # three results as if three were all that were attempted is a false report.
        lost_note = (
            f" Trials {', '.join(str(i) for i in missing_trials)} produced no result at all "
            f"(not created or failed during execution); they will be absent from "
            f"read_results. Say so explicitly."
            if missing_trials else ""
        )
        report_state = await board_state(registry, args.run_tag)
        final_validation = None
        two_way_evaluation = False
        config_path = run_dir / "config.json"
        if config_path.is_file() and not args.report_only:
            from memstara.final_validation import run as run_final_validation
            from memstara.evaluation import active_plan
            frozen_config = active_plan() or json.loads(config_path.read_text())
            two_way_evaluation = frozen_config.get('partition_policy') == 'two_way_stratified_v1'
            if not two_way_evaluation:
                final_validation = run_final_validation(run_dir, frozen_config, report_state["tasks"])
                note("final independent validation: " + str(final_validation.get("status", "unknown")))
        validation_note = (
            " Two-way train/test policy: report each task's saved test metrics. There is no independent "
            "validation reserve and no final refit. Do not describe these test results as independent "
            "validation. Training-only CV may choose settings; test results must not tune them. "
            if two_way_evaluation else
            " Final independent-validation record, computed once after every exploration Loop: "
            + json.dumps(final_validation, ensure_ascii=False, allow_nan=False)
            + ". This record was withheld from all Loops. Describe its scope accurately; if its status is not "
              "completed, say independent validation metrics are unavailable. Do not tune or select candidates "
              "using this same reserve. "
        )
        incomplete = [{"trial": t["trial"], "status": t["status"], "error": t.get("error", "")}
                      for t in report_state["tasks"] if t["status"] != "done"]
        text, report_entry = await checkpoint.phase("final_report", lambda: call_report(
            agents["report"],
            f"Write the report for run '{args.run_tag}'. Call read_results with that run_tag. "
            f"{seeded_total} trials were seeded across {waves_run} wave(s)"
            + (f" (of {args.waves} requested; some scheduled Loops did not seed an analysis)"
               if not args.continuous and waves_run < args.waves else "")
            + f". State how many of those {seeded_total} produced a result.{lost_note}"
            + " Skipped question-generation Loops (not completed analyses): "
            + json.dumps(round_summary(run_dir))
            + " Each result may contain several interpretations of ONE ML evaluation. "
              "Compare all interpreter perspectives, including disagreement and unavailable interpretations. "
              "Do not count interpretations as independent hypotheses or repeated ML experiments. "
            + validation_note
            + report_skill_note(args.skill) + " Unfinished trials (report these explicitly): " + json.dumps(incomplete),
            tools=by_stage["report"], registry=registry, stage="report",
        ))
        report_ok = save_report(run_dir, text, report_entry)
        finalize_rounds(run_dir, report_ok)
        summary = round_summary(run_dir)
        if summary:
            write_progress(run_dir, summary["attempted"], "report",
                           completed=summary["outcome"] == "completed")

        # The last state of the board is saved whole as well. It is what a later retrace
        # reads.
        final = await board_state(registry, args.run_tag)
        (run_dir / "board.json").write_text(
            json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        run_ids = [t.get("task_id") for t in final["tasks"]]
        print(f"\n{'=' * 68}\n{text}\n{'=' * 68}")
        print(f"\nrun directory: {run_dir}")
        report_file = "report.md" if report_ok else "report_status.json (failed)"
        print(f"  {report_file} · board.json ({len(run_ids)} tasks) · prompts.json")
        if log_path:
            print(f"  {log_path.name}")
        if not report_ok:
            note("Report failed; see report_status.json. Completed analysis results are preserved.")
        unfinished = [t["task_id"] for t in final["tasks"] if t["status"] != "done"]
        validation_ok = final_validation is None or final_validation.get("status") == "completed"
        successful_analyses = (
            report_ok and validation_ok and bool(final["tasks"]) and not unfinished
            and not missing_trials and not (summary or {}).get("blocked", 0)
        )
        skipped = (summary or {}).get("skipped", 0)
        complete = successful_analyses and not skipped
        (run_dir / "pipeline_status.json").write_text(json.dumps({
            "status": "completed" if complete else "completed_with_skips" if successful_analyses else "incomplete",
            "exploration": summary,
            "report_completed": report_ok, "unfinished_task_ids": unfinished,
            "missing_trials": sorted(set(missing_trials)), "final_validation": final_validation,
        }, indent=2), encoding="utf-8")
        checkpoint.finish()
        return 0 if successful_analyses else 1
    except asyncio.CancelledError:
        from memstara.pipeline.exploration import close_active_round
        from memstara.pipeline.paused_recovery import enabled as durable_pause
        if durable_pause(run_dir) and (run_dir / 'pause.request').exists():
            # A service shutdown during an acknowledged pause is not user Stop.
            # Keep call receipts, tasks and checkpoint open for a fresh process.
            close_active_round(run_dir, 'interrupted', 'Paused execution preserved for Resume.')
            raise
        if ownership_lost():
            # Preserve unfinished checkpoint calls/phases: their effects must not
            # be blindly replayed. No database cleanup after losing ownership.
            close_active_round(run_dir, "interrupted", "Database execution ownership lost; saved results retained.")
            raise
        if checkpoint:
            checkpoint.finish()
        close_active_round(run_dir, "interrupted", "Stopped by the user; this attempt was not completed.")
        if seed_task is not None and not seed_task.done():
            seed_task.cancel()
            await asyncio.gather(seed_task, return_exceptions=True)
        await live_workers.close()
        (run_dir / "pipeline_status.json").write_text(json.dumps({"status": "cancelled"}), encoding="utf-8")
        try:
            state = await board_state(registry, args.run_tag)
            for task in state["tasks"]:
                if task["status"] == "in_progress":
                    await call_board_tool(registry, "submit_result", {
                        "task_id": task["task_id"], "worker": task.get("claimed_by", ""),
                        "error": "Pipeline cancelled; completed stage results are preserved."})
        except Exception:
            note("Cancellation recorded; board cleanup could not complete. Inspect task state before resuming.")
        raise
    except Exception as exc:
        from memstara.pipeline.exploration import close_active_round
        close_active_round(run_dir, "blocked",
                           str(exc) if isinstance(exc, PipelineExecutionFailure) else
                           f"Execution could not be verified ({type(exc).__name__}). Review run log.")
        raise
    finally:
        if seed_task is not None and not seed_task.done():
            seed_task.cancel()
            await asyncio.gather(seed_task, return_exceptions=True)
        await live_workers.close()
        # The trace files are written **inside finally.** Even if it dies partway or is
        # cut short with Ctrl-C, the record of the runs called up to that point has to
        # survive — a run that died is precisely the one worth retracing. It is written
        # before the tool servers are disconnected: what is read here is core's DB and has
        # nothing to do with the tool servers, but reversing the order would break quietly
        # the day somebody changes this to use a tool.
        try:
            n = 0 if ownership_lost() else await write_traces(run_dir)
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
        async with conn.transaction():
            from memstara.interpretation_fanout import aggregate
            parents = await conn.fetch("SELECT DISTINCT evaluation->'interpretation_branch'->>'source_task_id' AS id "
                                       "FROM memstara_blackboard WHERE task_id=ANY($1::bigint[]) "
                                       "AND evaluation ? 'interpretation_branch'", task_ids)
            for parent in sorted(int(p['id']) for p in parents):
                await conn.execute('SELECT pg_advisory_xact_lock(72331, $1::integer)', parent)
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
            for parent in parents:
                await aggregate(conn, int(parent['id']))
    finally:
        await conn.close()
    return [r["trial"] for r in rows]


async def main() -> int:
    """The door in from the command line. Reads the arguments, checks them, takes the
    lock and calls run()."""
    # Resolve the selected project source before runtime initialization.
    # Shell injection is supported only in explicit environment mode.
    load_env()

    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline-id", default="")
    ap.add_argument("--pipeline-name", default="")
    ap.add_argument("--evaluation", default="{}")
    ap.add_argument("--ml-overrides", default="{}", help="JSON: bounded user settings for selected ML models")
    ap.add_argument("--ablate-okf", action="store_true",
                    help="Disable OKF retrieval and mark the execution as an ablation")
    ap.add_argument("--baseline-columns", default="[]", help="JSON array of fixed baseline predictor columns")
    ap.add_argument("--question", default="")
    ap.add_argument("--trials", type=int, default=3, help="how many hypotheses to seed per wave")
    ap.add_argument("--continuous", action="store_true",
                    help="repeat rounds until stopped or the question bank runs dry")
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
    ap.add_argument("--provider", default="",
                    choices=["anthropic", "azure_foundry", "openai", "openrouter", "local", "bedrock"])
    ap.add_argument("--model", default="")
    ap.add_argument("--model-connection-id", default="")
    ap.add_argument("--stage-models", default="{}",
                    help="Optional JSON qwen/sonnet profiles: Sonnet for Explanation, Qwen for other stages")
    ap.add_argument('--controlled-comparison', default='{}',
                    help='Optional fixed feature count and paired ML plan for matched comparisons')
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
    ap.add_argument(
        "--hypothesis-agents", type=int, default=1,
        help="how many hypothesis workers seed the board at once. Each claims its own "
             "question out of the bank, so two never set out from one question (default 1; "
             "the floor plan is laid out for up to 3 and is not capped)",
    )
    for stage_flag in ("hypothesis", "data", "ml", "interpreter", "report"):
        public_stage = "explanation" if stage_flag == "report" else stage_flag
        ap.add_argument(
            *( ["--playbook-explanation", "--playbook-report"] if stage_flag == "report"
               else [f"--playbook-{stage_flag}"] ),
            dest="playbook_explanation" if stage_flag == "report" else f"playbook_{stage_flag}",
            default={"interpreter": "shared-shap",
                     "report": "shared-heart-failure-cardiovascular"}.get(stage_flag, ""),
            help=f"a behavioural standard for the {public_stage} stage, named without the "
                 f".md — the prompt must carry a {{{{playbook}}}} line to receive it "
                 f"(default: the prompt as written)",
        )
    ap.add_argument("--combination-plan", default="", help="Frozen Cartesian skill schedule")
    ap.add_argument("--specialist-pilot-config", type=Path,
                    help="Complete isolated paired-model specialist study configuration")
    ap.add_argument("--specialist-execute", action="store_true",
                    help="Execute the specialist study; without this flag only preflight is performed")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--knowledge-mode", choices=("okf", "llm_only"), default="okf")
    ap.add_argument("--data-mode", choices=("dataset", "proposal"), default="dataset")
    ap.add_argument("--research-objective", default="")
    ap.add_argument("--research-input-id", default="", help="Saved user corpus, dataset and prediction target")
    ap.add_argument("--start-loop", type=int, default=1, help="First ordinal in a new retry attempt")
    ap.add_argument("--retry-source-run", default="", help="Original failed run retained as evidence")
    ap.add_argument("--retry-seed-schedule", default="", help="Recorded seed schedule from the retry source")
    ap.add_argument("--retry-experiment-policy", default="", help="Original scientific policy for a retry")
    ap.add_argument("--resume", action="store_true", help="Recover this execution from its durable checkpoint")
    args = ap.parse_args()
    if args.start_loop < 1 or (args.start_loop > 1 and not args.retry_source_run):
        ap.error("Starting after the first scheduled run requires an explicit retry source")
    if args.specialist_pilot_config:
        from memstara.pipeline.specialist_pilot import preflight as pilot_preflight, run_study
        config = json.loads(args.specialist_pilot_config.read_text())
        if config.get('expected_combinations') != 64:
            raise ValueError('This experimental entry point requires an explicit 64-condition design')
        conditions, _ = pilot_preflight(config)
        if not args.specialist_execute:
            print(json.dumps({'status': 'configuration_valid', 'combinations': len(conditions),
                              'paid_calls': 0, 'remote_connectivity_verified': False}))
            return 0
        if not args.run_dir:
            raise ValueError('Specialist execution requires an explicit --run-dir under outputs/')
        from memstara.paths import DEFAULT_OUTPUT_DIR
        destination = Path(args.run_dir).resolve()
        destination.relative_to(Path(DEFAULT_OUTPUT_DIR).resolve())
        configure(Settings())
        result = await run_study(config, destination, resume=args.resume)
        print(json.dumps(result))
        return 0
    if args.specialist_execute:
        raise ValueError('--specialist-execute requires --specialist-pilot-config')
    if args.combination_plan and not args.resume:
        from memstara.combinations import validate_plan
        try:
            schedule = json.loads(args.combination_plan)
            validate_plan(schedule)
            args.waves = schedule['total_loops']
            args.trials = args.hypothesis_agents = args.interpret_agents = 1
            args.continuous = False
            for stage, entries in schedule['skills'].items():
                for entry in entries:
                    load_prompt(f'board/{stage}', entry['id'])
        except (ValueError, KeyError, TypeError, OSError) as exc:
            ap.error(str(exc))
    if args.resume:
        from memstara.pipeline.checkpoint import Checkpoint
        if not args.run_dir:
            ap.error("--resume requires --run-dir")
        root = Path(args.run_dir).resolve()
        Checkpoint(root, resume=True)
        saved = json.loads((root / "resume_arguments.json").read_text())
        if args.run_tag and args.run_tag != saved.get("run_tag"):
            ap.error("Resume run tag does not match the saved execution")
        args = argparse.Namespace(**saved)
        args.resume = True
        args.run_dir = str(root)
    if args.report_only and not getattr(args, 'model_connection_id', ''):
        from memstara.pipeline.preparation import frozen_model_source
        original_models = frozen_model_source(args, Path(args.run_dir) if args.run_dir else Path('.'))
        args.model_connection_id = (original_models or {}).get('model_connection_id', '')
    if getattr(args, 'model_connection_id', ''):
        from memstara.model_connections import execution_environment
        selected_env = execution_environment(args.model_connection_id)
        for name in set(os.environ) - set(selected_env):
            os.environ.pop(name, None)
        os.environ.update(selected_env)
    if getattr(args, 'research_input_id', ''):
        from memstara.research_inputs import prepare, activate, validate_skills
        try:
            books = chosen_playbooks(args)
            if args.combination_plan:
                books = {stage: [item['id'] for item in entries] for stage, entries
                         in json.loads(args.combination_plan)['skills'].items()}
            profile = getattr(args, 'research_profile', None) if args.resume else None
            args.research_profile = profile or prepare(args.research_input_id)
            validate_skills(books, args.research_profile)
            activate(args.research_profile)
            research = args.research_profile['configuration']
            args.y_column = research['target']['column'] or 'outcome'
            args.knowledge_mode, args.data_mode = research['knowledge_mode'], research['data_mode']
            args.research_objective = research['target']['description']
        except (ValueError, OSError) as exc:
            ap.error(str(exc))
    args.data_mode = getattr(args, 'data_mode', 'dataset')
    args.knowledge_mode = getattr(args, 'knowledge_mode', 'okf')
    args.research_objective = getattr(args, 'research_objective', '')
    args.ablate_okf = args.ablate_okf or args.knowledge_mode == 'llm_only'
    from memstara.corpus_skills import corpus_profile
    if args.ablate_okf or args.data_mode == 'proposal' or corpus_profile() != 'general':
        from memstara.research_inputs import validate_skills
        try:
            books = chosen_playbooks(args)
            if args.combination_plan:
                books = {stage: [item['id'] for item in entries] for stage, entries
                         in json.loads(args.combination_plan)['skills'].items()}
            validate_skills(books, getattr(args, 'research_profile', None),
                            knowledge_mode='llm_only' if args.ablate_okf else args.knowledge_mode)
        except ValueError as exc:
            ap.error(str(exc))
    if args.data_mode == 'proposal' and not args.research_objective:
        ap.error('Proposal mode requires --research-objective or a saved research objective')
    from memstara.stage_models import for_stage, deployment_profiles
    frozen_profiles = json.loads(args.stage_models) if isinstance(args.stage_models, str) else args.stage_models
    if not frozen_profiles and not (args.resume or args.report_only):
        frozen_profiles = deployment_profiles()
        args.stage_models = json.dumps(frozen_profiles)
    if frozen_profiles:
        metadata_model = for_stage(frozen_profiles, 'hypothesis')
        args.provider, args.model = metadata_model['provider'], metadata_model['model']
    from memstara.evaluation import validate
    try:
        args.evaluation = json.dumps(validate(json.loads(args.evaluation)))
        from memstara.ml_configuration import validate_overrides
        overrides = validate_overrides(json.loads(getattr(args, 'ml_overrides', '{}')))
        args.ml_overrides = json.dumps(overrides, allow_nan=False)
    except (ValueError, TypeError) as exc:
        ap.error(str(exc))
    # Capacity follows the configured hypotheses; single-role UI stays unchanged.
    args.data_agents = max(args.data_agents, args.hypothesis_agents)
    args.ml_agents = max(args.ml_agents, args.hypothesis_agents)
    if args.trials < args.hypothesis_agents:
        ap.error("trials must give every hypothesis at least one evaluation")

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

    # The playbooks are read here for the same reason, and it buys more: `load_prompt`
    # refuses a playbook whose stage has no `{{playbook}}` line, so a stage that cannot
    # receive a standard says so now rather than provisioning an agent that quietly
    # works to no standard at all. Reading is the check — the result is thrown away and
    # read again at provisioning, which costs a few kilobytes and keeps one loader.
    for stage, stage_books in chosen_playbooks(args).items():
        for book in stage_books:
            try:
                load_prompt(f"board/{stage}", book)
            except (OSError, ValueError) as e:
                ap.error(f"--playbook-{stage} {book!r}: {e}")
        if len(stage_books) > 1:
            # Two ways to write more than one name and only one of them is a request.
            # Both are refused here rather than at provisioning, where the first agent
            # would already exist and the extra names would go quietly unused — the same
            # failure `load_prompt` is checked for above, one layer out.
            if stage not in ("hypothesis", "interpreter"):
                ap.error(
                    f"--playbook-{stage} takes one name and was given {len(stage_books)} "
                    f"({', '.join(stage_books)}). Only the hypothesis stage runs a worker per "
                    f"standard; the other four run one agent however many workers claim "
                    f"from the board, so a second name there would never be read."
                )
            count = args.hypothesis_agents if stage == "hypothesis" else args.interpret_agents
            if len(stage_books) != count:
                ap.error(
                    f"--playbook-{stage} has {len(stage_books)} names and its worker count "
                    f"is {count}. Give one name per worker, or one name "
                    f"for all of them — pairing them by position is the whole point, and "
                    f"there is no order in which {len(stage_books)} standards fit "
                    f"{args.hypothesis_agents} workers that someone would not have to guess at."
                )

    # If the prerequisites are missing it ends **without doing anything.** Stopping
    # before the start leaves the board cleaner than dying halfway through.
    #
    # `--report-only` does not use the outcome column. It only reads and tidies what has
    # already finished, so it never opens the dataset. Check the outcome column anyway
    # and the default `outcome` blocks **the very path meant for rescuing an interrupted
    # run** — the means of rescue failing only when rescue is needed.
    if args.resume or args.report_only:
        from memstara.pipeline.preparation import frozen_model_source
        from memstara.stage_models import resolve_run_profiles
        frozen_profiles = resolve_run_profiles(
            args.stage_models, recovering=True,
            frozen=frozen_model_source(args, Path(args.run_dir) if args.run_dir else Path('.')),
        )
    problems = await check_environment(
        provider=args.provider,
        stage_models=frozen_profiles or None,
        y_column="" if args.report_only or args.data_mode == "proposal" else args.y_column,
        use_okf=not args.ablate_okf,
        use_data=args.data_mode == "dataset",
        prepare_matcher=not args.report_only,
        run_dir=Path(args.run_dir) if args.run_dir else None,
    )
    if problems:
        if args.run_dir:
            from memstara.pipeline.failures import record_startup_failure
            record_startup_failure(Path(args.run_dir), problems)
        print("Environment is not ready:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    started = datetime.now()
    # If no run name is given, one is made from the clock. This name is what ties the
    # sheets on the board together.
    args.run_tag = args.run_tag or started.strftime("board_%Y%m%dT%H%M%S")
    if args.ablate_okf and not args.run_tag.endswith("_ablate_okf"):
        args.run_tag += "_ablate_okf"
    run_dir = Path(args.run_dir) if args.run_dir else new_run_dir(
        f"board_{args.trials}trials", started.strftime("%Y-%m-%dT%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    # CLI and report-only runs are visible to the same controller as UI launches.
    from memstara.control.recovery import identity, save_record
    if not (run_dir / "control_record.json").exists():
        save_record({"run_tag": args.run_tag, "run_dir": str(run_dir.resolve()), "skill": args.skill,
                     "pid": os.getpid(), "started": started.isoformat(timespec="seconds"),
                     "process_identity": identity(os.getpid()), "report_only": args.report_only,
                     "pipeline_id": args.pipeline_id or None})

    # Whatever is printed to the screen is left in console.log as well.
    with tee_console(run_dir / "console.log", append=args.resume):
        try:
            # Refuse to be the second driver on this tag. Held for the whole run and
            # released with the connection, so a killed process leaves nothing behind.
            # Two of them once ran at the same time, taking each other's sheets, and the
            # board ended up scrambled.
            from memstara.pipeline.run_ownership import record_health
            async with run_lock(args.run_tag, on_lost=lambda reason: record_interruption(run_dir, reason),
                                on_health=lambda value: record_health(run_dir, value)):
                if args.resume:
                    (run_dir / "infrastructure_status.json").unlink(missing_ok=True)
                    from memstara.pipeline.checkpoint import atomic_json
                    atomic_json(run_dir / "pipeline_status.json",
                                {"status": "running", "resumed": True, "report_completed": False})
                    record = json.loads((run_dir / "control_record.json").read_text())
                    if record.get("pid") != os.getpid():
                        record = {k: v for k, v in record.items() if k not in ("exit_code", "ended")}
                        record.update(pid=os.getpid(), process_identity=identity(os.getpid()))
                        save_record(record)
                    (run_dir / "pause.request").unlink(missing_ok=True)
                return await run(args, run_dir)
        except RunOwnershipLost:
            record_interruption(run_dir, "execution_ownership_lost")
            print("Execution interrupted by database connection loss; saved results and checkpoints are retained.",
                  file=sys.stderr)
            return 75
        except RunLockCleanupError:
            return record_cleanup_warning(run_dir)
        except BoardBusy as e:
            # Somebody is already running under this name.
            print(f"\n{e}", file=sys.stderr)
            return 2
        except Exception as exc:
            from memstara.evaluation import DataQualityError
            import traceback
            # Preserve the failure location without serializing locals, credentials,
            # tool arguments or patient records into diagnostics.
            (run_dir / "failure_frames.json").write_text(json.dumps({
                "error_type": type(exc).__name__,
                "frames": [{"file": frame.filename, "line": frame.lineno,
                            "function": frame.name}
                           for frame in traceback.extract_tb(exc.__traceback__)],
            }, indent=2), encoding="utf-8")
            message = (str(exc) if isinstance(exc, (DataQualityError, PipelineExecutionFailure)) else
                       "Pipeline could not safely continue; inspect console.log and trace/.")
            from memstara.pipeline.failures import read_failure
            original_failure = read_failure(run_dir) or {}
            message = original_failure.get("message", message)
            (run_dir / "pipeline_status.json").write_text(json.dumps({
                "status": "failed", "error_type": type(exc).__name__,
                "message": message,
                **{k: original_failure[k] for k in ("code", "stage", "loop") if k in original_failure},
            }, indent=2), encoding="utf-8")
            print(f"Pipeline failed ({type(exc).__name__}): {message}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            # The board is a database; whatever was written stays written. Say what to
            # do next rather than leaving a bare traceback.
            print("\n\ninterrupted. the board is still there.")
            print("  see the state:  python -m memstara.blackboard --show")
            print(f"  report only:    python -m memstara.pipeline.board --report-only --run-tag {args.run_tag}")
            return 130
        finally:
            if (run_dir / 'config.json').exists():
                from memstara.experiment_registry import reconcile
                synced = await reconcile(run_dir)
                if not synced:
                    # Preserve scientific completion, but stop batch continuation
                    # until durable evidence can be reconciled successfully.
                    raise RuntimeError('Experiment registry is pending; reconcile before the next execution')


if __name__ == "__main__":
    # asyncio.run drives main() to the end, and its return value (0/1/2/130) becomes the
    # exit code.
    raise SystemExit(asyncio.run(main()))
