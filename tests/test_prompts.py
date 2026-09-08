"""The prompt loader.

Fixtures only — no repository file is read here and `memstara.pipeline.core` is never
imported. That is not fastidiousness: CI has no `../motoro` checkout and no litellm

on the runner and nowhere else. `memstara.pipeline.prompts` imports `re`, `pathlib`
and `memstara.paths`, and `memstara/__init__.py` imports only `os`, so this module is
importable anywhere.
"""

from __future__ import annotations

import hashlib

import pytest

from memstara.pipeline import prompts


@pytest.fixture
def prompt_dir(tmp_path, monkeypatch):
    """A prompts directory of our own, so these tests say nothing about the real one."""
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def playbook_dir(tmp_path, monkeypatch):
    """The same, for the standards a run may attach. A separate directory in the tests
    because it is a separate directory in the package: a playbook is chosen at run time
    and a prompt fragment is not, and one folder holding both would lose that."""
    directory = tmp_path / "playbooks"
    directory.mkdir()
    monkeypatch.setattr(prompts, "PLAYBOOKS_DIR", directory)
    return directory


def write(directory, name: str, text: str) -> None:
    path = directory / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
#  The happy path
# --------------------------------------------------------------------------- #


def test_reads_goal_and_body(prompt_dir):
    write(prompt_dir, "solo", "---\ngoal: Do the thing.\n---\n\nYou are an agent.\n")
    assert prompts.load_prompt("solo") == {
        "goal": "Do the thing.",
        "system_prompt": "You are an agent.",
    }


def test_comments_do_not_reach_the_model(prompt_dir):
    write(prompt_dir, "solo", (
        "---\ngoal: Do the thing.\n---\n\n"
        "<!--\nWhy the second paragraph says what it says.\n-->\n\n"
        "First paragraph.\n\n"
        "<!-- an aside -->\n\n"
        "Second paragraph.\n"
    ))
    # The blank line between the two paragraphs survives; the comment that sat in it
    # does not, and it does not leave a wider gap behind either.
    assert prompts.load_prompt("solo")["system_prompt"] == "First paragraph.\n\nSecond paragraph."


def test_include_pastes_the_fragment_in_place(prompt_dir):
    write(prompt_dir, "_shared", "Claim your work.\n\nStop when there is none.\n")
    write(prompt_dir, "solo", (
        "---\ngoal: Do the thing.\n---\n\n"
        "You are an agent.\n\n"
        "{{_shared}}\n\n"
        'Your type is "data".\n'
    ))
    assert prompts.load_prompt("solo")["system_prompt"] == (
        "You are an agent.\n\n"
        "Claim your work.\n\n"
        "Stop when there is none.\n\n"
        'Your type is "data".'
    )


def test_a_fragment_needs_no_front_matter(prompt_dir):
    """`_claim_preamble.md` is not an agent, so it has no goal — and must still read."""
    write(prompt_dir, "_shared", "Claim your work.\n")
    write(prompt_dir, "solo", "---\ngoal: g\n---\n\n{{_shared}}\n")
    assert prompts.load_prompt("solo")["system_prompt"] == "Claim your work."


def test_subdirectories_work(prompt_dir):
    write(prompt_dir, "board/curator", "---\ngoal: g\n---\n\nYou are a question agent.\n")
    assert prompts.load_prompt("board/curator")["system_prompt"] == "You are a question agent."


def test_include_resolves_beside_the_file_that_asked(prompt_dir):
    """A fragment is looked up in the including file's own directory, not the root.

    `board/` and `mvp/` are separate paths on purpose; a `board/_x.md` must never be
    what `mvp/data.md` gets.
    """
    write(prompt_dir, "board/_shared", "the board's wording")
    write(prompt_dir, "mvp/_shared", "the mvp's wording")
    write(prompt_dir, "board/data", "---\ngoal: g\n---\n\n{{_shared}}\n")
    assert prompts.load_prompt("board/data")["system_prompt"] == "the board's wording"


# --------------------------------------------------------------------------- #
#  The failures, which are the point — every one of these used to be silent
# --------------------------------------------------------------------------- #


def test_missing_file_raises_with_the_path(prompt_dir):
    with pytest.raises(FileNotFoundError, match="ghost"):
        prompts.load_prompt("ghost")


def test_missing_goal_raises(prompt_dir):
    write(prompt_dir, "solo", "You are an agent.\n")
    with pytest.raises(ValueError, match="no 'goal'"):
        prompts.load_prompt("solo")


def test_unknown_front_matter_key_raises(prompt_dir):
    """Ignoring it would mean a prompt silently does not say what its author wrote."""
    write(prompt_dir, "solo", "---\ngoal: g\ntemperature: 0.9\n---\n\nYou are an agent.\n")
    with pytest.raises(ValueError, match="unknown front matter key 'temperature'"):
        prompts.load_prompt("solo")


def test_unclosed_front_matter_raises(prompt_dir):
    write(prompt_dir, "solo", "---\ngoal: g\n\nYou are an agent.\n")
    with pytest.raises(ValueError, match="never closed"):
        prompts.load_prompt("solo")


