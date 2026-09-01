# SOURCE: PORTED FROM afc-forge — NOT sandbox-authored code.
#   upstream: shared/afc-forge/ade_forge/tools/impl/matcher.py (490 lines)
# --- PORT NOTE (memstara) -------------------------------------
# This file is a port of afc-forge `ade_forge/tools/impl/matcher.py` (490 lines)
# and is byte-identical to upstream apart from the three edits listed below.
#
# Allowed edits (these three only):
#   1. the 5 local import lines -> memstara.matcher.*
#   2. the CLI hint in __init__'s shape-mismatch message
#   3. the CLI hint in from_catalog's stale-matrix message
#
# The prose below this banner is UPSTREAM'S OWN TEXT, kept verbatim. Where it
# says "FE_Demo2" or cites a "§6.x" rule, those are afc-forge's references to
# its own predecessor and design notes, not this sandbox's. Rewriting them to
# say "afc-forge" would read better and would also add diff lines that are not
# on the allowed list, which is how a checkable port stops being checkable.
#
# Sandbox glue (the lru_cache singleton, MCP wrappers) does NOT go here. The
# moment it does, "identical to afc-forge" stops being checkable with a diff.
# It goes in src/memstara/matcher/service.py.
# -------------------------------------------------------------------------
"""The matcher — a concept an agent can say, mapped to feature keys it can request.

Ported from FE_Demo2 `tools/impl/matcher.py`. The mechanism is unchanged: rank the
whole catalog by cosine over `match_text`, cut at a floor, and hand back
`feature_name` **verbatim** — it is the exact downstream column key, and a retyped
name is a feature silently lost.

**The contract is PICK-THE-GROUP, not pick-one** (§6.7.1). A concept names a group:
*CD4 count* means `CD4`, `CD4 ABS #` and `CD4:CD8`; *race* means every level this
cohort records. The matcher's job is to make the group **visible**; the agent's job
is to **judge** it. That division is forced by measurement, not taste — the false
friends sit *inside* the top ranks (`HEMOGLOBIN` scores 0.9539 for *hemoglobin
A1c*, above several real A1c keys; `HDL CHOLESTEROL` is rank 3 for *LDL
cholesterol*), so no threshold or rank window separates them from real siblings. A
clinician rejects all three instantly by name. **There is therefore no lexical or
name-similarity cull anywhere in this module**: within nominated groups, the most
string-identical pair measured (`LYMPHOCYTES ABSOLUTE COUNT` ↔ `ABSOLUTE LYMPHS`)
correlated **+0.069**. Collinearity belongs to the Statistician, which is the only
agent that can see the data.

Four generalizations of the port, each covering a defect measured in FE_Demo2:

1. **Code injection is parameterized by the declared vocabulary** (§6.7.5), never by
   an ICD-10 literal — see `vocab.py`. Query and catalog key pass through the same
   normalizer, so `E119` and `E11.9` are one lookup; a token that is code-shaped in
   some vocabulary and resolves in none comes back **empty with a reason** rather
   than as a cosine ranking of look-alikes.
2. **Injected hits do not share the agent-facing `top_k` budget.** A root
   prefix-matches every child at one identical score, so a ranked cut truncates the
   family arbitrarily (`E11` surfaced 8 children, tie broken by catalog order).
3. **The adaptive one-hot family window** (§6.7.1) — a flat `top_k` cannot serve a
   34-level family and a 2-level one at once, and the truncation is not cosmetic:
   *race* showed 5 of 11+ above-floor levels, hiding `HISPANIC OR LATINO` at rank 7.
4. **The encoder is injected, never imported.** Every test here runs on a
   deterministic fake, and no CI job downloads 1.3 GB to check a ranking rule.

**Structure only, never patient statistics** (§6.7.1, §13). Everything this module
reads off the catalog — `feature_name`, `feature_type`, source column, encode kind,
family membership — is structure. No prevalence, no coverage, no distribution. That
line is what lets a data-blind agent use this tool at all.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from memstara.matcher.config import RunConfig
from memstara.matcher import catalog as catalog_mod
from memstara.matcher import vocab as vocab_mod
from memstara.matcher.catalog import CatalogEntry
from memstara.matcher.embedder import (
    Encoder,
    embed_catalog,
    embeddings_stale,
    l2_normalize,
    load_embeddings,
)

#: Score given to a code that resolves to a catalog key exactly, and to one that
#: resolves as a declared parent of it. Ported: definitional matches, not cosines.
EXACT_CODE_SCORE = 1.0
PREFIX_CODE_SCORE = 0.9

#: Ceiling on what one call returns once a one-hot family has expanded. A BLOWUP
#: GUARD, not a dial: it exists so a pathological source column cannot return
#: thousands of levels, not to choose how many levels to show. Read as
#: `max(top_k, FAMILY_CAP)`, so raising `top_k` past it never truncates.
#:
#: A shipped constant since 2026-08-24, and config before that. It never bound on
#: either FE_Demo2 cohort — the widest family measured 34 levels — which is what a
#: guard is supposed to do, and nobody ever had a catalog that needed it moved. A
#: site with a genuinely wider family raises this here; the alternative is that
#: family arriving cut in rank order rather than judged whole (§6.7.1: levels are
#: never collapsed in code).
FAMILY_CAP = 40


@dataclasses.dataclass(frozen=True)
class Match:
    """One candidate. `feature_name` is copied verbatim downstream."""

    feature_name: str
    feature_type: str
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "feature_type": self.feature_type,
            "similarity_score": round(self.similarity, 4),
        }


@dataclasses.dataclass(frozen=True)
class MatchResult:
    """What one concept resolved to — and, when it resolved to nothing, why.

    `note` is populated **only** on an empty result. "The lookup ran and found
    nothing" and "the lookup never ran because the token is a code this cohort does
    not carry" are different facts, and an agent that cannot tell them apart wastes
    its reword budget on the one rewording cannot fix.
    """

    concept: str
    matches: tuple[Match, ...] = ()
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "concept": self.concept,
            "candidates": [m.to_dict() for m in self.matches],
        }
        if self.note:
            out["note"] = self.note
        return out


class Matcher:
    """A built catalog + its embedding matrix, ready to answer concepts.

    Construct with `build` (embeds now) or `from_catalog` (loads the cached matrix).
    Both take the encoder as an argument; this class never imports one.
    """

    def __init__(
        self,
        entries: Sequence[CatalogEntry],
        embeddings: np.ndarray,
        *,
        encoder: Encoder,
        config: RunConfig | None = None,
    ) -> None:
        if embeddings.shape[0] != len(entries):
            raise ValueError(
                f"catalog/embedding mismatch: {len(entries)} entries vs "
                f"{embeddings.shape[0]} vectors. Rebuild with "
                f"`python scripts/build_matcher_cache.py`."
            )
        self.entries = tuple(entries)
        self.embeddings = np.asarray(embeddings, dtype=np.float32)
        self.encoder = encoder
        self.config = config or RunConfig()
        self._code_index = _build_code_index(self.entries)
        self._type_cache: dict[str, np.ndarray] = {}
        self._family_cache: dict[str, np.ndarray] = {}

    # -- construction ---------------------------------------------------------
    @classmethod
    def build(
        cls,
        entries: Sequence[CatalogEntry],
        *,
        encoder: Encoder,
        config: RunConfig | None = None,
    ) -> Matcher:
        matrix = embed_catalog([e.match_text for e in entries], encoder)
        return cls(entries, matrix, encoder=encoder, config=config)

    @classmethod
    def from_catalog(
        cls,
        catalog_json: str | Path,
        *,
        encoder: Encoder,
        config: RunConfig | None = None,
        fingerprint: dict[str, Any] | None = None,
    ) -> Matcher:
        """Load a built catalog and its cached matrix, refusing a stale pair.

        Passing `fingerprint` runs the catalog's own staleness guard first. A stale
        catalog does not crash on its own — it quietly matches against a vocabulary
        the cohort no longer has, which is the failure the guard exists to prevent.

        The matrix gets the same treatment against its own stamp, because the row
        count below catches only the rebuild that changes how MANY entries there
        are, never the one that changes what they SAY. Refused here rather than
        re-embedded: vectors are built once, before any run (§6.1.2), and this is
        a library entry point with no console to report a minutes-long encode on.
        """
        if fingerprint is not None:
            stale = catalog_mod.verify_catalog(catalog_json, fingerprint)
            if stale:
                raise RuntimeError(stale)
        entries = catalog_mod.load_catalog(catalog_json)
        stale_matrix = embeddings_stale(
            catalog_json,
            match_texts=[e.match_text for e in entries],
            cfg=config.embedding if config is not None else None,
        )
        if stale_matrix:
            raise RuntimeError(
                f"{stale_matrix}. Build the vectors before running: "
                f"`python scripts/build_matcher_cache.py`."
            )
        return cls(entries, load_embeddings(catalog_json), encoder=encoder, config=config)

    # -- the public surface ---------------------------------------------------
    def match(
        self,
        concept: str,
        *,
        feature_type: str | None = None,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> MatchResult:
        return self.match_many(
            [concept], feature_type=feature_type, top_k=top_k, threshold=threshold
        )[0]

    def match_many(
        self,
        concepts: Sequence[str],
        *,
        feature_type: str | None = None,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> list[MatchResult]:
        """Resolve a batch of concepts in one encoder pass.

        Batched because the agent-facing tool is batched: one `match_concepts([...])`
        carrying every concept, not one call per concept (§6.14 — the round trip, not
        the encoder, is what a turn pays for).
        """
        cfg = self.config.matcher
        k = cfg.top_k if top_k is None else top_k
        floor = cfg.sim_threshold if threshold is None else threshold

        cleaned = [(c or "").strip() for c in concepts]
        # Code-shaped concepts still take the cosine path as well — an ICD-10 root
        # should surface the English descriptions of its children too — so every
        # non-empty concept is embedded, in one call.
        to_embed = [c for c in cleaned if c]
        vectors = l2_normalize(np.asarray(self.encoder(to_embed))) if to_embed else np.zeros((0, 1))
        by_text = {text: vectors[i] for i, text in enumerate(to_embed)}

        return [
            self._match_one(c, by_text.get(c), feature_type=feature_type, top_k=k, threshold=floor)
            for c in cleaned
        ]

    # -- one concept ----------------------------------------------------------
    def _match_one(
        self,
        concept: str,
        query_vector: np.ndarray | None,
        *,
        feature_type: str | None,
        top_k: int,
        threshold: float,
    ) -> MatchResult:
        if not concept or query_vector is None:
            return MatchResult(concept, (), note="no concept was given, so nothing was looked up")

        # 1) Code injection, parameterized by the declared vocabulary (§6.7.5).
        recognized = vocab_mod.recognize(concept)
        injected: dict[int, float] = {}
        if recognized:
            injected = self._inject_code(concept, recognized)
            if not injected:
                note = self._unresolved_code_note(concept, recognized)
                return MatchResult(concept, (), note=note)

        # 2) Full-catalog cosine. Ranking over the whole catalog rather than a
        #    lexical shortlist is what lets a synonym with zero string overlap match
        #    ("high blood pressure" -> hypertension); it is one (n x d) @ (d,) matmul.
        with np.errstate(all="ignore"):  # silence spurious Accelerate warnings
            cos = self.embeddings @ query_vector

        pool = self._type_indices(feature_type) if feature_type is not None else None
        ranked_cosine = self._rank_cosine(cos, pool, top_k=top_k, threshold=threshold)

        # 3) Injected hits are exempt from `top_k` (§6.7.5 property 3): a root
        #    prefix-matches every child at one identical score, so a ranked cut would
        #    truncate the family in catalog order rather than by any judgment.
        kept = [
            (i, s)
            for i, s in injected.items()
            if feature_type is None or self.entries[i].feature_type == feature_type
        ]
        seen = {i for i, _ in kept}
        ranked_cosine = [(i, s) for i, s in ranked_cosine if i not in seen]

        # 4) The adaptive one-hot family window. Skipped when the query is
        #    type-scoped, which keeps a rollup expander's call byte-identical to the
        #    same call with this step removed.
        if feature_type is None:
            ranked_cosine = self._expand_onehot_family(
                kept + ranked_cosine, ranked_cosine, cos, top_k=top_k, threshold=threshold
            )

        ranked = sorted(
            kept + ranked_cosine, key=lambda t: (-t[1], self.entries[t[0]].feature_name)
        )
        matches = tuple(
            Match(
                feature_name=self.entries[i].feature_name,
                feature_type=self.entries[i].feature_type,
                similarity=float(s),
            )
            for i, s in ranked
        )
        if not matches:
            return MatchResult(
                concept,
                (),
                note=(
                    "nothing in this cohort's catalog was close enough to this concept. "
                    "Reword it — a more common clinical phrasing, the generic drug name, "
                    "the measurement rather than the syndrome — or record that this cohort "
                    "does not carry it."
                ),
            )
        return MatchResult(concept, matches)

    # -- the pieces -----------------------------------------------------------
    def _rank_cosine(
        self,
        cos: np.ndarray,
        pool: np.ndarray | None,
        *,
        top_k: int,
        threshold: float,
    ) -> list[tuple[int, float]]:
        """Prefilter, floor, then cut at `top_k`.

        When scoped to a `feature_type` the prefilter ranks **within that type's
        rows**; otherwise off-type neighbors eat the budget and a genuine in-type hit
        past the cut is lost — the dx-expander leak, where meds and labs near a
        diagnosis concept crowded out ICD-10 codes.
        """
        width = max(top_k * 4, 50)
        if pool is None:
            if cos.size == 0:
                return []
            n = min(cos.size, width)
            top = np.argpartition(-cos, n - 1)[:n]
        elif pool.size:
            n = min(pool.size, width)
            top = pool[np.argpartition(-cos[pool], n - 1)[:n]]
        else:
            return []
        scored = [(int(i), float(cos[int(i)])) for i in top]
        scored = [(i, s) for i, s in scored if s >= threshold]
        scored.sort(key=lambda t: (-t[1], self.entries[t[0]].feature_name))
        return scored[:top_k]

    def _expand_onehot_family(
        self,
        ranked_all: list[tuple[int, float]],
        ranked_cosine: list[tuple[int, float]],
        cos: np.ndarray,
        *,
        top_k: int,
        threshold: float,
    ) -> list[tuple[int, float]]:
        """Surface a categorical's whole family when one of its levels is in play.

        A demographic entry is one *level* of a closed family keyed by its source
        column, and the families are wildly uneven — `RACE_1` 34 levels, SEX 2 — so
        no flat `k` serves both. Sizing the window from the family itself is what
        makes it cohort-agnostic.

        Keyed on the highest-ranked **categorical**, not strictly rank 1: *tobacco
        use* ranks an ICD-10 code above `TOBACCO_LAST_STATUS`, and a rank-1 trigger
        would leave that family half-shown. Exactly one family expands, so
        *ethnicity* pulls `ETHNIC_GROUP`'s levels rather than also `RACE_1`'s.

        Scanning the full similarity vector rather than the prefiltered shortlist is
        deliberate: a legitimate sibling level can rank below the prefilter cut and
        still clear the floor.

        **Levels are never collapsed in code.** An agent asked for *race* may
        deliberately take only the minority levels, because those populations face
        documented barriers in care — that is a clinical claim the Critic reviews, so
        the whole family is shown and the argument is left to the agent.
        """
        anchor = next(
            (
                self.entries[i]
                for i, _ in sorted(ranked_all, key=lambda t: -t[1])
                if self.entries[i].encode_kind == "categorical" and self.entries[i].source_col
            ),
            None,
        )
        if anchor is None:
            return ranked_cosine

        seen = {i for i, _ in ranked_all}
        siblings = [
            (int(i), float(cos[int(i)]))
            for i in self._family_indices(anchor.source_col)
            if int(i) not in seen and float(cos[int(i)]) >= threshold
        ]
        if not siblings:
            return ranked_cosine
        merged = sorted(
            ranked_cosine + siblings,
            key=lambda t: (-t[1], self.entries[t[0]].feature_name),
        )
        # `max` of the two, so raising `top_k` past the guard never truncates.
        return merged[: max(top_k, FAMILY_CAP)]

    def _inject_code(self, concept: str, recognized: Sequence[str]) -> dict[int, float]:
        """Exact (1.0) and declared-parent (0.9) code hits, in the DECLARED systems only.

        Prefix matching is gated on `vocab.hierarchical` because `startswith` is a
        parent-of relation only where the string carries the hierarchy. A
        LOINC-declared catalog is exact-match-only — `2160-0` and `2159-2` are
        neighbors in issue order and nothing else — and that is a complete
        capability rather than a degraded one (§6.7.5).
        """
        out: dict[int, float] = {}
        for system, index in self._code_index.items():
            if system not in recognized:
                continue
            vocab = vocab_mod.VOCABULARIES[system]
            q = vocab.normalize(concept)
            for i in index.get(q, ()):
                out[i] = EXACT_CODE_SCORE
            if vocab.hierarchical:
                for code, rows in index.items():
                    if code != q and code.startswith(q):
                        for i in rows:
                            out[i] = max(out.get(i, 0.0), PREFIX_CODE_SCORE)
        return out

    def _unresolved_code_note(self, concept: str, recognized: Sequence[str]) -> str:
        """Why a code-shaped token returned nothing — the reason IS the answer.

        Never fall through to cosine here. `J05AR` (an ATC class) handed to an
        ICD-10 catalog returns `J00`, `J03.90`, `J06.0`, `J01.01` — respiratory
        diagnoses matched on the leading letter, every one above the floor. Empty
        with a reason routes into the agent's existing reword/abandon loop; a
        confident wrong ranking does not.
        """
        declared = sorted(self._code_index)
        if declared:
            where = "this cohort's catalog is coded in " + ", ".join(declared)
        else:
            where = "this cohort's catalog declares no coding system at all"
        return (
            f"{concept!r} is written like a code in {', '.join(recognized)}, and {where}. "
            "No entry matches it, and a ranking of codes that merely look similar would be "
            "worse than nothing. Name the concept in clinical English instead — and if you "
            "meant something whose ordinary name only looks like a code, spell it out "
            "(`vitamin B12` rather than `B12`)."
        )

    def _type_indices(self, feature_type: str) -> np.ndarray:
        if feature_type not in self._type_cache:
            self._type_cache[feature_type] = np.fromiter(
                (i for i, e in enumerate(self.entries) if e.feature_type == feature_type),
                dtype=np.int64,
            )
        return self._type_cache[feature_type]

    def _family_indices(self, source_col: str) -> np.ndarray:
        """Row indices of one closed categorical family — pure catalog structure."""
        if source_col not in self._family_cache:
            self._family_cache[source_col] = np.fromiter(
                (
                    i
                    for i, e in enumerate(self.entries)
                    if e.encode_kind == "categorical" and e.source_col == source_col
                ),
                dtype=np.int64,
            )
        return self._family_cache[source_col]


def _build_code_index(entries: Iterable[CatalogEntry]) -> dict[str, dict[str, list[int]]]:
    """system -> normalized code -> catalog rows, built from what the cohort DECLARES.

    Normalizing here with the same function the query will use is the whole fix for
    the `E119` / `E11.9` defect: one written form of a code cannot resolve while
    another falls through to cosine, because neither side ever sees a written form.
    """
    index: dict[str, dict[str, list[int]]] = {}
    for i, entry in enumerate(entries):
        vocab = vocab_mod.vocabulary(entry.coding_system)
        if vocab is None:
            continue
        code = vocab.normalize(entry.key or entry.feature_name)
        if code:
            index.setdefault(vocab.system, {}).setdefault(code, []).append(i)
    return index
