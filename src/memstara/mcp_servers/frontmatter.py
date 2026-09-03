"""Narrow a set of OKF documents by what their front matter says they are.

Why this is a module and not four lines inside `okf.py`
-------------------------------------------------------
`okf.py` imports `motoro.mcp_servers.okf` and `yaml`. CI has neither — there is no
`../motoro` checkout on a runner, and PyYAML is deliberately undeclared in
`pyproject.toml`. A test that imported `okf.py` would therefore fail on the runner and
nowhere else. This module imports the standard library and nothing else, so the rule it
enforces can actually be tested. `src/memstara/pipeline/prompts.py` was split out of
`core.py` for the same reason and is the pattern being followed.

Why a field and not a tag
-------------------------
The corpus files every branch twice: once as a structured field (`terminus_kind:`,
`mechanism_family:`) and again inside `tags:`. Those two do not agree. Measured
2026-09-02 over the 312 documents `_load` returns for
`../shared/Memstara/OKF_Corpus/okf` (333 `.md` files there, 0 skipped):

    mechanism_family  seven values, tag count == field count for all seven
    terminus_kind     psychiatric  field 212, tag  81
                      sud          field  52, tag  48
                      dual-diagnosis     4,        4

So a tag filter shows **81 of the 212** documents of the largest branch, silently. The
field is what the corpus actually asserts; the tag is a label that was not always

were the only handle available and proposed an `all`/`any` tag mode on that basis. The
measurement above is why that is not what was built.

An intersection needs no special mode here. `treatment-toxicity × sud` is two field
equalities, which is the same code path as one.

The filter expression
---------------------
``"terminus_kind=sud,mechanism_family=treatment-toxicity"`` — comma between constraints,
`=` inside each. Splitting on a comma is safe for the same reason it is safe everywhere
else in `okf.py`: no field value in this bundle contains one.

**One constraint per key.** The expression is a mapping, so `"tags=a,tags=b"` cannot be
written; the second silently replaces the first, and that is reported as an error rather
than allowed. Several values of one key is what the `tags` argument already does.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def parse_field_filter(raw: str) -> dict[str, str]:
    """Read the filter expression.

    Args:
        raw: ``"terminus_kind=sud,mechanism_family=treatment-toxicity"``. Empty or all
            whitespace gives an empty filter, which matches everything.

    Returns:
        Key to value, both stripped. Case is preserved here and ignored when comparing;
        the caller may want to echo back what was asked for.

    Raises:
        ValueError: A piece with no ``=``, an empty key, an empty value, or a key given
            twice. All four are reported rather than guessed at, because each of them
            silently narrows to something the caller did not ask for.
    """
    wanted: dict[str, str] = {}
    for piece in (p.strip() for p in raw.split(",")):
        if not piece:
            continue
        key, sep, value = piece.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key or not value:
            raise ValueError(f"filter piece is not 'key=value': {piece!r}")
        if key in wanted:
            raise ValueError(
                f"field {key!r} constrained twice ({wanted[key]!r} then {value!r}); "
                f"a filter holds one value per field — use `tags` for several"
            )
        wanted[key] = value
    return wanted


def _as_strings(value: Any) -> list[str]:
    """The values a front matter entry offers for comparison.

    A YAML entry is a scalar or a list, and `tags:` is routinely a list. Returning both
    shapes as a list is what lets one comparison serve both, without the caller having
    to know which shape a given key happens to have in a given bundle.
    """
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(v).strip() for v in value]
    return [str(value).strip()]


def matches(doc_fields: Mapping[str, Any], wanted: Mapping[str, str]) -> bool:
    """Does one document satisfy every constraint?

    Args:
        doc_fields: That document's front matter, as parsed.
        wanted: The output of `parse_field_filter`.

    Returns:
        True when every key is present on the document and its value matches. A key the
        document does not carry is a **miss**, never a pass: this filter exists to name
        a branch, and a document with no `terminus_kind` is not in any of them.
        Comparison is case-folded, so `SUD` and `sud` are the same branch.
    """
    for key, value in wanted.items():
        if key not in doc_fields:
            return False
        target = value.casefold()
        if not any(v.casefold() == target for v in _as_strings(doc_fields[key])):
            return False
    return True


def merge_locked(locked: Mapping[str, str], asked: Mapping[str, str]) -> dict[str, str]:
    """One filter from the branch a run is confined to and the one a caller wrote.

    Args:
        locked: the confinement, from outside the caller's reach.
        asked: what the caller passed. May narrow further inside the branch — a second
            key, or the same key with the same value — and may not leave it.

    Returns:
        Both sets of constraints together.

    Raises:
        ValueError: the caller asked for a different value of a key the lock holds. That
            is reported rather than silently overruled in either direction: honouring it
            would let a run reach outside its branch, and dropping it would answer a
            question the caller did not ask while looking like a successful call.
    """
    merged = dict(locked)
    for key, value in asked.items():
        if key in merged:
            if merged[key].casefold() != value.casefold():
                raise ValueError(
                    f"field {key!r} is locked to {merged[key]!r} for this run; "
                    f"{value!r} is outside it"
                )
            continue   # the same constraint written twice — the lock's spelling stands
        merged[key] = value
    return merged


def values_for(all_fields: Iterable[Mapping[str, Any]], key: str) -> list[str]:
    """Every value that `key` actually takes across the bundle, sorted.

    For the message handed back when a filter matches nothing. "The search found
    nothing" and "no document is filed that way" are different facts, and an agent that
    cannot tell them apart will either retry a query that cannot succeed or abandon one
    that can. `okf_search` already draws this distinction for a mistyped `domain`.
    """
    seen: set[str] = set()
    for fields in all_fields:
        if key in fields:
            seen.update(v for v in _as_strings(fields[key]) if v)
    return sorted(seen)
