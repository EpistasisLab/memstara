"""Which store each tool touches, and where things sit on the scene.

The mapping is derived from `memstara.pipeline.core.BOARD_TOOLS` / `BOARD_SERVERS`
rather than
copied. Copying a table means the pipeline can change and only the picture goes stale —
and a picture that is quietly wrong is worse than no picture. (A written-out fallback
does live in the function below, for the case where the import fails; that copy is
watched by `check_definitions.py`.)

The subtle part: **one server can point at two different stores.** The board server
carries `create_task`/`claim_task`/`submit_result`, which touch the board, and
`read_results`, which touches the results table. Those are separate stores on purpose
(the board holds what is moving, the results table what was found), so mapping by
server alone would draw them as one place. That is why `TOOL_STORE` below is keyed by
tool, not by server.

==============================================================================
 HOW TO READ THIS FILE
==============================================================================

 What it is
   Pure tables. No database, no async. It defines agent name <-> stage, tool <->
   store, and the scene's coordinates. `scene.py` reads these to build what the
   screen draws.

 The tables, top to bottom
   _pipeline_definitions()  import the real definitions; fall back to a written copy
   BOARD_TOOLS / BOARD_SERVERS / BOARD_AGENT_NAMES   per-stage tools, servers, names
   AGENT_BY_NAME            agent name -> stage (board path only)
   SUPERVISOR_AGENT_NAMES   the older supervisor path's four agents
   AGENT_BY_NAME_ANY        BOTH paths merged  <- the access map uses this one
   AGENT_PATH               agent name -> "board" or "supervisor"
   PLACES / HOME            scene coordinates (the SVG's own 1000x560 space)
   DRAWN_AS / drawn_as()    stage -> the character it is drawn as  <- display only
   AGENT_LABELS             stage -> the name shown on screen
   TOOL_STORE / store_of()  tool -> store
   normalise_server()       fold the old `ecoxai-*` server names into the current ones
   BOARD_WINDOWS            the eight windows the board server opens, and whose they are

 Easy to miss
   1. **Keyed by tool, not by server.** By server, the board and the results table
      collapse into one place.
   2. **There are two paths.** The board path (BOARD_*) and the older supervisor path
      (SUPERVISOR_*). The supervisor path has far more runs (159 against 48), so
      dropping it understates the access map roughly fivefold. The scene draws only
      the board characters; `path` is what separates the two everywhere else.
   3. The coordinates live in the **backend**. The frontend invents no positions, so a
      place can be moved without touching a component.
   4. `read_board` and `count_waiting` showing zero calls is **the correct picture,
      not a bug** — the first belongs to the driving script, the second to nobody.
   5. **Six stages, five characters.** `DRAWN_AS` folds the curator into the
      hypothesis stage *on the scene only*, and the merged character is labelled plainly
      `Hypothesis` — the drawing does not name the curator anywhere. Nothing else folds:
      the cost table, the access map and the feed all still report six, by name. If you
      are looking for the curator and it is not in `HOME`, it has not been deleted —
      read `DRAWN_AS`, then the Agents tab.
==============================================================================
"""

from __future__ import annotations

import sys
from typing import Any

# There used to be a `sys.path.insert` of the sandbox root here, so that
# `src/memstara/pipeline/core.py` sitting there could be imported. The pipeline is now the installed
# `memstara` package, so the interpreter finds it on its own — or does not, in Docker,
# which is what the fallback below is for.


