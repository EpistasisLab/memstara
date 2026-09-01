# SOURCE: PORTED FROM afc-forge — NOT sandbox-authored code.
#   upstream: shared/afc-forge/tests/test_vocab.py (153 lines)
#   Only the import paths differ. See the PORT NOTE below.
"""The declared vocabularies — recognizers, normalizers, and the root relation.

Every case here is a measured FE_Demo2 defect or a §6.7.5 rule, not a spot check
of a regex. The three that matter most:

* one code, two spellings, one lookup (`E11.9` / `E119`);
* a code-shaped token is recognized across **all** known vocabularies, so one
  written in a system this cohort does not carry can be refused rather than
  re-ranked;
* a root is **declared**. `root_len is None` is a positive statement — this
  vocabulary's string carries no hierarchy — and the test asserts the absence.
"""

# --- PORT NOTE (memstara) -------------------------------------
# Ported from afc-forge `tests/test_vocab.py`. The ONLY edits are the
# import paths (`ade_forge.tools.impl.*` -> `matcher_impl.*`). Assertions,
# fixtures and docstrings are untouched: an edited test no longer proves that
# this matcher behaves the way afc-forge's does, which is the whole point of
# running them here.
# -------------------------------------------------------------------------


from __future__ import annotations

import pytest

from memstara.matcher import vocab

#: pure code normalization and recognition (§9.2 layer 1).
pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Normalization — the E119 / E11.9 defect.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("system", "written", "normalized"),
    [
        ("ICD-10-CM", "E11.9", "E119"),
        ("ICD-10-CM", "E119", "E119"),
        ("ICD-10-CM", " e11.9 ", "E119"),
        ("ICD-9-CM", "250.02", "25002"),
        ("LOINC", "2160-0", "21600"),
        ("NDC", "0002-8215-01", "0002821501"),
        ("ATC", "j05ar01", "J05AR01"),
    ],
)
def test_written_forms_collapse_to_one_key(system: str, written: str, normalized: str) -> None:
    assert vocab.normalize(system, written) == normalized


def test_unknown_system_still_normalizes_consistently() -> None:
    """The fallback is what makes both SIDES of a comparison agree.

    A catalog whose `coding_system` this build does not know must still get the
    same treatment on the query and on the key, or the `E119` defect reappears
    for every vocabulary added after this one.
    """
    assert vocab.normalize("ICD-11", "1A00.0") == vocab.normalize("ICD-11", "1A000")


def test_alias_spellings_resolve_to_the_same_vocabulary() -> None:
    assert vocab.vocabulary("icd10") is vocab.vocabulary("ICD-10-CM")
    assert vocab.vocabulary("none") is None
    assert vocab.vocabulary(None) is None
    assert vocab.vocabulary("ICD-11") is None  # known spelling, undeclared here


# ---------------------------------------------------------------------------
# Recognition — over every vocabulary, not just the declared ones.
# ---------------------------------------------------------------------------
def test_recognize_answers_across_vocabularies() -> None:
    """`J05AR` is ATC-shaped, and that is what lets an ICD-10 catalog refuse it."""
    assert "ATC" in vocab.recognize("J05AR")
    assert "ICD-10-CM" in vocab.recognize("E11.9")
    assert "LOINC" in vocab.recognize("2160-0")


@pytest.mark.parametrize(
    "concept",
    [
        "hemoglobin a1c",
        "chronic kidney disease",
        "essential hypertension (I10)",  # the hybrid: hint inside English
        "race",
        "A1C",  # a bare analyte name, not a code
        "T4",
        "",
    ],
)
def test_english_concepts_are_not_mistaken_for_codes(concept: str) -> None:
    """A false positive here costs a wasted turn, because refusal is the rule.

    Property 2 of §6.7.5 says a code-shaped token that resolves nowhere comes
    back empty. That makes an over-wide recognizer expensive: it converts a query
    that would have matched into a reword. `A1C` is the near miss the tightened
    recognizer buys back — an ICD-10-CM category's third character is a digit,
    `A` or `B`, never `C`.
    """
    assert vocab.recognize(concept) == ()


def test_a_genuinely_ambiguous_token_stays_ambiguous() -> None:
    """`B12` really is code-shaped, and no recognizer can rule that out.

    `B12` is a well-formed ICD-10-CM category and a well-formed ATC level-2 group;
    only a validity table — which is not what a recognizer is — could say that
    neither vocabulary assigns it. So a bare `B12` takes the code path and, when
    it resolves nowhere, is refused. That is the deliberate trade: the matcher's
    note names the recovery (`vitamin B12`), which costs one turn, where the
    alternative silently ranks look-alikes. Single-token analyte names that
    collide with a code shape should be written out.
    """
    assert set(vocab.recognize("B12")) >= {"ICD-10-CM", "ATC"}


def test_real_alphabetic_categories_are_still_recognized() -> None:
    """The tightening must not cost the categories that genuinely use letters."""
    for code in ("C4A", "C7B", "D3A", "M1A", "Z3A.19", "U07.1"):
        assert "ICD-10-CM" in vocab.recognize(code), code


# ---------------------------------------------------------------------------
# The root relation — declared, never inferred.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("system", "code", "expected"),
    [
        ("ICD-10-CM", "E11.22", "E11"),
        ("ICD-10-CM", "E119", "E11"),
        ("ICD-10-CM", "E11", "E11"),  # already a root: itself, not a truncation
        ("ICD-9-CM", "250.02", "250"),
        ("ICD-9-CM", "E812.0", "E812"),  # the E series roots one character longer
        ("ATC", "J05AR01", "J05AR"),
    ],
)
def test_declared_hierarchies_root_where_the_string_carries_them(
    system: str, code: str, expected: str
) -> None:
    assert vocab.root(system, code) == expected


@pytest.mark.parametrize("system", ["LOINC", "SNOMED-CT", "RxNorm", "NDC", "CPT", "HCPCS"])
def test_undeclared_hierarchies_yield_no_families(system: str) -> None:
    """No root means NO families — fabricating one is the worse failure (§6.7.5).

    `2160-0` and `2159-2` are neighbors in LOINC's issue order and nothing else,
    so a prefix rule here would invent confident, clinically meaningless groups
    that nothing downstream could tell from real ones.
    """
    v = vocab.vocabulary(system)
    assert v is not None
    assert not v.hierarchical
    assert v.root("2160-0") is None
    assert v.hierarchy_note, "a vocabulary with no hierarchy must say why in English"


def test_every_declared_vocabulary_explains_itself() -> None:
    for name in vocab.known_systems():
        v = vocab.vocabulary(name)
        assert v is not None and v.system == name
        assert v.hierarchy_note, f"{name} declares no hierarchy note"
