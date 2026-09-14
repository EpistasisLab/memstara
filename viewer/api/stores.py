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
   reported_as()            agent name -> the name every screen reports it under
   label_of()               agent name -> what the screen calls it, after the fold
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
   5. **Five stages, five agents on screen — and a sixth name still in the database.**
      The pipeline had a `curator` agent until 2026-09-07; writing the wave's questions
      is the hypothesis agent's other job now. `LEGACY_BOARD_AGENT_NAMES` keeps the old
      agent name and `DRAWN_AS` folds it into the hypothesis stage, so every run it made
      still counts. The rows are **added together**, not dropped: totals are the same
      with the fold and without it. Deleting the fold would silently subtract hundreds
      of runs of real spend from the cost table.
==============================================================================
"""

from __future__ import annotations

import sys
from typing import Any

# There used to be a `sys.path.insert` of the sandbox root here, so that
# `src/memstara/pipeline/core.py` sitting there could be imported. The pipeline is now the installed
# `memstara` package, so the interpreter finds it on its own — or does not, in Docker,
# which is what the fallback below is for.


def _pipeline_definitions() -> tuple[
    dict[str, set[str]], dict[str, set[str]], dict[str, str], set[str],
]:
    """BOARD_TOOLS / BOARD_SERVERS / BOARD_AGENT_NAMES / QUESTION_TOOLS from the pipeline.

    Imported lazily and defensively: `memstara.pipeline.core` pulls in motoro, which needs
    its own environment. If that fails the viewer must still start — it just falls back
    to the same tables written out, and says so (`IMPORTED_FROM_PIPELINE`, which
    `/api/health` carries out to the screen).

    `QUESTION_TOOLS` is the fourth because it is not a stage and has no entry in the
    other three: it is the tool list the hypothesis agent is handed when it writes the
    wave's questions rather than answering one. The screen has to know about it or the
    hypothesis character's window list loses three windows it really can open.
    `QUESTION_SERVERS` is deliberately not fetched — nothing here draws servers per
    stage, and a copied table nothing reads is a table that goes stale unnoticed.
    """
    try:
        from memstara.pipeline.core import (  # type: ignore
            BOARD_AGENT_NAMES,
            BOARD_SERVERS,
            BOARD_TOOLS,
            QUESTION_TOOLS,
        )

        return (dict(BOARD_TOOLS), dict(BOARD_SERVERS), dict(BOARD_AGENT_NAMES),
                set(QUESTION_TOOLS))
    except Exception:  # noqa: BLE001 - any import failure has the same fallback
        # Whatever the import failed for, the outcome is the same: use the tables
        # below. These three blocks are a COPY. A copy is fine; a copy nobody checks is
        # not, so `check_definitions.py` reads them back (by parsing this file with ast,
        # never importing it) and compares them with the real definitions. Run that
        # checker after editing anything here.
        return (
            {
                "hypothesis": {"okf_list_domains", "okf_search", "okf_read",
                               "describe_dataset", "match_concepts", "match_concept",
                               "claim_question", "create_task"},
                "data": {"describe_dataset", "slice_columns", "claim_task", "submit_result"},
                "ml": {"train_and_score", "claim_task", "submit_result"},
                "interpreter": {"claim_task", "submit_result"},
                "report": {"read_results", "okf_search", "okf_read"},
            },
            {
                "hypothesis": {"okf", "memstara-data", "memstara-blackboard",
                               "semantic-matcher"},
                "data": {"memstara-data", "memstara-blackboard"},
                "ml": {"memstara-ml", "memstara-blackboard"},
                "interpreter": {"memstara-blackboard"},
                "report": {"okf", "memstara-blackboard"},
            },
            {
                "hypothesis": "memstara-board-hypothesis",
                "data": "memstara-board-data",
                "ml": "memstara-board-ml",
                "interpreter": "memstara-board-interpreter",
                "report": "memstara-board-report",
            },
            {"okf_list_domains", "okf_search", "okf_read",
             "read_question_catalog", "propose_questions"},
        )


BOARD_TOOLS, BOARD_SERVERS, BOARD_AGENT_NAMES, QUESTION_TOOLS = _pipeline_definitions()

# Agents that are not in the pipeline any more but are in the database. **The viewer has
# to keep knowing their names or it stops counting their runs.**
#
# `memstara-board-curator` was the board path's sixth agent until 2026-09-07, when
# writing the wave's questions became the hypothesis agent's other job rather than a
# second agent (`src/memstara/pipeline/core.py:345-371`). The pipeline no longer names
# it, so it no longer arrives through `BOARD_AGENT_NAMES` — but motoro still holds every
# run it ever made, and `scene._access` drops any row whose agent name is not in
# `AGENT_BY_NAME_ANY`. Forget the name and hundreds of runs of real spend leave the cost
# total with nothing on any screen to say so.
#
# It maps to the `curator` stage key, which `DRAWN_AS` below folds into `hypothesis` —
# so those historical rows land where they always have, under the agent that does that
# work now. That is the fold doing what it was built for, one version later.
LEGACY_BOARD_AGENT_NAMES = {"curator": "memstara-board-curator"}

# Live stages plus retired ones — **every board stage the viewer can be asked to draw**,
# which is not the same set as the pipeline's. `scene.py` reads this rather than
# `BOARD_TOOLS`: a stage missing here never reaches `_members_of_each_character`, so its
# runs are indexed and then never looked up, and the character's card silently shows
# `idle` while that agent is the one working.
BOARD_AGENT_NAMES_ANY = {**BOARD_AGENT_NAMES, **LEGACY_BOARD_AGENT_NAMES}

# Every window a stage can open, across **all** of its jobs. `BOARD_TOOLS` is per call
# and this is per agent, and since 2026-09-07 those are two different questions: the
# hypothesis agent is handed `QUESTION_TOOLS` when it writes the wave's questions and
# `BOARD_TOOLS["hypothesis"]` when it answers one, and it really can open both sets —
# just never in the same call. The scene reads this so its window list keeps saying
# what the agent can do rather than what one call can do.
#
# `curator` is the retired stage, and QUESTION_TOOLS is exactly the grant it used to
# hold — so a run replayed from before the merge shows the same windows it always did.
STAGE_WINDOWS: dict[str, set[str]] = {
    **{stage: set(tools) for stage, tools in BOARD_TOOLS.items()},
    "curator": set(QUESTION_TOOLS),
}
STAGE_WINDOWS["hypothesis"] = STAGE_WINDOWS["hypothesis"] | QUESTION_TOOLS
# True if the real definitions were read, False if the written fallback was used.
# `/api/health` passes this straight through, so someone looking at the screen can tell
# whether the picture is drawn against the real pipeline.
IMPORTED_FROM_PIPELINE = "memstara.pipeline.core" in sys.modules

# Reverse of BOARD_AGENT_NAMES, so a row from core's `agents` table becomes a scene
# character — "memstara-board-ml" -> "ml". The legacy names are in it too: a historical
# row has to resolve to a stage before `DRAWN_AS` can fold it anywhere.
AGENT_BY_NAME = {v: k for k, v in BOARD_AGENT_NAMES_ANY.items()}

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
    # BOTH paths merged, plus the retired names. The access map (scene._access) must use
    # this rather than AGENT_BY_NAME, or the supervisor path's calls are not counted at
    # all — and it drops any name missing from here, which is why the legacy entries
    # matter as much as the live ones.
    **{v: k for k, v in BOARD_AGENT_NAMES_ANY.items()},
    **{v: k for k, v in SUPERVISOR_AGENT_NAMES.items()},
}
AGENT_PATH = {
    # Which path an agent name belongs to, so the screen can tell the two apart. A
    # retired board agent is still a board agent — its runs happened on that path.
    **{v: "board" for v in BOARD_AGENT_NAMES_ANY.values()},
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
# characters on the floor, and the only one**: `scene.py` iterates it. Five stages come
# out of the pipeline and five stand here; the retired `curator` reaches the floor too,
# through `DRAWN_AS` below, which folds it into the hypothesis stage. A stage that
# neither appears here nor resolves through `DRAWN_AS` to something that does is
# silently dropped from the drawing, which is what `check_definitions.py` watches for.
HOME: dict[str, dict[str, int]] = {
    "hypothesis":  {"x": 160, "y": 470},
    "data":        {"x": 335, "y": 470},
    "ml":          {"x": 510, "y": 470},
    "interpreter": {"x": 685, "y": 470},
    "report":      {"x": 860, "y": 470},
}

# The stations that may show more than one figure at once. **Everything not named here
# is drawn as exactly one character however many workers are running behind it.**
#
# This is the meeting's decision of 2026-08-26, not an implementation detail: the backend
# may run N of any stage in parallel, and the screen shows the hypothesis stage split
# because that is the parallelism the user is choosing, while the data agent stays a
# single figure — the user does not need to know that it is internally run more than once.
#
# **`interpreter` was added here on 2026-09-08 and taken out again the same day**, and the
# reason is worth keeping because the argument for adding it was persuasive and wrong.

# interpretation agents → reporting*, so interpretation belonged beside hypothesis. The
# record says the opposite twice over: the V1 role table is *hypothesis 1–2 (the screen
# extensible to 3), data · ML · interpreter · report one each*, and combinatorial
# interpretation — one hypothesis read by several interpreters — was **rejected** for the

# `:97`). The same page states the rule this line implements almost word for word: the
# internal execution count of a non-hypothesis role is deliberately not shown to the user
# as a duplicated role.
#
# So `data`, `ml` and `interpreter` are alike here, and they are alike for a reason that is
# about the design rather than about them all running N workers by the same mechanism
# (`board.py:1680-1725`) — which they do, and which is not why.
#
# It is declared here rather than in `scene.py` for the same reason `HOME` and `DRAWN_AS`
# are: the definition lives in one file and `scene.py` consumes it, which is the shape
# `check_definitions.py` can read. A name here that is not a key of `HOME` is a station
# that does not exist; that file is what says so, because this module has no import-time
# guards and adding the first one here would hide the check where nobody runs it.
#
# **This was shipped backwards once.** Until 2026-09-08 `_build_scene` split every key of
# `HOME` by worker, so `--data-agents 2` drew `data#1` and `data#2` — the exact thing the

# asked for. Every check passed, because all three of them had been written from the
# implementation instead of from the item.
#
# **The floor plan is not what decides this, and A-33 assumed it was.** That item deferred
# adding a second station on the expectation that the row could not hold it. It can, at any
# station: figures are 128 wide, stand at `home.x - 64`, and step `+22, -62` per slot
# (`viewer/web/src/panels/ScenePanel.tsx:76`), so a stack of three spans 172 against a row
# spaced 175 apart and clears the next station's column by 3px. The same 3px everywhere,
# because it is the same 175. `tests/test_scene_layout.py` derives that from `HOME` rather
# than asserting it, so moving a station makes it a pixel question again loudly.
#
# The arithmetic is kept here although the station it was worked out for is gone, because
# it is what establishes that this set is settled by the design and by nothing else. A
# future stage arriving here needs an argument from the record, not from the canvas.
#
# **Three is the ceiling, and it is not enforced here.** A fourth figure would land across
# the next station's column. The limit belongs to the drawing, so it is written where the
# drawing's requests are checked — `_MAX_HYPOTHESIS_AGENTS`
# (`src/memstara/control/request.py:63`), which caps a browser-started run and says in its
# own comment why the driver is deliberately left uncapped. A cap in *this* file would
# silently hide a running worker, which is the exact failure `folded` was written to avoid.
SPLITTABLE: frozenset[str] = frozenset({"hypothesis", "interpreter"})

# Which character a stage is *drawn* as. **This is now a compatibility layer**, and it
# is the reason a run from before 2026-09-07 still shows up on every screen.
#
# It was written when the pipeline had six agents, to draw the curator and the
# hypothesis stage as one: the floor plan shows which store a character stands in front
# of, and for most of a run those two stood in front of the same one. Measured on the
# three-trial run of 2026-09-05 (`outputs/runs/2026-09-05T184303_board_3trials/trace/`):
# the curator made 13 tool calls and 11 went to the OKF shelf — everything except
# `read_questions` and `propose_questions` — and the hypothesis workers spent 8 of 12,
# 9 of 13 and 6 of 10 calls in the same place. Two characters at one shelf, and the
# drawing distinguishing nothing.
#
# **The pipeline has since agreed.** Writing the wave's questions is the hypothesis
# agent's other job now, not a second agent (`src/memstara/pipeline/core.py:345-371`),
# and the reasoning the fold used to argue against — that the two are genuinely
# different work — is preserved one layer down, in the tool list each *call* is handed
# (`core.py:448-466`). So for a run made today this table has nothing to do.
#
# **Do not delete it.** motoro holds hundreds of runs recorded against
# `memstara-board-curator`, `LEGACY_BOARD_AGENT_NAMES` above resolves that name to the
# `curator` stage, and this line is what carries it onto a screen. Without it those rows
# reach `AGENT_LABELS` with a stage no character has, and the shortest way to make that
# stop being an error is to drop them — which takes real spend off the cost total with
# nothing anywhere to say so.
#
# Two properties of the fold, both still true and neither hidden:
#
#   - **The numbers are added, never dropped.** `_agent_totals` sums the folded rows and
#     `_access` re-aggregates them, so total cost, tokens and call counts are identical
#     with the fold and without it.
#   - **You cannot ask the viewer what the curator alone cost.** That question needs the
#     database, or `verify.py`, which reads it unfolded.
#
# The Log panel still prints `curator0` for a run made before the merge, because that
# panel tails the pipeline's stdout and rewriting a console is falsifying a record. A run
# made after it prints `question0` (`src/memstara/pipeline/board.py:1019-1022`).
DRAWN_AS: dict[str, str] = {"curator": "hypothesis"}


def drawn_as(stage: str) -> str:
    """The character `stage` appears as on the scene. Identity for every live stage."""
    return DRAWN_AS.get(stage, stage)


def base_agent_name(name: str) -> str:
    """An agent name with its playbook suffix taken off, if it has one.

    `memstara-board-hypothesis-cardiometabolic` -> `memstara-board-hypothesis`. Every
    other name comes back exactly as it arrived, including one this file has never heard
    of — the viewer's rule everywhere is that an unrecognised name is passed through, not
    guessed at.

    **Why this exists.** Until 2026-09-08 an agent name was one of nine fixed strings and
    `AGENT_BY_NAME` could be a dict. `A-32` made the hypothesis stage provision one agent
    per behavioural standard, named for the standard it carries, so the set is now open —
    it grows with `src/memstara/playbooks/`. Every lookup in `scene.py` filters on
    membership of that dict, so without this a run under a standard is dropped at the
    door: no figure on the scene, no row in the cost table, and no error anywhere,
    because being absent from a dict is not a failure.

    **Matched by prefix rather than by reading the playbook directory.** The directory is
    the authority on which standards exist, but the viewer runs in a container that may
    not have it — `_pipeline_definitions` already falls back for exactly that reason —
    and a name that arrived from the database is evidence the agent existed whatever the
    directory says today. A prefix is also the one form that cannot go stale.

    The prefix has to be a *whole* segment: `-` is required after the base name, so
    `memstara-board-ml` is never read as a suffixed `memstara-board-m`. Only board names
    are stripped; the supervisor path has no playbooks.
    """
    for base in BOARD_AGENT_NAMES_ANY.values():
        if name.startswith(f"{base}-"):
            return base
    return name


def stage_of_agent(name: str) -> str | None:
    """The board stage an agent name belongs to, or `None` if it is not a board agent.

    Use this rather than `AGENT_BY_NAME.get`, and `stage_of_agent(n) is not None` rather
    than `n in AGENT_BY_NAME`: the dict holds one name per stage and a playbook-suffixed
    name is not in it (`base_agent_name`).
    """
    return AGENT_BY_NAME.get(base_agent_name(name))


def stage_of_agent_any(name: str) -> str | None:
    """As `stage_of_agent`, across the board path and the supervisor path both.

    The access map, the cost table and the feed use this one — they show what actually
    ran, and most of what ran historically was the supervisor path.
    """
    return AGENT_BY_NAME_ANY.get(base_agent_name(name))


def path_of_agent(name: str) -> str:
    """`"board"`, `"supervisor"`, or `"other"` for a name the viewer does not know."""
    return AGENT_PATH.get(base_agent_name(name), "other")


def playbook_of(name: str) -> str:
    """The standard a suffixed agent name carries, or `""` if it carries none.

    The inverse half of `base_agent_name`, and the reason both exist: the suffix has to
    come off for the stage lookup and stay visible on the label, or two agents running to
    two different standards appear on the cost table as two rows called the same thing.
    """
    base = base_agent_name(name)
    return name[len(base) + 1:] if base != name else ""


def reported_as(name: str) -> str:
    """The agent name a row is *shown under*. Identity unless the stage folds.

    The fold is display-wide, not scene-only: the cost table, the access map and the feed
    all report the retired curator's runs under the hypothesis agent, which is the agent
    that does that work now. Only historical rows reach it — nothing made since
    2026-09-07 is recorded under a folded name.

    **The numbers must survive it.** Callers do not just relabel — they add the folded
    rows together, so the cost, the token counts and the call counts are the same before
    and after. A fold that quietly dropped a row would take that spend off the total,
    which is the one failure here that would be invisible on screen.

    The fold stays inside one path. The board path had a curator; the supervisor path
    never did, so there is nothing there to fold, and `AGENT_PATH` keeps the two apart
    the way it always has.

    **A playbook-suffixed name reports under itself, and that is the decision here.** Two
    hypothesis agents running to two standards are two agents; folding their rows together
    would make the one question the split exists to answer — did the standard change what
    the agent did, and what did each cost — unaskable from the screen. The suffix is
    resolved for the *stage* lookup and kept in the name.
    """
    stage = stage_of_agent_any(name)
    if stage is None:
        return name  # An agent the viewer cannot name is left exactly as it arrived.
    target = drawn_as(stage)
    if target == stage:
        return name
    names = BOARD_AGENT_NAMES if path_of_agent(name) == "board" else SUPERVISOR_AGENT_NAMES
    return names.get(target, name)


def label_of(name: str) -> str:
    """What the screen calls the agent behind `name`, after the fold. Raw name if unknown.

    A suffixed name carries its standard into the label — `Hypothesis · cardiometabolic` —
    because `AGENT_LABELS` is per stage and two agents of one stage would otherwise be two
    rows reading identically in the cost table and the access map.
    """
    reported = reported_as(name)
    stage = stage_of_agent_any(reported)
    if not stage:
        return name
    label = AGENT_LABELS.get(stage, name)
    book = playbook_of(reported)
    return f"{label} · {book}" if book else label


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
    # `curator` is a retired stage and no screen ever reads this entry — everything goes
    # through `label_of`, which resolves the fold first and arrives at `hypothesis`. It
    # is here because `check_definitions.py:154` requires a label for every stage the
    # viewer knows, and `LEGACY_BOARD_AGENT_NAMES` makes this one of them.
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
    # The question step's two. They are drawn as the board, but the table they really touch
    # is `memstara_questions` (src/memstara/mcp_servers/blackboard.py:719, 833, 898) — a third store on the
    # same server, not the task board. Folded in on purpose for now; if the question
    # bank is ever worth its own place on screen, it needs PLACES here plus StoreId and
    # STORE_LABEL on the web side.
    "read_questions": "board",  # Legacy trace lookup only.
    "read_question_catalog": "board",
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
    # These two say "Hypothesis" and that is now literally true rather than a reader's
    # convenience: they are in `QUESTION_TOOLS` (`src/memstara/pipeline/core.py:448-466`),
    # which is the tool list the hypothesis agent is handed when it writes the wave's
    # questions instead of answering one. They are deliberately not in
    # `BOARD_TOOLS["hypothesis"]`, so `check_definitions.py` does not see them there —
    # the permission is per call, and this table is per tool.
    {"tool": "read_question_catalog", "holder": "Hypothesis",      "store": "board"},
    {"tool": "propose_questions", "holder": "Hypothesis",      "store": "board"},
]
