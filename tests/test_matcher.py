# SOURCE: PORTED FROM afc-forge — NOT sandbox-authored code.
#   upstream: shared/afc-forge/tests/test_matcher.py (495 lines)
#   Only the import paths differ. These 21 tests are the evidence that this
#   matcher behaves as afc-forge's does; see the PORT NOTE below.
"""The matcher — PICK-THE-GROUP, the adaptive family window, and code injection.

Every test runs on `conftest.bag_of_words_encoder`: cosine is token-set overlap,
so the geometry is not the real encoder's and each test states its own floor.
That is the point of injecting the encoder (§6.7.1) — the ranking *rules* are
what is under test, and none of them needs 1.3 GB of weights to check.

The fixtures reproduce measured FE_Demo2 catalog shapes: a false friend sitting
inside the top ranks, two near-identical component names, an 11-level demographic
family beside a smaller one, and a dx group whose `match_text` is `desc (code)`.
"""

# --- PORT NOTE (memstara) -------------------------------------
# Ported from afc-forge `tests/test_matcher.py`. The ONLY edits are the
# import paths (`ade_forge.tools.impl.*` -> `matcher_impl.*`). Assertions,
# fixtures and docstrings are untouched: an edited test no longer proves that
# this matcher behaves the way afc-forge's does, which is the whole point of
# running them here.
# -------------------------------------------------------------------------


from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pytest

from matcher_impl.config import EmbeddingConfig, RunConfig
from matcher_impl import catalog as catalog_mod
from matcher_impl import matcher as matcher_mod
from matcher_impl.catalog import CatalogEntry
from matcher_impl.embedder import (
    embeddings_path,
    embeddings_stale,
    embeddings_stamp_path,
    save_embeddings,
)
from matcher_impl.matcher import Matcher

#: pure ranking over a stubbed encoder (§9.2 layer 1).
pytestmark = pytest.mark.unit

# The fake encoder's overlap geometry lands well below the ported 0.88 floor,
# which was calibrated on real embeddings. Each fixture states the floor its own
# ranking question needs; none of them means anything outside this file.
LOW_FLOOR = 0.3


def _cfg(**matcher_kw: object) -> RunConfig:
    return RunConfig(matcher={"sim_threshold": LOW_FLOOR, **matcher_kw})  # type: ignore[arg-type]


def _lab(name: str) -> CatalogEntry:
    return CatalogEntry(
        feature_name=name,
        feature_type="lab",
        match_text=name,
        encode_kind="lab_numeric",
        source_col="LAB_COMPONENT",
        key=name,
        value_col="LAB_VALUE",
        group="labs",
    )


def _level(col: str, label: str, level: str) -> CatalogEntry:
    return CatalogEntry(
        feature_name=f"{col}={level}",
        feature_type="demographic",
        match_text=f"{label}: {level}",
        encode_kind="categorical",
        source_col=col,
        key=level,
    )


def _dx(code: str, desc: str) -> CatalogEntry:
    return CatalogEntry(
        feature_name=code,
        feature_type="diagnosis",
        match_text=f"{desc} ({code})",
        encode_kind="list_presence",
        source_col="DX_CODE_LIST",
        key=catalog_mod.norm_upper(code),
        normalize="upper_strip",
        coding_system="ICD-10-CM",
        group="dx",
    )


def _loinc(code: str, desc: str) -> CatalogEntry:
    return CatalogEntry(
        feature_name=code,
        feature_type="lab",
        match_text=f"{desc} ({code})",
        encode_kind="lab_numeric",
        source_col="LAB_LOINC_LIST",
        key=catalog_mod.norm_upper(code),
        normalize="upper_strip",
        value_col="LAB_VALUE_LIST",
        coding_system="LOINC",
        group="labs",
    )


LAB_ENTRIES = [
    _lab("HEMOGLOBIN A1C"),
    _lab("HEMOGLOBIN A1C POC"),
    _lab("HGB A1C"),
    _lab("HEMOGLOBIN"),  # the false friend — a different analyte entirely
    _lab("LYMPHOCYTES ABSOLUTE COUNT"),
    _lab("ABSOLUTE LYMPHS"),  # the +0.069 pair: near-identical name, uncorrelated
    _lab("SERUM CREATININE"),
]

