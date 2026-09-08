#!/usr/bin/env python3
"""Fail if the viewer's copy of the pipeline's tool tables has drifted.

`viewer/api/stores.py` keeps a written-out copy of `BOARD_TOOLS`, `BOARD_SERVERS` and
`BOARD_AGENT_NAMES` because the viewer runs in its own virtualenv and cannot import
`pipeline_core` (that needs motoro). A copy is fine; a copy nobody checks is not —
the pipeline would change and only the picture would go stale, which is exactly the kind
of quietly-wrong output this project keeps having to dig out.

Run with the *core* interpreter, which can import both sides::

    ../../motoro/.venv/bin/python check_definitions.py

==============================================================================
 How to read this file
==============================================================================

 What this file does
   It compares the pipeline's real definitions (`pipeline_core`) against the stand-in
   tables the viewer copied out (the fallback inside `_pipeline_definitions()` in
   `stores.py`). Anything that does not line up gives exit code 1; not being able to
   read pipeline_core gives 2; everything matching gives 0.

 The main functions
   _copy_from_stores()  pulls out the copy alone by **parsing stores.py rather than
                        importing it**
   main()               compares the three tables, then goes on to check the scene
                        places and the tool mapping

 The five things checked
   1. BOARD_TOOLS       which tools each stage uses
   2. BOARD_SERVERS     which MCP server each stage connects to
   3. BOARD_AGENT_NAMES stage -> the name in the agents table
   4. scene places / tool->store   does every stage have a HOME and a label, and does
                                   every tool have a store
   5. SPLITTABLE        does every station allowed to show several figures exist

 Easy things to miss
   ★ Why `_copy_from_stores` uses **ast parsing instead of an import.** On an import
     the try block inside stores.py succeeds, the *real* definitions load, and it ends
     up comparing the original with the original — a meaningless check that always
     passes. So the source code is read literally and only the fallback values are
     taken out of it.
   ★ Do not stop at check 3. Without check 4 (the scene places), a newly added stage
     means one character **vanishes from the drawing without a word.**
==============================================================================
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
# HERE = viewer/. The pipeline it checks against is the installed `memstara` package,
# so nothing has to be put on sys.path to reach it. `HERE / "api"` still does, further
# down — that directory is a set of flat sibling modules, not a package.


def _copy_from_stores() -> dict[str, object]:
    """Read the fallback tables out of stores.py without importing it.

    Parsing rather than importing keeps this honest: importing would let the *real*
    definitions load and the comparison would compare them with themselves — a sham
    check that passes unconditionally.
    """
    tree = ast.parse((HERE / "api" / "stores.py").read_text(encoding="utf-8"))
    # The source is read as a syntax tree only. Nothing at all is executed.
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_pipeline_definitions")
    # Find the `_pipeline_definitions` function node, and
    ret = [n for n in ast.walk(fn) if isinstance(n, ast.Return)][-1]
    # take the **last** return inside it. The first return is the one in the try that
    # "hands back the real definitions as they are"; the last return is the except
    # clause's **stand-in table.**
    # `literal_eval` evaluates only literals such as dict/set/str, so there is no risk
    # of code being run.
    tools, servers, names, question = ast.literal_eval(ret.value)
    return {"tools": tools, "servers": servers, "names": names, "question": question}


def main() -> int:
    # The exit code is the result: 0 everything matches / 1 something does not line up /
    # 2 pipeline_core could not be read. The point is that CI or a shell can pick it up
    # as a failure as it stands.
    # This is where the real pipeline definitions are fetched. On failure it ends with 2
    # (= "the check could not be made"), not with 1 (= "they do not line up"). Mix the
    # two and picking the wrong interpreter looks like broken definitions.
    try:
        from memstara.pipeline.core import (
            BOARD_AGENT_NAMES,
            BOARD_SERVERS,
            BOARD_TOOLS,
            QUESTION_TOOLS,
        )
    except Exception as e:  # noqa: BLE001
        print(f"  could not read memstara.pipeline.core — "
              f"run it with the core interpreter: {e}")
        return 2

    copy = _copy_from_stores()
    # checks below: triples of (name, the real definition, the viewer's copy). Why the
    # dict() wrappers: the pipeline side may be another type such as a MappingProxy —
    # and then `==` is false even when the contents are the same, inventing a mismatch
    # that is not there.
    checks = [
        ("BOARD_TOOLS", dict(BOARD_TOOLS), copy["tools"]),
        ("BOARD_SERVERS", dict(BOARD_SERVERS), copy["servers"]),
        ("BOARD_AGENT_NAMES", dict(BOARD_AGENT_NAMES), copy["names"]),
        # Not a stage table — the tools the hypothesis agent holds when it writes the
        # wave's questions instead of answering one. Checked here for the same reason as
        # the three above: the viewer copies it, and a copy nobody compares is how the
        # screen comes to disagree with the pipeline quietly.
        ("QUESTION_TOOLS", set(QUESTION_TOOLS), copy["question"]),
    ]

    bad = False
    # It does not stop at the first mismatch: it **goes all the way through** and prints
    # every item that did not line up, so whoever fixes it can see the lot at once.
    for label, real, mirror in checks:
        if real == mirror:
            print(f"  {label:20} match")
            continue
        bad = True
        print(f"  {label:20} ⛔ mismatch")
        if not isinstance(real, dict):
            # QUESTION_TOOLS is a flat set, not a stage table. Printing which side each
            # difference is on says the same thing the per-key loop below says, and a set
            # has no .get() for that loop to call.
            print(f"     only in the pipeline: {sorted(set(real) - set(mirror))}")
            print(f"     only in the viewer:   {sorted(set(mirror) - set(real))}")
            continue
        for key in sorted(set(real) | set(mirror)):
            if real.get(key) != mirror.get(key):
                # The union is walked and compared with get() so that a key present on
                # only one side is caught too. The pipeline value and the viewer value
                # are printed one above the other.
                print(f"     {key}: pipeline {real.get(key)}")
                print(f"     {' ' * len(key)}  viewer   {mirror.get(key)}")

    # The scene also needs a place and a home for every stage, or a character would be
    # silently dropped from the drawing. Even with the three tables matching, without
    # this check the state "a new stage exists but is not on screen" would be missed.
    sys.path.insert(0, str(HERE / "api"))
    import stores  # noqa: PLC0415
    # Here stores **is genuinely imported.** The purpose differs from above
    # (_copy_from_stores): that one had to look at "the table copied out", whereas this
    # has to check **the viewer's actual behaviour** — HOME, AGENT_LABELS, store_of().

    # `real` is rebound by the loop above; name the table we actually mean.
    stages = set(BOARD_TOOLS)
    # Retired stages count as known here. The pipeline has not named `curator` since
    # 2026-09-07, but the viewer still has to draw and label the runs recorded against
    # it, so `stores.LEGACY_BOARD_AGENT_NAMES` keeps the key alive on this side alone.
    # Leaving it out of `known` would make the checks below reject exactly the mapping
    # that keeps those runs on screen — a checker refusing the thing it exists to
    # protect.
    known = stages | set(stores.LEGACY_BOARD_AGENT_NAMES)
    # A stage does not need a place of its own — it needs to be **drawn**, and
    # `stores.DRAWN_AS` lets one character stand for two stages (the retired curator is
    # drawn as the hypothesis stage). So the question is whether the character it
    # resolves to has a place, not whether the stage does. Every stage still needs its
    # own label: `AGENT_LABELS` is what names an agent in the cost table, the access map
    # and the feed.
    missing_home = {stores.drawn_as(s) for s in known} - set(stores.HOME)
    missing_label = known - set(stores.AGENT_LABELS)
    # `DRAWN_AS` is checked from both ends, or the grouping becomes a way to lose a
    # stage quietly: a key naming a stage nothing knows about folds nothing, and a value
    # naming a character with no place folds a real stage into thin air.
    unknown_source = set(stores.DRAWN_AS) - known
    unknown_target = set(stores.DRAWN_AS.values()) - set(stores.HOME)
    if missing_home or missing_label or unknown_source or unknown_target:
        bad = True
        print(f"  {'scene places':20} ⛔ missing stages home={missing_home} label={missing_label}")
        if unknown_source or unknown_target:
            print(f"  {'':20}    DRAWN_AS bad keys={unknown_source} bad targets={unknown_target}")
    else:
        drawn = f"{len(known)} stages drawn as {len(stores.HOME)} characters"
        print(f"  {'scene places':20} match — {drawn}, every one with a place and a name")

    # `SPLITTABLE` names the stations that may show more than one figure. A name in it
    # that is not a station is not a harmless spare entry — `_build_scene` tests
    # `character not in stores.SPLITTABLE`, so a typo there silently folds the stage it
    # meant to split, which is the failure that made A-24 need reopening in the first
    # place. It reads as working: five characters on the floor, one per stage, exactly
    # what a default run looks like anyway.
    unknown_split = stores.SPLITTABLE - set(stores.HOME)
    if unknown_split:
        bad = True
        print(f"  {'splittable':20} ⛔ not stations: {sorted(unknown_split)}")
    else:
        folded = sorted(set(stores.HOME) - stores.SPLITTABLE)
        print(f"  {'splittable':20} match — {sorted(stores.SPLITTABLE)} split by worker, "
              f"{len(folded)} folded to one figure")

    every_tool = ({t for ts in BOARD_TOOLS.values() for t in ts}
                  | set(QUESTION_TOOLS)
                  | {"read_board", "count_waiting"})
    # Every tool the stages use, plus the question step's — that is the hypothesis
    # agent's other job, so its tools are in `QUESTION_TOOLS` and in no entry of
    # `BOARD_TOOLS`. Without the union `read_questions` and `propose_questions` would go
    # unchecked here while still being listed in `BOARD_WINDOWS`, which is the one
    # combination that puts a tool on screen with no place to light up.
    #
    # Plus the two that belong to no stage: `read_board` is the driving script's business
    # and `count_waiting` is used by nobody, but they still have to have a store mapping —
    # because they have to appear in the "windows" list on screen.
    unmapped = {t for t in every_tool if stores.store_of(t) == "unknown"}
    # If `store_of` returns "unknown", that tool call **lights up no place at all** on
    # screen. Rather than have it vanish quietly, it is caught here.
    if unmapped:
        bad = True
        print(f"  {'tool -> store':20} ⛔ tools with no mapping {sorted(unmapped)}")
    else:
        print(f"  {'tool -> store':20} match — all {len(every_tool)} tools have a store")

    print("\n  " + ("⛔ mismatch — fix the stand-in tables in stores.py" if bad else "everything matches"))
    return 1 if bad else 0


if __name__ == "__main__":
    # The return value is used as the exit code as it stands.
    raise SystemExit(main())
