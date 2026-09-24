"""`stores`'s agent-name resolution — the thing that broke when agent names stopped"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewer" / "api"))

import stores  # noqa: E402

SUFFIXED = "memstara-board-hypothesis-cardiometabolic"


# --------------------------------------------------------------------------- #
#  A name with a standard on it
# --------------------------------------------------------------------------- #


def test_a_playbook_suffixed_name_resolves_to_its_stage():
    """The whole point. Without this the run is dropped from the scene, the cost table
    and the access map, and nothing raises."""
    assert stores.stage_of_agent(SUFFIXED) == "hypothesis"
    assert stores.stage_of_agent_any(SUFFIXED) == "hypothesis"
    assert stores.path_of_agent(SUFFIXED) == "board"


def test_the_standard_stays_on_the_label():
    """Two agents of one stage would otherwise be two rows in the cost table reading
    identically, which makes "what did each standard cost" unanswerable from the
    screen."""
    assert stores.label_of(SUFFIXED) == "Hypothesis · cardiometabolic"
    assert stores.playbook_of(SUFFIXED) == "cardiometabolic"


def test_a_suffixed_name_is_reported_under_itself():
    """It is not folded into the base agent. Folding would add the two standards'
    spend together, and telling them apart is the reason there are two agents."""
    assert stores.reported_as(SUFFIXED) == SUFFIXED


def test_the_suffix_has_to_be_a_whole_segment():
    """`memstara-board-ml` must never be read as a suffixed `memstara-board-m`. The
    separator is required, so a shorter agent name is not a prefix of a longer one by
    accident."""
    assert stores.base_agent_name("memstara-board-ml") == "memstara-board-ml"
    assert stores.playbook_of("memstara-board-ml") == ""


# --------------------------------------------------------------------------- #
#  Everything that was already true stays true
# --------------------------------------------------------------------------- #


def test_every_plain_board_name_resolves_as_it_did():
    """The regression guard. Each of the five stages keeps its stage, its path and its
    label, and none of them is treated as carrying a standard."""
    for stage, name in stores.BOARD_AGENT_NAMES.items():
        assert stores.base_agent_name(name) == name
        assert stores.stage_of_agent(name) == stage
        assert stores.path_of_agent(name) == "board"
        assert stores.playbook_of(name) == ""


def test_the_retired_curator_still_folds_into_hypothesis():
    """Hundreds of runs are recorded under this name and the fold is what carries their
    spend onto the screen. It is a board name, so `base_agent_name` must leave it
    alone — stripping it would resolve it to no stage and drop the rows."""
    curator = stores.LEGACY_BOARD_AGENT_NAMES["curator"]
    assert stores.stage_of_agent(curator) == "curator"
    assert stores.reported_as(curator) == stores.BOARD_AGENT_NAMES["hypothesis"]
    assert stores.label_of(curator) == "Hypothesis"


def test_the_supervisor_path_is_still_board_invisible_and_access_visible():
    """`stage_of_agent` is the scene's filter and draws only board characters;
    `stage_of_agent_any` is what the cost table and the feed use, and dropping the
    supervisor path there understates the system about fivefold."""
    for stage, name in stores.SUPERVISOR_AGENT_NAMES.items():
        assert stores.stage_of_agent(name) is None
        assert stores.stage_of_agent_any(name) == stage
        assert stores.path_of_agent(name) == "supervisor"


def test_an_unknown_name_is_passed_through_not_guessed_at():
    """The viewer's rule everywhere: a name it cannot place arrives on screen exactly as
    it was stored. A guess would be a label nobody can trace back to a row."""
    assert stores.base_agent_name("something-else") == "something-else"
    assert stores.stage_of_agent("something-else") is None
    assert stores.stage_of_agent_any("something-else") is None
    assert stores.path_of_agent("something-else") == "other"
    assert stores.label_of("something-else") == "something-else"
