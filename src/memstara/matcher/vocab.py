# SOURCE: PORTED FROM afc-forge — NOT sandbox-authored code.
#   upstream: afc-forge/ade_forge/tools/impl/vocab.py (260 lines)
#   The only edit is at line ~43: one import is replaced by the four-line
#   function it named, inlined with its table. That block carries its own
#   PORT NOTE. Everything else is byte-identical to upstream.
#
#   The docstring below is UPSTREAM'S OWN TEXT, kept verbatim — "FE_Demo2" and
#   the "§6.x" citations are afc-forge's references to its own predecessor and
#   design notes, not this sandbox's.
"""Coding vocabularies — one recognizer, normalizer and root relation per system."""

from __future__ import annotations

import dataclasses
import re

# --- PORT NOTE (memstara) -------------------------------------
# Upstream (afc-forge) this line read:
#     from ade_forge.leakage.rules import canonical_system
# That one import executes `ade_forge/leakage/__init__`, which pulls in
# `leakage.verify` -> `cohorts.descriptor`. The function itself is a four-line
# dict lookup, so it is inlined here together with its table (rules.py:65-81).
# Apart from this block the file is byte-identical to upstream.
_SYSTEM_ALIASES: dict[str, str] = {
    "icd10": "ICD-10-CM",
    "icd-10": "ICD-10-CM",
    "icd10cm": "ICD-10-CM",
    "icd-10-cm": "ICD-10-CM",
    "icd9": "ICD-9-CM",
    "icd-9-cm": "ICD-9-CM",
    "snomed": "SNOMED-CT",
    "snomed-ct": "SNOMED-CT",
    "rxnorm": "RxNorm",
    "ndc": "NDC",
    "cpt": "CPT",
    "hcpcs": "HCPCS",
    "loinc": "LOINC",
    "atc": "ATC",
    "none": "none",
}


def canonical_system(system: str | None) -> str | None:
    """Ported verbatim from afc-forge `ade_forge/leakage/rules.py:93-96`."""
    if system is None:
        return None
    return _SYSTEM_ALIASES.get(system.strip().lower(), system.strip())


# --- end PORT NOTE --------------------------------------------------------

__all__ = [
    "Vocabulary",
    "canonical_system",
    "known_systems",
    "normalize",
    "recognize",
    "root",
    "vocabulary",
]


@dataclasses.dataclass(frozen=True)
class Vocabulary:
    """One coding system's three declared properties."""

    system: str
    #: Accepts a token written in this vocabulary, in any of its spellings. Used
    #: only to decide whether the code path applies — never to rank.
    recognizer: re.Pattern[str]
    #: Characters removed before comparison, on BOTH the query and the catalog key.
    separators: str = ".- \t"
    #: Length of the parent prefix, on the normalized (separator-free) form.
    #: `None` = this vocabulary declares no hierarchy: no families, no prefix
    #: injection. Never guess one.
    root_len: int | None = None
    #: Codes whose root runs one character longer. ICD-9's external-cause `E`
    #: series is the only member and it is a real property of that vocabulary:
    #: `E812` is the category, `E81` names nothing.
    long_root_prefixes: tuple[str, ...] = ()
    #: Plain English, shown when a run has to explain why a vocabulary produced no
    #: families. "No hierarchy" is a finding a user should be able to read.
    hierarchy_note: str = ""

    def normalize(self, code: str) -> str:
        out = str(code).upper()
        for ch in self.separators:
            out = out.replace(ch, "")
        return out.strip()

    def matches(self, token: str) -> bool:
        return bool(self.recognizer.fullmatch(token.strip().upper()))

    @property
    def hierarchical(self) -> bool:
        return self.root_len is not None

    def root(self, code: str) -> str | None:
        """The declared parent of `code`, or `None` where none is declared."""
        if self.root_len is None:
            return None
        norm = self.normalize(code)
        n = self._root_len(norm)
        return norm[:n] if len(norm) > n else norm

    def sibling_root(self, code: str) -> str | None:
        """One level BELOW `root()` — the finest grouping whose members are one idea."""
        if self.root_len is None:
            return None
        norm = self.normalize(code)
        n = self._root_len(norm) + 1
        return norm[:n] if len(norm) > n else None

    def _root_len(self, normalized: str) -> int:
        return (
            self.root_len + 1  # type: ignore[operator]
            if normalized.startswith(self.long_root_prefixes)
            else self.root_len  # type: ignore[return-value]
        )