#: 11 levels on one column, 4 on another — the unevenness is the point (§6.7.1).
RACE_LEVELS = [
    "WHITE",
    "ASIAN",
    "OTHER",
    "UNKNOWN",
    "DECLINED",
    "BLACK OR AFRICAN AMERICAN",
    "HISPANIC OR LATINO",
    "TWO OR MORE RACES",
    "AMERICAN INDIAN OR ALASKA NATIVE",
    "MIDDLE EASTERN OR NORTH AFRICAN",
    "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
]
DEMO_ENTRIES = [
    *[_level("RACE_1", "Race", lvl) for lvl in RACE_LEVELS],
    *[
        _level("MOTHER_RACE", "Maternal race", lvl)
        for lvl in ("WHITE", "ASIAN", "OTHER", "UNKNOWN")
    ],
    *[_level("ETHNIC_GROUP", "Ethnicity", lvl) for lvl in ("HISPANIC OR LATINO", "NOT HISPANIC")],
]

DX_ENTRIES = [
    _dx("E11.9", "Type 2 diabetes mellitus without complications"),
    _dx("E11.21", "Type 2 diabetes mellitus with diabetic nephropathy"),
    _dx("E11.22", "Type 2 diabetes mellitus with diabetic chronic kidney disease"),
    _dx("E11.65", "Type 2 diabetes mellitus with hyperglycemia"),
    _dx("E10.9", "Type 1 diabetes mellitus without complications"),
    _dx("I10", "Essential primary hypertension"),
    _dx("N18.3", "Chronic kidney disease stage 3"),
]

LOINC_ENTRIES = [
    _loinc("2160-0", "Creatinine serum or plasma"),
    _loinc("2159-2", "Creatinine urine"),
    _loinc("718-7", "Hemoglobin blood"),
]


def _matcher(entries: list[CatalogEntry], encoder, **matcher_kw: object) -> Matcher:
    return Matcher.build(entries, encoder=encoder, config=_cfg(**matcher_kw))


def _names(result) -> list[str]:
    return [m.feature_name for m in result.matches]


# ---------------------------------------------------------------------------
# PICK-THE-GROUP — the matcher makes the group visible; the agent judges it.
# ---------------------------------------------------------------------------
def test_the_false_friend_is_shown_not_culled(fake_encoder) -> None:
    """`HEMOGLOBIN` outranks a real A1c sibling, and both come back.

    This is the measured shape (`HEMOGLOBIN` 0.9539 for *hemoglobin A1c*, above
    several genuine A1c keys). No threshold and no rank window separates a false
    friend from a real sibling, because the false friend is *inside* the top
    ranks — so the matcher shows the group and the agent, who rejects it by name
    in a second, decides.
    """
    m = _matcher(LAB_ENTRIES, fake_encoder)
    names = _names(m.match("hemoglobin a1c"))

    assert names[0] == "HEMOGLOBIN A1C"
    assert {"HEMOGLOBIN A1C", "HEMOGLOBIN A1C POC", "HGB A1C", "HEMOGLOBIN"} <= set(names)
    # The false friend really does outrank a genuine sibling — the fixture is not
    # making the easy case look hard.
    assert names.index("HEMOGLOBIN") < names.index("HGB A1C")


def test_near_identical_names_are_both_returned(fake_encoder) -> None:
    """No lexical or name-similarity cull, anywhere (§6.7.1, §13).

    `LYMPHOCYTES ABSOLUTE COUNT` and `ABSOLUTE LYMPHS` are the most
    string-identical pair measured and correlate **+0.069**. Deduping by name
    would have dropped a genuinely independent feature. Collinearity is the
    Statistician's, and only the Statistician can see the data.
    """
    m = _matcher(LAB_ENTRIES, fake_encoder)
    names = _names(m.match("absolute lymphocyte count", threshold=0.35))
    assert {"LYMPHOCYTES ABSOLUTE COUNT", "ABSOLUTE LYMPHS"} <= set(names)


def test_candidates_carry_structure_only(fake_encoder) -> None:
    """The payload is name, type, score — never a patient statistic (§6.7.1, §13).

    A prevalence or a coverage count riding along here would put a distribution
    in front of every data-blind agent in the roster, which is the leakage the
    binding-level invariant exists to prevent.
    """
    m = _matcher(LAB_ENTRIES, fake_encoder)
    payload = m.match("hemoglobin a1c").to_dict()
    assert set(payload) == {"concept", "candidates"}
    for candidate in payload["candidates"]:
        assert set(candidate) == {"feature_name", "feature_type", "similarity_score"}


