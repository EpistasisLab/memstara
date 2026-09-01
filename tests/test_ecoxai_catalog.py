# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. It tests the builder half
#   of catalog.py, which is itself sandbox code, so upstream has no counterpart.
"""The EcoXAI builder half of `catalog.py` — the fields the matcher actually reads.

The ported tests in `test_matcher.py` prove the matcher ranks the way afc-forge's
does. They say nothing about whether THIS catalog hands it entries it can work
with, and that is where the previous sandbox catalog failed silently: all 1,393
entries carried `encode_kind="passthrough"` and `source_col=""`, so the one-hot
family expander could never fire on any query.
"""

from __future__ import annotations

import pytest

from memstara.matcher.catalog import CatalogEntry, build_catalog, catalog_fingerprint
from memstara.matcher.config import RunConfig
from memstara.matcher.matcher import Matcher

pytestmark = pytest.mark.unit

LOW_FLOOR = 0.3  # the fake encoder's geometry, not the calibrated 0.88

SEX = ["CAT__SEX__Male"]
RACE = [f"CAT__RACE_ETHNICITY__{lvl}" for lvl in ("White", "Black", "Hispanic", "Other")]
TOBACCO = [f"CAT__TOBACCO_STATUS__{lvl}" for lvl in ("Never", "Former", "Current", "Unknown")]
COLUMNS = [
    "DX__I10__Essential hypertension",
    "DX__I11.0__Hypertensive heart disease with heart failure",
    "DX__IMO0001__Proprietary IMO concept",
    "MED__RITONAVIR",
    "LAB__CD4",
    "CURRENT_AGE",
    "BMI",
    *SEX,
    *RACE,
    *TOBACCO,
    "HIV_DETECTABLE",
]


def _matcher(entries, encoder, **matcher_kw):
    cfg = RunConfig(matcher={"sim_threshold": LOW_FLOOR, **matcher_kw})  # type: ignore[arg-type]
    return Matcher.build(entries, encoder=encoder, config=cfg)


def _by_name(entries) -> dict[str, CatalogEntry]:
    return {e.feature_name: e for e in entries}


def test_the_outcome_column_never_becomes_a_feature() -> None:
    entries = build_catalog(COLUMNS, "HIV_DETECTABLE")
    assert "HIV_DETECTABLE" not in _by_name(entries)
    # ...and exclusion is by exact name, so a legitimate column that merely
    # mentions the same disease survives.
    kept = build_catalog(["DX__G63__Neuropathy due to HIV (HCC)"], "HIV_DETECTABLE")
    assert len(kept) == 1


def test_a_code_outside_the_declared_vocabulary_carries_no_coding_system() -> None:
    """2 of EcoXAI's 540 DX codes are IMO proprietary.

    Declaring ICD-10-CM on them would have the matcher derive a root from a string
    that carries no hierarchy — the exact defect `vocab.py:21-28` exists to prevent.
    """
    entries = _by_name(build_catalog(COLUMNS, "HIV_DETECTABLE"))
    icd = entries["DX__I10__Essential hypertension"]
    assert (icd.coding_system, icd.key) == ("ICD-10-CM", "I10")
    imo = entries["DX__IMO0001__Proprietary IMO concept"]
    assert (imo.coding_system, imo.key) == (None, None)


def test_a_categorical_family_is_expanded_whole(fake_encoder) -> None:
    """`encode_kind="categorical"` + a non-empty `source_col` is the only trigger.

    This is the test the previous sandbox catalog would have failed: with every
    entry a `passthrough` with `source_col=""`, a query for "race" returned only
    whichever levels happened to clear the floor, and no query ever saw a family.
    """
    entries = build_catalog(COLUMNS, "HIV_DETECTABLE")
    got = _matcher(entries, fake_encoder, top_k=2).match("race or ethnicity")
    names = [m.feature_name for m in got.matches]
    assert set(RACE) <= set(names)  # all four levels, though top_k is 2


def test_a_family_smaller_than_expected_is_a_dropped_reference_level(fake_encoder) -> None:
    """`CAT__SEX__Male` is the only sex column; 0 means not male.

    Asserted so the fixture stays honest about it — this is the shape the agent
    prompt has to explain, not a bug in the builder.
    """
    entries = build_catalog(COLUMNS, "HIV_DETECTABLE")
    got = _matcher(entries, fake_encoder).match("sex")
    assert [m.feature_name for m in got.matches if m.feature_name.startswith("CAT__SEX")] == SEX


def test_an_unmapped_categorical_family_fails_the_build() -> None:
    """A family embedded under its raw column-name spelling is never retrieved and
    nothing downstream reports the loss, so the build stops instead."""
    with pytest.raises(ValueError, match="_CAT_LABELS"):
        build_catalog(["CAT__GENDER_IDENTITY__Nonbinary"], "HIV_DETECTABLE")


def test_the_fingerprint_sees_a_reordered_header_and_a_new_template(tmp_path) -> None:
    """Column ORDER is part of the identity: the matrix's rows are positional, so
    the same columns in a different order is a different catalog."""
    csv = tmp_path / "cohort.csv"
    kw = dict(
        cohort_file=csv,
        outcome_col="HIV_DETECTABLE",
        schema_version=1,
        builder_version=1,
        embedding_model="m",
        embedding_revision="r",
    )
    base = catalog_fingerprint(columns=COLUMNS, **kw)  # type: ignore[arg-type]
    assert base == catalog_fingerprint(columns=list(COLUMNS), **kw)  # type: ignore[arg-type]
    assert base != catalog_fingerprint(columns=COLUMNS[::-1], **kw)  # type: ignore[arg-type]
    # Same columns, changed match_text template: columns_sha1 cannot see it, which
    # is why builder_version is a separate field rather than a comment.
    bumped = catalog_fingerprint(columns=COLUMNS, **{**kw, "builder_version": 2})  # type: ignore[arg-type]
    assert bumped["columns_sha1"] == base["columns_sha1"] and bumped != base
