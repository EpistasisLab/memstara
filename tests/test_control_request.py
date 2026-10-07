"""What the control service will accept as a request to start a run."""

from __future__ import annotations

import re

import pytest

from memstara.control.request import DEFAULTS, PLAYBOOK_STAGES, PROVIDERS, build_argv
from memstara.paths import REPO_ROOT

# Two of the 26 the real bundle has, enough to test "in the list" and "not in it".
OFFERED = ["terminus_kind=sud", "mechanism_family=treatment-toxicity,terminus_kind=sud"]

#: What `GET /control/playbooks` answers with, written out rather than read off the disk.
#: The real answer grows every time somebody writes a playbook or marks a prompt, and a
#: test that followed it would change meaning without anyone editing it — these two lists
#: are here to be *stale on purpose*, so that what is asserted below is the rule and not
#: today's contents of two directories.
BOOKS = ["ml_reporting", "governance"]
MARKED = ["hypothesis", "ml"]


@pytest.fixture(autouse=True)
def deployment_environment(monkeypatch):
    monkeypatch.setattr("memstara.stage_models.deployment_profiles", lambda: {})
    monkeypatch.setenv("MEMSTARA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MEMSTARA_LLM_MODEL", "test-deployment")


def flags(argv: list[str]) -> dict[str, str]:
    """`["--trials", "3", ...]` as a dict, so a test can name the one field it means."""
    return dict(zip(argv[::2], argv[1::2], strict=True))


# --------------------------------------------------------------------------- #
#  The empty request is today's run
# --------------------------------------------------------------------------- #


def test_an_empty_body_is_the_default_run():
    """A form nobody touched starts what the CLI with no flags would start."""
    got = flags(build_argv({}, OFFERED))
    assert got == {"--trials": "3", "--waves": "1", "--hypothesis-agents": "1", "--interpret-agents": "1",
                   "--y-column": "outcome", "--provider": "openai",
                   "--model": "test-deployment", "--skill": ""}


def test_the_skill_is_always_passed_even_when_empty():
    """Never omitted. `board.py:1890` writes the environment variable unconditionally so
    that the flag is the whole answer; leaving the flag off here would put a value left
    over in this service's own environment back in charge."""
    assert "--skill" in flags(build_argv({}, OFFERED))


# --------------------------------------------------------------------------- #
#  An unknown field is an error, not something ignored
# --------------------------------------------------------------------------- #


def test_a_field_that_is_not_a_field_is_refused_by_name():
    with pytest.raises(ValueError, match="report_only"):
        build_argv({"report_only": True}, OFFERED)


def test_the_refusal_lists_what_a_run_does_take():
    with pytest.raises(ValueError, match="model"):
        build_argv({"nonsense": 1}, OFFERED)


# --------------------------------------------------------------------------- #
#  The skill must be one the bundle actually has
# --------------------------------------------------------------------------- #


def test_a_branch_from_the_offered_list_is_accepted():
    argv = build_argv({"skill": "terminus_kind=sud"}, OFFERED)
    assert flags(argv)["--skill"] == "terminus_kind=sud"


def test_a_crossing_is_accepted_whole():
    """The two-key form is what gets a run down to single figures, so it has to survive
    as one argument rather than being split on its comma."""
    argv = build_argv({"skill": OFFERED[1]}, OFFERED)
    assert flags(argv)["--skill"] == OFFERED[1]


def test_a_branch_the_bundle_does_not_have_is_refused():
    """`terminus_kind=cardiac` parses perfectly well and selects nothing. A run confined
    to nothing is a run whose agents can read nothing and will not say so."""
    with pytest.raises(ValueError, match="not one of the branches"):
        build_argv({"skill": "terminus_kind=cardiac"}, OFFERED)


# --------------------------------------------------------------------------- #
#  Numbers
# --------------------------------------------------------------------------- #


def test_trials_above_the_ceiling_is_refused_with_the_ceiling_named():
    with pytest.raises(ValueError, match="between 1 and 20"):
        build_argv({"trials": 200}, OFFERED)