# ---------------------------------------------------------------------------
# The adaptive one-hot family window.
# ---------------------------------------------------------------------------
def test_the_whole_family_surfaces_past_top_k(fake_encoder) -> None:
    """A flat `k` cannot serve an 11-level family and a 2-level one at once.

    *race* showed 5 of 11+ above-floor levels in FE_Demo2, hiding
    `HISPANIC OR LATINO` at rank 7 — a truncation with a clinical cost, since a
    level an agent never sees is a level it cannot argue about.
    """
    m = _matcher(DEMO_ENTRIES, fake_encoder, top_k=5)
    names = _names(m.match("race"))

    assert set(names) == {f"RACE_1={lvl}" for lvl in RACE_LEVELS}
    assert len(names) > 5
    # Sized by the family, not by a score band: every MOTHER_RACE level clears the
    # floor and outscores six of the returned RACE_1 levels, and none is pulled in.
    # Exactly one family expands, or *ethnicity* would drag race in behind it.
    assert not any(n.startswith("MOTHER_RACE") for n in names)


def test_the_family_anchor_is_the_top_categorical_not_rank_one(fake_encoder) -> None:
    """*tobacco use* ranks an ICD-10 code first; the family must still expand.

    Keying the window on rank 1 would leave `TOBACCO_LAST_STATUS` half-shown
    whenever a coded diagnosis for the same concept scores above it — which is
    the common case, because the code carries the concept's words verbatim.
    """
    entries = [
        _dx("Z72.0", "Tobacco use"),
        *[
            _level("TOBACCO_LAST_STATUS", "Tobacco status", lvl)
            for lvl in ("NEVER", "FORMER", "CURRENT", "UNKNOWN")
        ],
    ]
    m = _matcher(entries, fake_encoder, top_k=2)
    names = _names(m.match("tobacco use"))

    assert names[0] == "Z72.0"  # rank 1 is not categorical
    assert {f"TOBACCO_LAST_STATUS={lvl}" for lvl in ("NEVER", "FORMER", "CURRENT", "UNKNOWN")} <= (
        set(names)
    )


def test_the_family_windows_blowup_guard_does_not_bind_by_default(
    fake_encoder, monkeypatch
) -> None:
    """40 guards against a pathological column; it does not choose how many to show.

    So on an ordinary family it must be invisible — an 11-level family comes back
    whole — and it may only ever cut a family genuinely wider than itself, because
    a family cut in rank order is a family the agent never judged whole (§6.7.1:
    levels are never collapsed in code).

    A shipped constant since 2026-08-24 and config before that. It never bound on
    either cohort measured, the widest family there being 34 levels, and nobody
    ever had a catalog that needed it moved. A site with a wider family raises
    `FAMILY_CAP` itself, which is what the monkeypatch below stands in for.
    """
    default = _matcher(DEMO_ENTRIES, fake_encoder, top_k=2)
    assert len(_names(default.match("race"))) == len(RACE_LEVELS)

    monkeypatch.setattr(matcher_mod, "FAMILY_CAP", 4)
    tight = _matcher(DEMO_ENTRIES, fake_encoder, top_k=2)
    assert len(_names(tight.match("race"))) == 4

    # `max(top_k, FAMILY_CAP)`: a `top_k` above the guard is never truncated by it,
    # which is why raising one knob can never silently shrink the other's answer.
    wide = _matcher(DEMO_ENTRIES, fake_encoder, top_k=9)
    assert len(_names(wide.match("race"))) == 9


def test_levels_are_never_collapsed_in_code(fake_encoder) -> None:
    """Every level is shown separately, including the ones a run may not use.

    An agent asked for *race* may deliberately take only the minority levels,
    because those populations face documented barriers in care. That is a
    clinical claim for the Critic to review, so the matcher hands over the whole
    family rather than pre-deciding it.
    """
    m = _matcher(DEMO_ENTRIES, fake_encoder, top_k=5)
    names = _names(m.match("race"))
    assert "RACE_1=NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER" in names
    assert "RACE_1=AMERICAN INDIAN OR ALASKA NATIVE" in names
    assert not any("|" in n or n.endswith("=OTHER_COMBINED") for n in names)


def test_a_type_scoped_query_skips_the_family_window(fake_encoder) -> None:
    """Rollup expanders call type-scoped, and their call stays exactly the ranked cut.

    Keeping the window off that path is what makes §6.7.3's expander byte-identical
    to the same call with this step removed — the window is an agent-facing
    affordance, not a change to what the catalog says.
    """
    m = _matcher(DEMO_ENTRIES, fake_encoder, top_k=5)
    scoped = _names(m.match("race", feature_type="demographic"))
    unscoped = _names(m.match("race"))

    assert len(scoped) == 5
    assert set(scoped) <= set(unscoped)
    assert len(unscoped) == len(RACE_LEVELS)


def test_a_type_scope_that_matches_nothing_is_empty(fake_encoder) -> None:
    m = _matcher(DEMO_ENTRIES, fake_encoder)
    result = m.match("race", feature_type="medication")
    assert result.matches == ()
    assert result.note