def _pipeline_definitions() -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, str]]:
    """BOARD_TOOLS / BOARD_SERVERS / BOARD_AGENT_NAMES straight from the pipeline.

    Imported lazily and defensively: `memstara.pipeline.core` pulls in motoro, which needs
    its own environment. If that fails the viewer must still start — it just falls back
    to the same tables written out, and says so (`IMPORTED_FROM_PIPELINE`, which
    `/api/health` carries out to the screen).
    """
    try:
        from memstara.pipeline.core import BOARD_AGENT_NAMES, BOARD_SERVERS, BOARD_TOOLS  # type: ignore

        return dict(BOARD_TOOLS), dict(BOARD_SERVERS), dict(BOARD_AGENT_NAMES)
    except Exception:  # noqa: BLE001 - any import failure has the same fallback
        # Whatever the import failed for, the outcome is the same: use the tables
        # below. These three blocks are a COPY. A copy is fine; a copy nobody checks is
        # not, so `check_definitions.py` reads them back (by parsing this file with ast,
        # never importing it) and compares them with the real definitions. Run that
        # checker after editing anything here.
        return (
            {
                "curator": {"okf_list_domains", "okf_search", "okf_read",
                            "read_questions", "read_results", "propose_questions"},
                "hypothesis": {"okf_list_domains", "okf_search", "okf_read",
                               "describe_dataset", "match_concepts", "match_concept",
                               "claim_question", "create_task"},
                "data": {"describe_dataset", "slice_columns", "claim_task", "submit_result"},
                "ml": {"train_and_score", "claim_task", "submit_result"},
                "interpreter": {"claim_task", "submit_result"},
                "report": {"read_results", "okf_search", "okf_read"},
            },
            {
                "curator": {"okf", "memstara-blackboard"},
                "hypothesis": {"okf", "memstara-data", "memstara-blackboard",
                               "semantic-matcher"},
                "data": {"memstara-data", "memstara-blackboard"},
                "ml": {"memstara-ml", "memstara-blackboard"},
                "interpreter": {"memstara-blackboard"},
                "report": {"okf", "memstara-blackboard"},
            },
            {
                "curator": "memstara-board-curator",
                "hypothesis": "memstara-board-hypothesis",
                "data": "memstara-board-data",
                "ml": "memstara-board-ml",
                "interpreter": "memstara-board-interpreter",
                "report": "memstara-board-report",
            },
        )


BOARD_TOOLS, BOARD_SERVERS, BOARD_AGENT_NAMES = _pipeline_definitions()
# True if the real definitions were read, False if the written fallback was used.
# `/api/health` passes this straight through, so someone looking at the screen can tell
# whether the picture is drawn against the real pipeline.
IMPORTED_FROM_PIPELINE = "memstara.pipeline.core" in sys.modules

# Reverse of BOARD_AGENT_NAMES, so a row from core's `agents` table becomes a scene
# character — "memstara-board-ml" -> "ml".
AGENT_BY_NAME = {v: k for k, v in BOARD_AGENT_NAMES.items()}

# The older supervisor path (src/memstara/pipeline/mvp.py) has its own four agents, kept side by
# side so the two ways of driving the same four stages can be compared. They do real
# work — 159 runs against the board path's 48 — so the access map has to include them
# or it understates what actually happened by about five times. The scene draws only
# the board characters; `path` is what keeps the two apart everywhere else.
SUPERVISOR_AGENT_NAMES = {
    "hypothesis": "memstara-hypothesis",
    "data": "memstara-data",
    "ml": "memstara-ml",
    "interpreter": "memstara-interpreter",
}
AGENT_BY_NAME_ANY = {
    # BOTH paths merged. The access map (scene._access) must use this rather than
    # AGENT_BY_NAME, or the supervisor path's calls are not counted at all.
    **{v: k for k, v in BOARD_AGENT_NAMES.items()},
    **{v: k for k, v in SUPERVISOR_AGENT_NAMES.items()},
}
AGENT_PATH = {
    # Which path an agent name belongs to, so the screen can tell the two apart.
    **{v: "board" for v in BOARD_AGENT_NAMES.values()},
    **{v: "supervisor" for v in SUPERVISOR_AGENT_NAMES.values()},
}