def test_empty_body_raises(prompt_dir):
    """An agent provisioned with "" does not fail — it behaves oddly and looks like
    a model problem. So the load fails instead."""
    write(prompt_dir, "solo", "---\ngoal: g\n---\n\n<!-- all of it was a comment -->\n")
    with pytest.raises(ValueError, match="body is empty"):
        prompts.load_prompt("solo")


def test_missing_include_raises(prompt_dir):
    write(prompt_dir, "solo", "---\ngoal: g\n---\n\n{{_absent}}\n")
    with pytest.raises(FileNotFoundError, match="_absent"):
        prompts.load_prompt("solo")


def test_include_does_not_fire_inside_prose(prompt_dir):
    """Anchored to a whole line, so a prompt may talk about the syntax."""
    write(prompt_dir, "solo", "---\ngoal: g\n---\n\nWrite {{_shared}} on its own line.\n")
    assert prompts.load_prompt("solo")["system_prompt"] == "Write {{_shared}} on its own line."


# --------------------------------------------------------------------------- #
#  The digest a run records
# --------------------------------------------------------------------------- #
#
#  `board.py` writes these into `prompts.json` so a run directory can answer *which
#  wording produced this*. What that answer is worth is exactly the two properties
#  below: an edit the model cannot see must not move the digest, and an edit it can
#  see must. The `board.py` write itself is not tested — CI has no `../motoro` and no
#  litellm, so that module is not importable on the runner.


def test_digest_is_the_sha256_of_what_load_prompt_returns(prompt_dir):
    write(prompt_dir, "solo", "---\ngoal: Do the thing.\n---\n\nYou are an agent.\n")
    loaded = prompts.load_prompt("solo")
    digest = prompts.prompt_digest("solo")

    assert digest.keys() == loaded.keys()
    assert digest == {
        field: hashlib.sha256(text.encode("utf-8")).hexdigest()
        for field, text in loaded.items()
    }


def test_a_comment_edit_does_not_move_the_digest(prompt_dir):
    """The reasoning above a prompt is edited often and is stripped before the model
    sees it. A digest that moved with it would report a changed condition on every
    such edit, and the record would stop meaning anything."""
    write(prompt_dir, "solo", (
        "---\ngoal: g\n---\n\n<!-- because the first draft over-claimed -->\n\nYou are an agent.\n"
    ))
    before = prompts.prompt_digest("solo")

    write(prompt_dir, "solo", (
        "---\ngoal: g\n---\n\n<!-- rewritten, at length, saying something else -->\n\n"
        "You are an agent.\n"
    ))
    assert prompts.prompt_digest("solo") == before


def test_editing_an_included_fragment_moves_the_digest(prompt_dir):
    """And it moves for every prompt that includes it, which is what that edit is."""
    write(prompt_dir, "_shared", "Claim your work.\n")
    write(prompt_dir, "data", "---\ngoal: g\n---\n\n{{_shared}}\n\nYour type is \"data\".\n")
    write(prompt_dir, "ml", "---\ngoal: g\n---\n\n{{_shared}}\n\nYour type is \"ml\".\n")
    before = {name: prompts.prompt_digest(name) for name in ("data", "ml")}

    write(prompt_dir, "_shared", "Claim your work. Stop when there is none.\n")

    for name in ("data", "ml"):
        assert prompts.prompt_digest(name)["system_prompt"] != before[name]["system_prompt"]
        assert prompts.prompt_digest(name)["goal"] == before[name]["goal"]


def test_the_two_fields_are_digested_apart(prompt_dir):
    """Rewording the goal must not read as a changed system prompt, or the record
    cannot tell the two experiments apart."""
    write(prompt_dir, "solo", "---\ngoal: Do the thing.\n---\n\nYou are an agent.\n")
    before = prompts.prompt_digest("solo")

    write(prompt_dir, "solo", "---\ngoal: Do the other thing.\n---\n\nYou are an agent.\n")
    after = prompts.prompt_digest("solo")

    assert after["goal"] != before["goal"]
    assert after["system_prompt"] == before["system_prompt"]


def test_digest_raises_rather_than_hashing_nothing(prompt_dir):
    """A digest of "" is a valid-looking hex string, and it would be recorded as one."""
    with pytest.raises(FileNotFoundError, match="ghost"):
        prompts.prompt_digest("ghost")


# --------------------------------------------------------------------------- #
#  The playbook a run chooses
# --------------------------------------------------------------------------- #
#
#  The second include, and the one whose file is named at run time rather than in the
#  prompt. What has to hold: it lands where the prompt put it, a marked prompt with no
#  playbook is the prompt it was before the marker, and both of those are visible in
#  the digest — because the digest is what `board.py` writes into the run record, and a
#  standard that reached the model without reaching the record leaves two differently
#  instructed runs looking identical afterwards.