# ---------------------------------------------------------------------------
# Code injection, parameterized by the declared vocabulary (§6.7.5).
# ---------------------------------------------------------------------------
def test_both_spellings_of_a_code_are_one_lookup(fake_encoder) -> None:
    """`E119` and `E11.9` resolve identically — the measured FE_Demo2 defect.

    Only the dotted form was recognized; the dot-stripped form, which is how the
    catalog stores its key, fell through to cosine and returned `Z3A.19`,
    `R11.10`, `H15.009` — all above the floor, all wrong, and silently.
    """
    m = _matcher(DX_ENTRIES, fake_encoder)
    dotted = m.match("E11.9")
    stripped = m.match("E119")

    assert _names(dotted) == ["E11.9"]
    assert dotted.matches[0].similarity == pytest.approx(1.0)
    assert [x.to_dict() for x in stripped.matches] == [x.to_dict() for x in dotted.matches]


def test_injected_hits_do_not_share_the_top_k_budget(fake_encoder) -> None:
    """A root prefix-matches every child at ONE score, so a ranked cut is arbitrary.

    FE_Demo2 surfaced 8 of `E11`'s children with the tie broken by catalog order —
    a family truncated by insertion order rather than by any judgment.
    """
    m = _matcher(DX_ENTRIES, fake_encoder, top_k=2)
    result = m.match("E11")

    assert set(_names(result)) == {"E11.9", "E11.21", "E11.22", "E11.65"}
    assert len(result.matches) > 2
    assert all(x.similarity == pytest.approx(0.9) for x in result.matches)


def test_an_out_of_vocabulary_code_is_empty_with_a_reason(fake_encoder) -> None:
    """`J05AR` on an ICD-10 catalog returned J00, J03.90, J06.0 — the leading letter.

    The floor is dropped to zero here so the assertion is unambiguous: the code
    path REFUSES rather than merely scoring poorly. Empty routes into the agent's
    existing reword/abandon loop; a confident wrong ranking does not.
    """
    m = _matcher(DX_ENTRIES, fake_encoder)
    result = m.match("J05AR", threshold=0.0)

    assert result.matches == ()
    assert "ATC" in result.note and "ICD-10-CM" in result.note
    assert "English" in result.note


def test_a_hybrid_code_hint_takes_the_cosine_path_and_is_rewarded(fake_encoder) -> None:
    """15 of 296 committed concepts carried a code inside English — and it helps.

    `desc (code)` is the deliberate `match_text` shape: the parenthetical anchors
    the right chapter, which is why *'essential hypertension (I10)'* returns the
    hypertension family where the bare phrase drifts into ocular hypertension.
    """
    m = _matcher(DX_ENTRIES, fake_encoder)
    assert _names(m.match("essential hypertension (I10)"))[0] == "I10"


def test_a_vocabulary_with_no_declared_hierarchy_is_exact_match_only(fake_encoder) -> None:
    """LOINC resolves `2160-0` and refuses `216` — it does not invent a family.

    Prefix-rooting an unhierarchical vocabulary is the worse of the two available
    failures: `2160-0` and `2159-2` are neighbors in issue order, so a family
    built from them would be confident, clinically meaningless, and
    indistinguishable downstream from a real one.
    """
    m = _matcher(LOINC_ENTRIES, fake_encoder)
    assert _names(m.match("2160-0")) == ["2160-0"]

    truncated = m.match("216", threshold=0.0)
    assert truncated.matches == ()
    assert "LOINC" in truncated.note


# ---------------------------------------------------------------------------
# Empties, batching, and the artifact pair.
# ---------------------------------------------------------------------------
def test_nothing_close_enough_says_so_and_says_what_to_do(fake_encoder) -> None:
    m = _matcher(LAB_ENTRIES, fake_encoder)
    result = m.match("photosynthesis in maize", threshold=0.5)
    assert result.matches == ()
    assert "Reword" in result.note or "reword" in result.note


def test_an_empty_concept_is_distinguishable_from_a_failed_lookup(fake_encoder) -> None:
    m = _matcher(LAB_ENTRIES, fake_encoder)
    assert m.match("   ").note != m.match("photosynthesis in maize", threshold=0.5).note


