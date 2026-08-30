#!/usr/bin/env python3
# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. The floor it measures
#   (MatcherConfig.sim_threshold) is upstream's value; this instrument for
#   re-checking that value against the EcoXAI cohort is sandbox-authored.
"""Measure `sim_threshold` against this cohort. Read-only — writes nothing.

    conda run -n memstara python scripts/calibrate_threshold.py

The floor is not a taste. It is the answer to one question: what is the highest
floor that loses no real concept and truncates no categorical family? Everything
printed below exists to answer that, and the last line states the answer.

This re-embeds in process rather than reading the cached `.npy`, so it can be run
BEFORE a rebuild — on an M-series machine the 1,393 texts take a few seconds. That
also means it measures the CURRENT templates in `catalog.py`, not whatever the
cache happens to hold, which is the comparison you want when you have just changed
a template and are deciding whether to keep it.

The query lists below are the instrument. They are meant to be edited when the
cohort changes — a GOOD query is a concept a clinician would ask for and this
cohort genuinely carries; an ABSENT query is one it genuinely does not. Adding a
GOOD query that is actually absent moves the recommended floor down for no reason.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_ROOT))

import numpy as np

from matcher_impl.catalog import build_catalog
from matcher_impl.embedder import embed_catalog, l2_normalize, sentence_transformer_encoder
from matcher_impl.service import build_run_config, dataset_path, outcome_column, read_columns

#: (query, a substring of the column it should reach). `None` where only the
#: top-1 score matters and no single column is "the" right answer.
GOOD: list[tuple[str, str | None]] = [
    ("hypertension", "DX__I10"),
    ("essential hypertension", "DX__I10"),
    ("type 2 diabetes mellitus", "DX__E11"),
    ("chronic kidney disease", "DX__N18"),
    ("hemoglobin a1c", "LAB__HEMOGLOBIN A1C"),
    ("cd4 count", "LAB__CD4"),
    ("cd4 to cd8 ratio", "LAB__CD4:CD8"),
    ("serum creatinine", "LAB__CREATININE"),
    ("estimated glomerular filtration rate", None),
    ("low density lipoprotein cholesterol", "LAB__LDL"),
    ("body mass index", "BMI"),
    ("age", "CURRENT_AGE"),
    ("sex", "CAT__SEX"),
    ("race or ethnicity", "CAT__RACE_ETHNICITY"),
    ("marital status", "CAT__MARITAL_STATUS"),
    ("tobacco use", "CAT__TOBACCO_STATUS"),
    ("alcohol use", "CAT__ALCOHOL_STATUS"),
    ("illicit drug use", "CAT__ILL_DRUG_STATUS"),
    ("depression", None),
    ("antiretroviral therapy", None),
    ("statin", None),
]

#: Concepts this cohort does not carry. Several are clinically ADJACENT to things
#: it does carry, which is deliberate: a floor that only rejects nonsense proves
#: nothing. What comes back for these is the nearest real column, and under the
#: PICK-THE-GROUP contract judging that is the agent's job — the floor's job is
#: only to keep the group small enough to read.
ABSENT: list[str] = [
    "left ventricular ejection fraction",
    "MRI of the knee",
    "APOE genotype",
    "colonoscopy findings",
    "hours of sleep per night",
    "household income",
    "distance to nearest clinic",
    "zip code",
]

FLOORS = [0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94]


def main() -> int:
    run_config = build_run_config()
    csv_path = dataset_path()
    columns = read_columns(csv_path)
    entries = build_catalog(columns, outcome_col=outcome_column())
    names = [e.feature_name for e in entries]

    print(f"cohort   {csv_path.name}  ({len(columns)} columns, {len(entries)} entries)")
    print(f"model    {run_config.embedding.model}@{run_config.embedding.revision}")
    print(f"current  sim_threshold={run_config.matcher.sim_threshold}\n")

    encoder = sentence_transformer_encoder(run_config.embedding)
    catalog_matrix = embed_catalog([e.match_text for e in entries], encoder)
    queries = [q for q, _ in GOOD] + ABSENT
    query_matrix = l2_normalize(np.asarray(encoder(queries), dtype=np.float32))
    cos = query_matrix @ catalog_matrix.T  # (n_queries, n_entries)

    good_cos = cos[: len(GOOD)]
    absent_cos = cos[len(GOOD) :]

    # -- 1. what each query actually reaches ---------------------------------
    print("=" * 78)
    print("1. TOP-12 PER QUERY  (! = the expected column is outside the top 12)")
    print("=" * 78)
    for i, (query, expected) in enumerate(GOOD):
        order = np.argsort(-good_cos[i])
        rank = None
        if expected is not None:
            hits = [r for r, j in enumerate(order, 1) if expected in names[j]]
            rank = hits[0] if hits else None
        flag = "" if expected is None else ("!" if rank is None or rank > 12 else f"rank {rank}")
        print(f"\n  {query!r}  {flag}")
        for j in order[:12]:
            mark = "<--" if expected and expected in names[j] else ""
            print(f"      {good_cos[i][j]:.3f}  {names[j][:62]} {mark}")

    # -- 2. the two distributions --------------------------------------------
    print("\n" + "=" * 78)
    print("2. TOP-1 DISTRIBUTIONS")
    print("=" * 78)
    g1 = sorted(float(row.max()) for row in good_cos)
    a1 = sorted(float(row.max()) for row in absent_cos)
    print(f"  GOOD   n={len(g1):2d}  min {g1[0]:.3f}  median {statistics.median(g1):.3f}  max {g1[-1]:.3f}")
    print(f"  ABSENT n={len(a1):2d}  min {a1[0]:.3f}  median {statistics.median(a1):.3f}  max {a1[-1]:.3f}")
    print(f"  separation = GOOD_min - ABSENT_max = {g1[0] - a1[-1]:+.3f}")
    print(
        "  A negative separation is the expected result, and it is the finding: no\n"
        "  floor separates 'present' from 'absent'. That is why the contract is\n"
        "  PICK-THE-GROUP and not 'take the top match above the threshold'."
    )

    # -- 3. the sweep ---------------------------------------------------------
    print("\n" + "=" * 78)
    print("3. FLOOR SWEEP")
    print("=" * 78)
    print(f"  {'floor':>6}  {'GOOD lost':>9}  {'ABSENT thru':>11}  {'cands med':>9}  {'p90':>5}")
    viable: list[float] = []
    for floor in FLOORS:
        lost = [q for (q, _), row in zip(GOOD, good_cos) if float(row.max()) < floor]
        through = [q for q, row in zip(ABSENT, absent_cos) if float(row.max()) >= floor]
        counts = sorted(int((row >= floor).sum()) for row in good_cos)
        med = statistics.median(counts)
        p90 = counts[min(len(counts) - 1, int(0.9 * len(counts)))]
        print(f"  {floor:>6.2f}  {len(lost):>9}  {len(through):>11}  {med:>9.0f}  {p90:>5}")
        if lost:
            print(f"          lost: {', '.join(lost)}")
        if not lost:
            viable.append(floor)

    # -- 4. family coverage (the one failure rewording cannot fix) ------------
    print("\n" + "=" * 78)
    print("4. CATEGORICAL FAMILY COVERAGE")
    print("=" * 78)
    families: dict[str, list[int]] = {}
    for idx, e in enumerate(entries):
        if e.encode_kind == "categorical" and e.source_col:
            families.setdefault(e.source_col, []).append(idx)
    truncated: list[str] = []
    for family, idxs in sorted(families.items()):
        # score each level against the query that should reach the family
        best = max(
            (float(good_cos[i][idxs].min()), q)
            for i, (q, exp) in enumerate(GOOD)
            if exp and exp.startswith(f"CAT__{family}")
        ) if any(exp and exp.startswith(f"CAT__{family}") for _, exp in GOOD) else None
        if best is None:
            print(f"  {family:<20} {len(idxs)} levels   (no GOOD query targets it — not measured)")
            continue
        worst_level, query = best
        for floor in viable:
            if worst_level < floor:
                truncated.append(f"{family} @ {floor:.2f}")
        print(f"  {family:<20} {len(idxs)} levels   worst level {worst_level:.3f} via {query!r}")
    if truncated:
        print("\n  FAMILY TRUNCATED BY FLOOR: " + "; ".join(truncated))
        print("  A truncated family is the one failure an agent cannot reword its way out")
        print("  of — it sees a family with a level missing and cannot tell it is missing.")

    # -- 5. the false friends this cohort actually has ------------------------
    print("\n" + "=" * 78)
    print("5. FALSE FRIENDS  (why rank 1 is not the answer)")
    print("=" * 78)
    # `exact` matters: LAB__HEMOGLOBIN is a prefix of LAB__HEMOGLOBIN A1C, so a
    # prefix test here reports the query's own target as its own false friend.
    for query, intruder, exact in [
        ("hypertension", "DX__I11", False),
        ("chronic kidney disease", "DX__E11.22", False),
        ("hemoglobin a1c", "LAB__HEMOGLOBIN", True),
    ]:
        i = next((k for k, (q, _) in enumerate(GOOD) if q == query), None)
        if i is None:
            continue
        order = np.argsort(-good_cos[i])
        def is_intruder(name: str, intruder: str = intruder, exact: bool = exact) -> bool:
            return name == intruder if exact else name.startswith(intruder)

        hit = next(((r, j) for r, j in enumerate(order, 1) if is_intruder(names[j])), None)
        if hit is None:
            print(f"  {query!r}: {intruder} not in the catalog — group may be truncated")
        else:
            r, j = hit
            print(f"  {query!r}: {names[j][:52]} at rank {r} ({good_cos[i][j]:.3f})")

    # -- 6. the verdict -------------------------------------------------------
    print("\n" + "=" * 78)
    safe = [f for f in viable if not any(t.endswith(f"{f:.2f}") for t in truncated)]
    if not safe:
        print("VERDICT: no floor in the sweep keeps every GOOD query and every family.")
        print("         Widen FLOORS downward, or fix the match_text template first.")
        return 1
    rec = max(safe)
    print(f"RECOMMENDED sim_threshold = {rec:.2f}")
    print(f"  the highest floor that loses none of the {len(GOOD)} real concepts and")
    print("  truncates no categorical family")
    current = run_config.matcher.sim_threshold
    if abs(current - rec) > 1e-9:
        print(f"  CONFIG SAYS {current:.2f} — update MatcherConfig.sim_threshold or explain why not")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