def test_zero_trials_is_refused():
    """`board.py` would take it and sit on a board that never fills."""
    with pytest.raises(ValueError, match="between 1 and 20"):
        build_argv({"trials": 0}, OFFERED)


def test_true_is_not_a_number_of_trials():
    """`isinstance(True, int)` is true in Python, so a JSON `true` would otherwise arrive
    as `--trials 1` and look like somebody's choice."""
    with pytest.raises(ValueError, match="whole number"):
        build_argv({"trials": True}, OFFERED)


def test_a_number_written_as_text_is_refused():
    with pytest.raises(ValueError, match="whole number"):
        build_argv({"waves": "2"}, OFFERED)


# --------------------------------------------------------------------------- #
#  The one place the hypothesis count is capped
# --------------------------------------------------------------------------- #


def test_three_hypothesis_agents_is_accepted():
    """Verify that three hypothesis agents is accepted."""
    assert flags(build_argv({"hypothesis_agents": 3}, OFFERED))["--hypothesis-agents"] == "3"


def test_refuses_a_fifth_hypothesis_agent():
    """The user's V1 contract limits configuration to four distinct hypotheses."""
    with pytest.raises(ValueError, match="between 1 and 4"):
        build_argv({"hypothesis_agents": 5}, OFFERED)


def test_a_ninth_hypothesis_agent_is_refused_with_the_ceiling_named():
    """Refused **here** and not in `board.py`, where the flag is uncapped on purpose. What
    is left at 8 is a guard on a slipped keypress in a number field, the same kind as
    `_MAX_TRIALS`, so the message has to name the ceiling rather than only say no."""
    with pytest.raises(ValueError, match="hypothesis_agents must be between 1 and 4"):
        build_argv({"hypothesis_agents": 9}, OFFERED)


def test_zero_hypothesis_agents_is_refused():
    """`board.py` refuses it too (`ap.error`, `board.py:1948-1952`), twenty seconds and a
    provisioned run later. Same answer, sooner."""
    with pytest.raises(ValueError, match="between 1 and 4"):
        build_argv({"hypothesis_agents": 0}, OFFERED)


# --------------------------------------------------------------------------- #
#  The rest of the fields
# --------------------------------------------------------------------------- #


def test_a_provider_outside_the_three_is_refused():
    with pytest.raises(ValueError, match="provider must be one of"):
        build_argv({"provider": "ollama"}, OFFERED)


def test_a_y_column_that_could_not_be_a_column_name_is_refused():
    with pytest.raises(ValueError, match="not a column name"):
        build_argv({"y_column": "outcome; drop table"}, OFFERED)


def test_a_model_with_a_space_in_it_is_refused():
    with pytest.raises(ValueError, match="not a model identifier"):
        build_argv({"model": "claude sonnet"}, OFFERED)


def test_surrounding_whitespace_is_forgiven():
    """A value pasted out of a document arrives with a space on it. That is a typo to
    absorb, not a run to refuse."""
    argv = build_argv({"model": "  gpt-4.1  "}, OFFERED)
    assert flags(argv)["--model"] == "test-deployment"


# --------------------------------------------------------------------------- #
#  The playbooks
# --------------------------------------------------------------------------- #
#
#  A playbook is prose spliced into a stage's system prompt, so unlike `--skill` it is
#  not enforced anywhere downstream — nothing checks that the model obeyed it. What can
#  be checked is that the run was told the right thing, and these are that check.


def test_a_chosen_playbook_becomes_the_stages_flag():
    argv = build_argv({"playbook_ml": "ml_reporting"}, OFFERED, BOOKS, MARKED)
    assert flags(argv)["--playbook-ml"] == "ml_reporting"