def test_a_batch_is_one_encoder_pass_and_keeps_its_order(fake_encoder) -> None:
    """The agent-facing tool is batched, so the encoder is called once per turn."""
    calls: list[int] = []

    def counting(texts: Sequence[str]) -> np.ndarray:
        calls.append(len(texts))
        return fake_encoder(texts)

    m = _matcher(LAB_ENTRIES, counting)
    calls.clear()  # the build pass is not what is under test
    concepts = ["hemoglobin a1c", "", "serum creatinine", "hemoglobin a1c"]
    results = m.match_many(concepts)

    assert [r.concept for r in results] == [
        "hemoglobin a1c",
        "",
        "serum creatinine",
        "hemoglobin a1c",
    ]
    assert calls == [3]  # blanks are never embedded; a repeat is embedded once
    assert _names(results[0]) == _names(results[3])
    assert _names(results[2])[0] == "SERUM CREATININE"


def test_a_catalog_and_matrix_that_disagree_refuse_to_load(fake_encoder) -> None:
    """Silently matching against a shorter matrix is a wrong answer, not a crash."""
    matrix = np.zeros((len(LAB_ENTRIES) - 1, 8), dtype=np.float32)
    with pytest.raises(ValueError, match="catalog/embedding mismatch"):
        Matcher(LAB_ENTRIES, matrix, encoder=fake_encoder)


def test_from_catalog_round_trips_and_refuses_a_stale_pair(tmp_path, fake_encoder) -> None:
    """Two guards, not one: the catalog's fingerprint and the matrix's own stamp."""
    built = _matcher(DX_ENTRIES, fake_encoder)
    catalog_json = tmp_path / "dx.catalog.json"
    catalog_mod.save_catalog(list(DX_ENTRIES), catalog_json)
    save_embeddings(built.embeddings, catalog_json, match_texts=[e.match_text for e in DX_ENTRIES])

    fingerprint = {"cohort_sha1": "abc123", "embedding_revision": "r1"}
    catalog_mod.save_catalog_meta(list(DX_ENTRIES), catalog_json, fingerprint)

    loaded = Matcher.from_catalog(
        catalog_json, encoder=fake_encoder, config=_cfg(), fingerprint=fingerprint
    )
    assert _names(loaded.match("E11.9")) == ["E11.9"]

    with pytest.raises(RuntimeError, match="STALE"):
        Matcher.from_catalog(
            catalog_json,
            encoder=fake_encoder,
            config=_cfg(),
            fingerprint={**fingerprint, "embedding_revision": "r2"},
        )


def test_a_reworded_catalog_invalidates_its_cached_matrix(tmp_path, fake_encoder) -> None:
    """The row count sees how MANY entries changed, never what one of them SAYS.

    Same entry count, same encoder, one reworded `match_text`: every concept then
    ranks against a vector for text the catalog no longer contains, and nothing
    raises. That is what the stamp is for — the cache is reused on identity, not on
    existence.
    """
    catalog_json = tmp_path / "dx.catalog.json"
    catalog_mod.save_catalog(list(DX_ENTRIES), catalog_json)
    texts = [e.match_text for e in DX_ENTRIES]
    save_embeddings(_matcher(DX_ENTRIES, fake_encoder).embeddings, catalog_json, match_texts=texts)
    assert embeddings_stale(catalog_json, match_texts=texts) is None

    reworded = [*DX_ENTRIES[:-1], _dx("N18.3", "CKD stage 3, moderately decreased GFR")]
    assert len(reworded) == len(DX_ENTRIES)  # the row count is no help here
    catalog_mod.save_catalog(reworded, catalog_json)
    with pytest.raises(RuntimeError, match="match texts changed"):
        Matcher.from_catalog(catalog_json, encoder=fake_encoder, config=_cfg())


def test_an_unstamped_or_differently_embedded_matrix_reads_as_stale(tmp_path, fake_encoder) -> None:
    """Cannot prove identity == stale. One re-embed is cheaper than one wrong catalog."""
    catalog_json = tmp_path / "dx.catalog.json"
    catalog_mod.save_catalog(list(DX_ENTRIES), catalog_json)
    texts = [e.match_text for e in DX_ENTRIES]
    save_embeddings(_matcher(DX_ENTRIES, fake_encoder).embeddings, catalog_json, match_texts=texts)

    other = EmbeddingConfig(model="pritamdeka/S-PubMedBert-MS-MARCO", revision="deadbee")
    assert "was embedded by" in (embeddings_stale(catalog_json, match_texts=texts, cfg=other) or "")

    embeddings_stamp_path(catalog_json).unlink()  # a matrix cached before stamping
    assert "no identity stamp" in (embeddings_stale(catalog_json, match_texts=texts) or "")

    embeddings_path(catalog_json).unlink()
    assert "no cached embedding matrix" in (embeddings_stale(catalog_json, match_texts=texts) or "")