#: The declared vocabularies, keyed by the descriptor's canonical spelling
#: (`CodingSystem` in `cohorts/descriptor.py`). Adding one is a data edit here,
#: never a branch at a call site.
VOCABULARIES: dict[str, Vocabulary] = {
    "ICD-10-CM": Vocabulary(
        system="ICD-10-CM",
        # `U` is included: U07.1 (COVID-19) is a live ICD-10-CM code. The third
        # character is `[0-9AB]` because that is the real shape of an ICD-10-CM
        # category (C4A, C7B, D3A, M1A, Z3A) — and a recognizer wider than the
        # vocabulary is not a harmless over-accept here: `A1C` and `B12` are
        # clinical concepts an agent may name bare, and a code-shaped token that
        # resolves nowhere is REFUSED (property 2), not re-ranked. Widening this
        # class costs a wasted turn on a query that should simply have matched.
        recognizer=re.compile(r"[A-Z][0-9][0-9AB](\.?[0-9A-Z]{1,4})?"),
        root_len=3,
        hierarchy_note=(
            "the 3-character category is the parent — E11.22 rolls to E11.2 to E11, "
            "and each level is a real clinical grouping"
        ),
    ),
    "ICD-9-CM": Vocabulary(
        system="ICD-9-CM",
        recognizer=re.compile(r"([0-9]{3}(\.[0-9]{1,2})?|[EV][0-9]{3}(\.[0-9]{1,2})?)"),
        root_len=3,
        long_root_prefixes=("E",),
        hierarchy_note="the 3-character category is the parent (4 for the E series)",
    ),
    "ATC": Vocabulary(
        system="ATC",
        recognizer=re.compile(r"[A-V][0-9]{2}([A-Z]{1,2}([0-9]{2})?)?"),
        #: Level 4 — the chemical subgroup, which is the level the medication axis
        #: rolls up on (§6.7.2).
        root_len=5,
        hierarchy_note="the 5-character level-4 chemical subgroup is the parent (J05AR01 -> J05AR)",
    ),
    "SNOMED-CT": Vocabulary(
        system="SNOMED-CT",
        recognizer=re.compile(r"[0-9]{6,18}"),
        hierarchy_note=(
            "concept ids are opaque integers — the hierarchy lives in the relationship "
            "file, not in the string, so no families are derived without that artifact"
        ),
    ),
    "RxNorm": Vocabulary(
        system="RxNorm",
        recognizer=re.compile(r"[0-9]{1,8}"),
        hierarchy_note=(
            "RXCUIs are opaque integers; ingredient/brand relationships come from the "
            "RxNorm release, not from the code"
        ),
    ),
    "NDC": Vocabulary(
        system="NDC",
        recognizer=re.compile(r"[0-9]{4,5}-?[0-9]{3,4}-?[0-9]{1,2}"),
        hierarchy_note=(
            "labeler-product-package segments vary in width (4-4-2, 5-3-2, 5-4-1, 5-4-2), "
            "so no fixed prefix names the product"
        ),
    ),
    "CPT": Vocabulary(
        system="CPT",
        recognizer=re.compile(r"[0-9]{4}[0-9A-Z]"),
        hierarchy_note=(
            "numeric blocks are only a proxy for clinical category — the real grouping "
            "needs a released CCS/CPT category artifact"
        ),
    ),
    "HCPCS": Vocabulary(
        system="HCPCS",
        recognizer=re.compile(r"[A-V][0-9]{4}"),
        hierarchy_note="letter series are administrative, not clinical, groupings",
    ),
    "LOINC": Vocabulary(
        system="LOINC",
        recognizer=re.compile(r"[0-9]{1,5}-?[0-9]"),
        hierarchy_note=(
            "a LOINC code is a sequence number plus a check digit — 2160-0 and 2159-2 are "
            "neighbors in issue order and nothing else. Real grouping (Parts, the "
            "Multiaxial Hierarchy, CLASS) needs a released LOINC artifact"
        ),
    ),
}


def known_systems() -> tuple[str, ...]:
    return tuple(VOCABULARIES)


def vocabulary(system: str | None) -> Vocabulary | None:
    """The declared vocabulary, or `None` for free text / an unknown spelling."""
    canon = canonical_system(system)
    if canon is None or canon == "none":
        return None
    return VOCABULARIES.get(canon)


def normalize(system: str | None, code: str) -> str:
    """Normalize with the vocabulary's own rule; separator-strip + upper otherwise.

    The fallback matters: a catalog whose `coding_system` this build does not know
    still gets consistent treatment on both sides of the comparison, which is the
    property that makes `E119` and `E11.9` the same lookup.
    """
    vocab = vocabulary(system)
    if vocab is not None:
        return vocab.normalize(code)
    return re.sub(r"[.\-\s]", "", str(code)).upper()


def recognize(token: str) -> tuple[str, ...]:
    """Every KNOWN vocabulary whose recognizer accepts `token`, declared or not.

    Answering over all of them is what lets an out-of-vocabulary code be refused
    (§6.7.5 property 2): `J05AR` is ATC-shaped, so a catalog that declares only
    ICD-10 can say "that is a code and I do not hold it" instead of returning a
    cosine ranking of respiratory diagnoses that share its leading letter.
    """
    t = token.strip().upper()
    if not t:
        return ()
    return tuple(name for name, vocab in VOCABULARIES.items() if vocab.matches(t))


def root(system: str | None, code: str) -> str | None:
    """The declared parent code, or `None` where the vocabulary declares no hierarchy."""
    vocab = vocabulary(system)
    return vocab.root(code) if vocab is not None else None