MARKED = "---\ngoal: g\n---\n\nYou are an agent.\n\n{{playbook}}\n\nYour type is \"ml\".\n"
UNMARKED = "---\ngoal: g\n---\n\nYou are an agent.\n\nYour type is \"ml\".\n"


def test_the_playbook_lands_where_the_prompt_put_it(prompt_dir, playbook_dir):
    write(prompt_dir, "ml", MARKED)
    write(playbook_dir, "governance", "Report what the tool returned.\n")

    body = prompts.load_prompt("ml", "governance")["system_prompt"]
    assert body == (
        'You are an agent.\n\nReport what the tool returned.\n\nYour type is "ml".'
    )


def test_a_marked_prompt_with_no_playbook_is_the_prompt_it_was_before_the_marker(
    prompt_dir, playbook_dir
):
    """Byte-identical, not merely similar. This is what lets a stage be given the marker
    in one commit and a standard in another without the first commit changing what any
    default run sends — and it is checked on the digest, because that is the claim."""
    write(prompt_dir, "ml", UNMARKED)
    before = prompts.prompt_digest("ml")

    write(prompt_dir, "ml", MARKED)
    assert prompts.load_prompt("ml")["system_prompt"] == 'You are an agent.\n\nYour type is "ml".'
    assert prompts.prompt_digest("ml") == before


def test_attaching_a_playbook_moves_the_digest(prompt_dir, playbook_dir):
    """The whole reason `prompt_digest` takes the playbook too. Without this the record
    would say two runs were told the same thing when one was working to a standard."""
    write(prompt_dir, "ml", MARKED)
    write(playbook_dir, "governance", "Report what the tool returned.\n")

    plain = prompts.prompt_digest("ml")
    under = prompts.prompt_digest("ml", "governance")

    assert under["system_prompt"] != plain["system_prompt"]
    assert under["goal"] == plain["goal"]


def test_editing_a_playbook_moves_the_digest(prompt_dir, playbook_dir):
    write(prompt_dir, "ml", MARKED)
    write(playbook_dir, "governance", "Report what the tool returned.\n")
    before = prompts.prompt_digest("ml", "governance")

    write(playbook_dir, "governance", "Report what the tool returned, and the engine.\n")
    assert prompts.prompt_digest("ml", "governance") != before


def test_two_playbooks_are_two_digests(prompt_dir, playbook_dir):
    """Otherwise the record cannot tell one condition from another, which is the only
    thing it is written for."""
    write(prompt_dir, "ml", MARKED)
    write(playbook_dir, "strict", "Report what the tool returned.\n")
    write(playbook_dir, "loose", "Use your judgement.\n")

    assert prompts.prompt_digest("ml", "strict") != prompts.prompt_digest("ml", "loose")


def test_a_playbook_for_a_prompt_with_nowhere_to_put_it_raises(prompt_dir, playbook_dir):
    """The alternative is a run that was asked to work to a standard, did not, and says
    nowhere that it did not."""
    write(prompt_dir, "ml", UNMARKED)
    write(playbook_dir, "governance", "Report what the tool returned.\n")

    with pytest.raises(ValueError, match="no .*playbook.* line"):
        prompts.load_prompt("ml", "governance")


def test_a_playbook_that_is_not_there_raises_and_lists_the_ones_that_are(
    prompt_dir, playbook_dir
):
    write(prompt_dir, "ml", MARKED)
    write(playbook_dir, "governance", "Report what the tool returned.\n")

    with pytest.raises(FileNotFoundError, match="governance"):
        prompts.load_prompt("ml", "ghost")


def test_an_empty_playbook_raises(prompt_dir, playbook_dir):
    """Same rule as an empty prompt body. A run recorded as working to a standard, whose
    standard was a blank file, is worse than one recorded as working to none."""
    write(prompt_dir, "ml", MARKED)
    write(playbook_dir, "hollow", "<!-- notes and nothing else -->\n")

    with pytest.raises(ValueError, match="empty"):
        prompts.load_prompt("ml", "hollow")


def test_a_playbook_comment_does_not_reach_the_model(prompt_dir, playbook_dir):
    """A playbook is read by the same reader as a prompt, so the reasoning above it stays
    with it rather than moving to a commit message nobody opens."""
    write(prompt_dir, "ml", MARKED)
    write(playbook_dir, "governance", "<!-- why -->\n\nReport what the tool returned.\n")

    assert "why" not in prompts.load_prompt("ml", "governance")["system_prompt"]


def test_the_marker_does_not_fire_inside_prose(prompt_dir, playbook_dir):
    """Anchored to a whole line, exactly like the fragment include, so a prompt may talk
    about the syntax — and this file's own ml.md comment does."""
    write(prompt_dir, "ml", '---\ngoal: g\n---\n\nA {{playbook}} line is spliced.\n')
    assert prompts.load_prompt("ml")["system_prompt"] == "A {{playbook}} line is spliced."


def test_playbook_names_lists_what_is_there(playbook_dir):
    write(playbook_dir, "governance", "x\n")
    write(playbook_dir, "reporting", "x\n")
    assert prompts.playbook_names() == ["governance", "reporting"]
