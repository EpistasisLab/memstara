"""The body of the MVP pipeline — agent definitions, supervisor, aggregation.

The four stages fixed in the 2026-08-06 meeting, expressed against the
motoro API.

    (1) hypothesis   read the OKF, decide which columns to pull   <- the only judge
    (2) data         slice those columns plus Y                   <- pure executor
    (3) ML           train, report AUC and feature importance     <- pure executor
    (4) interpreter  narrate the result                           <- narrator

The supervisor is :func:`run_one_trial` — a Python function, not an LLM. When the job
is "call these in order and hand each output to the next," there is no reason to pay a
model to do it; it only adds cost and non-determinism.

The to-do list is :class:`TodoRow`. The meeting called this a blackboard pattern, but
core does not ship one yet (2 of 37 patterns ported) and the four stages are linear, so
a dataclass is enough.


==============================================================================
 How to read this file
==============================================================================

 The **body shared by both pipelines** (02 and 03). It defines the agents, writes
 the prompts, and gathers the results.

 The four stages, exactly as fixed in the 2026-08-06 meeting:

   (1) hypothesis   read the knowledge source, decide which columns to pull
                                                          <- **the only one that judges**
   (2) data         cut those columns plus the outcome     <- does as it is told
   (3) ML           train, report AUC and importance       <- does as it is told
   (4) interpreter  put the result into words              <- narrates only

 There are three blocks of it.

   (1) Diversity        PERSPECTIVES, temperature_for
                        Asking the same question 20 times obviously produces the
                        same answer. That is not evidence. Shaking the perspective
                        is what makes it "different angles converged on one place"

   (2) Agent definitions  provision_all (the 4 for 02), provision_board_agents
                        (the 6 for 03). Every prompt is in here. **The most
                        important part of this file.**

   (3) Execution and aggregation  run_one_trial (02's supervisor), aggregate,
                        tools_for

 The key point is that the supervisor **is a Python function, not an LLM.** There is
 no reason to pay a model for "call these in order and hand each output to the next"
 — it only costs money and makes the result waver.
"""

from __future__ import annotations

import json      # agent output (a JSON string) into Python values
import uuid      # run ids
from collections import Counter   # for counting how often each column was chosen
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import structlog

from motoro.runner import (
    create_agent,
    create_run,
    execute_run,
    get_agent_by_name,
    update_agent,
)
from motoro.schemas.agent import LLMProvider, ModelConfig

# --------------------------------------------------------------------------- #
#  Diversity — what makes 20 repetitions mean anything
# --------------------------------------------------------------------------- #
#
# Running the same agent on the same prompt 20 times will obviously produce overlap.
# That is evidence of "the same input yields the same answer," not of "these features
# are the most predictive." Varying the perspective is what turns overlap into
# "different angles converged on the same features," which is the claim the paper
# actually makes.
#
# The meeting never discussed this. It is a design judgement, not a settled decision.
PERSPECTIVES: list[str] = [
    "from a metabolic-pathway perspective",
    "from a cardiovascular risk-factor perspective",
    "from a demographic and age perspective",
    "from a chronic-inflammation perspective",
    "from a lipid-metabolism perspective",
    "from a glycemic-control perspective",
    "from a lifestyle-factor perspective",
    "from an anthropometric-measurement perspective",
    "using laboratory measurements only",
    "using vital signs only",
    "using modifiable risk factors only",
    "using non-modifiable baseline factors only",
    "using only the best-evidenced markers",
    "using markers likely to be weakly correlated with each other",
    "using whatever is most routinely measured in clinical practice",
    "using the cheapest measurements to obtain",
    "using the markers least likely to be missing",
    "using markers that act through several pathways at once",
    "using markers specific to a single pathway",
    "aiming for maximum performance from the fewest columns",
]


# Minimum columns the hypothesis agent must choose (no upper bound — the agent
# decides how many OKF-grounded columns the hypothesis needs).
# src/memstara/trace/report.py uses this to flag runs where the agent chose nothing at all.
COLUMN_COUNT_MIN = 1


def perspective_for(trial: int) -> str:
    """Which angle this trial is asked to take.

    Trial number -> perspective phrase. It is a modulo (%), so past trial 20 it wraps
    back to the beginning.
    """
    return PERSPECTIVES[trial % len(PERSPECTIVES)]


def temperature_for(trial: int) -> float:
    """Add a little sampling diversity on top of the perspective diversity.

    0.30, 0.45, 0.60, 0.75 and 0.90 are used in rotation. The higher the temperature,
    the less predictable the model's answer.

    Is the perspective not enough on its own? No — at a low temperature the same
    perspective yields nearly the same answer every time. Both have to be shaken for
    20 trials to be worth 20 trials.
    """
    return round(0.3 + (trial % 5) * 0.15, 2)


# --------------------------------------------------------------------------- #
#  The to-do list — the whole life of one hypothesis fits on this single row
# --------------------------------------------------------------------------- #


