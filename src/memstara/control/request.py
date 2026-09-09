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
PROVIDERS = ("anthropic", "azure_foundry", "openai")

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

#: **This was 3 until 2026-09-09, and three was a drawing's limit rather than a run's.**
#: The meeting of 2026-08-26 scoped V1 to one or two hypothesis agents with the screen
#: expandable to three, and the floor plan was laid out to exactly that: the figures fan
#: upwards from a row of five stations 175 apart, a figure is 128 wide, and a fixed 22px
#: sideways step means three span 172 and the fourth walks into the next station.
#:
#: The step is no longer fixed. `ScenePanel.tsx` now divides the same 175-wide envelope by
#: however many figures there are, so the stack tightens instead of overflowing and there
#: is no N at which it draws something wrong. That removes the reason this number was 3,
#: and a number kept after its reason has gone is the kind that gets cited later as though
#: it meant something.
#:
#: It is 8 rather than removed. `board.py` deliberately does **not** cap
#: `--hypothesis-agents` (`src/memstara/pipeline/board.py:1930-1933`), because a cap in the
#: driver stops an experiment; this one is on the *screen's* requests, where the thing being
#: guarded is a slipped keypress in a number field — the same reason as `_MAX_TRIALS` above,
#: and the same kind of ceiling. Eight hypothesis agents is already a run nobody starts by
#: accident, and the CLI is still there for a deliberate ninth.
_MAX_HYPOTHESIS_AGENTS = 8

#: What the form sends when a field is left alone. The same values as `board.py`'s own
#: argparse defaults, so a request that names nothing starts the run the CLI would.
#:
#: `hypothesis_agents` is the only stage count here. The same meeting fixed the other
#: three at one each — one data, one ml, one interpreter — so putting them on the form
#: would reopen a decision on screen that was made in a meeting. They are still free on
#: the command line, and `A-24` draws whatever number results as one character with the
#: count on it.
#: The stages that may be given a playbook, in the order they are put on the command
#: line. The same five as `board.py`'s `PLAYBOOK_STAGES`, written out rather than
#: imported for the reason in the module docstring — and `tests/test_control_request.py`
#: compares the two lists, so the copy cannot drift without a test failing.
#:
#: **Every stage is here, and whether a stage can actually take one is not this file's
#: answer.** A prompt has to carry a `{{playbook}}` line to receive a standard. All five
#: carry it as of 2026-09-08 — but that is a fact about five `.md` files, changeable with a
#: one-line edit, and a copy of it here would be a second answer to the same question kept
#: in step by hand. `GET /control/playbooks` reads the prompts themselves and the caller
#: passes the answer in. This list stays the *stages a flag exists for*, which is a
#: different and slower-moving question.
PLAYBOOK_STAGES = ("hypothesis", "data", "ml", "interpreter", "report")

#: The one stage that may be given several standards, one per worker. Everything else runs
#: a single agent however many workers claim from the board, so a second name there would
#: be accepted and never read — `board.py` refuses it and so does `build_argv`, at the
#: earlier of the two points.
#:
#: A tuple of one rather than a bare string: `hypothesis` is the only such stage because
#: it is the only one whose workers set out independently, and if a second ever qualifies
#: the check below does not change shape.
MULTI_PLAYBOOK_STAGES = ("hypothesis",)

DEFAULTS: dict[str, Any] = {
    "skill": "",
    "trials": 3,
    "waves": 1,
    "hypothesis_agents": 1,
    "y_column": "outcome",
    "provider": "azure_foundry",
    "model": "claude-sonnet-4-6",
    # One key per stage rather than one `playbooks` object, so the allow-list stays flat
    # and an unknown *stage* is caught by the same check that catches an unknown field
    # — a nested object would need its own copy of that rule, and the copy is what goes
    # wrong. Empty means the prompt as written, which is also what `board.py` means by
    # the flag being absent.
    **{f"playbook_{stage}": "" for stage in PLAYBOOK_STAGES},
}


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
    """The arguments for one run, or `ValueError` saying which field was wrong.

    Args:
        body: the decoded JSON object from the request.
        offered: the skills `GET /control/skills` listed, as `field=value` strings. A
            skill outside this set is refused **even though it may be a perfectly good
            filter**: the list is generated from the bundle, so anything missing from
            it selects no documents, and a run confined to nothing is a run whose
            agents can read nothing and will not say so.
        playbooks: the playbook stems `GET /control/playbooks` listed. Named here for
            the same reason the skills are: `board.py` refuses an unknown one, but it
            does so after the process has started, where the message reaches a log
            rather than the person who pressed the button.
        playbook_stages: the stages whose prompts carry a ``{{playbook}}`` line, out of
            the same endpoint. **Both default to empty, which refuses every playbook.**
            A caller that does not say what exists cannot be assumed to have meant
            anything is allowed, and no playbook is the state every run was in until
            this field existed.

    **`playbook_hypothesis` may name several standards, comma-separated, one per agent.**
    That is the request half of `A-32`: the hypothesis stage provisions an agent per
    standard, so two workers choosing the same column is two standards agreeing rather
    than one standard asked twice. The count has to equal ``hypothesis_agents`` — they are
    paired by position, and the check is here as well as in `board.py` so that a mismatch
    is a red message under the button instead of a process that exits 2 into a log.

    Returns:
        The tail of the command line — `["--trials", "3", ...]`. The caller adds
        `--run-tag` and `--run-dir`, because those are its own bookkeeping and are
        never taken from the request.

    Raises:
        ValueError: one field was missing a type, out of range, outside the offered
            skills, or not a field at all. The message names the field and the value,
            because it is shown to whoever pressed the button.
    """
    unknown = sorted(set(body) - set(DEFAULTS))
    if unknown:
        raise ValueError(
            f"not something a run takes: {', '.join(unknown)}. "
            f"The fields are {', '.join(sorted(DEFAULTS))}"
        )

    skill = _text(body, "skill")
    if skill and skill not in set(offered):
        raise ValueError(
            f"{skill!r} is not one of the branches this bundle has. "
            f"Ask GET /control/skills for the list"
        )

    y_column = _text(body, "y_column")
    if not _COLUMN.match(y_column):
        raise ValueError(f"y_column {y_column!r} is not a column name")

    provider = _text(body, "provider")
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {', '.join(PROVIDERS)}; {provider!r} is not")

    model = _text(body, "model")
    if not _MODEL.match(model):
        raise ValueError(f"model {model!r} is not a model identifier")

    trials = _whole_number(body, "trials", _MAX_TRIALS)
    waves = _whole_number(body, "waves", _MAX_WAVES)
    hypothesis_agents = _whole_number(body, "hypothesis_agents", _MAX_HYPOTHESIS_AGENTS)

    known = set(playbooks)
    markable = set(playbook_stages)
    chosen: list[tuple[str, str]] = []
    for stage in PLAYBOOK_STAGES:
        # Comma-separated, and for four of the five stages that only ever yields one name.
        # The split is here rather than only in `board.py` so the person who pressed the
        # button gets the message: `board.py` refuses the same things, but it does so in a
        # child process whose stderr goes to a log nobody is looking at.
        books = [b.strip() for b in _text(body, f"playbook_{stage}").split(",") if b.strip()]
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
            if len(books) != hypothesis_agents:
                raise ValueError(
                    f"the hypothesis stage was given {len(books)} standards "
                    f"({', '.join(books)}) and {hypothesis_agents} agents. Give one "
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
        "--y-column", y_column,
        "--provider", provider,
        "--model", model,
        "--skill", skill,
    ]
    for stage, book in chosen:
        argv += [f"--playbook-{stage}", book]
    return argv
