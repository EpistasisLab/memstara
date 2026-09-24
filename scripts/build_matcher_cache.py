#!/usr/bin/env python3
# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. This replaces upstream's
#   `ade-forge build-catalog` / `ade-forge embed-catalog` CLI, which needs the
#   descriptor system. It calls the ported code; it is not ported code.
"""Build the matcher cache — run once before the pipeline, and again whenever the
cohort header, the match_text templates, or the embedding model changes.

    MEMSTARA_DATASET_PATH=/path/to/cohort.csv \\
    MEMSTARA_OUTCOME_COLUMN=HIV_DETECTABLE \\
    conda run -n memstara python scripts/build_matcher_cache.py

Writes four artifacts, all derived from `config.CATALOG_JSON`:

    matcher_catalog.json        the entries
    matcher_catalog.emb.npy     their embedding matrix
    matcher_catalog.emb.json    the matrix's identity stamp (match_text_sha1 + model)
    matcher_catalog.meta.json   the catalog fingerprint

WHAT THIS SCRIPT REFUSES TO DO
------------------------------
The version this replaces had two silent holes, both of which produce a working
matcher that answers the wrong questions:

1. The outcome column was the literal "HIV_DETECTABLE", and when the cohort did
   not contain it the script printed a warning and set `outcome = ""` — which
   includes EVERY column, the label among them. A warning on stdout is not a
   guard; nothing downstream reads it.
2. An unset MEMSTARA_DATASET_PATH fell back to `outputs/dataset.csv`, a 41-column
   NHANES file, and built a 41-entry catalog without comment.

Both are now hard failures. Nothing here defaults.
"""

from __future__ import annotations

import sys

from memstara.matcher.rules import load_rules

from memstara.matcher import config
from memstara.matcher.catalog import build_catalog, save_catalog, save_catalog_meta
from memstara.matcher.embedder import (
    embed_catalog,
    embeddings_path,
    embeddings_stamp_path,
    load_sentence_transformer,
    save_embeddings,
    sentence_transformer_encoder,
)
from memstara.matcher.service import (
    build_run_config,
    current_fingerprint,
    dataset_path,
    outcome_column,
    read_columns,
)


def main() -> int:
    rules = load_rules()
    run_config = build_run_config()
    csv_path = dataset_path()  # raises if unset or missing — no fallback cohort
    outcome = outcome_column()  # raises if unset — no literal label name

    print(f"[1/5] cohort header: {csv_path}")
    columns = read_columns(csv_path)
    print(f"      {len(columns)} columns")

    if outcome not in columns:
        print(
            f"[FAIL] the outcome column {outcome!r} is not in {csv_path.name}.\n"
            "       Refusing to build: the previous version warned here and then included\n"
            "       every column, which is how a label reaches an agent as a feature.\n"
            "       Set MEMSTARA_OUTCOME_COLUMN to a column this cohort actually has.",
            file=sys.stderr,
        )
        return 1

    print("[2/5] building the catalog")
    entries = build_catalog(columns, outcome_col=outcome, rules=rules)
    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e.feature_type] = by_type.get(e.feature_type, 0) + 1
    print(f"      {len(entries)} entries  {by_type}")

    # Post-build assertion. `build_catalog` already filters by exact name; this is
    # the invariant restated where it can fail loudly, because it is the one thing
    # in this script that must never be wrong.
    names = {e.feature_name for e in entries}
    assert outcome not in names, f"outcome column {outcome!r} leaked into the catalog"

    n_families = len({e.source_col for e in entries if e.encode_kind == "categorical"})
    n_coded = sum(1 for e in entries if e.coding_system)
    print(f"      {n_families} categorical families, {n_coded} entries with a declared code")

    print(f"[3/5] loading {run_config.embedding.model}")
    load_sentence_transformer(run_config.embedding)  # warms the cache, reports the device
    encoder = sentence_transformer_encoder(run_config.embedding)

    print("[4/5] embedding")
    match_texts = [e.match_text for e in entries]
    matrix = embed_catalog(match_texts, encoder)
    print(f"      matrix {matrix.shape}")

    print("[5/5] writing artifacts")
    catalog_json = config.CATALOG_JSON
    save_catalog(entries, catalog_json)
    save_embeddings(matrix, catalog_json, match_texts=match_texts, cfg=run_config.embedding)
    meta = save_catalog_meta(entries, catalog_json, current_fingerprint(run_config, rules=rules))
    for p in (catalog_json, embeddings_path(catalog_json), embeddings_stamp_path(catalog_json)):
        print(f"      {p}")
    print(f"      fingerprint columns_sha1={meta['columns_sha1'][:12]}… outcome={meta['outcome_col']}")

    print("\nDone. Verify with: python scripts/calibrate_threshold.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