def test_two_stages_can_take_different_standards_in_one_run():
    """The reason the fields are per-stage and not one `playbook` box. A reporting
    standard on `ml` and a questioning standard on `hypothesis` is the ordinary case."""
    argv = build_argv(
        {"playbook_ml": "ml_reporting", "playbook_hypothesis": "governance"},
        OFFERED, BOOKS, MARKED,
    )
    got = flags(argv)
    assert got["--playbook-ml"] == "ml_reporting"
    assert got["--playbook-hypothesis"] == "governance"


def test_an_empty_playbook_adds_no_flag():
    """`board.py` reads the flag's **absence** as "the prompt as written"; there is no
    value of it that means that. Passing "" would ask `load_prompt` for a playbook whose
    name is the empty string, which is a FileNotFoundError twenty seconds in."""
    assert "--playbook-ml" not in flags(build_argv({"playbook_ml": ""}, OFFERED, BOOKS, MARKED))


def test_a_playbook_this_checkout_does_not_have_is_refused():
    with pytest.raises(ValueError, match="not a playbook this checkout has"):
        build_argv({"playbook_ml": "no_such_standard"}, OFFERED, BOOKS, MARKED)


def test_a_stage_whose_prompt_has_no_marker_is_refused_and_says_why():
    """`report` is a real stage and `ml_reporting` is a real playbook; the pair is still
    refused, because `board/report.md` carries no `{{playbook}}` line to put it on. The
    message names the missing marker rather than saying the stage is unknown — the stage
    is perfectly known, and the fix is one line in a prompt file."""
    with pytest.raises(ValueError, match=r"no \{\{playbook\}\} line"):
        build_argv({"playbook_report": "ml_reporting"}, OFFERED, BOOKS, MARKED)


def test_nothing_is_offered_when_the_caller_names_nothing():
    """Both lists default to empty and empty refuses everything. A caller that has not
    said what exists cannot be read as saying anything goes — and every call site that
    predates the playbooks is such a caller."""
    with pytest.raises(ValueError, match="no .*playbook.* line|not a playbook"):
        build_argv({"playbook_ml": "ml_reporting"}, OFFERED)


def test_every_playbook_stage_has_a_field():
    """The form is built from `DEFAULTS`, so a stage missing here is a stage that cannot
    be given a standard from the browser however many markers its prompt carries."""
    for stage in PLAYBOOK_STAGES:
        from memstara.control.request import playbook_field
        assert playbook_field(stage) in DEFAULTS




def test_the_hypothesis_stage_takes_one_standard_per_agent():
    """Verify that the hypothesis stage takes one standard per agent."""
    argv = build_argv(
        {"playbook_hypothesis": "governance,ml_reporting", "hypothesis_agents": 2},
        OFFERED, BOOKS, MARKED,
    )
    assert flags(argv)["--playbook-hypothesis"] == "governance,ml_reporting"


def test_the_standards_have_to_be_one_per_agent():
    """Two standards and three agents is refused rather than padded or truncated. They
    are paired by position, so there is no third standard to invent and no rule for
    which two of the three agents would get one."""
    with pytest.raises(ValueError, match="2 standards.*and 3 agents"):
        build_argv(
            {"playbook_hypothesis": "governance,ml_reporting", "hypothesis_agents": 3},
            OFFERED, BOOKS, MARKED,
        )


def test_a_single_agent_stage_is_refused_a_second_standard():
    """`ml` runs one agent however many workers claim from the board, so a second name
    would be accepted here and never reach a model. Refused where the person pressing
    the button can read it, not in the child process's stderr."""
    with pytest.raises(ValueError, match="takes one standard and was given 2"):
        build_argv({"playbook_ml": "ml_reporting,governance"}, OFFERED, BOOKS, MARKED)


def test_an_unknown_standard_is_caught_anywhere_in_the_list():
    """The second name is checked as hard as the first. A list validated only at its
    head is a list whose tail reaches `load_prompt`."""
    with pytest.raises(ValueError, match="not a playbook this checkout has"):
        build_argv(
            {"playbook_hypothesis": "governance,no_such_standard", "hypothesis_agents": 2},
            OFFERED, BOOKS, MARKED,
        )


