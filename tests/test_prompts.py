"""The prompt loader.

Fixtures only — no repository file is read here and `memstara.pipeline.core` is never
imported. That is not fastidiousness: CI has no `../motoro` checkout and no litellm

on the runner and nowhere else. `memstara.pipeline.prompts` imports `re`, `pathlib`
and `memstara.paths`, and `memstara/__init__.py` imports only `os`, so this module is
importable anywhere.
"""

from __future__ import annotations

import pytest

from memstara.pipeline import prompts


@pytest.fixture
def prompt_dir(tmp_path, monkeypatch):
    """A prompts directory of our own, so these tests say nothing about the real one."""
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    return tmp_path


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