# The places on the scene. Coordinates are in the SVG's own 1000x560 space; the
# frontend does not invent positions, so the backend stays the single source of the
# layout and a place can be moved without touching a component.
#
# `id` must match a value in `TOOL_STORE`, or tool calls never reach the place.
PLACES: list[dict[str, Any]] = [
    {"id": "okf",     "label": "Knowledge source", "sub": "OKF bundle",          "x": 120, "y": 110},
    {"id": "matcher", "label": "Semantic matcher", "sub": "semantic-matcher",    "x": 330, "y": 110},
    {"id": "board",   "label": "Board",            "sub": "memstara_blackboard", "x": 500, "y": 110},
    {"id": "results", "label": "Results table",    "sub": "memstara_results",    "x": 870, "y": 110},
    {"id": "dataset", "label": "Dataset",          "sub": "CSV",                 "x": 120, "y": 300},
    {"id": "ml",      "label": "Trainer",          "sub": "train_and_score",     "x": 330, "y": 300},
]

# Where each character rests when it has nothing to do — five of them side by side
# along the bottom (y=470), in the order the pipeline runs them. **This is the list of
# characters on the floor, and the only one**: `scene.py` iterates it. Six stages come
# out of the pipeline and five stand here, because `DRAWN_AS` below folds the curator
# into the hypothesis stage. A stage that neither appears here nor resolves through
# `DRAWN_AS` to something that does is silently dropped from the drawing, which is what
# `check_definitions.py` watches for.
HOME: dict[str, dict[str, int]] = {
    "hypothesis":  {"x": 160, "y": 470},
    "data":        {"x": 335, "y": 470},
    "ml":          {"x": 510, "y": 470},
    "interpreter": {"x": 685, "y": 470},
    "report":      {"x": 860, "y": 470},
}

# Which character a stage is *drawn* as. **This is the picture, not the pipeline.**
#
# The curator and the hypothesis stage are drawn as one because the floor plan draws
# which store a character is standing in front of, and for most of a run those two are
# standing in front of the same one. Measured on the three-trial run of 2026-09-05
# (`outputs/runs/2026-09-05T184303_board_3trials/trace/`): the curator made 13 tool
# calls and 11 went to the OKF shelf — everything except `read_questions` and
# `propose_questions` — and the hypothesis workers spent 8 of 12, 9 of 13 and 6 of 10
# calls in the same place. Two characters at one shelf, and the drawing distinguishing
# nothing.
#
# **The curator stage is not removed and this table does not remove it.** It keeps its
# agent, its prompt, its tool grant and every row it has ever written. The pipeline
# genuinely does tell the two apart, and deliberately — `src/memstara/pipeline/core.py`
# `:382-387` gives the curator `read_results` because that is the whole feedback path,
# and `:394-396` keeps `read_questions` with it because a stage that can read the whole
# bank can pick itself a second question. None of that is affected by where a character
# stands. `_agent_totals`, `_access` and `_feed` go on reporting six agents under six
# names.
#
# The merged character is labelled `Hypothesis`, not "Hypothesis · Curator": the drawing
# is meant to show one stage, and a compound name puts the word back on the screen the
# fold was supposed to take it off. The cost of that is worth stating — a reader who
# sees a "Curator" line in the feed cannot point at the character it belongs to, and has
# to go to the Agents tab, where the curator is still its own row. That is the trade
# this table makes on purpose.
DRAWN_AS: dict[str, str] = {"curator": "hypothesis"}


def drawn_as(stage: str) -> str:
    """The character `stage` appears as on the scene. Identity for all but the curator."""
    return DRAWN_AS.get(stage, stage)


AGENT_LABELS = {
    # Stage -> the name shown on screen.
    #
    # "Report · Insight" is one stage under two names on purpose. The plan calls this the
    # insight agent (`spec/components/05_agents_implementation_plan_KR.md:121` — a finished
    # board in, a report out) and the code has always called it `report`. Only the label
    # moves: the
    # stage key stays `report` here and in the pipeline, and the agent stays
    # `memstara-board-report` in motoro's database, because `_ensure_agent`
    # (`src/memstara/pipeline/core.py:234-269`) finds an agent by its name. Renaming it
    # would create a second agent, orphan the first, and leave every run recorded so far
    # pointing at a name this table no longer knows — which on this screen means a
    # character with no label.
    "curator": "Curator",
    "hypothesis": "Hypothesis", "data": "Data", "ml": "ML",
    "interpreter": "Interpreter", "report": "Report · Insight",
}

