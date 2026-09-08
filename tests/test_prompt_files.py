"""The prompt files this repository actually ships.

`tests/test_prompts.py` tests the loader against fixtures. This file tests the nine real
prompts, and it exists for one reason the loader tests cannot cover: **a prompt is now
edited by someone who never opens `core.py`.** That is the whole point of the move, and
it is also what removes the reader who used to notice.

`core.py` is not imported here, so the expected agent names are written out below rather
than read from `AGENT_NAMES` and `BOARD_AGENT_NAMES`. That duplication is deliberate and
it is not free: adding an agent means editing this list too. CI has no `../motoro`

`core.py` would fail on the runner and nowhere else — a duplicated list that fails loudly
is worth more than an import that cannot run.
"""

from __future__ import annotations

import pytest

from memstara.paths import PROMPTS_DIR
from memstara.pipeline.prompts import load_prompt

#: Every agent, by the path `provision_all` and `provision_board_agents` pass to
#: `_ensure_agent_from_file`. Four on the 02 (supervisor) path, five on the 03 (board) one.
#: `board/curator` was here until 2026-09-07. It is gone because the agent is: writing the
#: wave's questions is the hypothesis agent's other job now, and its text lives in the
#: second half of `board/hypothesis.md`. There is no sixth file, which is the whole of what
#: `test_no_file_is_unaccounted_for` below then has to agree with.
AGENTS = [
    "mvp/hypothesis", "mvp/data", "mvp/ml", "mvp/interpreter",
    "board/hypothesis", "board/data", "board/ml", "board/interpreter",
    "board/report",
]

#: Files that are not agents. A fragment has no goal and is never loaded on its own.
FRAGMENTS = ["board/_claim_preamble"]

#: The directory's rules file, which is prose for people and never loaded as a prompt.
#: Named here rather than filtered by a pattern, on the same principle as
#: `scripts/check_citations.py:47-49`: an exemption a reader can see beats one that a
#: glob happens to make.
NOT_A_PROMPT = ["CLAUDE"]


def prompt_files() -> list:
    return sorted(PROMPTS_DIR.rglob("*.md"))


@pytest.mark.parametrize("name", AGENTS)
def test_every_agent_has_a_loadable_prompt(name):
    """A rename in `core.py` without the matching file rename fails here, not at run time.

    Provisioning is the first thing a run does, so the real failure is cheap too — but
    it needs Postgres and a model, and this does not.
    """
    prompt = load_prompt(name)
    assert prompt["goal"], f"{name}: empty goal"
    assert prompt["system_prompt"], f"{name}: empty system prompt"


def test_no_file_is_unaccounted_for():
    """A prompt nothing loads is a prompt nobody knows is dead.

    The failure this catches is an agent renamed and its old file left behind: the run
    keeps working, and the stale file goes on being edited by whoever finds it first.
    """
    on_disk = {p.relative_to(PROMPTS_DIR).with_suffix("").as_posix() for p in prompt_files()}
    assert on_disk == set(AGENTS) | set(FRAGMENTS) | set(NOT_A_PROMPT)


@pytest.mark.parametrize("name", AGENTS)
def test_the_outcome_column_is_never_named_to_an_agent(name):


    A model that can see the label does not predict it, it reads it. Until the prompts
    were files this rule was enforced only at the tool servers

    """
    prompt = load_prompt(name)
    assert "HIV_DETECTABLE" not in prompt["system_prompt"]
    assert "HIV_DETECTABLE" not in prompt["goal"]


def test_a_fragment_carries_no_goal():
    """`_claim_preamble.md` is included into three prompts, so a goal in it would be
    silently dropped — the loader returns only the including file's front matter."""
    for name in FRAGMENTS:
        text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert not text.startswith("---"), f"{name}: a fragment must not declare front matter"


def test_the_shared_preamble_reaches_exactly_the_three_claimers():
    """data, ml and interpreter take work off the board; hypothesis creates it.

    Getting this wrong in either direction is silent. A hypothesis agent told to
    `claim_task` would find nothing and stop, and the run would produce no questions
    with no error anywhere.
    """
    marker = "Your work comes from a shared board"
    for stage in ("data", "ml", "interpreter"):
        assert marker in load_prompt(f"board/{stage}")["system_prompt"], stage
    assert marker not in load_prompt("board/hypothesis")["system_prompt"]


def test_no_comment_survives_into_a_prompt():
    """The `<!-- -->` blocks carry the reasoning and are for people, not models.

    Checked against the shipped files rather than a fixture because the cost of getting
    it wrong lands here: the comments are long, and a model reading them would be told
    about its own prompt's history.
    """
    for name in AGENTS:
        prompt = load_prompt(name)
        assert "<!--" not in prompt["system_prompt"], name
        assert "-->" not in prompt["system_prompt"], name
