"""The body of the MVP pipeline — agent definitions, supervisor, aggregation."""

from __future__ import annotations

import json  # agent output (a JSON string) into Python values
import uuid  # run ids
from collections import Counter  # for counting how often each column was chosen
from collections.abc import Iterator, Sequence
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
from motoro.schemas.agent import ModelConfig

from memstara.pipeline.scientific_policy import PRIMARY_QUESTION_TOOLS
from memstara.pipeline.prompts import load_prompt

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

    trial: int  # which trial this is
    perspective: str = ""  # the perspective phrase that trial was given

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
    silently ineffective, and it also means an edited file under `src/memstara/prompts/`
    never reaches the running agent: an agent is a durable resource and its
    configuration was frozen at creation time. See `_ensure_agent_from_file` below.

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
        if current != wanted_mc.model_dump(mode="json"):
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


async def _ensure_agent_from_file(name: str, prompt: str, playbook: str = "", **kwargs: Any) -> Any:
    """`_ensure_agent`, with `goal` and `system_prompt` read from a prompt file.

    Args:
        name: The agent's name, from `AGENT_NAMES` or `BOARD_AGENT_NAMES`.
        prompt: Path under `PROMPTS_DIR` without the suffix — "board/hypothesis".
        playbook: A behavioural standard to splice into that prompt, or "" for the
            prompt as written. Nothing below here needs to know: `_ensure_agent`
            compares the `system_prompt` it is handed against the stored one and
            updates it, so a run that attaches a playbook and one that does not
            reprovision the same agent in the same way.
        **kwargs: Passed straight through; `model_config` and `pattern_config` in
            practice.

    Returns:
        The agent, created or refreshed. `load_prompt` raises rather than handing
        back an empty prompt, so a mis-named or malformed file fails here, loudly,
        before any model is called.
    """
    return await _ensure_agent(name, **load_prompt(prompt, playbook), **kwargs)


