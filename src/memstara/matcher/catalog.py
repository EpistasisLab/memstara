# SOURCE: MIXED — this file is part afc-forge and part sandbox. Every top-level
#   symbol below carries its own SOURCE tag; the map is also given here.
#
#   upstream: shared/afc-forge/ade_forge/tools/impl/catalog.py (674 lines)
#
#   PORTED VERBATIM (byte-identical to upstream, docstrings included) — 7:
#       norm_upper   CatalogEntry   save_catalog   load_catalog
#       catalog_index   meta_path   save_catalog_meta
#   PORTED WITH EDITS — 1:
#       verify_catalog  (upstream logic; only the "rebuild it" CLI hint changed
#                        from `ade-forge build-catalog` to this repo's script)
#   SANDBOX-ORIGINAL (afc-forge has no counterpart) — 3:
#       ENCODE_KINDS's `wide_passthrough` member   _CAT_LABELS   _parse_column
#   SANDBOX-ORIGINAL, upstream name reused — 2:
#       build_catalog   catalog_fingerprint
#       Same names and same output shape as upstream, but the bodies share no
#       code: upstream's take a pandas DataFrame, a CohortDescriptor and a
#       leakage RuleSet. Do not read these two as ported.
"""The catalog — a ported half and an EcoXAI builder half.

**Ported half** (`CatalogEntry`, `norm_upper`, `save_catalog`, `load_catalog`,
`catalog_index`, `meta_path`, `save_catalog_meta`, `verify_catalog`) comes
straight from afc-forge `ade_forge/tools/impl/catalog.py`, docstrings included,
so it stays checkable against upstream with a diff.

**Builder half** (`_parse_column`, `_CAT_LABELS`, `build_catalog`,
`catalog_fingerprint`) is new sandbox code. afc-forge's builder parses an
18-column long-format cohort (list columns like DX_CODE_LIST); EcoXAI arrives as
1,393 wide columns with no lists to parse. What ports is the *shape of the
output*, not the builder.

**Caveat (out of scope):** in afc-forge this file is the single choke point for
leakage. This port does not carry that layer — see `src/memstara/matcher/__init__.py`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

from memstara.matcher.vocab import VOCABULARIES

# ---------------------------------------------------------------------------
# Ported half — afc-forge `ade_forge/tools/impl/catalog.py`
# ---------------------------------------------------------------------------

#: Encode kinds. afc-forge's `encode.py` dispatches on exactly these; the
#: sandbox holds no encoder, so only `categorical` is load-bearing here — it is
#: half of the one-hot family expander's trigger (`matcher.py:_expand_onehot_family`).
ENCODE_KINDS = (
    "categorical",  # scalar_categorical level indicator
    "numeric",  # scalar_numeric passthrough
    "list_presence",  # one item present in a list column
    "list_presence_any",  # ROLLUP meta-feature: ANY member key present
    "lab_numeric",  # mean of a component's numeric + censored values
    "lab_censoring",  # companion indicator: -1 below / 0 uncensored / +1 above
    "lab_categorical",  # COMPONENT=LEVEL indicator for a qualitative result
    "lab_presence",  # component was MEASURED (administrative != measured)
    # Added by the sandbox. EcoXAI columns are already wide 0/1 and float, so
    # there is no source list column to parse. Borrowing `list_presence` or
    # `lab_numeric` would write an untrue instruction into the catalog — "parse
    # the list column named in source_col" — that nothing checks today and an
    # encoder would act on tomorrow.
    "wide_passthrough",
)


# SOURCE: PORTED VERBATIM from afc-forge catalog.py
def norm_upper(s: str) -> str:
    """Ported verbatim."""
    return s.strip().upper()


# SOURCE: PORTED VERBATIM from afc-forge catalog.py — field list, defaults,
#   comments and both methods are upstream's. Nothing here is sandbox-authored.
@dataclasses.dataclass(frozen=True)
class CatalogEntry:
    """One matchable feature. Frozen: an entry is an identity, not a workspace."""

    feature_name: str  # verbatim downstream key
    feature_type: str  # one of constants.FEATURE_TYPES
    match_text: str  # embedded + fuzzy-matched text
    encode_kind: str  # one of ENCODE_KINDS
    source_col: str  # for lab_*: the COMPONENTS/description column
    key: str | None = None  # level (categorical) / token (list_presence/lab_*)
    normalize: str | None = None  # "upper_strip" | "med_head"
    value_col: str | None = None  # paired VALUES column (lab_numeric/censoring/etc.)
    # ROLLUP meta-features only (`list_presence_any`): the SET of member keys, any
    # of which present -> 1.0. Kept LAST + defaulted so an older catalog.json (no
    # `keys`) still loads, and atomic entries stay `keys=None`. Ported.
    keys: tuple[str, ...] | None = None
    #: Declared vocabulary, carried so the matcher's code-injection path and the
    #: leakage layer are parameterized by it rather than by an ICD-10 literal.
    coding_system: str | None = None
    #: The aligned group this came from, so siblings are recoverable without
    #: re-deriving them from column names.
    group: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> CatalogEntry:
        if isinstance(d.get("keys"), list):  # a tuple round-trips as a list
            d = {**d, "keys": tuple(d["keys"])}
        fields = {f.name for f in dataclasses.fields(CatalogEntry)}
        return CatalogEntry(**{k: v for k, v in d.items() if k in fields})


# ---------------------------------------------------------------------------
# Persistence + the staleness guard
# SOURCE: PORTED FROM afc-forge catalog.py. The next five functions
#   (save_catalog, load_catalog, catalog_index, meta_path, save_catalog_meta)
#   are byte-identical to upstream. verify_catalog, at the end of this section,
#   is upstream's logic with only its rebuild hint changed — it is tagged there.
# ---------------------------------------------------------------------------
def save_catalog(entries: list[CatalogEntry], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps([e.to_dict() for e in entries], ensure_ascii=False, indent=0),
        encoding="utf-8",
    )
    return p


def load_catalog(path: str | Path) -> list[CatalogEntry]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [CatalogEntry.from_dict(d) for d in data]


def catalog_index(entries: list[CatalogEntry]) -> dict[str, CatalogEntry]:
    return {e.feature_name: e for e in entries}


def meta_path(catalog_json: str | Path) -> Path:
    p = Path(catalog_json)
    return p.parent / f"{p.stem}.meta.json"


def save_catalog_meta(
    entries: list[CatalogEntry],
    catalog_json: str | Path,
    fingerprint: dict[str, Any],
) -> dict[str, Any]:
    meta = {**fingerprint, "n_entries": len(entries)}
    meta_path(catalog_json).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return meta


# SOURCE: PORTED WITH EDITS from afc-forge catalog.py:647. The control flow and
#   the drift comparison are upstream's, unchanged. The only edit: upstream names
#   its own CLI (`ade-forge build-catalog`) in three separate message strings;
#   here that text is hoisted into `hint` and points at this repo's script, so a
#   reader of the message can act on it without a CLI this sandbox does not have.
def verify_catalog(catalog_json: str | Path, fingerprint: dict[str, Any]) -> str | None:
    """`None` if the catalog is current; a human-readable reason if it is stale.

    Fails loud with a rebuild hint. A stale catalog does not crash — it quietly
    encodes against a vocabulary the cohort no longer has, which is the failure
    this guard exists to make impossible.
    """
    p = meta_path(catalog_json)
    hint = "Rebuild it: `python scripts/build_matcher_cache.py`."
    if not Path(catalog_json).exists():
        return f"no catalog at {catalog_json}. {hint}"
    if not p.exists():
        return (
            f"{Path(catalog_json).name} has no {p.name} sidecar, so it cannot be "
            f"checked against its cohort. {hint}"
        )
    stored = json.loads(p.read_text(encoding="utf-8"))
    drift = [
        f"{k}: built with {stored.get(k)!r}, now {v!r}"
        for k, v in fingerprint.items()
        if stored.get(k) != v
    ]
    if not drift:
        return None
    return f"{Path(catalog_json).name} is STALE — " + "; ".join(drift) + f". {hint}"


# ---------------------------------------------------------------------------
# Builder half — EcoXAI wide columns
# SOURCE: SANDBOX-ORIGINAL. Nothing from here to the end of the file is copied
#   from afc-forge. `build_catalog` and `catalog_fingerprint` reuse upstream's
#   NAMES and return shapes so the ported half above still fits them, but the
#   bodies share no code with upstream's (which take a pandas DataFrame, a
#   CohortDescriptor and a leakage RuleSet). Diffing this half against upstream
#   is meaningless — it is a different builder for a different cohort layout.
# ---------------------------------------------------------------------------

#: FAMILY in `CAT__<FAMILY>__<Level>` -> a label a human would write. **A hardcoded
#: map rather than a transform**: `.title()` turns `ILL_DRUG_STATUS` into "Ill Drug
#: Status", and "ill" is not "illicit". To a sentence encoder that is not a typo, it
#: is a different meaning. A family missing from this map fails the build — a column
#: embedded under the wrong text is never retrieved and nothing reports the loss.
_CAT_LABELS = {
    "SEX": "Sex",
    "RACE_ETHNICITY": "Race or ethnicity",
    "MARITAL_STATUS": "Marital status",
    "TOBACCO_STATUS": "Tobacco use status",
    "ALCOHOL_STATUS": "Alcohol use status",
    "ILL_DRUG_STATUS": "Illicit drug use status",
}

#: Human-readable names for the un-prefixed scalar columns.
_SCALAR_LABELS = {
    "CURRENT_AGE": "age in years",
    "BMI": "body mass index (BMI)",
}


# SOURCE: SANDBOX-ORIGINAL — afc-forge has no counterpart.
def _parse_column(col: str) -> CatalogEntry:
    """One EcoXAI column name -> one CatalogEntry.

    `feature_name` is **verbatim** — a retyped name is a feature silently lost.

    | column                  | feature_type | encode_kind       | source_col |
    |-------------------------|--------------|-------------------|------------|
    | `DX__<code>__<desc>`    | diagnosis    | wide_passthrough  | ""         |
    | `MED__<name>`           | medication   | wide_passthrough  | ""         |
    | `LAB__<name>`           | lab          | wide_passthrough  | ""         |
    | `CAT__<FAM>__<Level>`   | demographic  | **categorical**   | **<FAM>**  |
    | `CURRENT_AGE` / `BMI`   | demographic  | wide_passthrough  | ""         |

    `categorical` plus a non-empty `source_col` is the ONLY trigger for one-hot
    family expansion (`matcher.py:_expand_onehot_family`). Those two fields have to
    mean exactly what they mean in afc-forge; the rest is ours to choose.
    """
    if col.startswith("DX__"):
        rest = col[len("DX__"):]
        code, _, desc = rest.partition("__")
        # coding_system is **conditional**. 2 of the 540 DX codes (IMO0001,
        # IMO0002) are IMO proprietary and do not pass the ICD-10-CM recognizer.
        # Declaring ICD-10-CM on a code that is not one would have the matcher
        # derive a root from a string that carries no hierarchy — "a ROOT is
        # DECLARED, never inferred from the string" (vocab.py:21-28).
        is_icd10 = VOCABULARIES["ICD-10-CM"].matches(code)
        text = f"{desc} ({code})" if desc else code
        return CatalogEntry(
            feature_name=col,
            feature_type="diagnosis",
            match_text=text,
            encode_kind="wide_passthrough",
            source_col="",
            key=code if is_icd10 else None,
            coding_system="ICD-10-CM" if is_icd10 else None,
        )

    if col.startswith("MED__"):
        name = col[len("MED__"):]
        return CatalogEntry(
            feature_name=col,
            feature_type="medication",
            match_text=f"{name} medication",
            encode_kind="wide_passthrough",
            source_col="",
        )

    if col.startswith("LAB__"):
        name = col[len("LAB__"):]
        return CatalogEntry(
            feature_name=col,
            feature_type="lab",
            match_text=f"{name} lab test",
            encode_kind="wide_passthrough",
            source_col="",
        )

    if col.startswith("CAT__"):
        rest = col[len("CAT__"):]
        family, _, level = rest.partition("__")
        if family not in _CAT_LABELS:
            raise ValueError(
                f"{col}: categorical family {family!r} has no label in _CAT_LABELS. "
                "Add one — a family embedded under its raw column-name spelling is a "
                "column nobody can find, and nothing downstream reports the loss."
            )
        return CatalogEntry(
            feature_name=col,
            feature_type="demographic",
            # `:` rather than `=` — S-PubMedBERT is a sentence encoder.
            match_text=f"{_CAT_LABELS[family]}: {level}",
            encode_kind="categorical",
            source_col=family,
            key=level,
            group=family,
        )

    return CatalogEntry(
        feature_name=col,
        feature_type="demographic",
        match_text=_SCALAR_LABELS.get(col, col.replace("_", " ").lower()),
        encode_kind="wide_passthrough",
        source_col="",
    )


# SOURCE: SANDBOX-ORIGINAL, upstream name reused. afc-forge's build_catalog
#   (catalog.py:322, ~200 lines) takes a DataFrame + CohortDescriptor + RuleSet.
#   This shares its name and its return type, and no code.
def build_catalog(columns: list[str], outcome_col: str) -> list[CatalogEntry]:
    """Build the catalog from an EcoXAI CSV header, excluding `outcome_col`.

    Exclusion is by **exact name match only**. Adding prefix or substring matching
    would silently drop legitimate columns — the only other column containing
    "HIV" is `DX__G63__Neuropathy due to HIV (HCC)`, a real feature.
    """
    entries = [_parse_column(c) for c in columns if c != outcome_col]
    names = {e.feature_name for e in entries}
    if outcome_col in names:  # redundant with the filter above; an invariant should be stated
        raise AssertionError(f"outcome column {outcome_col!r} leaked into the catalog")
    return entries


# SOURCE: SANDBOX-ORIGINAL, upstream name reused. afc-forge's catalog_fingerprint
#   (ade_forge/tools/impl/catalog.py:587) hashes a CohortDescriptor and a leakage
#   RuleSet and stores `leakage_rules_sha1`. This one hashes a column list. The
#   MISSING field is the visible sign that the leakage layer did not come across
#   — see __init__.py.
def catalog_fingerprint(
    *,
    cohort_file: str | Path,
    columns: list[str],
    outcome_col: str,
    schema_version: int,
    builder_version: int,
    embedding_model: str,
    embedding_revision: str | None,
) -> dict[str, Any]:
    """The identity of the inputs this catalog was built from.

    afc-forge hashes the **whole CSV bytes**, because there the catalog is derived
    from cell values (the distinct tokens in a list column), so changed values mean
    a changed catalog. EcoXAI's catalog is derived from the **header alone**, so
    hashing rows would raise a false alarm on every resample. A deliberate
    divergence, recorded here.

    Why `builder_version` is needed: the same column list with a changed match_text
    template yields the same columns_sha1. The embedding stamp (match_text_sha1)
    catches that change but the catalog meta does not, and the two guards have to be
    independent.
    """
    ordered = json.dumps(columns, ensure_ascii=False)
    return {
        "schema_version": schema_version,
        "builder_version": builder_version,
        "cohort_file": Path(cohort_file).name,
        "n_columns": len(columns),
        "columns_sha1": hashlib.sha1(ordered.encode("utf-8")).hexdigest(),
        "outcome_col": outcome_col,
        "embedding_model": embedding_model,
        "embedding_revision": embedding_revision,
    }
