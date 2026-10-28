"""What a start request may contain, and nothing else.

This module turns one JSON object into the argument list for
`python -m memstara.pipeline.board`. It is the whole of the boundary between a
browser and a process on this machine, so it is written as an allow-list: twelve keys,
each with a type and a range, and **an unknown key is an error rather than a key that
is ignored.** Silently dropping a field means a run that is not the one that was asked
for — the same reasoning the prompt loader gives for refusing unknown front matter
(`src/memstara/pipeline/prompts.py`).

Nothing from the request ever becomes a string a shell will parse. The caller of
`build_argv` passes the result to `subprocess.Popen` as a list, with no `shell=True`
anywhere, so the danger this file guards against is not injection — it is a run
started with a mistyped column name, a model nobody meant to pay for, or a branch that
does not exist in the bundle. Each of those is cheap to catch here and expensive to
notice twenty minutes into a run.

It imports the standard library and nothing else, on purpose: `service.py` reads the
bundle through the okf server, which needs `yaml` and `../motoro`, and neither is
present on a CI runner. The rules below are the part worth testing, so they are the
part that stays importable — the same split that put the `fields=` predicate in
`src/memstara/mcp_servers/frontmatter.py`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

#: The providers `board.py` accepts (`src/memstara/pipeline/board.py:1823`). Copied
#: rather than imported for the reason in the module docstring — importing board.py
#: pulls in asyncpg, litellm and motoro. `tests/test_control_request.py` reads the
#: real `add_argument` line out of the source and compares, so the copy cannot drift
#: without a test failing.
PROVIDERS = ("anthropic", "azure_foundry", "openai", "openrouter", "local", "bedrock")

#: A column name. Not a whitelist of real columns — the control service does not open
#: the cohort file, and it must not: that is the one place patient data lives. This
#: only rejects what could not be a column name in any dataset.
_COLUMN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")

#: A model identifier: `claude-sonnet-4-6`, `gpt-4.1`, `azure_foundry/whatever`.
_MODEL = re.compile(r"[A-Za-z0-9._:/-]{1,120}\Z")

#: Ceilings, not defaults. A wave of 20 trials is already a long run; these are here so
#: that a slipped keypress in a number field cannot start something that runs all night
#: and costs accordingly.
_MAX_TRIALS = 20
_MAX_WAVES = 10

_MAX_HYPOTHESIS_AGENTS = 4

PLAYBOOK_STAGES = ("hypothesis", "data", "ml", "interpreter", "report")

#: The one stage that may be given several standards, one per worker. Everything else runs
#: a single agent however many workers claim from the board, so a second name there would
#: be accepted and never read — `board.py` refuses it and so does `build_argv`, at the
#: earlier of the two points.
#:
#: A tuple of one rather than a bare string: `hypothesis` is the only such stage because
#: it is the only one whose workers set out independently, and if a second ever qualifies
#: the check below does not change shape.
MULTI_PLAYBOOK_STAGES = ("hypothesis", "interpreter")

def playbook_field(stage):
    return "playbook_explanation" if stage in ("report", "explanation") else f"playbook_{stage}"


def normalize_agent_configuration(body):
    """Read legacy settings; write only the canonical Explanation configuration key."""
    if not isinstance(body, Mapping):
        raise ValueError("Pipeline settings must be an object")
    result = dict(body)
    if "playbook_report" in result:
        legacy = result.pop("playbook_report")
        if "playbook_explanation" in result and result["playbook_explanation"] != legacy:
            raise ValueError("Conflicting Explanation skill settings")
        result["playbook_explanation"] = legacy
    return result


DEFAULTS: dict[str, Any] = {
    "research_input_id": "",
    "knowledge_mode": "okf",
    "data_mode": "dataset",
    "research_objective": "",
    "question": "",
    "combination_skills": {},
    "combination_repetitions": 1,
    "combination_execution_order": "all_pipelines_first",
    "combination_random_start": False,
    "combination_max_loops": None,
    "evaluation": {},
    "ml_overrides": {},
    "baseline_columns": [],
    "skill": "",
    "trials": 3,
    "waves": 1,
    "continuous": False,
    "hypothesis_agents": 1,
    "interpret_agents": 1,
    "y_column": "outcome",
    "provider": "",
    "model": "",
    "stage_models": {},
    "model_connection_id": "",
    "controlled_comparison": {},
    # One key per stage rather than one `playbooks` object, so the allow-list stays flat
    # and an unknown *stage* is caught by the same check that catches an unknown field
    # — a nested object would need its own copy of that rule, and the copy is what goes
    # wrong. Empty means the prompt as written, which is also what `board.py` means by
    # the flag being absent.
    **{playbook_field(stage): "" for stage in PLAYBOOK_STAGES if stage != "report"},
    "playbook_explanation": "",
}


def configured_llm(stage: str = 'hypothesis') -> tuple[str, str]:
    """Legacy scalar metadata for the specified agent, never a deployment default."""
    from memstara.operational import agent_profile
    profile = agent_profile(stage)
    if not _MODEL.fullmatch(profile['model']):
        raise ValueError(f'{stage}: model is not a model identifier')
    return profile['provider'], profile['model']


def _whole_number(body: Mapping[str, Any], key: str, ceiling: int) -> int:
    """One integer between 1 and *ceiling*, rejecting `True` along the way.

    `isinstance(True, int)` is true in Python, so a JSON `true` would otherwise arrive
    as `--trials 1` and look like a deliberate choice.
    """
    value = body.get(key, DEFAULTS[key])
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be a whole number, not {value!r}")
    if not 1 <= value <= ceiling:
        raise ValueError(f"{key} must be between 1 and {ceiling}; {value} is not")
    return value


def _text(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key, DEFAULTS[key])
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text, not {value!r}")
    return value.strip()


def build_argv(
    body: Mapping[str, Any],
    offered: Iterable[str],
    playbooks: Iterable[str] = (),
    playbook_stages: Iterable[str] = (),
) -> list[str]:
    """The arguments for one run, or `ValueError` saying which field was wrong."""
    body = normalize_agent_configuration(body)
    from memstara.corpus_skills import with_default_hypothesis
    body = with_default_hypothesis(body)
    # The HTTP boundary rejects these fields from callers; workspace retry owns them.
    retry_fields = {"_retry_from_loop", "_retry_source_run", "_retry_combination_plan", "_retry_seed_schedule",
                    "_retry_experiment_policy"}
    unknown = sorted(set(body) - set(DEFAULTS) - retry_fields)
    if unknown:
        raise ValueError(
            f"not something a run takes: {', '.join(unknown)}. "
            f"The fields are {', '.join(sorted(DEFAULTS))}"
        )

    research_id = _text(body, 'research_input_id')
    if research_id:
        from memstara.research_inputs import load
        profile = load(research_id)
        config = profile['configuration']
        body = {**body, 'knowledge_mode': config['knowledge_mode'], 'data_mode': config['data_mode'],
                'research_objective': config['target']['description'],
                'y_column': config['target']['column'] or 'outcome'}
    knowledge_mode, data_mode = _text(body, 'knowledge_mode'), _text(body, 'data_mode')
    if knowledge_mode not in ('okf', 'llm_only') or data_mode not in ('dataset', 'proposal'):
        raise ValueError('Select supported knowledge and data modes')
    objective = _text(body, 'research_objective')
    if len(objective) > 8000 or (data_mode == 'proposal' and not objective):
        raise ValueError('Proposal mode requires a research objective (at most 8000 characters)')
    if knowledge_mode == 'llm_only' and _text(body, 'skill'):
        raise ValueError('Clear knowledge filters in LLM-only mode')
    if data_mode == 'proposal' and body.get('baseline_columns'):
        raise ValueError('Proposal mode cannot bind fixed baseline columns without a dataset')
    from memstara.evaluation import validate
    evaluation = body.get("evaluation", {})
    if not isinstance(evaluation, dict):
        raise ValueError("evaluation must be an object")
    validate(evaluation)
    from memstara.controlled_comparison import validate as validate_controls
    controls = validate_controls(body.get('controlled_comparison', {}))
    from memstara.comparisons import validate_baseline
    baseline = validate_baseline(body.get("baseline_columns", []), body.get("y_column", DEFAULTS["y_column"]))
    question = _text(body, "question")
    if len(question) > 8000:
        raise ValueError("Research question must be at most 8000 characters")
    skill = _text(body, "skill")
    if skill and skill not in set(offered):
        raise ValueError(
            f"{skill!r} is not one of the branches this bundle has. "
            f"Ask GET /control/skills for the list"
        )

    y_column = _text(body, "y_column")
    if data_mode == "proposal" and not y_column:
        y_column = "outcome"  # Internal placeholder; no dataset is evaluated.
    if data_mode == "dataset" and not y_column:
        raise ValueError("Select a target column in Data & target, or select a saved research input")
    if not _COLUMN.match(y_column):
        raise ValueError(f"y_column {y_column!r} is not a column name")

    # Validate legacy request fields, but deployment configuration controls execution.
    requested_provider = _text(body, "provider")
    requested_model = _text(body, "model")
    if requested_provider and requested_provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {', '.join(PROVIDERS)}")
    if requested_model and not _MODEL.fullmatch(requested_model):
        raise ValueError("model is not a model identifier")
    connection_id = _text(body, 'model_connection_id')
    connection = None
    if connection_id:
        from memstara.model_connections import load
        connection = load(connection_id)['connection']
        provider, model = connection['provider'], connection['model']
    else:
        provider, model = configured_llm()

    continuous = body.get("continuous", False)
    if not isinstance(continuous, bool):
        raise ValueError("continuous must be a boolean")

    trials = _whole_number(body, "trials", _MAX_TRIALS)
    combination_plan = None
    if body.get("combination_skills"):
        if baseline:
            raise ValueError("All Combinations uses 4–20 hypothesis predictors; clear fixed baseline columns")
        from memstara.combinations import build_plan
        combination_plan = build_plan(body["combination_skills"], body.get("combination_repetitions", 1),
                                      random_start=body.get('combination_random_start', False),
                                      execution_order=body.get('combination_execution_order', 'all_pipelines_first'),
                                      max_loops=body.get('combination_max_loops'))
        continuous = False
        if combination_plan['total_loops'] > 10000:
            raise ValueError('Choose at most 10000 total replicates')
    if body.get('_retry_combination_plan'):
        from memstara.combinations import validate_plan
        combination_plan = validate_plan(body['_retry_combination_plan'])
    waves = combination_plan['total_loops'] if combination_plan else _whole_number(body, "waves", _MAX_WAVES)
    hypothesis_agents = _whole_number(body, "hypothesis_agents", _MAX_HYPOTHESIS_AGENTS)
    interpret_agents = _whole_number(body, "interpret_agents", 4)

    # Retired skills may still appear in trusted saved runs. New API designs
    # are rejected by validate_new_design before reaching this execution adapter.
    known = set(playbooks) | {'random_features', 'heart-failure-all'}
    if combination_plan:
        known.update(item['id'] for entries in combination_plan['skills'].values() for item in entries)
    markable = set(playbook_stages)
    chosen: list[tuple[str, str]] = []
    for stage in PLAYBOOK_STAGES:
        # Comma-separated, and for four of the five stages that only ever yields one name.
        # The split is here rather than only in `board.py` so the person who pressed the
        # button gets the message: `board.py` refuses the same things, but it does so in a
        # child process whose stderr goes to a log nobody is looking at.
        books = [b.strip() for b in _text(body, playbook_field(stage)).split(",") if b.strip()]
        if not books:
            continue
        if stage not in markable:
            raise ValueError(
                f"the {stage} prompt has no {{{{playbook}}}} line, so it cannot be given "
                f"the {books[0]!r} standard. "
                f"Ask GET /control/playbooks for the stages that can"
            )
        for book in books:
            if book not in known:
                raise ValueError(
                    f"{book!r} is not a playbook this checkout has. "
                    f"Ask GET /control/playbooks for the list"
                )
        if len(books) > 1:
            if stage not in MULTI_PLAYBOOK_STAGES:
                raise ValueError(
                    f"the {stage} stage takes one standard and was given {len(books)} "
                    f"({', '.join(books)}). Only the hypothesis stage runs an agent per "
                    f"standard; the others run one agent however many workers claim from "
                    f"the board, so a second name would never be read"
                )
            count = hypothesis_agents if stage == "hypothesis" else interpret_agents
            if len(books) != count:
                raise ValueError(
                    f"the {stage} stage was given {len(books)} standards "
                    f"({', '.join(books)}) and {count} agents. Give one "
                    f"standard per agent, or one for all of them — they are paired by "
                    f"position, and there is no order in which {len(books)} standards fit "
                    f"{hypothesis_agents} agents that would not have to be guessed at"
                )
        chosen.append((stage, ",".join(books)))

    # --skill is passed even when it is empty, so that the run is confined by what this
    # request said and never by a value left over in the environment this service was
    # started with. `board.py:1890` writes it unconditionally for the same reason.
    #
    # --playbook-* is the opposite: written only when one was chosen. There is no value
    # of the flag that means "the prompt as written" — `board.py` reads its absence as
    # that — and passing an empty string would ask `load_prompt` for a playbook named "".
    #
    # `--playbook-hypothesis` may carry several names joined by commas, which is one
    # argument and not several flags. That is `board.py`'s own shape, and it is what keeps
    # this function's contract *the tail of a command line* rather than a second encoding
    # the driver would have to learn.
    argv = [
        "--trials", str(trials),
        "--waves", str(waves),
        "--hypothesis-agents", str(hypothesis_agents),
        "--interpret-agents", str(interpret_agents),
        "--y-column", y_column,
        "--provider", provider,
        "--model", model,
        "--skill", skill,
    ]
    from memstara.corpus_skills import corpus_profile
    if research_id or knowledge_mode == 'llm_only' or data_mode == 'proposal' or corpus_profile() != 'general':
        from memstara.research_inputs import validate_skills
        selected_books = {stage: value.split(',') for stage, value in chosen}
        if combination_plan:
            selected_books = {stage: [item['id'] for item in entries]
                              for stage, entries in combination_plan['skills'].items()}
        validate_skills(selected_books, profile if research_id else None, knowledge_mode=knowledge_mode)
        if research_id:
            argv += ['--research-input-id', research_id]
    if knowledge_mode != 'okf':
        argv += ['--knowledge-mode', knowledge_mode]
    if data_mode != 'dataset':
        argv += ['--data-mode', data_mode]
    if objective:
        argv += ['--research-objective', objective]
    from memstara.stage_models import resolve_run_profiles
    if connection is not None:
        from memstara.model_connections import profiles
        stage_models = profiles(connection)
        supplied = body.get('stage_models')
        if supplied and supplied != stage_models:
            raise ValueError('Model settings differ from the checked connection')
        argv += ['--model-connection-id', connection_id]
    else:
        stage_models = resolve_run_profiles(body.get("stage_models"))
    if stage_models:
        import json
        from memstara.stage_models import validate_profiles
        argv += ["--stage-models", json.dumps(validate_profiles(stage_models))]
    if controls:
        import json
        argv += ['--controlled-comparison', json.dumps(controls)]
    if continuous:
        argv += ["--continuous"]
    for stage, book in chosen:
        argv += [f"--playbook-{"explanation" if stage == "report" else stage}", book]
    import json
    from memstara.ml_configuration import validate_overrides
    ml_skills = (body.get('combination_skills', {}).get('ml', []) if body.get('combination_skills')
                 else str(body.get('playbook_ml', '')).split(','))
    overrides = validate_overrides(body.get('ml_overrides', {}), ml_skills, replicates=evaluation.get('replicates', 1))
    if overrides:
        if controls:
            raise ValueError('Controlled comparisons cannot also use advanced ML overrides')
        argv += ['--ml-overrides', json.dumps(overrides, allow_nan=False)]
    if "baseline_columns" in body:
        argv += ["--baseline-columns", json.dumps(baseline)]
    if "evaluation" in body:
        import json
        argv += ["--evaluation", json.dumps(evaluation)]
    if question:
        argv += ["--question", question]
    if combination_plan:
        argv += ["--combination-plan", json.dumps(combination_plan)]
    if body.get('_retry_from_loop'):
        start = body['_retry_from_loop']
        if type(start) is not int or not 1 <= start <= waves:
            raise ValueError('The requested replicate is outside the saved schedule')
        argv += ['--start-loop', str(start), '--retry-source-run', body['_retry_source_run']]
        if body.get('_retry_seed_schedule'):
            argv += ['--retry-seed-schedule', json.dumps(body['_retry_seed_schedule'], allow_nan=False)]
        if body.get('_retry_experiment_policy') is not None:
            argv += ['--retry-experiment-policy', json.dumps(body['_retry_experiment_policy'], allow_nan=False)]
    return argv