async def provision_all(*, provider: str = "", model: str = "") -> dict[str, uuid.UUID]:
    """Create the four agents (or find the existing ones) and return their ids.

    The mvp path. Its four prompts are one file each under
    `src/memstara/prompts/mvp/`, named for their key in `AGENT_NAMES`, on the same
    rule as the board's — see `provision_board_agents`. They are kept separate from
    `board/` rather than shared: the two pipelines exist to be compared, and a
    prompt one of them edits must not silently change the other.

    No api_key is passed: ModelConfig.api_key is exclude=True, so it does not survive
    being persisted with the agent. Credentials resolve at call time instead.
    """
    from memstara.stage_models import deployment_profiles, for_stage

    profiles = deployment_profiles()
    react = {"execution_pattern": "reason_act"}

    hypothesis = await _ensure_agent_from_file(
        AGENT_NAMES["hypothesis"],
        "mvp/hypothesis",
        model_config=ModelConfig(**for_stage(profiles, "hypothesis")),
        pattern_config=react,
    )
    data = await _ensure_agent_from_file(
        AGENT_NAMES["data"],
        "mvp/data",
        model_config=ModelConfig(**for_stage(profiles, "data")),
        pattern_config=react,
    )
    ml = await _ensure_agent_from_file(
        AGENT_NAMES["ml"],
        "mvp/ml",
        model_config=ModelConfig(**for_stage(profiles, "ml")),
        pattern_config=react,
    )
    interpreter = await _ensure_agent_from_file(
        AGENT_NAMES["interpreter"],
        "mvp/interpreter",
        model_config=ModelConfig(**for_stage(profiles, "interpreter")),
        pattern_config=react,
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

# The **five** agents of the board path. One more than the 02 path — `report`, which
# reads the results table at the end and writes the account.
#
# **Writing the questions is the hypothesis agent's other job, not a sixth agent.**
# There used to be a `curator` here, standing at the very front and deciding what gets
# asked. Deciding what to ask and then answering it are two moments of one person's
# work, and splitting them into two agents bought nothing that separate *calls* do not
# buy already: `call_agent` takes the agent id and the tool list as separate arguments
# (`src/memstara/pipeline/board.py:486-494`), so the same agent is handed
# QUESTION_TOOLS below when it writes and BOARD_TOOLS["hypothesis"] when it answers,
# and a tool absent from a call cannot be reached however the prompt is worded. What
# the two stages were separating is still separated, mechanically, one layer down.
#
# What did NOT move: the reason the questions are grounded in the corpus at all. They
# used to be the 20 PERSPECTIVES hardcoded above, and that list did not line up with
# the subjects the knowledge-source corpus actually holds.
#
# **The `memstara-board-curator` agent record in motoro is left where it is.** It is
# not in this dict any more, so nothing provisions or calls it, but hundreds of past
# runs are recorded against it and `_ensure_agent` finds an agent by *name* (:234-269).
# Renaming or deleting it would cut those runs loose from the agent that did them, and
# `viewer/api/stores.py` keeps the name explicitly so the viewer's cost totals still
# include them.
#
# The names are prefixed with `board-` to keep them apart from the 02 path's. Under the
# same names the two paths would share one agent, and editing one path's prompt would
# quietly change the other.
BOARD_AGENT_NAMES = {
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
    "hypothesis": {
        "okf_list_domains",
        "okf_search",
        "okf_read",
        "describe_dataset",
        "match_concepts",
        "match_concept",
        "claim_question",
        "create_task",
    },
    "data": {"describe_dataset", "slice_columns", "claim_task", "submit_result"},
    "ml": {"get_ml_configuration", "train_and_score", "claim_task", "submit_result"},
    "interpreter": {"claim_task", "submit_result"},
    "report": {"read_results", "okf_search", "okf_read"},
}

# Which servers may be reached **at all.** Together with BOARD_TOOLS above this filters
# in two layers: narrowed once by server, then narrowed again by tool name within it.
BOARD_SERVERS = {
    "hypothesis": {"okf", "memstara-data", "memstara-blackboard", "semantic-matcher"},
    "data": {"memstara-data", "memstara-blackboard"},
    "ml": {"memstara-ml", "memstara-blackboard"},
    "interpreter": {"memstara-blackboard"},
    "report": {"okf", "memstara-blackboard"},
}

# The hypothesis agent's **other job**: writing the wave's questions before anybody
# answers them. This is not a stage. There is no agent of this name, nothing is drawn
# for it, and no run is recorded against it — it exists as its own pair of constants
# only because the permission is per *call* rather than per agent, and one agent that
# does two jobs therefore needs two tool lists.
#
# It is deliberately kept out of BOARD_TOOLS / BOARD_SERVERS rather than added as a
# sixth key. Those two tables are read as "one entry per agent" by everything that
# consumes them — `board.py`'s `by_stage` loop, and `viewer/check_definitions.py:139`,
# which takes their key set to *be* the set of stages and reports anything else as an
# error. A sixth key would make that checker call a job an agent.
#
# Raw result tools remain excluded. Iterative runs receive scoped feedback from the driver.
# The catalog is a restricted, current-run duplicate-avoidance view.
QUESTION_TOOLS = set(PRIMARY_QUESTION_TOOLS)
QUESTION_SERVERS = {"okf", "memstara-blackboard"}


def hypothesis_agent_names(playbooks: Sequence[str]) -> list[str]:
    """One durable identity per skill, including single-hypothesis configurations.

    The legacy unsuffixed name remains for an empty skill. A nonempty skill must
    keep the same identity when another hypothesis is added or removed.
    """
    base = BOARD_AGENT_NAMES["hypothesis"]
    return [f"{base}-{book}" if book else base for book in (playbooks or [""])]


def _sole(books: dict[str, list[str]], stage: str) -> str:
    """The one playbook a single-agent stage was given, or "" for none.

    Only `hypothesis` runs an agent per standard. Every other stage takes at most
    one, which `board.main` refuses at argument-parsing time rather than here — this
    reads the first and would rather be given a list of one.
    """
    return (books.get(stage) or [""])[0]


def board_workers(playbooks: dict[str, list[str]] | None = None, namespace: str = "") -> dict[str, tuple[str, str]]:
    """Worker key -> (agent name, the playbook that worker carries).

    **The one place that decides what the workers of a run are.** `provision_board_agents`
    builds its agents from this and `board.run` writes `prompts.json` from it, so the
    record and the agents cannot describe different runs — which they would the moment
    two functions each derived the key format from the same rule in their own words.

    The keys are worker keys: the stage name for the first agent of each stage, and
    `hypothesis#2`, `hypothesis#3`, … for the further hypothesis agents a run with
    several standards has. Use `stage_of` to get back to something `BOARD_TOOLS` can be
    keyed by.

    Args:
        playbooks: Stage -> the standards it was given, in worker order. Only
            `hypothesis` may hold more than one; `board.main` refuses the others.

    Returns:
        An ordered mapping, hypothesis workers first. `""` as a playbook means the
        prompt as written.
    """
    books = playbooks or {}
    hypothesis_books = books.get("hypothesis") or [""]
    out = {
        ("hypothesis" if k == 0 else f"hypothesis#{k + 1}"): (name, book)
        for k, (name, book) in enumerate(zip(hypothesis_agent_names(hypothesis_books), hypothesis_books, strict=True))
    }
    for stage in ("data", "ml", "interpreter", "report"):
        choices = (books.get(stage) or [""]) if stage == "interpreter" else [_sole(books, stage)]
        for k, book in enumerate(choices):
            key = stage if k == 0 else f"{stage}#{k + 1}"
            name = BOARD_AGENT_NAMES[stage]
            if stage == "interpreter" and book:
                name += f"-{book}"
            out[key] = (name, book)
    return {key: (f"{name}-{namespace}" if namespace else name, book) for key, (name, book) in out.items()}


async def provision_board_agents(
    *,
    provider: str = "",
    model: str = "",
    playbooks: dict[str, list[str]] | None = None,
    namespace: str = "",
    stage_models: dict | None = None,
) -> dict[str, uuid.UUID]:
    """Create the board-driven agents (or find the existing ones)."""
    from memstara.stage_models import deployment_profiles, validate_profiles, for_stage

    profiles = validate_profiles(stage_models) if stage_models else deployment_profiles()
    react = {"execution_pattern": "reason_act"}

    out: dict[str, uuid.UUID] = {}
    for key, (name, book) in board_workers(playbooks, namespace).items():
        selected_model = ModelConfig(**for_stage(profiles, key))
        agent = await _ensure_agent_from_file(
            name,
            f"board/{stage_of(key)}",
            book,
            model_config=selected_model,
            pattern_config=react,
        )
        out[key] = agent.id
    return out


def stage_of(worker_key: str) -> str:
    """The stage a key from `provision_board_agents` belongs to.

    `"hypothesis#2"` -> `"hypothesis"`; every other key is already its own stage.
    Everything keyed by the five stages — `BOARD_TOOLS`, `BOARD_SERVERS`, the prompt
    path — must go through this, because a second hypothesis agent is a second
    **worker** and not a sixth stage.
    """
    return worker_key.split("#", 1)[0]


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
    server_ids = [
        key
        for key, entry in registry.servers.items()
        if entry.name in servers and (entry.owner_id is None or entry.is_system)
    ]
    picked = [t for t in registry.get_all_tools(server_ids=server_ids) if t.get("server") in servers]
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
        from memstara.pipeline.llm import PipelineLLMService

        result = await execute_run(
            run_id=run.id,
            registry=registry,
            available_tools=tools,
            llm_service=PipelineLLMService(principal_id=run.owner_id),
        )
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
    run = await create_run(agent_id=agent_id, user_input=user_input, metadata={"trial": row.trial, "stage": stage})
    row.run_ids[stage] = str(run.id)

    with _tagged(trial=row.trial, stage=stage, run_id=run.id):
        from memstara.pipeline.llm import PipelineLLMService

        result = await execute_run(
            run_id=run.id,
            registry=registry,
            available_tools=[],
            llm_service=PipelineLLMService(principal_id=run.owner_id),
        )
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

    hyp_servers = {"okf", "memstara-data", "semantic-matcher"} if cfg.use_okf else {"memstara-data", "semantic-matcher"}
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
        f"The outcome column is '{cfg.y_column}'. Choose the columns that will predict it, {row.perspective}.",
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

PLANTED_SIGNAL = ["LBXGH", "BMXBMI", "RIDAGEYR", "BPXSY1"]


def aggregate(
    rows: list[TodoRow],
    *,
    y_column: str,
    dataset_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Extract the two things the paper needs from a set of trials."""
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
    """Interpret the whole set of trials once more, over the aggregate."""
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
