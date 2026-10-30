#!/usr/bin/env python3
"""Flatten pipe-delimited HIV cohort columns into counts and indicator features.

The source CSV must contain the columns in FLAT, LISTS and OUTCOME. It is read
without modification; generated features are written to the output directory.

Usage::

    python -m memstara.prep.hiv --source /path/to/cohort.csv
    python -m memstara.prep.hiv --source /path/to/cohort.csv --top 12
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from memstara.paths import DEFAULT_OUTPUT_DIR

DEFAULT_OUT = DEFAULT_OUTPUT_DIR / "hiv_cohort.csv"

OUTCOME = "HIV_DETECTABLE"  # what we are trying to predict — is the virus detectable

# Columns that already hold one value per patient. Nothing to unpack, so they are
# carried across untouched.
FLAT = [
    "CURRENT_AGE",
    "BMI",
    "SEX",
    "ETHNIC_GROUP",
    "RACE_1",
    "MARITAL_STATUS",
    "TOBACCO_LAST_STATUS",
    "ILL_DRUG_LAST_STATUS",
    "ALCOHOL_LAST_STATUS",
]

# (source column, count column name, flag prefix or None)
#
# The two with a prefix of None get **a count only**, no present/absent flags.
# Surgeries and lab components are spread too thin: even the eight most common
# would be columns of zeros for most patients.
LISTS = [
    ("DX_NAME_LIST", "n_diagnoses", "dx"),
    ("MED_NAME_LIST", "n_medications", "med"),
    ("SURGERY_PROC_LIST", "n_surgeries", None),
    ("GENERAL_LAB_COMPONENTS_LIST", "n_lab_components", None),
]


def items(cell: object) -> list[str]:
    """Split one pipe-delimited cell into its distinct entries.

    Dropping the duplicates is the point. The same diagnosis is written again at
    every visit, so counting the raw entries would make "number of diagnoses"
    measure **how many visits** the patient had rather than how many conditions
    they have. A blank cell, or anything that is not a string, returns an empty list.
    """
    if not isinstance(cell, str) or not cell.strip():
        return []
    return sorted({p.strip() for p in cell.split("|") if p.strip()})


def column_name(prefix: str, label: str) -> str:
    """A readable column name.

    Readable on purpose. The thing that has to connect a knowledge-source concept to a
    column is an LLM reading both, and it cannot connect `dx_f329` to "depression".

    So the diagnosis name is lowercased, every symbol becomes an underscore, and
    the prefix goes in front — producing names like `dx_major_depressive_disorder`.
    Cut at 40 characters.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return f"{prefix}_{slug[:40]}".rstrip("_")


def build(source: Path, top: int) -> tuple[pd.DataFrame, dict[str, list[tuple[str, int]]]]:
    """Flatten the cohort as received. **The body of this file.**

    It returns two things — the cleaned table, and a record of which diagnoses and
    medications were picked.

    Every column is read as text (dtype=str) with `keep_default_na=False`. If
    pandas were allowed to convert to numbers or turn blanks into NaN on its own,
    the list-splitting step would have to check whether each value is a string
    every time. Only the columns that need it are converted to numbers afterwards.
    """
    raw = pd.read_csv(source, dtype=str, keep_default_na=False)

    # The shared file has a few rows where a diagnosis name spilled into the label
    # column — an unescaped delimiter upstream. Keep only rows whose label is 0 or 1
    # and say how many were dropped; silently losing rows is how row counts stop
    # matching between steps.
    keep = raw[OUTCOME].isin(["0", "1"])
    dropped = int((~keep).sum())
    raw = raw[keep].reset_index(drop=True)

    # (1) The columns that already hold one value are carried across as they are. An
    #     empty string has to become missing, or "blank" and "the empty string" end up
    #     mixed together. Only age and BMI become numbers.
    out = pd.DataFrame(index=raw.index)
    for c in FLAT:
        s = raw[c].replace("", pd.NA)
        out[c] = pd.to_numeric(s) if c in ("CURRENT_AGE", "BMI") else s

    # (2) Unpack the list columns. Each one gets a count; the ones with a prefix also
    #     get present/absent (1/0) columns for the `top` most common entries.
    chosen: dict[str, list[tuple[str, int]]] = {}
    for src, count_col, prefix in LISTS:
        parsed = raw[src].map(items)  # each cell becomes a list
        out[count_col] = parsed.map(len)  # the length of that list = the count
        if prefix is None:
            continue
        freq = Counter(v for lst in parsed for v in lst)  # how many patients had it at all
        picked = freq.most_common(top)  # the `top` most common
        chosen[src] = picked
        # `bound=label` pins the value down here and now. Without it only the value
        # label holds after the loop ends is used, and every flag column would point
        # at that one last diagnosis.
        for label, _ in picked:
            out[column_name(prefix, label)] = parsed.map(lambda lst, bound=label: int(bound in lst))

    # (3) The outcome is attached last so that it sits at the end of the table.
    out[OUTCOME] = pd.to_numeric(raw[OUTCOME])
    return out, {"__dropped__": dropped, **chosen}  # type: ignore[dict-item]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="Path to the source cohort CSV")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--top", type=int, default=8, help="how many diagnoses / medications to flag")
    args = ap.parse_args()

    source = Path(args.source)
    if not source.is_file():
        print(f"!! not found: {source}", file=sys.stderr)
        return 1

    # build returns the number of dropped rows inside the record of what was picked.
    # Take it back out here.
    df, chosen = build(source, args.top)
    dropped = chosen.pop("__dropped__")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    pos = int(df[OUTCOME].sum())
    print(f"source: {source}")
    print("        (read only — nothing is written back there)\n")
    print(f"rows    {len(df):,}   ({dropped} dropped: label was not 0/1)")
    print(
        f"columns {len(df.columns)}   = {len(FLAT)} as-is + {len(LISTS)} counts "
        f"+ {sum(len(v) for v in chosen.values())} flags + outcome"
    )
    print(f"outcome {OUTCOME}: {pos} positive / {len(df) - pos} negative  ({pos / len(df) * 100:.1f}%)\n")

    for src, picked in chosen.items():
        print(f"{src} — {len(picked)} most prevalent")
        for label, n in picked:
            print(f"   {n / len(df) * 100:5.1f}%  {label[:64]}")
        print()

    # Missingness is the one property a column name cannot convey, and the hypothesis
    # agent decides from names. Print it so the number is on the record here too — it
    # is what makes it possible to work out later why a column turned out to be useless.
    miss = df.isna().mean().sort_values(ascending=False)
    miss = miss[miss > 0]
    if len(miss):
        print("columns with missing values")
        for c, frac in miss.items():
            print(f"   {frac * 100:5.1f}%  {c}")

    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
