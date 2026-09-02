"""Read an agent's system prompt from a file instead of a string literal.

Why this file exists
--------------------
Every agent's role — what it is, what it must do first, what it must never do — used
to be a string literal inside `core.py`, and `provision_board_agents` said so in its
own docstring: *"What each stage is, and what it must do first, is written out here as
a prompt and nowhere else."* Ten agents' worth of that prose is about 13,000
characters, and it sat in the middle of a 1,200-line module.

The reason for moving it is not tidiness. It is that **in this project a prompt is an

records the decision and names the cost of not doing it: *"프롬프트를 이렇게 바꿨더니
결과가 이렇게 달라졌다"* cannot be traced afterwards while the prompt's history is
tangled with every unrelated edit to the module it lived in. One file per agent makes
`git log` on that file the experiment log for that agent.

What this is not
----------------
**A reader, not a template engine.** There is no expression syntax, no loops, no
conditionals, and exactly one include. Everything a prompt needs at *call* time —
the run tag, the worker name, the trial number, the outcome column — is interpolated
into the per-call message in `board.py` and deliberately stays there, where the
branching that chooses it is visible as code.

The file format
---------------
::

    ---
    goal: One line. Handed to the model as the agent's goal.
    ---

    <!--
    Why the text below is worded the way it is. Stripped before the model sees it.
    -->

    You are a question agent. You do not investigate anything. ...

Three rules, and they are the whole of it:

1. **Front matter.** `goal` is the only key. An unrecognised key raises rather than
   being ignored — a key that is silently dropped is a prompt that silently does not
   say what its author wrote, and the author has no way to notice.
2. **`<!-- ... -->` blocks are stripped**, along with the blank lines they leave
   behind. This is where the reasoning lives. It stays with the text it explains
   rather than in a comment beside a call site, because those two drift apart and the
   text is the thing people edit.
3. **One include.** A line that is exactly ``{{_claim_preamble}}`` is replaced by the
   body of `_claim_preamble.md` in the same directory. It exists because the data, ml
   and interpreter stages share a passage *in the middle* of their prompts — the one
   that tells a worker to claim from the board and to stop when there is nothing to
   claim. Three copies of it would defeat the point of their sharing it. There is no
   nesting and no second directive.

Failure is loud on purpose. A missing file, an empty body or an unknown key raises;
none of them returns "". An agent provisioned with an empty system prompt does not
fail, it behaves strangely, and it looks like a model problem for as long as it takes
someone to go and check.
"""

from __future__ import annotations

import re
from pathlib import Path

from memstara.paths import PROMPTS_DIR

#: A whole `<!-- ... -->` block plus the newlines directly after it. Removing the
#: trailing newlines as part of the match is what keeps the paragraph spacing of the
#: remaining text intact: a comment sitting between two paragraphs leaves exactly the
#: blank line that was already between them, not three.
_COMMENT = re.compile(r"<!--.*?-->\n*", re.DOTALL)

#: The one include. Anchored to a whole line so it cannot fire inside prose.
_INCLUDE = re.compile(r"^\{\{(\w+)\}\}$", re.MULTILINE)

#: The keys a prompt file may declare. Adding one means deciding what passes it to
#: the agent; until then, an unknown key is a mistake and is reported as one.
_FRONT_MATTER_KEYS = frozenset({"goal"})


def _split_front_matter(text: str, path: Path) -> tuple[dict[str, str], str]:
    """Separate a leading ``---`` block from the body.

    Args:
        text: The whole file.
        path: Only for the error messages — a parse failure that does not say which
            file failed is a search through ten of them.

    Returns:
        ``(front_matter, body)``. Front matter is empty when the file does not open
        with ``---``; that is how a shared fragment like `_claim_preamble.md`, which
        is not an agent and has no goal, is read by the same code.

    Raises:
        ValueError: The block is opened and never closed, a line inside it is not
            ``key: value``, or the key is not one this loader knows.
    """
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---\n", 3)
    if end == -1:
        raise ValueError(f"{path}: front matter opens with --- and is never closed")

    front: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"{path}: front matter line is not 'key: value': {line!r}")
        key = key.strip()
        if key not in _FRONT_MATTER_KEYS:
            raise ValueError(
                f"{path}: unknown front matter key {key!r}. "
                f"Known keys: {', '.join(sorted(_FRONT_MATTER_KEYS))}"
            )
        front[key] = value.strip()

    return front, text[end + len("\n---\n"):]


def _body(text: str) -> str:
    """The prompt as the model will see it: comments gone, ends trimmed."""
    return _COMMENT.sub("", text).strip()


def _read(path: Path) -> tuple[dict[str, str], str]:
    """One file, front matter separated and comments stripped.

    Raises:
        FileNotFoundError: With the full path. The names come from `core.py`'s agent
            tables, so a miss means those two have fallen out of step.
    """
    if not path.is_file():
        raise FileNotFoundError(f"no prompt file at {path}")
    front, rest = _split_front_matter(path.read_text(encoding="utf-8"), path)
    return front, _body(rest)


def load_prompt(name: str) -> dict[str, str]:
    """Read one agent's prompt.

    Args:
        name: Path under `PROMPTS_DIR` without the suffix — ``"board/curator"``,
            ``"mvp/hypothesis"``.

    Returns:
        ``{"goal": ..., "system_prompt": ...}``, shaped to be passed straight into
        `core._ensure_agent`, which already compares both against the stored agent
        and updates it when either has changed.

    Raises:
        FileNotFoundError: No such prompt file, or an include naming a fragment that
            is not beside it.
        ValueError: No `goal`, an empty body, or malformed front matter.
    """
    path = (PROMPTS_DIR / name).with_suffix(".md")
    front, body = _read(path)

    if "goal" not in front:
        raise ValueError(f"{path}: no 'goal' in front matter")

    def _include(match: re.Match[str]) -> str:
        fragment = path.parent / f"{match.group(1)}.md"
        _, text = _read(fragment)
        return text

    body = _INCLUDE.sub(_include, body)

    if not body:
        raise ValueError(f"{path}: the prompt body is empty")

    return {"goal": front["goal"], "system_prompt": body}