# A tool touches exactly one store. Keyed by tool, not by server, because the board
# server serves two stores — see the module docstring. (`claim_task`/`submit_result`
# -> the board, `read_results` -> the results table. Same server, different places.)
TOOL_STORE: dict[str, str] = {
    # core's original three. Still registered on the okf server and still working;
    # simply not handed to any agent any more (pipeline_core BOARD_TOOLS). Kept so a
    # historical run that called them still lights up a place.
    "search_concepts": "okf",
    "get_concept": "okf",
    "list_concepts": "okf",
    # What the stages actually call now.
    "okf_list_domains": "okf",
    "okf_search": "okf",
    "okf_read": "okf",
    # The semantic matcher gets a store of its own rather than being folded into
    # "dataset". It reads the catalog built from the dataset's header, never the rows,
    # and the whole point of showing it is that a name came from the matcher instead of
    # from the agent's own typing — which is invisible if the two share a place.
    "match_concepts": "matcher",
    "match_concept": "matcher",
    "describe_dataset": "dataset",
    "slice_columns": "dataset",
    "train_and_score": "ml",
    "create_task": "board",
    "claim_task": "board",
    "submit_result": "board",
    "read_board": "board",
    "count_waiting": "board",
    "read_results": "results",
    # The curator's two. They are drawn as the board, but the table they really touch
    # is `memstara_questions` (src/memstara/mcp_servers/blackboard.py:697, 811, 876) — a third store on the
    # same server, not the task board. Folded in on purpose for now; if the question
    # bank is ever worth its own place on screen, it needs PLACES here plus StoreId and
    # STORE_LABEL on the web side.
    "read_questions": "board",
    "propose_questions": "board",
    # The hypothesis stage's one claim against the bank — the same third store as the
    # two above, drawn as the board for the same reason.
    "claim_question": "board",
}


def store_of(tool: str) -> str:
    """Which place a tool call should light up. Unknown tools go nowhere, visibly.

    An unmapped tool returns "unknown" rather than quietly lighting nothing, and
    `check_definitions.py` reads that value to catch the missing mapping.
    """
    return TOOL_STORE.get(tool, "unknown")


def normalise_server(server: str | None) -> str:
    """Fold the pre-rename server names into the current ones.

    Rows written before 2026-08-18 say `ecoxai-data`; the same server is now
    `memstara-data`. Leaving both means the access map shows one server twice. The
    same fold happens on the SQL side, in `queries.FLAT_CALLS`.
    """
    if not server:
        return ""
    return server.replace("ecoxai-", "memstara-")


# Every window the board server exposes, and who is meant to hold it. The access map
# uses this to show the ones no agent ever calls — `read_board` belongs to the driving
# script and `count_waiting` to nobody, and both being empty is the correct picture,
# not missing data. `verify.py` checks those two zeros for real.
BOARD_WINDOWS: list[dict[str, str]] = [
    {"tool": "create_task",   "holder": "Hypothesis",          "store": "board"},
    {"tool": "claim_task",    "holder": "Data / ML / Interp.", "store": "board"},
    {"tool": "submit_result", "holder": "Data / ML / Interp.", "store": "board"},
    {"tool": "read_results",  "holder": "Report",              "store": "results"},
    {"tool": "read_board",    "holder": "Driving script",      "store": "board"},
    {"tool": "count_waiting", "holder": "Nobody",              "store": "board"},
    {"tool": "read_questions",    "holder": "Curator",         "store": "board"},
    {"tool": "propose_questions", "holder": "Curator",         "store": "board"},
]
