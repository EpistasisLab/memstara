#!/usr/bin/env python3
"""Memstara MVP — hypothesis -> data -> ML -> interpreter, repeated N times.

An executable example of the four-stage pipeline fixed in the 2026-08-06 meeting. It
runs over synthetic data and a sample OKF bundle, and reads feature importance out of
the overlap in column selections across trials. The idea is that a column picked again
and again across trials that changed perspective is more trustworthy than one trial
that happened to guess well.

Setup::

    cp .env.example .env && docker compose up -d
    uv sync --frozen --group dev          # or: uv pip install -e .
    uv pip install pandas scikit-learn

    SB=../memstara                 # this folder, outside the repo
    python $SB/make_sample_data.py

    set -a && . ./.env && set +a
    export AGENTIC_OKF_BUNDLE_DIR="$PWD/$SB/outputs/okf_synthetic_sample"
    export MEMSTARA_DATASET_PATH="$PWD/$SB/outputs/dataset.csv"
    export MEMSTARA_OUTPUT_DIR="$PWD/$SB/outputs"

Run::

    python $SB/02_mvp_pipeline.py --trials 3      # smoke
    python $SB/02_mvp_pipeline.py --trials 20     # full

Point AGENTIC_OKF_BUNDLE_DIR at a different bundle folder to swap knowledge
sources — the server reads exactly one bundle; several cannot be loaded at once. See
outputs/README.md.

Every invocation writes one directory under ``outputs/runs/``::

    2026-08-13T142530_mvp_3trials/
      REPORT.md        did it go normally, and if not, what was wrong — read this first
      run.jsonl        structured, DEBUG, every record tagged with trial and stage
      console.log      what the terminal showed, colour codes stripped
      manifest.json    arguments, paths, timing, result
      trace/           one file per trial: every step, tool arguments, tool results
      todo_rows.json   this run's rows and summary (outputs/ keeps only the latest)
      summary.json

Nothing appends to a previous run, so a folder is always exactly one invocation. It does
not get mixed up with yesterday's, so opening one later leaves no doubt about what is
being looked at.

==============================================================================
 How to read this file
==============================================================================

 This file is the **supervisor-style** pipeline. A Python function calls the four
 stages (hypothesis -> data -> machine learning -> interpretation) itself in a fixed
 order, holding each stage's result in a variable and handing it to the next. What
 decides the order is Python code, not an LLM. That is repeated as many times as there
 are trials, and then the columns the trials picked are gathered and aggregated.

 The main functions (top to bottom, in the order they run)
   main()             — reads the two .env files, takes the arguments, makes the run
                        directory, turns on the console record, then calls run_pipeline
   run_pipeline()     — leaves the actual work to _run_pipeline, but guarantees that
                        manifest.json is written whether it succeeds or dies
   _run_pipeline()    — check the environment -> prepare the agents -> connect the
                        tools -> N trials -> aggregate -> save files -> build the
                        report -> print
   check_environment()— check **before anything starts**, all at once, that every
                        environment variable needed is there
   setup_tools()      — register the four MCP servers and connect them
   dataset_columns()  — read only the CSV's first line to get the column names
   write_manifest()   — record in a file what this run was
   print_summary()    — print the aggregate to the terminal in readable form

 Easy things to miss
   1. **This file is the comparison held up beside 03 (the board style).** 03 does the
      same work with a different structure — the agents each write onto a shared
      blackboard. If the two give different answers, that fact is itself information.
      For that the yardstick must not move, so **this file is left alone.** New ideas
      go into 03.
   2. **This is not an LLM supervisor.** The word "supervisor" invites the
      misunderstanding, but what supervises here is ordinary Python code inside
      `_run_pipeline`. No LLM decides "what to do next".
   3. **There are two `.env` files.** That is why both are read at the very top of
      main(). The reason is written out in the comment inside main().
   4. **`dump_all` writes a trace file per trial.** The database holds every tool call
      with its arguments and result, but none of it is visible until someone goes and
      gets it, so it is pulled out to files when the run ends. 03 records this a
      different way.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

# Below are the sibling modules in this folder. Most of the actual work happens in
# them; this file's role is to call them in order.
#   logging_setup  — make the run directory, configure logging, record the console
#   pipeline_core  — run one trial, aggregate, prepare the agents
#   run_report     — read the run directory, write REPORT.md, judge normal/abnormal
#   settings       — the settings object that reads the environment variables
#   trace_run      — pull the database's record of tool calls out into files
from logging_setup import new_run_dir, setup_logging, tee_console
from pipeline_core import (
    TrialConfig,
    aggregate,
    interpret_overall,
    provision_all,
    run_one_trial,
    save_rows,
)
from run_report import build_report
from settings import Settings

# There are two .env files, so the program reads them itself — see the comment in main().
from dotenv import load_dotenv
from trace_run import dump_all

from agentic_core import configure
from agentic_core.mcp.registry import MCPServerRegistry
from agentic_core.services.mcp_service import (
    get_server_by_name,
    hydrate_registry,
    register_server,
    update_server,
)

HERE = Path(__file__).parent
OUT_DIR = HERE / "outputs"

# Recorded in the manifest by name. Never dump os.environ: it holds the provider
# credentials, and a run directory is something you hand to someone else to read. The
# three named here are only paths, so nothing goes wrong if they leak.
RECORDED_ENV_VARS = ("AGENTIC_OKF_BUNDLE_DIR", "MEMSTARA_DATASET_PATH", "MEMSTARA_OUTPUT_DIR")


def dataset_columns() -> list[str] | None:
    """The dataset's column names, read from its header row alone.

    Only `aggregate` needs this, and only to decide whether this is the synthetic data
    make_sample_data.py produced — that is, whether the planted-signal answer key may be
    applied to it. There is no reason to pull a file of tens of thousands of rows into
    memory for that one judgement, so a single line is read.

    Returns:
        The list of column names. None if the path is unset, the file is missing, or
        reading fails. None means "unknown", and aggregate then skips the scoring.
    """
    path = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    if not path or not Path(path).is_file():
        return None
    try:
        with Path(path).open(encoding="utf-8", newline="") as fh:
            # next(...) takes only the first line from the CSV reader. The rest is not read.
            return next(csv.reader(fh))
    # Empty file (StopIteration), read failure (OSError), broken encoding
    # (UnicodeDecodeError). All three are treated the same, as "the columns cannot be
    # known" — none of them is grounds for throwing upward and killing the whole run.
    except (StopIteration, OSError, UnicodeDecodeError):
        return None


def write_manifest(path: Path, *, args: argparse.Namespace, started: str, summary: dict | None) -> None:
    """Record what this run was, so the folder explains itself a month later.

    Every key is read with .get. This function is also the last thing that runs when a
    run dies, so it has to survive a half-built summary — and it did not: reading
    ``summary["planted_recall"]`` directly raised KeyError on the first dataset without
    a planted signal, taking down the manifest and the report along with it. Code whose
    job is to leave a record was what made leaving a record impossible, so since then a
    missing key simply becomes None.

    Args:
        path: the file to write (manifest.json).
        args: the whole command line.
        started: the start time as a string.
        summary: the aggregate. None if the run never got that far.
    """
    result = None
    if summary is not None:
        result = {
            "n_trials": summary.get("n_trials"),
            "n_succeeded": summary.get("n_succeeded"),
            "n_failed": summary.get("n_failed"),
            "mean_auc": summary.get("mean_auc"),
            "errors": summary.get("errors", []),
        }
        # `planted_recall` — how many of the planted answers were recovered — is
        # present only on the dataset that carries the answer key. Any other dataset has
        # no answers, so the key itself is absent and nothing is recorded. See aggregate().
        if "planted_recall" in summary:
            result["planted_recall"] = summary["planted_recall"]

    manifest = {
        "started_at": started,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "args": vars(args),
        "environment": {name: os.environ.get(name, "") for name in RECORDED_ENV_VARS},
        "result": result,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# The credentials each provider needs. Only the one chosen with `--provider` is checked.
#
# While this was absent, empty credentials did not blow up **until the first LLM call.**
# Stopping before anything starts is better — nothing is written, and what has to be
# filled in is known right there.
_PROVIDER_KEYS = {
    "azure_foundry": ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


def check_environment(provider: str = "") -> list[str]:
    """Report everything missing at once, before anything starts.

    Without this the MCP servers fail to connect quietly, and the only symptom is a
    line reading "tools available: []". It is hard to work out from that line alone that
    the cause is a missing environment variable.

    Reporting all of it at once is the point — otherwise it goes fix one, run again,
    find another one missing, over and over.

    Returns:
        A list of strings describing the problems. Empty means everything is ready.

    Args:
        provider: the value chosen with `--provider`. Only the credentials matching it
            are checked.
    """
    problems: list[str] = []

    # LLM credentials. These live in `agentic-core/.env` and main() reads them in.
    for name in _PROVIDER_KEYS.get(provider, ()):
        if not os.environ.get(name, "").strip():
            problems.append(
                f"{name} is not set — needed for --provider {provider}. "
                "Check agentic-core/.env."
            )

    # The three below are this sandbox's path settings. "not set" and "set but pointing
    # at nothing" are reported apart — a path wrong by a typo is genuinely common.
    okf = os.environ.get("AGENTIC_OKF_BUNDLE_DIR", "").strip()
    if not okf:
        problems.append(
            "AGENTIC_OKF_BUNDLE_DIR is not set — export AGENTIC_OKF_BUNDLE_DIR="
            f'"{OUT_DIR / "okf_synthetic_sample"}"'
        )
    elif not Path(okf).is_dir():
        problems.append(f"AGENTIC_OKF_BUNDLE_DIR does not exist: {okf}")

    ds = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    if not ds:
        problems.append(f'MEMSTARA_DATASET_PATH is not set — export MEMSTARA_DATASET_PATH="{OUT_DIR / "dataset.csv"}"')
    elif not Path(ds).is_file():
        problems.append(f"MEMSTARA_DATASET_PATH file not found: {ds} (run make_sample_data.py first)")

    if not os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip():
        problems.append(f'MEMSTARA_OUTPUT_DIR is not set — export MEMSTARA_OUTPUT_DIR="{OUT_DIR}"')

    return problems


async def setup_tools() -> MCPServerRegistry:
    """Register the three MCP servers (once) and hydrate the registry.

    register_server is a one-time setup step of the same character as provision.py;
    hydrate_registry runs every process, exactly as a worker or a restarted API would.

    An MCP server is a separate process that provides a **bundle of tools** for an agent
    to use. There are four here: knowledge lookup (okf), data access (memstara-data),
    machine learning (memstara-ml) and the board (memstara-blackboard).

    The two operations differ in character:
      - `register_server` is the preparatory step that writes "a server like this
        exists" into the database, once. It is the same in character as provision.py
        registering the agents.
      - `hydrate_registry` reads that record and actually starts the processes and
        connects them, and it happens **once per process.** A worker or a restarted API
        server goes through exactly the same thing.

    Returns:
        The MCP server registry, connected.
    """
    registry = MCPServerRegistry()

    # The executable must be on core's allowlist (python/node/npx/...) and the command
    # must contain no shell metacharacters. sys.executable is python, whose
    # basename is python, so it passes. It is the safeguard that stops an arbitrary
    # command from being run.
    #
    # okf runs core's server through tools_okf.py rather than `-m ...okf` directly. That
    # wrapper turns off one YAML behaviour so list_concepts stops failing on bundles core
    # did not write (this synthetic bundle, for one); core's tools themselves are
    # unchanged — they are only wrapped. See tools_okf.py.
    #
    # memstara-blackboard is connected but not yet handed to any agent. The board exists
    # and its window works (see test_blackboard.py), but no agent is told to use it —
    # the prompts still receive their input from run_one_trial. Connecting it now means
    # the wiring is exercised on every run instead of only when someone remembers to
    # test it — and in between it could be quietly broken with nobody the wiser. Handing
    # out its tools waits until the prompts ask for them.
    servers = [
        ("okf", f"{sys.executable} {HERE / 'tools_okf.py'}"),
        ("memstara-data", f"{sys.executable} {HERE / 'tools_data.py'}"),
        ("memstara-ml", f"{sys.executable} {HERE / 'tools_ml.py'}"),
        ("memstara-blackboard", f"{sys.executable} {HERE / 'tools_blackboard.py'}"),
        # PROTOTYPE semantic matcher: OKF concept name -> EcoXAI column name
        # needs the cache: python scripts/build_matcher_cache.py
        ("semantic-matcher", f"{sys.executable} {HERE / 'tools_matcher.py'}"),
    ]

    for name, command in servers:
        existing = await get_server_by_name(name)
        if existing is None:
            # A name never seen before gets registered.
            await register_server(name=name, transport="stdio", command=command, registry=registry)
        elif existing.command != command:
            # Registration is idempotent by name, so an edited command would otherwise
            # never reach the running server — the same trap _ensure_agent avoids for
            # agents. A server's identity is its name, not the command behind it, so
            # when the name matches and the command does not, it is updated.
            await update_server(existing.id, command=command, registry=registry)

    # Actually start the registered servers and connect them. Whatever failed comes
    # back as a list.
    failed = await hydrate_registry(registry=registry)
    if failed:
        # It does not stop here. If there is no tool at all, _run_pipeline decides that
        # for itself and halts. There is no reason to cut a run short here just because
        # some of them failed.
        print(f"!! MCP reconnect failed: {failed}", file=sys.stderr)
    return registry


def print_summary(summary: dict) -> None:
    """Print the aggregate to the terminal in a form a person can read.

    The same content also goes into summary.json and REPORT.md, so a failure to print
    here does not lose the record.
    """
    print("\n" + "=" * 68)
    print("AGGREGATE")
    print("=" * 68)
    print(f"trials: {summary['n_succeeded']}/{summary['n_trials']} succeeded", end="")
    if summary["n_failed"]:
        print(f"  ({summary['n_failed']} failed)")
    else:
        print()
    if summary["mean_auc"] is not None:
        print(f"AUC: mean {summary['mean_auc']}  best {summary['best_auc']} (trial #{summary['best_trial']})")

    print("\nColumn selection frequency — the meeting's 'overlap'")
    # **How many times a column was selected.** This is the 'overlap' the meeting meant.
    # If trials with different perspectives kept picking the same column, that column is
    # likely something the data is actually pushing rather than one perspective's taste.
    # The `#` bar only makes the count visible. Only the top 12 are printed.
    for col, n in summary["selection_frequency"][:12]:
        bar = "#" * n
        print(f"  {col:16} {n:2}  {bar}")

    print("\nCumulative feature importance — actual contribution")
    # **Cumulative feature importance.** Where the one above is "how often was it
    # picked", this is "when it was picked, how much did it actually contribute to the
    # model". A column picked often that contributes nothing, and one picked rarely that
    # contributes a lot when it is, can only be told apart by putting the two side by side.
    for col, val in summary["weighted_importance"][:8]:
        print(f"  {col:16} {val}")

    if summary["columns_missing_seen"]:
        # Columns the agent picked that were not in the dataset. Usually it means it
        # bit on one of OKF's trap concepts (PAQ620 and the like). A non-empty list does
        # not mean the run failed, but it is a sign that concept and column have come
        # apart, so it is surfaced.
        print(f"\nColumns absent from the dataset (concept/column name mismatch): {summary['columns_missing_seen']}")

    # Present only when the dataset actually carries the planted signal. On any other
    # dataset there is no answer key, and printing "0/4" would report a failure that
    # did not happen. Saying nothing at all is the right thing when there is no key.
    # See aggregate().
    if "planted_signal" in summary:
        print(f"\nPlanted signal {summary['planted_signal']}")
        print(f"  found in top 6: {summary['planted_found_in_top6']}  ({summary['planted_recall']})")

    if summary["errors"]:
        print("\nFailed trials:")
        for e in summary["errors"]:
            print(f"  #{e['trial']}: {e['error']}")


async def main() -> int:
    """Read the settings, take the arguments, prepare the run directory, start the pipeline.

    Returns:
        The exit code. 0 means at least one trial succeeded.
    """
    # This project has **two** `.env` files and they hold different things.
    #
    #     memstara/.env   the MEMSTARA_* paths
    #     agentic-core/.env           LLM credentials · AGENTIC_DATABASE_URL
    #
    # `env_file=".env"` at `settings.py:27` reads the current folder only, so without
    # reading core's separately the first LLM call dies with "Azure Anthropic requests
    # require an api_base". Running `source` on both in the shell avoids it, but that
    # varies with how it is launched, so the program reads them itself.
    #
    # `load_dotenv` does not overwrite a value that is already there (override=False is
    # the default). So whatever the shell or launch.json gave takes precedence over both
    # — the intent of using a different bundle for that one run is preserved.
    load_dotenv(HERE / ".env")
    load_dotenv(HERE / ".." / "agentic-core" / ".env")

    ap = argparse.ArgumentParser()
    # --trials: how many times to form a hypothesis. 3 is for a quick check, 20 is the real run.
    ap.add_argument("--trials", type=int, default=20, help="number of hypothesis trials")
    # At 5 the Foundry endpoint slows enough that reason_act's pre_act hook times out
    # (observed: 5 failures out of 8). 3 is stable against this resource. The number
    # came out of observation, not theory.
    ap.add_argument("--concurrency", type=int, default=3, help="concurrency cap (rate limits)")
    # --y-column: name of the column to predict. The MEMSTARA_OUTCOME_COLUMN env var
    # wins; failing that, "outcome".
    ap.add_argument(
        "--y-column",
        default=os.environ.get("MEMSTARA_OUTCOME_COLUMN", "outcome"),
        help="name of the outcome column",
    )
    ap.add_argument("--provider", default="azure_foundry", choices=["anthropic", "azure_foundry", "openai"])
    ap.add_argument("--model", default="claude-sonnet-4-6")
    # --no-overall: skip the final stage that interprets the whole aggregate. One fewer
    # LLM call, so it is faster, but there is no overall comment for a person to read.
    ap.add_argument("--no-overall", action="store_true", help="skip the final interpretation of the aggregate")
    # Ablation: withhold the OKF tools. Since the dataset's columns are opaque codes,
    # this leaves the hypothesis agent with no way to learn what any column measures.
    # Run it against a normal run — if the planted signal is still recovered, OKF was
    # not what produced the answer. It is the device that makes the claim "OKF helps"
    # falsifiable.
    ap.add_argument("--ablate-okf", action="store_true", help="run without the OKF tools (ablation)")
    ap.add_argument("--trace", action="store_true", help="print per-trial detail")
    ap.add_argument("--verbose", action="store_true", help="console DEBUG: phases, hooks, every tool call")
    ap.add_argument("--run-dir", default=None, help="where to write this run's records (default: a new one)")
    args = ap.parse_args()

    started = datetime.now()
    # The tag that goes on the folder name. An ablation gets `_ablate`, so a normal run
    # and an ablation can be told apart from the folder listing alone.
    tag = f"mvp_{args.trials}trials{'_ablate' if args.ablate_okf else ''}"
    run_dir = (
        Path(args.run_dir)
        if args.run_dir
        else new_run_dir(tag, started.strftime("%Y-%m-%dT%H%M%S"))
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    # The tee goes on first: dictConfig's StreamHandler binds sys.stderr when it is
    # constructed, so a tee installed after setup_logging would not reach it — the logs
    # would go out through the original stderr it had already grabbed, and that part
    # would be missing from console.log.
    with tee_console(run_dir / "console.log"):
        code = await run_pipeline(args, run_dir=run_dir, started=started)
    return code


async def run_pipeline(args: argparse.Namespace, *, run_dir: Path, started: datetime) -> int:
    """Run the pipeline and write the manifest, finished or not.

    That one guarantee is this function's whole reason for existing.
    """
    # _run_pipeline fills this in once it has a summary. Passing a box rather than
    # returning the summary keeps the manifest writable from `finally` — which is when
    # it matters most: the folder a person comes back to is the run that died, not the
    # one that finished well. A return value does not come back when an exception is
    # raised; a box keeps whatever was already put into it.
    outcome: dict[str, dict] = {}
    # partial makes "a function with some of its arguments filled in already". From here
    # on only summary has to be passed — the rest (path, args, start time) is in place.
    write = partial(write_manifest, run_dir / "manifest.json", args=args, started=started.isoformat(timespec="seconds"))
    try:
        return await _run_pipeline(args, run_dir=run_dir, outcome=outcome, write_manifest_now=write)
    finally:
        # Success or exception, this is always passed through. If there is no summary
        # yet, .get returns None, and write_manifest is built to accept that.
        write(summary=outcome.get("summary"))


async def _run_pipeline(
    args: argparse.Namespace,
    *,
    run_dir: Path,
    outcome: dict[str, dict],
    write_manifest_now: Any,
) -> int:
    """The pipeline's actual body. Read top to bottom once and the whole flow is visible.

    This function *is* the 'supervisor'. No LLM decides the next step; the Python code
    below calls each stage in its fixed turn and carries the result on in a variable.

    Returns:
        The exit code. 1 if not one trial succeeded, 0 if any did.
    """
    # [1] Check the environment. If anything is missing, nothing starts and it ends here.
    problems = check_environment(provider=args.provider)
    if problems:
        print("Environment is not ready:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    # [2] Inject the settings. Once per process, and necessarily before any core module
    # reads a setting — do it later and some module has already taken the old settings.
    configure(Settings())

    # [3] Configure logging. --verbose means DEBUG (hooks and tool calls and all),
    #     otherwise INFO.
    log_path = setup_logging(
        level="DEBUG" if args.verbose else "INFO",
        log_file=run_dir / "run.jsonl",
    )

    # [4] Prepare the agents. The hypothesis, data, ML and interpreter agents are made
    #     here. If one is already registered it is used as it is; if not, it is created.
    agents = await provision_all(provider=args.provider, model=args.model)
    print(f"{len(agents)} agents ready: {', '.join(agents)}")

    # [5] Connect the tools. From here on the registry has to be closed, so it is
    #     wrapped in a try.
    registry = await setup_tools()
    try:
        tools = registry.get_all_tools()
        print(f"{len(tools)} tools: {[t['name'] for t in tools]}\n")
        if not tools:
            # With no tools at all there is no point running a trial. This symptom is
            # exactly the "tools available: []" situation check_environment's comment
            # is about.
            print("!! no tools at all — the MCP servers did not connect.", file=sys.stderr)
            print("   Check mcp_allowed_env_vars in settings.py.", file=sys.stderr)
            return 1

        if args.ablate_okf:
            print("ABLATION: OKF tools withheld from the hypothesis agent\n")
        # [6] Bundle up everything one trial needs. The only thing that differs per
        #     trial is the number; every trial shares the rest of the settings.
        #     use_okf=False withholds the OKF tools from the hypothesis agent.
        cfg = TrialConfig(
            agents=agents,
            registry=registry,
            y_column=args.y_column,
            use_okf=not args.ablate_okf,
        )
        # A semaphore is the lock that enforces "only this many at once". Every trial is
        # launched together, but what actually calls the LLM is always at most
        # `concurrency` of them.
        sem = asyncio.Semaphore(args.concurrency)

        async def guarded(i: int):
            """Run one trial inside the lock and print its one result line."""
            async with sem:
                # The four stages (hypothesis -> data -> ML -> interpretation) happen in
                # order inside run_one_trial. This file only calls it once per trial.
                row = await run_one_trial(i, cfg)
                status = f"AUC {row.auc}" if row.ok else f"failed: {row.error}"
                # Printed the moment each trial finishes. On a 20-trial run, seeing
                # nothing until the end leaves no way to tell stalled from still going.
                print(f"  #{i:2} [{row.perspective}] {row.columns_used or row.columns} -> {status}")
                if args.trace and row.interpretation:
                    # Only under --trace, the first 200 characters of the interpretation
                    # are appended.
                    print(f"      {row.interpretation[:200]}")
                return row

        # [7] N trials. gather puts them all in flight at once and waits until every one
        #     is done. The semaphore above holds the real concurrency down.
        print(f"starting {args.trials} trials (concurrency {args.concurrency})")
        rows = await asyncio.gather(*[guarded(i) for i in range(args.trials)])

        # [8] Aggregate. Gather the per-trial results and compute selection frequency
        #     and importance. dataset_columns() is passed because aggregate has to judge
        #     "may the answer key be applied to this dataset".
        summary = aggregate(list(rows), y_column=args.y_column, dataset_columns=dataset_columns())

        # [9] An overall comment on the whole aggregate. If not one trial succeeded
        #     there is nothing to interpret, so it is skipped. --no-overall also
        #     turns it off.
        if not args.no_overall and summary["n_succeeded"]:
            summary["overall_interpretation"] = await interpret_overall(
                agents["interpreter"], summary, registry=registry
            )

        # The empty box taken earlier is filled here. Past this line, even if the run
        # dies, run_pipeline's finally can still put the aggregate into the manifest.
        outcome["summary"] = summary

        summary_json = json.dumps(summary, ensure_ascii=False, indent=2)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        # [10] The same file is written in two places. outputs/ keeps the latest — that
        #   is what trace_run.py reads by default. The run directory keeps this run's,
        #   which the latest will overwrite tomorrow while the run directory's stays.
        #   Convenience (always in the same spot) and preservation (one per run), both.
        for target in (OUT_DIR, run_dir):
            save_rows(list(rows), target / "todo_rows.json")
            (target / "summary.json").write_text(summary_json, encoding="utf-8")

        # [11] Turn the step rows into files. The database holds every tool call with its
        # arguments and its result, but only until someone goes and gets them; the
        # live log never carried them at all. So at the end of the run they are pulled
        # out here into files under trace/, one file per trial. (03 handles this a
        # different way.)
        traces = await dump_all(run_dir / "todo_rows.json", run_dir / "trace")

        # [12] The manifest has to exist before the report, which reads it for the run's
        # headline numbers. The write in `finally` is the safety net for a run that
        # died, not the normal path; this is the normal path.
        write_manifest_now(summary=summary)
        # [13] Build REPORT.md. The normal/abnormal verdict comes out with its grounds.
        verdict, reasons, report_path = build_report(run_dir)

        print_summary(summary)
        if summary.get("overall_interpretation"):
            print("\nOverall interpretation")
            print("-" * 68)
            print(summary["overall_interpretation"])

        print(f"\nrun directory: {run_dir}")
        print(f"  REPORT.md  ← start here")
        print(f"  console.log · manifest.json · todo_rows.json · summary.json")
        if log_path:
            print(f"  {log_path.name}  (structured, DEBUG, tagged with trial/stage)")
        print(f"  trace/  {len(traces)} files — every step, tool arguments and results")

        # [14] The verdict goes last, and after the run directory, because the whole point is
        # that nobody should have to go looking for it. "3/3 succeeded" was printed on a
        # run that had two warnings in it and nobody noticed. That is when it came out
        # that the success count alone says nothing about whether the run was sound.
        print(f"\nverdict: {verdict}")
        for reason in reasons:
            print(f"  - {reason}")
        print(f"  {report_path}")
        # 0 if any trial succeeded, 1 if none did.
        return 0 if summary["n_succeeded"] else 1
    finally:
        # The registry's lifetime is the process's, not a run's. So the connections are
        # closed here whether it succeeded or failed — leave them open and the MCP
        # server processes are left behind.
        await registry.disconnect_all()


if __name__ == "__main__":
    # This runs only when the file is executed directly. asyncio.run drives the async
    # main() to the end and its return value goes straight out as the process exit code.
    raise SystemExit(asyncio.run(main()))
