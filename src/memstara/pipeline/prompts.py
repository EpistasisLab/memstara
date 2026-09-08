"""Read an agent's system prompt from a file instead of a string literal.

Why this file exists
--------------------
Every agent's role — what it is, what it must do first, what it must never do — used
to be a string literal inside `core.py`, and `provision_board_agents` said so in its
own docstring: *"What each stage is, and what it must do first, is written out here as
a prompt and nowhere else."* Ten agents' worth of that prose is about 13,000
characters, and it sat in the middle of a 1,200-line module.

The reason for moving it is not tidiness. It is that **in this project a prompt is an

records the decision and names the cost of not doing it: *this prompt changed, so this
result changed* cannot be traced afterwards while the prompt's history is
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
3. **Two includes, and the leading underscore is what tells them apart.** A line that is
   exactly ``{{_claim_preamble}}`` is replaced by the body of `_claim_preamble.md` in
   the same directory: a fixed fragment, chosen when the prompt was written. It exists
   because the data, ml and interpreter stages share a passage *in the middle* of their
   prompts — the one that tells a worker to claim from the board and to stop when there
   is nothing to claim. Three copies of it would defeat the point of their sharing it.

   A line that is exactly ``{{playbook}}`` is replaced by the behavioural standard **this
   run** chose for this stage, out of `PLAYBOOKS_DIR`, and by nothing at all when the run
   chose none. No underscore, because the file is not beside this one and its name is not
   in this file — it arrives as an argument. That is the whole of the difference, and it
   is worth a character: everything else about the two directives is the same.

   There is no nesting and no third directive.

Failure is loud on purpose. A missing file, an empty body or an unknown key raises;
none of them returns "". An agent provisioned with an empty system prompt does not
fail, it behaves strangely, and it looks like a model problem for as long as it takes
someone to go and check.

**A playbook handed to a prompt with no ``{{playbook}}`` line raises too**, for the same
reason an unknown front matter key does. The alternative is a run that was asked to work
to a standard, did not, and says nowhere that it did not.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path

from memstara.paths import PLAYBOOKS_DIR, PROMPTS_DIR

#: A whole `<!-- ... -->` block plus the newlines directly after it. Removing the
#: trailing newlines as part of the match is what keeps the paragraph spacing of the
#: remaining text intact: a comment sitting between two paragraphs leaves exactly the
#: blank line that was already between them, not three.
_COMMENT = re.compile(r"<!--.*?-->\n*", re.DOTALL)

#: The fixed include. Anchored to a whole line so it cannot fire inside prose.
_INCLUDE = re.compile(r"^\{\{(\w+)\}\}$", re.MULTILINE)

#: The run-chosen include, with the blank lines after it, exactly like `_COMMENT`.
#:
#: Swallowing them is what makes **a marked prompt with no playbook byte-identical to the
#: same prompt before the marker was added**: `A.\n\n{{playbook}}\n\nB.` becomes `A.\n\nB.`,
#: not `A.\n\n\n\nB.`. That property is the reason a stage can be given the marker in one
#: commit and a playbook in another without the first commit changing what any default run
#: sends — and `prompt_digest` is what makes the claim checkable rather than hopeful.
#:
#: Substituted **before** `_INCLUDE`, so `{{playbook}}` never reaches the fragment resolver
#: and is never looked for as `playbook.md` beside the prompt.
_PLAYBOOK = re.compile(r"^\{\{playbook\}\}\n*", re.MULTILINE)

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


def playbook_names() -> list[str]:
    """Every playbook this checkout has, sorted, for an error message or a menu.

    Returns an empty list when the directory does not exist, which is the state before
    the first playbook is written and is not a failure.
    """
    if not PLAYBOOKS_DIR.is_dir():
        return []
    return sorted(p.stem for p in PLAYBOOKS_DIR.glob("*.md"))


def load_prompt(name: str, playbook: str = "") -> dict[str, str]:
    """Read one agent's prompt, optionally with a playbook spliced into it.

    Args:
        name: Path under `PROMPTS_DIR` without the suffix — ``"board/hypothesis"``,
            ``"mvp/hypothesis"``.
        playbook: The stem of a file in `PLAYBOOKS_DIR` — ``"governance"`` — or ``""``
            for a prompt as written. The prompt must carry a ``{{playbook}}`` line to
            receive one; see the module docstring for why that is an error and not a
            place to append.

    Returns:
        ``{"goal": ..., "system_prompt": ...}``, shaped to be passed straight into
        `core._ensure_agent`, which already compares both against the stored agent
        and updates it when either has changed.

    Raises:
        FileNotFoundError: No such prompt file, no such playbook, or an include naming
            a fragment that is not beside it.
        ValueError: No `goal`, an empty body, malformed front matter, or a playbook
            given to a prompt with nowhere to put it.
    """
    path = (PROMPTS_DIR / name).with_suffix(".md")
    front, body = _read(path)

    if "goal" not in front:
        raise ValueError(f"{path}: no 'goal' in front matter")

    if playbook:
        if not _PLAYBOOK.search(body):
            raise ValueError(
                f"{path}: asked for the {playbook!r} playbook and has no "
                f"{{{{playbook}}}} line to put it on"
            )
        book = (PLAYBOOKS_DIR / playbook).with_suffix(".md")
        if not book.is_file():
            raise FileNotFoundError(
                f"no playbook at {book}. This checkout has: "
                f"{', '.join(playbook_names()) or '(none)'}"
            )
        _, text = _read(book)
        if not text:
            raise ValueError(f"{book}: the playbook is empty")
        body = _PLAYBOOK.sub(lambda _: f"{text}\n\n", body, count=1)

    # Whatever is left goes, playbook or not: a marker nobody filled is a line of syntax
    # for the model to puzzle over, and a second marker is a stage asking for two
    # standards, which is a prompt to fix rather than a case to support.
    body = _PLAYBOOK.sub("", body)
    body = _INCLUDE.sub(_include_beside(path), body)

    if not body:
        raise ValueError(f"{path}: the prompt body is empty")

    return {"goal": front["goal"], "system_prompt": body}


def _include_beside(path: Path) -> Callable[[re.Match[str]], str]:
    """The `{{_fragment}}` resolver for one prompt: a file of that name beside it."""

    def _include(match: re.Match[str]) -> str:
        _, text = _read(path.parent / f"{match.group(1)}.md")
        return text

    return _include


def prompt_digest(name: str, playbook: str = "") -> dict[str, str]:
    """The sha256 of each field an agent is given, for a run's record.

    A digest and not the text: what a run directory is read for is *which wording
    produced this*, and two runs whose digests match were told the same thing — an
    answer a person gets in one glance and does not get from two copies of 13,000
    characters. The text is not lost by being left out, because the digest belongs to
    a commit: one file per agent under `src/memstara/prompts/` means `git log` on that
    file is the list of every wording it has ever had.

    Digested **after** the comments are stripped and both includes resolved, so it is a
    digest of what the model received. Editing a `<!-- -->` block does not change it,
    and editing `_claim_preamble.md` changes it for all three stages that include it —
    both of which are the truth about that edit.

    **This is why `playbook` is an argument here and not only on `load_prompt`.** The run
    record is written from these digests (`src/memstara/pipeline/board.py`), so a playbook
    that reached the model without reaching the digest would leave the record unable to
    say which condition the run was — two runs told different things and recorded as
    having been told the same. The name is stored beside the digest as well, because a
    changed hash says *something moved* and not *which standard was applied*.

    Args:
        name: The same path `load_prompt` takes — ``"board/hypothesis"``.
        playbook: The same playbook `load_prompt` takes, and it must be the same one.

    Returns:
        ``{"goal": <hex>, "system_prompt": <hex>}``.

    Raises:
        FileNotFoundError, ValueError: Whatever `load_prompt` raises, unchanged.
    """
    return {
        field: hashlib.sha256(text.encode("utf-8")).hexdigest()
        for field, text in load_prompt(name, playbook).items()
    }
