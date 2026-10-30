#!/usr/bin/env python3
"""Render what an agent actually did, from what core persisted.

This is the richer half of observability. Live logs are transient and only exist if you
were watching; core, by contrast, writes a `RunStep` for every phase of every run and
keeps it. That record holds the phase input and output, the LLM call (model, tokens,
latency, cost) and every tool call with its arguments and its result.

So any run can be reconstructed after the fact — including runs from before this script
existed, because none of this is new instrumentation. It is all already in the database.

Usage::

    python -m memstara.trace.run --trial 0
    python -m memstara.trace.run --trial 0 --stage hypothesis
    python -m memstara.trace.run --trial 0 --summary
    python -m memstara.trace.run --run-id 30b49492-d4bd-411c-bbad-999b41286bff
    python -m memstara.trace.run --trial 0 --full     # do not truncate payloads
    python -m memstara.trace.run --from outputs/runs/<run> --trial 0

src/memstara/pipeline/mvp.py calls :func:`dump_all` at the end of every run, so a run directory
already contains these traces as files; the CLI is for going back further.


==============================================================================
 How to read this file
==============================================================================

 From what core left in the database, it brings back **"what the agent actually did"**
 and prints it as prose. A log that scrolled past the screen can only be seen if you
 were watching at the time and is soon gone; core, by contrast, writes one line
 (a RunStep) for every phase of a run and **keeps it.**

 That line holds the phase's input and output, the model call (model name, tokens, time
 taken, cost), and **the tool call's arguments and result in full.** None of which a
 breakpoint could show you — the tools run in a separate process, and stopping there
 would show you that one occurrence only.

 There are five functions.

   _clip(text, limit, full)   trims text that is too long (with --full it does not)
   _load_rows(...)            reads todo_rows.json
   _resolve(trial, stage)     turns "trial 3" into the actual run ids
   render(...)                **the key function.** Prints one run as human prose
   dump_all(rows_file, out)   writes one file per trial, everything, untruncated

 Easy things to miss:

   · **Runs made before this script existed can be viewed exactly the same.** Because
     none of this is new instrumentation. Everything needed was already in the
     database; what was missing was the side that **reads it.**
   · By default the text is trimmed for display. When you need to see everything that
     went into a tool, always add `--full`.
   · src/memstara/pipeline/mvp.py calls dump_all at the end of every run, so a run directory
     already holds the trace/ files. Reaching for the command line is for going back to
     **something older than that.**
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from memstara.config import Settings

from memstara.paths import DEFAULT_OUTPUT_DIR

from motoro import configure
from motoro.runner import get_run, get_run_steps
from motoro.schemas.llm import flatten_tool_call_records

# The trial list the most recent run left behind. It is the key that turns "trial 3" into
# a run id.
ROWS_FILE = DEFAULT_OUTPUT_DIR / "todo_rows.json"

# The four stages one trial goes through. They are printed in this order too.
STAGES = ("hypothesis", "data", "ml", "interpreter")


def _clip(text: str, limit: int, full: bool) -> str:
    """Cut long text off at *limit* characters and say how many were cut.

    First newlines and runs of whitespace are squeezed down to a single space, making it
    one line. This is to stop a multi-line tool result from burying the screen.

    If *full* is true (--full) nothing at all is cut. **When you have to see everything
    that went back and forth, always use this side.** Judge from the truncated text alone
    and, if the cause was in the part that got cut, you will never find it.
    """
    text = " ".join(str(text).split())
    if full or len(text) <= limit:
        return text
    return f"{text[:limit]}... (+{len(text) - limit} chars)"


#: The fields that, in `readable` mode, **some other line has already said.**
#:
#: Why keep it as a list — just saying "do not print OUT" would mean that the day core
#: adds a new field, that field **quietly disappears.** The intent is to drop only what we
#: know about and keep what we do not.
#: (`_dump_leftovers` prints the remainder)
_SEEN_ELSEWHERE = {
    # sense: the system prompt, the tool specs and the conversation history all sit whole
    #        inside the request sent to the model. That text is in `NN_stage.llm.txt` in
    #        the same folder, so here only its size is mentioned.
    "sense": {"user_input", "agent_goal", "system_prompt", "conversation_history", "available_tools", "memories"},
    # reason: thought and final_answer are printed below in full. tool_calls are shown,
    #         arguments included, by **the TOOL line of the very next act phase.**
    # `pattern` and `step` are bookkeeping rather than content — which step number it is
    # the `[ 3]` prefix says, and which pattern it is stays the same for the whole run, so
    # the header has already said it.
    "reason": {"thought", "action", "tool_calls", "final_answer", "pattern", "step"},
    # act: results holds the same content as the `->` on the TOOL line above. This
    #      duplication was most of the file size (209KB in one run).
    "act": {
        "results",
        "final_response",
        "should_continue",
        "steps",
        "is_complete",
        "completion_reason",
        "action",
        "pattern",
    },
}


def _lines(value: Any, indent: str) -> list[str]:
    """Spread a dict out over several `key: value` lines. Anything else stays one blob.

    Left as a 300-character JSON string on one line it cannot be read, so it is broken up
    a line per field. **Nothing is cut** — if the cause is in the part that got cut, you
    will never find it.
    """
    if not isinstance(value, dict) or not value:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return [indent + line for line in str(text).splitlines()] or [indent]
    out = []
    for k, v in value.items():
        body = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        rows = str(body).splitlines() or [""]
        out.append(f"{indent}{k}: {rows[0]}")
        pad = indent + " " * (len(k) + 2)
        out.extend(pad + r for r in rows[1:])
    return out


def _dump_leftovers(emit: Any, data: Any, phase: str, tag: str) -> None:
    """Print **the remainder** once the known fields are dropped. Prints nothing if empty.

    This is what keeps a field newly added by core from being buried without a word.
    """
    if not isinstance(data, dict):
        if data:
            for line in _lines(data, "       "):
                emit(line)
        return
    rest = {k: v for k, v in data.items() if k not in _SEEN_ELSEWHERE.get(phase, ()) and v not in (None, "", [], {})}
    if rest:
        emit(f"     {tag}")
        for line in _lines(rest, "       "):
            emit(line)


def _load_rows(rows_file: Path = ROWS_FILE) -> list[dict[str, Any]]:
    """Read the trial list file. If it is not there, say what to run first and stop."""
    if not rows_file.is_file():
        print(f"!! {rows_file} not found — run `python -m memstara.pipeline.mvp` first", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(rows_file.read_text(encoding="utf-8"))


def _resolve(trial: int, stage: str | None, rows_file: Path = ROWS_FILE) -> list[tuple[str, uuid.UUID]]:
    """Map a trial number to its stage run ids, via todo_rows.json.

    A person says "trial 3", but core knows a run only by a meaningless UUID. What joins
    the two is todo_rows.json, which is why one trial usually holds four run ids, one per
    stage.

    Given --stage it returns that one stage; without it, **every stage that has a record.**
    A trial that died at an earlier stage simply has no later ids, so those are skipped.
    """
    rows = _load_rows(rows_file)
    match = next((r for r in rows if type(r.get("trial")) is int and r["trial"] == trial), None)
    if match is None:
        available = sorted(r["trial"] for r in rows if type(r.get("trial")) is int)
        print(f"!! trial {trial} not found. available: {available}", file=sys.stderr)
        invalid = len(rows) - len(available)
        if invalid:
            print(f"!! trial index contains {invalid} invalid trial identifiers", file=sys.stderr)
        raise SystemExit(1)

    run_ids = match.get("run_ids") or {}
    # With --stage, that one only. Otherwise, in order, just the stages that really do
    # have an id.
    wanted = [stage] if stage else [s for s in STAGES if s in run_ids]
    out: list[tuple[str, uuid.UUID]] = []
    for s in wanted:
        rid = run_ids.get(s)
        if rid:
            out.append((s, uuid.UUID(rid)))
        elif stage:
            # A specifically requested stage not being there means the trial died before
            # reaching it. Quietly printing nothing would make "there is no record" and
            # "it failed" indistinguishable.
            print(f"!! trial {trial} has no '{s}' run (it likely failed earlier)", file=sys.stderr)
            raise SystemExit(1)
    return out


async def render(
    label: str,
    run_id: uuid.UUID,
    *,
    full: bool,
    summary: bool,
    stream: Any = None,
    readable: bool = False,
) -> None:
    """Write one run's steps to *stream* (default: stdout).

    **The key function of this file.** It prints one run as prose a person can read.

    The order it prints in:

      header      status · tokens · cost · number of steps · the input the run started from
      per step    [number] stage-name time-taken
                  LLM   which model, and what it cost
                  TOOL  which tool was called **with which arguments**, and **what came
                        back**
                  IN/OUT  (only with --full) the phase's input and output in full

    Those two TOOL lines are the reason this whole file exists. Their arguments and
    results were never carried by the on-screen log, and attaching a debugger to a tool
    running in a separate process shows them to you that one time only.

    Given *stream* it prints to that file; without it, to the screen. It is arranged this
    way so the same code produces both the output a person watches and the file kept for
    the record.

    Called with readable=True it prints **for a person to read.** What changes:

      · instead of the JSON blobs of IN/OUT, **only the substance** — the thought in full,
        with whatever overlaps the previous phase dropped. Measured, that duplication was
        209KB in a single file
      · tool arguments and results are spread over `key: value` lines. Run together at
        300 characters a line they cannot be read
      · **nothing at all is cut.** Everything dropped is only what another line has
        already said, and a field we do not know about is left in by `_dump_leftovers`

    Why the default is False — so that the output of the existing way of using
    `src/memstara/trace/run.py`, from the command line, does not change.
    """
    out = stream if stream is not None else sys.stdout

    def emit(text: str = "") -> None:
        print(text, file=out)

    run = await get_run(run_id)  # the summary of one run — status, tokens, cost
    steps = await get_run_steps(run_id)  # the steps that run went through, in order

    # ---- header ------------------------------------------------------
    header = f"{label}  run={run_id}"
    emit("\n" + "=" * 100)
    emit(header)
    if run is not None:
        tokens = run.token_usage or {}
        emit(
            f"status={run.status.value}  "
            f"tokens={tokens.get('prompt_tokens', 0)}/{tokens.get('completion_tokens', 0)}  "
            f"cost=${float(run.cost_estimate or 0):.6f}  steps={len(steps)}"
        )
        if run.error:
            emit(f"error: {run.error}")
        emit(f"input: {_clip(run.input, 160, full)}")
    emit("=" * 100)

    # --summary stops here. Skimming several runs, the header alone is enough.
    if summary:
        return

    # ---- per step ----------------------------------------------------
    for step in steps:
        dur = ""
        if step.started_at and step.completed_at:
            dur = f"{(step.completed_at - step.started_at).total_seconds():.2f}s"
        emit(f"\n[{step.sequence:>2}] {step.phase.value:<9} {dur}")

        # If this phase called the model: which one, and at what cost.
        if step.llm_call:
            c = step.llm_call
            emit(
                f"     LLM  {c.get('model', '?')}  "
                f"{c.get('prompt_tokens', 0)}/{c.get('completion_tokens', 0)} tok  "
                f"{c.get('latency_ms', 0)}ms  ${c.get('cost_estimate', 0):.6f}"
            )
            if c.get("failure_reason"):
                emit(f"     LLM  failure_reason: {_clip(c['failure_reason'], 200, full)}")

        # flatten_tool_call_records handles both shapes core persists: a single call, or
        # {"calls": [...]} when one step invoked several. Unpack it by hand and you will
        # miss one of the two shapes — and then, in some runs, the tool calls do not show
        # up at all.
        #
        # The two lines below are the most valuable part of this file — what went in
        # (the arguments) and what came back (the result) are both right here.
        for call in flatten_tool_call_records(step.tool_call):
            server = call.get("server") or ""
            tool = call.get("tool") or "?"
            args = json.dumps(call.get("arguments") or {}, ensure_ascii=False)
            ok = "" if call.get("success", True) else "  [FAILED]"
            if readable:
                emit(f"     tool    {server}.{tool}{ok}")
                emit("     args")
                for line in _lines(call.get("arguments") or {}, "       "):
                    emit(line)
                emit("     result")
                result = call.get("result") or ""
                try:
                    result = json.loads(result) if isinstance(result, str) else result
                except (json.JSONDecodeError, TypeError):
                    pass
                for line in _lines(result, "       "):
                    emit(line)
            else:
                emit(f"     TOOL {server}.{tool}({_clip(args, 110, full)}){ok}")
                emit(f"          -> {_clip(call.get('result') or '', 150, full)}")

        # The phase's own input and output.
        #
        # In readable mode **only the substance** is printed. Print the JSON whole and
        # every phase carries the conversation so far all over again, growing the file
        # past reading (209KB, measured).
        if readable:
            phase = step.phase.value
            res = step.output if isinstance(step.output, dict) else {}

            if phase == "sense":
                # What the person asked for. It appears exactly once in a run.
                if res.get("user_input"):
                    emit("     input   " + str(res["user_input"]))
                if res.get("agent_goal"):
                    emit("     goal    " + str(res["agent_goal"]))
                # The system prompt, the tool specs and the memories go **whole into the
                # request sent to the model.** That text is in the `.llm.txt` beside this
                # file, so only its size is given here.
                sp = len(str(res.get("system_prompt") or ""))
                tools_n = len(res.get("available_tools") or [])
                mem_n = len(res.get("memories") or [])
                emit(
                    f"     kit     role brief {sp:,} chars · {tools_n} tools available · "
                    f"{mem_n} memories   (the text itself is in the .llm.txt beside this)"
                )

            elif phase == "reason":
                if res.get("thought"):
                    emit("     thought")
                    for line in _lines(str(res["thought"]), "       "):
                        emit(line)
                if res.get("final_answer"):
                    emit("     answer")
                    for line in _lines(str(res["final_answer"]), "       "):
                        emit(line)

            # For the act phase the "tool" lines above have already said all of it. Its
            # IN/OUT only carries the same content one more time, so it is not printed.

            _dump_leftovers(emit, step.output, phase, "rest (output)")
            _dump_leftovers(emit, step.input, phase, "rest (input)")

        elif full:
            if step.input:
                emit(f"     IN   {_clip(json.dumps(step.input, ensure_ascii=False), 400, full)}")
            if step.output:
                emit(f"     OUT  {_clip(json.dumps(step.output, ensure_ascii=False), 400, full)}")


async def dump_all(rows_file: Path, out_dir: Path) -> list[Path]:
    """Write one untruncated trace file per trial. Returns the files written.

    This is what turns the database into an artifact. The step rows hold every tool
    call with its arguments and its result, but they only become something you can read
    later if someone goes and gets them — a live log never carried them at all.

    src/memstara/pipeline/mvp.py calls this function at the end of every run. That is why a run
    directory holds its trace/ from the moment it is made.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for row in _load_rows(rows_file):
        trial = row.get("trial")
        run_ids = row.get("run_ids") or {}
        if trial is None or not run_ids:
            # a trial that failed before its first run has nothing to show. Leaving an
            # empty file behind would mix up "there is no record" with "nothing happened".
            continue

        path = out_dir / f"trial{trial:02d}.txt"
        with path.open("w", encoding="utf-8") as fh:
            print(f"trial {trial}  perspective: {row.get('perspective', '')}", file=fh)
            if row.get("error"):
                print(f"ERROR: {row['error']}", file=fh)
            for stage in STAGES:
                rid = run_ids.get(stage)
                if rid:
                    await render(stage, uuid.UUID(rid), full=True, summary=False, stream=fh)
        written.append(path)

    return written


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--trial", type=int, help="trial number, resolved via outputs/todo_rows.json")
    src.add_argument("--run-id", help="a core run id directly")
    ap.add_argument("--stage", choices=STAGES, help="restrict to one stage of the trial")
    ap.add_argument("--summary", action="store_true", help="header only, no steps")
    ap.add_argument("--full", action="store_true", help="do not truncate arguments, results or payloads")
    ap.add_argument(
        "--from",
        dest="run_dir",
        default=None,
        help="read todo_rows.json from this run directory instead of outputs/",
    )
    args = ap.parse_args()

    # Reaching the database needs the settings to be in place first.
    configure(Settings())

    # With --from, the trial list of that run directory; without it, the most recent one.
    rows_file = Path(args.run_dir) / "todo_rows.json" if args.run_dir else ROWS_FILE

    # --run-id is the way to take a run id directly, without going through the trial list.
    # An old run whose trial list is gone can still be viewed if you know the id.
    if args.run_id:
        targets = [("run", uuid.UUID(args.run_id))]
    else:
        targets = _resolve(args.trial, args.stage, rows_file)

    for label, rid in targets:
        await render(label, rid, full=args.full, summary=args.summary)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