def test_a_trailing_comma_is_not_a_nameless_standard():
    """`"governance,"` is one standard, so it pairs with one agent and adds no empty
    name. A form field or a shell history leaves these behind, and reading one as a
    request would ask `load_prompt` for a playbook called ""."""
    argv = build_argv({"playbook_hypothesis": "governance,"}, OFFERED, BOOKS, MARKED)
    assert flags(argv)["--playbook-hypothesis"] == "governance"


# --------------------------------------------------------------------------- #
#  The copies of board.py's own vocabulary
# --------------------------------------------------------------------------- #


def board_argument(flag: str) -> str:
    """The whole `add_argument` call in `board.py` that declares *flag*.

    The source is read as text rather than imported: `board.py` pulls in asyncpg,
    litellm and motoro, none of which a CI runner has.

    Matched across newlines rather than line by line. Half of `board.py`'s flags put the
    name on the line after `ap.add_argument(` — `--hypothesis-agents` and `--skill` both
    do — and a line-by-line search finds nothing for those, which is a test that passes
    by never looking rather than by agreeing.
    """
    source = (REPO_ROOT / "src/memstara/pipeline/board.py").read_text(encoding="utf-8")
    # One level of nesting is allowed for, which covers the `choices=[...]` and the
    # parenthesised asides inside help strings. No flag here nests deeper than that.
    call = re.search(
        r"add_argument\(\s*\"" + re.escape(flag) + r"\"(?:[^()]|\([^()]*\))*\)", source
    )
    assert call, f"board.py has no add_argument for {flag}"
    return call.group(0)


def test_the_providers_are_the_ones_board_py_accepts():
    """`PROVIDERS` is a copy, and a copy is only safe while something compares it."""
    line = board_argument("--provider")
    choices = re.search(r"choices=\[(.*?)\]", line)
    assert choices, "board.py's --provider no longer has a choices= list"
    assert tuple(re.findall(r'"([^"]+)"', choices.group(1))) == PROVIDERS, (
        "board.py's providers changed; PROVIDERS in src/memstara/control/request.py "
        "has to change with them"
    )


def test_the_playbook_stages_are_board_pys_stages():
    """`PLAYBOOK_STAGES` is a second copy of the same tuple, for the same reason as
    `PROVIDERS`, and it is checked the same way.

    Order matters as well as membership: `build_argv` walks this tuple to lay the flags
    out, and `chosen_playbooks` (`board.py:1141`) walks board.py's. Two lists holding the
    same names in different orders would put the flags in an order no `--help` describes,
    which is a diff nobody can read against the driver.
    """
    source = (REPO_ROOT / "src/memstara/pipeline/board.py").read_text(encoding="utf-8")
    written = re.search(r"^PLAYBOOK_STAGES = \((.*?)\)$", source, re.MULTILINE)
    assert written, "board.py no longer declares PLAYBOOK_STAGES as a one-line tuple"
    assert tuple(re.findall(r'"([^"]+)"', written.group(1))) == PLAYBOOK_STAGES, (
        "board.py's playbook stages changed; PLAYBOOK_STAGES in "
        "src/memstara/control/request.py has to change with them"
    )


def test_the_defaults_are_board_pys_defaults():
    """A form nobody touched must start the run the CLI would, which is only true while
    the two lists of defaults agree."""
    for flag, key in (("--trials", "trials"), ("--waves", "waves"),
                      ("--hypothesis-agents", "hypothesis_agents"),
                      ("--y-column", "y_column"), ("--provider", "provider"),
                      ("--model", "model")):
        line = board_argument(flag)
        written = re.search(r"default=(\d+|\"[^\"]*\")", line)
        assert written, f"{flag} no longer declares a default in board.py"
        value = written.group(1).strip('"')
        assert str(DEFAULTS[key]) == value, (
            f"{flag} defaults to {value!r} in board.py, but DEFAULTS says "
            f"{DEFAULTS[key]!r}"
        )