@dataclass
class TodoRow:
    """The whole life of one hypothesis. The four agents fill this row in turn.

    Used only on the 02 path (the supervisor arrangement). On 03 (the board
    arrangement) a database table stands in its place — that is what lets several
    stages pass one row back and forth between them.
    """

    trial: int                    # which trial this is
    perspective: str = ""         # the perspective phrase that trial was given

    # (1) hypothesis  — the fields the hypothesis stage fills in
    hypothesis: str = ""
    columns: list[str] = field(default_factory=list)
    okf_concept_ids: list[str] = field(default_factory=list)

    # (2) data  — the fields the data stage fills in
    subset_path: str = ""
    columns_used: list[str] = field(default_factory=list)
    columns_missing: list[str] = field(default_factory=list)

    # (3) ML  — the fields the training stage fills in
    auc: float | None = None
    feature_importance: dict[str, float] = field(default_factory=dict)
    model: str = ""

    # (4) interpreter  — the field the interpretation stage fills in
    interpretation: str = ""

    # Tracing — a core run id is an opaque UUID that cannot be a foreign key in a
    # product database, so recording it here is the only way to trace back later
    # with get_runs() / get_run_steps(). It is this value that lets `src/memstara/trace/run.py`
    # show what that agent asked the tools and what it got back.
    run_ids: dict[str, str] = field(default_factory=dict)
    error: str = ""

    # Cost and tokens per stage, taken from what execute_run returns.
    #
    # Not derivable from the logs: `llm.call.completed` is emitted only by _complete and
    # _complete_text (llm_service.py:576, :1053). complete_with_tools — the path every
    # reason_act turn takes — logs nothing, so a total summed from the log counted 9 of
    # 41 calls on a real run and understated the cost roughly tenfold. So what
    # `execute_run` returns is written down here directly.
    cost: dict[str, float] = field(default_factory=dict)
    tokens: dict[str, list[int]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Did this trial succeed?

        There is one criterion: **is there an AUC.** Reaching the training stage at
        all means the hypothesis and data stages before it obviously passed, so there
        is no need to mark each stage separately.
        """
        return self.auc is not None


def save_rows(rows: list[TodoRow], path: Path) -> None:
    """Save the to-do list to a JSON file.

    `src/memstara/trace/run.py` looks up trial number -> run id in this file. Without it, tracing
    afterwards is not possible.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
#  Agent provisioning — idempotent by name: found by name, created if absent
# --------------------------------------------------------------------------- #
#
# An agent is a **durable resource.** It is stored in core's DB and found again by the
# same name on the next run. So editing a prompt in this file does **not** reach an
# already-created agent by itself — `_ensure_agent` finds what differs and updates it.

AGENT_NAMES = {
    "hypothesis": "memstara-hypothesis",
    "data": "memstara-data",
    "ml": "memstara-ml",
    "interpreter": "memstara-interpreter",
}


async def _ensure_agent(name: str, **kwargs: Any) -> Any:
    """Idempotent by name, but refresh the definition when it has drifted.

    Returning the existing agent untouched makes the --provider / --model flags
    silently ineffective, and it also means an edited prompt in this file never
    reaches the running agent: an agent is a durable resource and its configuration
    was frozen at creation time.

    An agent's identity is its role (its name), not its model or its wording, so the
    right move is to keep the name and update what changed.
    """
    existing = await get_agent_by_name(name)
    if existing is None:
        return await create_agent(name=name, **kwargs)

    updates: dict[str, Any] = {}

    wanted_mc = kwargs.get("model_config")
    if wanted_mc is not None:
        # The ORM attribute is model_config_data; only the DB column is named
        # model_config (models/agent.py:49). Reading existing.model_config here
        # would pick up pydantic's own class attribute instead.
        current = existing.model_config_data or {}
        if (current.get("provider"), current.get("model")) != (wanted_mc.provider.value, wanted_mc.model):
            updates["model_config"] = wanted_mc

    for attr in ("system_prompt", "goal"):
        wanted = kwargs.get(attr)
        if wanted is not None and getattr(existing, attr, None) != wanted:
            updates[attr] = wanted

    if updates:
        updated = await update_agent(existing.id, **updates)
        if updated is not None:
            return updated
    return existing


async def provision_all(
    *, provider: str = "azure_foundry", model: str = "claude-sonnet-4-6"
) -> dict[str, uuid.UUID]:
    """Create the four agents (or find the existing ones) and return their ids.

    No api_key is passed: ModelConfig.api_key is exclude=True, so it does not survive
    being persisted with the agent. Credentials resolve at call time instead.
    """
    mc = ModelConfig(provider=LLMProvider(provider), model=model, max_tokens=4096)
    react = {"execution_pattern": "reason_act"}

    hypothesis = await _ensure_agent(
        AGENT_NAMES["hypothesis"],
        goal="Choose the set of columns that will predict the given outcome, grounded in the OKF knowledge source.",
        system_prompt=(
            "You are a hypothesis agent. Decide which columns to pull from the dataset in "
            "order to predict the outcome.\n\n"
            "The knowledge source (OKF) tells you WHICH PHENOMENA matter for this outcome "
            "and how strong the evidence is. The dataset tells you WHICH COLUMNS EXIST. "
            "Neither one alone is enough, and nothing connects them for you — making that "
            "connection is your job.\n\n"
            "Do NOT assume the knowledge source states column names. Different bundles are "
            "written by different people to different conventions; some name variables "
            "explicitly, some only describe a phenomenon in prose, and a field naming "
            "columns may not exist at all. Read what is actually there.\n\n"
            "Work in this order:\n"
            "1) Call describe_dataset FIRST. Read the column names and note "
            "   'missing_pct' — a column can exist and still be almost entirely blank, "
            "   and choosing such a column is close to choosing nothing.\n"
            "2) Call okf_list_domains to see what the knowledge source actually covers. It "
            "   is the cheapest possible picture of the bundle and costs one call.\n"
            "3) Search it with okf_search — on ideas, not on column names. It searches what "
            "   the authors said each document is ABOUT (title, tags, description, journal), "
            "   never the bodies, so a hit means the bundle says this document is about your "
            "   query. Pass several wordings at once, comma-separated.\n"
            "4) Open the promising ones with okf_read. Ask for section=\"Bottom line\" first — "
            "   it is the conclusion, and it is a tenth the length of the whole paper. Read "
            "   further sections only when the bottom line leaves you undecided. Several "
            "   references can go in one call, comma-separated.\n"
            "5) Call match_concepts with every concept at once. It returns a GROUP, not "
            "   an answer. The top-ranked candidate is frequently a false friend: for "
            "   'hypertension' it returns DX__I11.0__Hypertensive heart disease first "
            "   while the column you want, DX__I10__Essential hypertension, is third; for "
            "   'chronic kidney disease' a diabetes-complication code outranks DX__N18.3; "
            "   for 'hemoglobin a1c' the plain LAB__HEMOGLOBIN — a different analyte — "
            "   outranks real A1c columns. Read the whole group and pick the clinically "
            "   correct column by name. Never take rank 1 on faith. If nothing fits, "
            "   reword and call again. If a result is empty, read its 'note': "
            "   'nothing was close enough' means reword; 'a code this cohort does not "
            "   carry' means rewording will not help — name it in clinical English. "
            "   Codes work best INSIDE English: 'essential hypertension (I10)'.\n"
            "6) CAT__ columns are 0/1 indicators for one level of a family, and the "
            "   matcher returns the whole family. A family with fewer levels than you "
            "   expect has a dropped reference level — CAT__SEX__Male is the only sex "
            "   column, and 0 there means not male. Choose only column names spelled "
            "   exactly as describe_dataset or the matcher spelled them, and never the "
            "   outcome itself.\n\n"
            "Not every described variable is worth taking. The knowledge source covers far "
            "more phenomena than you may select, and it states how strong the evidence is "
            "for each. Judge, do not enumerate. If the knowledge source points at something "
            "this dataset does not measure, say so rather than substituting a weak proxy.\n\n"
            "Choose as many columns as the OKF evidence justifies — no fixed limit. "
            "More is not better: each column must map to a specific OKF path with a "
            "clear clinical rationale. Prefer fewer high-confidence matches over many "
            "weak ones. At minimum, choose 1 column.\n\n"
            "Your final answer MUST state, explicitly:\n"
            "- the list of chosen column names, spelled exactly as the dataset spells them\n"
            "- one sentence on why that combination should predict the outcome\n"
            "- the list of knowledge-source concept ids you relied on\n"
            "If you omit these, the downstream stages cannot read your decision."
        ),
        model_config=mc,
        pattern_config=react,
        output_contract={
            "name": "Hypothesis",
            "fields": [
                {
                    "name": "columns",
                    "type": "list",
                    "default": [],
                    "description": "The column names chosen, spelled exactly as the dataset spells them.",
                },
                {
                    "name": "hypothesis",
                    "type": "str",
                    "default": "",
                    "description": "One sentence on why these columns should predict the outcome.",
                },
                {
                    "name": "okf_concept_ids",
                    "type": "list",
                    "default": [],
                    "description": "Ids of the knowledge-source concepts relied on.",
                },
            ],
        },
    )

    data = await _ensure_agent(
        AGENT_NAMES["data"],
        goal="Extract only the specified columns and the outcome from the source dataset into a sub-dataset.",
        system_prompt=(
            "You are a data extraction agent. Use the slice_columns tool to cut out the "
            "given column list plus the outcome.\n\n"
            "Do not exercise judgement:\n"
            "- Do not add columns. 'This one looks relevant too' is not your call.\n"
            "- Do not drop columns. 'This one looks mostly missing' is not your call either.\n"
            "- Do not preprocess.\n"
            "- Do not retype or reformat a column name. You are given a JSON list; "
            "slice_columns takes a JSON list. Pass it through unchanged. Many names "
            "contain a comma ('LAB__HDL CHOLESTEROL, DIRECT') and that comma is part "
            "of the name, not a separator — splitting one produces two names that "
            "exist nowhere.\n\n"
            "If a requested column is absent from the dataset, REPORT THAT FACT in your "
            "final answer. Hiding it makes the next stage mistake a wrong result for a "
            "right one.\n\n"
            "State the file path produced, the row count, the columns actually used, and "
            "the columns that were missing."
        ),
        model_config=mc,
        pattern_config=react,
        output_contract={
            "name": "SubDataset",
            "fields": [
                {"name": "path", "type": "str", "description": "Path of the sub-dataset file produced."},
                {"name": "n_rows", "type": "int", "description": "Row count."},
                {
                    "name": "columns_used",
                    "type": "list",
                    "default": [],
                    "description": "Columns actually extracted, including the outcome.",
                },
                {
                    "name": "columns_missing",
                    "type": "list",
                    "default": [],
                    "description": "Columns requested but absent from the dataset.",
                },
            ],
        },
    )

    ml = await _ensure_agent(
        AGENT_NAMES["ml"],
        goal="Train a classifier on the sub-dataset and report AUC and feature importance.",
        system_prompt=(
            "You are an ML execution agent. Call train_and_score with the given path and "
            "report the returned numbers EXACTLY as they came back.\n\n"
            "- Do not perform feature selection. Train on the columns you were given.\n"
            "- Do not round or embellish the numbers.\n"
            "- If the tool returns an error, report that error verbatim.\n\n"
            "State the AUC, the per-column feature importance, the training row count, and "
            "the model name used."
        ),
        model_config=mc,
        pattern_config=react,
        output_contract={
            "name": "MLResult",
            "fields": [
                {"name": "auc", "type": "float", "description": "Test AUC."},
                {
                    "name": "feature_importance",
                    "type": "dict",
                    "default": {},
                    "description": "Column name to importance value.",
                },
                {"name": "n_train", "type": "int", "description": "Training row count."},
                {"name": "model", "type": "str", "default": "", "description": "Name of the model used."},
            ],
        },
    )

    interpreter = await _ensure_agent(
        AGENT_NAMES["interpreter"],
        goal="Interpret the ML result against the original hypothesis.",
        system_prompt=(
            "You are an interpretation agent. Given the hypothesis, the chosen columns, the "
            "AUC and the feature importance, argue whether the hypothesis was supported.\n\n"
            "- Do not claim anything the data does not say.\n"
            "- If the hypothesis was rejected, say so. Do not paper over it.\n"
            "- Treat an AUC of 0.5 as equivalent to chance.\n\n"
            "Three to five sentences."
        ),
        model_config=mc,
        pattern_config=react,  # even with no tools, reason_act finishes in one call and costs less
    )

    return {
        "hypothesis": hypothesis.id,
        "data": data.id,
        "ml": ml.id,
        "interpreter": interpreter.id,
    }


# --------------------------------------------------------------------------- #
#  The same four stages, plus a fifth, wired to the shared board
# --------------------------------------------------------------------------- #
#
# These are separate agents, not edits to the four above. The old path stays exactly as
# it is so the two can be run against each other — a board that produces different
# answers than the supervisor did is worth knowing about, and that comparison is only
# possible while both exist.
#
# What actually changes in the prompts is narrow: where the input comes from, and where
# the output goes. The rules about *not* exercising judgement are carried over word for
# word — the data and ml stages are no more free to think for themselves than before.
# Only the fetching and the writing are new.

# The **six** agents of the board path. Two more than the 02 path — `report`, which
# reads the results table at the end and writes the account, and `curator`, which
# stands at the very front and **decides what gets asked.** Why the curator is first:
# the questions used to be the 20 PERSPECTIVES hardcoded above, and that list did not
# line up with the subjects the knowledge-source corpus actually holds.
#
# The names are prefixed with `board-` to keep them apart from the 02 path's. Under the
# same names the two paths would share one agent, and editing one path's prompt would
# quietly change the other.
BOARD_AGENT_NAMES = {
    "curator": "memstara-board-curator",
    "hypothesis": "memstara-board-hypothesis",
    "data": "memstara-board-data",
    "ml": "memstara-board-ml",
    "interpreter": "memstara-board-interpreter",
    "report": "memstara-board-report",
}

# Which tools each stage may hold. Tool-level, not server-level: the board server
# carries every stage's tools in one place, so handing it out whole would let the
# hypothesis stage claim somebody else's work.
#
# This has actually happened: the hypothesis agent needs `describe_dataset`, which sits
# in the same server as `slice_columns`, so it was handed the cutter too — and cut six
# times over a three-trial run. Cutting the data is the data stage's job. The reason the
# stages are separated is so a result can be traced back to whose judgement produced it,
# and doing somebody else's work destroys that.
BOARD_TOOLS = {
    # okf_* rather than core's search_concepts/get_concept/list_concepts. Core's three
    # are still registered on the server and still work; they are simply not handed to
    # this agent. Measured on reviewer's 142-paper bundle, core's set reports 152 documents,
    # matches 132 of them on the substring "art", and returns whole 6,700-character
    # bodies. See src/memstara/mcp_servers/okf.py. Putting the old three names back here reverts the change.
    # `match_concepts` / `match_concept` are the same pair 02 hands its hypothesis
    # agent (see run_one_trial). `describe_matcher` is deliberately not here: it
    # reports cache paths and versions, which is a fact about this machine and not
    # about the cohort.
    # The curator writes the questions the hypothesis stage is then asked. It gets
    # `read_results` and the hypothesis stage does not: that is the whole feedback
    # path, and putting it here rather than there keeps the hypothesis stage's contract
    # intact (one perspective in, one hypothesis out) while still letting a wave learn
    # from the one before it. `record_question_outcomes` is deliberately absent — it is
    # bookkeeping about a wave having ended, which the driver knows and no agent does.
    "curator": {"okf_list_domains", "okf_search", "okf_read",
                "read_questions", "read_results", "propose_questions"},
    "hypothesis": {"okf_list_domains", "okf_search", "okf_read", "describe_dataset",
                   "match_concepts", "match_concept", "create_task"},
    "data": {"describe_dataset", "slice_columns", "claim_task", "submit_result"},
    "ml": {"train_and_score", "claim_task", "submit_result"},
    "interpreter": {"claim_task", "submit_result"},
    "report": {"read_results"},
}

# Which servers may be reached **at all.** Together with BOARD_TOOLS above this filters
# in two layers: narrowed once by server, then narrowed again by tool name within it.
BOARD_SERVERS = {
    "curator": {"okf", "memstara-blackboard"},
    "hypothesis": {"okf", "memstara-data", "memstara-blackboard", "semantic-matcher"},
    "data": {"memstara-data", "memstara-blackboard"},
    "ml": {"memstara-ml", "memstara-blackboard"},
    "interpreter": {"memstara-blackboard"},
    "report": {"memstara-blackboard"},
}

# The text prefixed to the prompts of the three stages that **take** work from the
# board (data, ml, interpreter).
#
# It is not prefixed to the hypothesis stage — that stage does not take work, it
# **creates** it.
#
# The most important sentence is number 2: when there is nothing to take, **stop.**
# Without it written down, an agent invents work that does not exist or takes a task
# of somebody else's type.
_CLAIM_PREAMBLE = (
    "Your work comes from a shared board, not from this message.\n\n"
    "1) Call claim_task with your own type **and the run_tag you were given in this "
    "   message**. It hands you one task from that run and marks it taken so nobody "
    "   else picks it up. Passing the run_tag matters: without it you may be handed a "
    "   task left behind by an unrelated run, and the work you do will be filed under "
    "   that run instead of this one.\n"
    "2) If it answers with a null task_id, there is nothing for you. **Stop there.** Do "
    "   not invent work, and do not claim a task of another type — that is somebody "
    "   else's job and taking it breaks the arrangement.\n"
    "3) Do your part on the task you were handed.\n"
    "4) Call submit_result with what you produced. That records it and passes the task "
    "   to whoever comes next.\n\n"
)


async def provision_board_agents(
    *, provider: str = "azure_foundry", model: str = "claude-sonnet-4-6"
) -> dict[str, uuid.UUID]:
    """Create the six board-driven agents (or find the existing ones).

    **The most important function in this file.** What each stage is, and what it must
    do first, is written out here as a prompt and nowhere else. Changing the pipeline's
    behaviour usually means editing this prose rather than the code.

    It goes through `_ensure_agent`, so editing the prose here **updates the existing
    agents** on the next run — the names stay and only the contents change.
    """
    mc = ModelConfig(provider=LLMProvider(provider), model=model, max_tokens=4096)
    react = {"execution_pattern": "reason_act"}
    hypothesis = await _ensure_agent(
        BOARD_AGENT_NAMES["hypothesis"],
        goal="Choose predictive columns from the knowledge source and put the work on the board.",
        system_prompt=(
            "You are a hypothesis agent. Decide which columns to pull from the dataset in "
            "order to predict the outcome, then put that decision on the shared board as a "
            "new task.\n\n"
            "You are the only stage that creates work. You never claim anything — there is "
            "nothing on the board for you to take.\n\n"
            "The knowledge source (OKF) tells you WHICH PHENOMENA matter for this outcome "
            "and how strong the evidence is. The dataset tells you WHICH COLUMNS EXIST. "
            "Neither one alone is enough, and nothing connects them for you — making that "
            "connection is your job.\n\n"
            "Do NOT assume the knowledge source states column names. Different bundles are "
            "written by different people to different conventions; a field naming columns "
            "may not exist at all. Read what is actually there.\n\n"
            "Work in this order:\n"
            "1) Call describe_dataset FIRST. Read the column names and note 'missing_pct' — "
            "   a column can exist and still be almost entirely blank.\n"
            "2) Call okf_list_domains to see what the knowledge source covers.\n"
            "3) Search it with okf_search — on ideas, not column names. It searches what the "
            "   authors said each document is ABOUT, never the bodies, so a hit means the "
            "   bundle says this document is about your query. Several wordings in one call, "
            "   comma-separated.\n"
            "4) Open the promising ones with okf_read, section=\"Bottom line\" first — the "
            "   conclusion, a tenth the length of the paper. Go deeper only if undecided.\n"
            "5) Call match_concepts with every concept at once. It returns a GROUP, not "
            "   an answer. The top-ranked candidate is frequently a false friend: for "
            "   'hypertension' it returns DX__I11.0__Hypertensive heart disease first "
            "   while the column you want, DX__I10__Essential hypertension, is third; for "
            "   'chronic kidney disease' a diabetes-complication code outranks DX__N18.3; "
            "   for 'hemoglobin a1c' the plain LAB__HEMOGLOBIN — a different analyte — "
            "   outranks real A1c columns. Read the whole group and pick the clinically "
            "   correct column by name. Never take rank 1 on faith. If nothing fits, "
            "   reword and call again. If a result is empty, read its 'note': "
            "   'nothing was close enough' means reword; 'a code this cohort does not "
            "   carry' means rewording will not help — name it in clinical English. "
            "   Codes work best INSIDE English: 'essential hypertension (I10)'.\n"
            "6) CAT__ columns are 0/1 indicators for one level of a family, and the "
            "   matcher returns the whole family. A family with fewer levels than you "
            "   expect has a dropped reference level — CAT__SEX__Male is the only sex "
            "   column, and 0 there means not male.\n"
            "7) Choose as many columns as the OKF evidence justifies — no fixed limit. "
            "   Each column must map to a specific OKF path. Prefer fewer high-confidence "
            "   matches over many weak ones, and never include the outcome itself.\n"
            "8) Call create_task with the columns you chose, the outcome column you were "
            "   given, one sentence on why that combination should predict it, and the "
            "   concept ids you relied on. The outcome goes on the task because every "
            "   later stage reads it from there — nobody will tell them separately.\n\n"
            "create_task takes `columns` as a JSON list, and the matcher already gave "
            "you the names exactly. Copy them across — do not retype or reformat one. "
            "Many contain a comma ('LAB__HDL CHOLESTEROL, DIRECT') and that comma is "
            "part of the name, not a separator; a name split there exists nowhere and "
            "the data stage will report it missing.\n\n"
            "Judge, do not enumerate. If the knowledge source points at something this "
            "dataset does not measure, say so rather than substituting a weak proxy.\n\n"
            "Your final answer must state the task_id create_task returned."
        ),
        model_config=mc,
        pattern_config=react,
    )

    data = await _ensure_agent(
        BOARD_AGENT_NAMES["data"],
        goal="Take a data task from the board, cut the requested columns, and record the result.",
        system_prompt=(
            "You are a data extraction agent.\n\n"
            + _CLAIM_PREAMBLE
            + 'Your type is "data".\n\n'
            "The task you claim carries a list of columns and, in `y_column`, the outcome "
            "they are meant to predict. Use slice_columns to cut out exactly those columns "
            "plus that outcome. Both come from the task — not from this message.\n\n"
            "Do not exercise judgement:\n"
            "- Do not add columns. 'This one looks relevant too' is not your call.\n"
            "- Do not drop columns. 'This one looks mostly missing' is not your call either.\n"
            "- Do not preprocess.\n"
            "- Do not retype or reformat a column name. You are given a JSON list; "
            "slice_columns takes a JSON list. Pass it through unchanged. Many names "
            "contain a comma ('LAB__HDL CHOLESTEROL, DIRECT') and that comma is part "
            "of the name, not a separator — splitting one produces two names that "
            "exist nowhere.\n\n"
            "If a requested column is absent from the dataset, REPORT THAT FACT in "
            "submit_result. Hiding it makes the next stage mistake a wrong result for a "
            "right one.\n\n"
            "Pass the file path produced, the columns actually used, and the columns that "
            "were missing."
        ),
        model_config=mc,
        pattern_config=react,
    )

    ml = await _ensure_agent(
        BOARD_AGENT_NAMES["ml"],
        goal="Take an ml task from the board, train on its sub-dataset, and record the numbers.",
        system_prompt=(
            "You are an ML execution agent.\n\n"
            + _CLAIM_PREAMBLE
            + 'Your type is "ml".\n\n'
            "The task you claim carries the path of a sub-dataset and, in `y_column`, the "
            "outcome column. Call train_and_score with both and report the returned numbers "
            "EXACTLY as they came back.\n\n"
            "- Do not perform feature selection. Train on the columns you were given.\n"
            "- Do not round or embellish the numbers.\n"
            "- If the tool returns an error, report that error verbatim.\n\n"
            "Pass the AUC and the per-column feature importance to submit_result."
        ),
        model_config=mc,
        pattern_config=react,
    )

    interpreter = await _ensure_agent(
        BOARD_AGENT_NAMES["interpreter"],
        goal="Take an interpretation task from the board and say whether its hypothesis held.",
        system_prompt=(
            "You are an interpretation agent.\n\n"
            + _CLAIM_PREAMBLE
            + 'Your type is "interpret".\n\n'
            "The task you claim carries everything the earlier stages left on it — the "
            "hypothesis, the columns used and missing, the AUC, the feature importance. "
            "Argue whether the hypothesis was supported.\n\n"
            "- Do not claim anything the data does not say.\n"
            "- If the hypothesis was rejected, say so. Do not paper over it.\n"
            "- Treat an AUC of 0.5 as equivalent to chance.\n\n"
            "Three to five sentences, passed to submit_result. That closes the task."
        ),
        model_config=mc,
        pattern_config=react,
    )

    report = await _ensure_agent(
        BOARD_AGENT_NAMES["report"],
        goal="Read every finished result and write the report for the whole run.",
        system_prompt=(
            "You are the reporting agent. You run once, after every other stage has "
            "finished, and you write the account of the whole run.\n\n"
            "Call read_results to get every trial that made it through — its hypothesis, "
            "the columns used, the AUC and the interpretation.\n\n"
            "Several hypothesis agents worked independently from different angles. What "
            "matters is where they converged:\n"
            "- Which columns were chosen by more than one, and which of those actually "
            "  carried weight in the models. **Those are different questions** — a column "
            "  can be popular and contribute nothing.\n"
            "- Where the results disagree, and what that disagreement suggests.\n"
            "- What the numbers do NOT support. An AUC near 0.5 is chance; say so.\n\n"
            "Do not invent trials that are not in what you read. If a result looks missing, "
            "say it is missing rather than filling the gap.\n\n"
            "Write for someone who was not here: what was tried, what held up, what did not."
        ),
        model_config=mc,
        pattern_config=react,
    )

    curator = await _ensure_agent(
        BOARD_AGENT_NAMES["curator"],
        goal="Write the questions this run will investigate, grounded in the knowledge source.",
        system_prompt=(
            "You are a question agent. You do not investigate anything. You decide WHAT "
            "GETS ASKED, and a hypothesis agent answers it afterwards.\n\n"
            "Each question is one short instruction phrase, handed to that agent word for "
            "word. Write it the way it will be read: \"from a ... perspective\", \"using "
            "only ...\". Not a sentence about a question — the question itself.\n\n"
            "Two failures this stage exists to prevent:\n\n"
            "1) ASKING WHAT THE KNOWLEDGE SOURCE CANNOT ANSWER. Before this stage existed "
            "   the questions were a fixed list written without reference to the corpus, "
            "   and they did not match it. The hypothesis agent was asked about metabolic "
            "   pathways while the corpus held papers on something else entirely, so it "
            "   cited whatever was there and chose columns on other grounds. It looked "
            "   like fabricated evidence. It was a question nothing could answer.\n"
            "   Therefore: every question you propose MUST carry okf_tags naming branches "
            "   the corpus actually has. propose_questions rejects one that does not.\n\n"
            "2) ASKING THE SAME THING TWICE. The bank spans runs, so a question answered "
            "   last week is still answered. Rewording does not make it a new question, "
            "   and propose_questions now checks for that as well as for exact repeats.\n\n"
            "Work in this order:\n"
            "1) Call okf_list_domains. This is the ground truth for what can be asked. "
            "   Note the tags and how many documents sit under each — a branch with three "
            "   papers supports one question, not five.\n"
            "2) Call read_questions to see what has already been asked and how it did.\n"
            "3) If read_results returns anything, read it before writing. This is the only "
            "   place in the pipeline where one wave can learn from the last. Look at "
            "   feature_importance: columns with negative importance made their model "
            "   worse, so a question that keeps producing them is a direction to drop, not "
            "   repeat. Look at which okf_concept_ids led to high AUC and ask a NEIGHBOURING "
            "   question, not the same one again. On the first wave this returns nothing; "
            "   that is expected, and you work from the corpus alone.\n"
            "4) Use okf_search on a branch you are considering if you need to see what it "
            "   actually claims before turning it into a question.\n"
            "5) Call propose_questions ONCE with all of them. Give each a rationale saying "
            "   what it is grounded in and, from wave two onward, which prior result "
            "   prompted it. A person reading the bank later should be able to see why "
            "   this question came after that one.\n\n"
            "Write questions about PHENOMENA AND MECHANISMS, never about column names. "
            "You cannot see the dataset and must not guess at it — finding the columns is "
            "the next stage's job, and it has a matcher for exactly that.\n\n"
            "Duplicates coming back from propose_questions are information, not failure: "
            "they mean you converged on something the bank already had. So is 'skipped', "
            "which means a question carried the same okf_tags as a banked one and said it "
            "in different words; each entry names the question_id it collided with, so "
            "read that question and move to a neighbouring mechanism instead of trying "
            "another phrasing. Both are worth reporting plainly.\n\n"
            "If everything you can think of comes back as a duplicate or a skip, SAY SO "
            "and propose nothing rather than padding. The bank running dry is a real "
            "finding about a finite corpus, and the run is built to notice it and stop — "
            "but only if you do not disguise it with rewordings."
        ),
        model_config=mc,
        pattern_config=react,
    )

    return {
        "curator": curator.id,
        "hypothesis": hypothesis.id,
        "data": data.id,
        "ml": ml.id,
        "interpreter": interpreter.id,
        "report": report.id,
    }


# --------------------------------------------------------------------------- #
#  Execution helpers
# --------------------------------------------------------------------------- #


def tools_for(
    registry: Any,
    servers: set[str],
    *,
    only: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Select the tools an agent may use.

    Handing every agent every tool lengthens the prompt and invites calls to tools
    that are not that agent's business. Give each one only what it needs.

    *servers* narrows by server; *only* narrows further to named tools within them.

    Server granularity alone is not enough, and the gap showed up in a real run: the
    hypothesis agent needs `describe_dataset` to learn which columns exist, but that
    tool ships in the same server as `slice_columns`, so it was handed the cutter too —
    and called it once per trial, three times over a three-trial run. Cutting the
    dataset is the data stage's job. The point of separating the stages is that the
    final result can be traced to the hypothesis agent's judgement, and that only holds
    if it cannot do the other stages' work itself.

    The same shape is about to matter more. A shared work board arrives as one server
    holding tools for every stage — creating a task, claiming one, writing a result
    back. Without tool-level filtering, giving any agent the board would give it all
    of those, and "each agent only takes its own work" would stop being true.
    """
    picked = [t for t in registry.get_all_tools() if t.get("server") in servers]
    if only is None:
        return picked
    return [t for t in picked if t.get("tool_name") in only]


@contextmanager
def _tagged(*, trial: int, stage: str, run_id: uuid.UUID) -> Iterator[None]:
    """Stamp trial, stage and run id onto every log line emitted inside the block.

    Trials run concurrently, so without this the log is one interleaved stream with no
    way to tell whose line is whose — measured on a real run: 0 of 391 records carried
    either field.

    Nothing else is needed to make this work. `logging_setup` already puts
    `merge_contextvars` in both the structlog chain and the `foreign_pre_chain`, so the
    tags reach core's own structlog records *and* the stdlib records from litellm and
    the mcp package.

    Each task from `asyncio.gather` copies the context at creation, so the bindings do
    not leak between concurrent trials; the reset covers the sequential stages within
    one trial.
    """
    tokens = structlog.contextvars.bind_contextvars(trial=trial, stage=stage, run_id=str(run_id))
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**tokens)


def _record_usage(row: TodoRow, stage: str, result: Any) -> None:
    """Keep this stage's cost and tokens on the row, whether it succeeded or not.

    A failed stage still spent money, and a report that only totals the successes
    understates what the run cost.
    """
    row.cost[stage] = float(getattr(result, "total_cost", 0.0) or 0.0)
    row.tokens[stage] = [
        int(getattr(result, "total_prompt_tokens", 0) or 0),
        int(getattr(result, "total_completion_tokens", 0) or 0),
    ]


async def _run_stage(
    agent_id: uuid.UUID,
    user_input: str,
    *,
    row: TodoRow,
    stage: str,
    tools: list[dict[str, Any]],
    registry: Any,
    model_config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Execute one run and return its output_contract payload, or None on failure.

    **This is the only place the 02 path calls an LLM.** Writing the run id into
    `row.run_ids[stage]` here matters: it is the only link back, and what lets
    `src/memstara/trace/run.py` later show what that agent asked the tools and what it got.
    """
    run = await create_run(
        agent_id=agent_id,
        user_input=user_input,
        metadata={"trial": row.trial, "stage": stage},
        model_config_overrides=model_config_overrides,
    )
    row.run_ids[stage] = str(run.id)

    with _tagged(trial=row.trial, stage=stage, run_id=run.id):
        result = await execute_run(run_id=run.id, registry=registry, available_tools=tools)
    _record_usage(row, stage, result)

    if result.error or result.status != "completed":
        row.error = f"[{stage}] {result.error or result.status}"
        return None

    # run.output is envelope JSON only when COMPLETED; otherwise it is the raw text.
    try:
        envelope = json.loads(result.output or "")
    except (json.JSONDecodeError, TypeError):
        row.error = f"[{stage}] could not parse the output envelope"
        return None
    return envelope.get("payload") or {}


async def _run_stage_text(
    agent_id: uuid.UUID,
    user_input: str,
    *,
    row: TodoRow,
    stage: str,
    registry: Any,
) -> str:
    """For agents with no output_contract — return the envelope's free-text result."""
    run = await create_run(
        agent_id=agent_id, user_input=user_input, metadata={"trial": row.trial, "stage": stage}
    )
    row.run_ids[stage] = str(run.id)

    with _tagged(trial=row.trial, stage=stage, run_id=run.id):
        result = await execute_run(run_id=run.id, registry=registry, available_tools=[])
    _record_usage(row, stage, result)

    if result.error or result.status != "completed":
        row.error = f"[{stage}] {result.error or result.status}"
        return ""
    try:
        return str(json.loads(result.output or "").get("result", ""))
    except (json.JSONDecodeError, TypeError):
        return result.output or ""


# --------------------------------------------------------------------------- #
#  Supervisor
# --------------------------------------------------------------------------- #


@dataclass
class TrialConfig:
    agents: dict[str, uuid.UUID]
    registry: Any
    y_column: str
    # Ablation switch. With False the hypothesis agent gets no OKF tools at all, so it
    # sees only opaque column codes and nothing that could explain them. Comparing the
    # two settings is the only way to show OKF is load-bearing rather than decorative —
    # if selection quality survives its removal, the knowledge source was not doing the
    # work.
    use_okf: bool = True


async def run_one_trial(trial: int, cfg: TrialConfig) -> TodoRow:
    """Drive one hypothesis through all four stages, recording where it stopped.

    **This function is the supervisor.** The 'S' on the whiteboard does nothing more
    than this.
    """
    row = TodoRow(trial=trial, perspective=perspective_for(trial))

    hyp_servers = (
        {"okf", "memstara-data", "semantic-matcher"}
        if cfg.use_okf else
        {"memstara-data", "semantic-matcher"}
    )
    # The hypothesis agent reads the knowledge source and asks what columns exist. It
    # does not cut the dataset — that is the data stage. `only` keeps `slice_columns`
    # out of its hands; without it the agent had the cutter and used it (six calls in
    # one three-trial run), which blurs whose judgement produced the result.
    # The matcher maps concept names to exact column names by S-PubMedBERT cosine.
    # Both tools are offered: `match_concepts` encodes a whole list in one pass and is
    # what the prompt asks for; `match_concept` stays for the single follow-up lookup.
    # `describe_matcher` is operational — it reports cache paths and versions, which is
    # a fact about this machine and not about the cohort, so the agent never sees it.
    hyp_tools = tools_for(
        cfg.registry,
        hyp_servers,
        only={
            "describe_dataset",
            "okf_list_domains",
            "okf_search",
            "okf_read",
            "match_concepts",
            "match_concept",
        },
    )
    data_tools = tools_for(cfg.registry, {"memstara-data"})
    ml_tools = tools_for(cfg.registry, {"memstara-ml"})

    # -- (1) hypothesis --------------------------------------------------
    payload = await _run_stage(
        cfg.agents["hypothesis"],
        f"The outcome column is '{cfg.y_column}'. Choose the columns that will predict it, "
        f"{row.perspective}.",
        row=row,
        stage="hypothesis",
        tools=hyp_tools,
        registry=cfg.registry,
        model_config_overrides={"temperature": temperature_for(trial)},
    )
    if payload is None:
        return row
    row.hypothesis = str(payload.get("hypothesis") or "")
    row.columns = [str(c) for c in (payload.get("columns") or [])]
    row.okf_concept_ids = [str(c) for c in (payload.get("okf_concept_ids") or [])]
    if not row.columns:
        row.error = "[hypothesis] produced no columns (check they were listed explicitly in the final answer)"
        return row

    # -- (2) data --------------------------------------------------------
    payload = await _run_stage(
        cfg.agents["data"],
        # A JSON array, not a comma-joined sentence. 158 of this cohort's 1,393
        # column names contain a comma (`LAB__HDL CHOLESTEROL, DIRECT`), so in a
        # joined sentence there is no way for the agent to tell a separator from
        # part of a name — and the names are already exact here, straight from
        # the matcher. Handing over the finished array removes the transcription
        # step instead of asking the agent to get it right.
        f"Extract only these columns plus the outcome '{cfg.y_column}'. "
        f"Pass this exact list to slice_columns:\n"
        f"{json.dumps(row.columns, ensure_ascii=False)}\n"
        f"Copy it as it stands — some names contain commas, and those commas are "
        f"part of the name. Use the file tag 't{trial:02d}'.",
        row=row,
        stage="data",
        tools=data_tools,
        registry=cfg.registry,
    )
    if payload is None:
        return row
    row.subset_path = str(payload.get("path") or "")
    row.columns_used = [str(c) for c in (payload.get("columns_used") or [])]
    row.columns_missing = [str(c) for c in (payload.get("columns_missing") or [])]
    if not row.subset_path:
        row.error = "[data] no sub-dataset was produced"
        return row

    # -- (3) ML ----------------------------------------------------------
    payload = await _run_stage(
        cfg.agents["ml"],
        f"Train on '{row.subset_path}' and report the AUC for the outcome '{cfg.y_column}'.",
        row=row,
        stage="ml",
        tools=ml_tools,
        registry=cfg.registry,
    )
    if payload is None:
        return row
    auc = payload.get("auc")
    row.auc = float(auc) if isinstance(auc, (int, float)) else None
    fi = payload.get("feature_importance") or {}
    row.feature_importance = {str(k): float(v) for k, v in fi.items() if isinstance(v, (int, float))}
    row.model = str(payload.get("model") or "")
    if row.auc is None:
        row.error = "[ml] no AUC was returned"
        return row

    # -- (4) interpretation ----------------------------------------------
    row.interpretation = await _run_stage_text(
        cfg.agents["interpreter"],
        f"Perspective: {row.perspective}\nHypothesis: {row.hypothesis}\n"
        f"Columns used: {row.columns_used}\nColumns missing: {row.columns_missing}\n"
        f"AUC: {row.auc}\nFeature importance: {row.feature_importance}\n\n"
        f"Was this hypothesis supported?",
        row=row,
        stage="interpreter",
        registry=cfg.registry,
    )
    return row


# --------------------------------------------------------------------------- #
#  Aggregation — the paper's output. Done in code, not by an LLM.
# --------------------------------------------------------------------------- #

# The real signal planted by src/memstara/prep/sample.py. Meaningful ONLY on that dataset.
# Opaque codes on purpose — see that file's module docstring.
#
# The answer key **planted deliberately** in the synthetic data. src/memstara/prep/sample.py
# makes these four genuinely predict the outcome (univariate AUC 0.73/0.66/0.63/0.60,
# against 0.51 for the noise columns).
#
# It is what makes it possible to **score** "did the pipeline find the right thing".
# Real data (NHANES, reviewer's cohort) has no such key, so there no claim about
# performance can be made — only the weaker check of "do the clinically well-known
# ones come out on top".
PLANTED_SIGNAL = ["LBXGH", "BMXBMI", "RIDAGEYR", "BPXSY1"]


def aggregate(
    rows: list[TodoRow],
    *,
    y_column: str,
    dataset_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Extract the two things the paper needs from a set of trials.

    - selection_frequency : how often each column was chosen — the meeting's "overlap"
    - weighted_importance : the running sum of actual contribution

    Both are needed: counting selections alone cannot separate "chosen often" from
    "chosen often and actually contributed."

    *dataset_columns* decides whether the planted-signal check applies. It is scored
    only when the dataset actually contains every planted column — that is, only on the
    synthetic dataset the answer key belongs to.

    Scoring it unconditionally was a real defect, not a hypothetical one. The first run
    against a real cohort reported "0/4" for columns that dataset never had, and because
    `interpret_overall` hands this whole summary to an agent, the agent wrote up a
    "Critical Failure … the hypothesis must be considered not supported." Nothing had
    failed. So when the check does not apply the keys are **absent**, not null — an
    agent reading the summary must not see a standard that does not exist here.
    """
    ok = [r for r in rows if r.ok]

    freq: Counter[str] = Counter()
    for r in ok:
        for c in r.columns_used:
            if c != y_column:
                freq[c] += 1

    weighted: dict[str, float] = {}
    for r in ok:
        for col, imp in r.feature_importance.items():
            if col != y_column:
                weighted[col] = weighted.get(col, 0.0) + imp

    summary: dict[str, Any] = {
        "n_trials": len(rows),
        "n_succeeded": len(ok),
        "n_failed": len(rows) - len(ok),
        "mean_auc": round(sum(r.auc or 0 for r in ok) / len(ok), 4) if ok else None,
        "best_auc": max((r.auc for r in ok if r.auc is not None), default=None),
        "best_trial": max(ok, key=lambda r: r.auc or 0).trial if ok else None,
        "selection_frequency": freq.most_common(),
        "weighted_importance": sorted(((k, round(v, 5)) for k, v in weighted.items()), key=lambda kv: -kv[1]),
        "columns_missing_seen": sorted({c for r in rows for c in r.columns_missing}),
        "errors": [{"trial": r.trial, "error": r.error} for r in rows if r.error],
    }

    # Synthetic-data check — did it actually recover the planted signal? Added only
    # when this really is that dataset.
    if dataset_columns is not None and set(PLANTED_SIGNAL) <= set(dataset_columns):
        top6 = {c for c, _ in freq.most_common(6)}
        found = [c for c in PLANTED_SIGNAL if c in top6]
        summary["planted_signal"] = PLANTED_SIGNAL
        summary["planted_found_in_top6"] = found
        summary["planted_recall"] = f"{len(found)}/{len(PLANTED_SIGNAL)}"

    return summary


async def interpret_overall(agent_id: uuid.UUID, summary: dict[str, Any], *, registry: Any) -> str:
    """Interpret the whole set of trials once more, over the aggregate.

    The meeting never said whether the interpreter runs per trial or once over the
    aggregate, so this does both. That costs one extra call and yields the
    whole-experiment narrative the paper needs.
    """
    row = TodoRow(trial=-1)
    return await _run_stage_text(
        agent_id,
        "Several hypothesis agents independently chose columns from different "
        "perspectives, and the results were aggregated. Given the summary below, discuss "
        "which variables were repeatedly selected and what that suggests.\n\n"
        f"{json.dumps(summary, ensure_ascii=False, indent=2)}",
        row=row,
        stage="interpreter_overall",
        registry=registry,
    )
