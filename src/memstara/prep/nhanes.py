#!/usr/bin/env python3
"""Turn the public NHANES survey into a table the pipeline can run against.

Why this dataset
----------------
Everything the board path has run on so far is synthetic, with the answer planted so
the pipeline could be scored. That proves it works; it does not show what breaks on
real data. And a paper needs one dataset a reviewer can download — reviewer's HIV cohort
cannot be published.

NHANES is public, clinical, and wide enough that a hypothesis limited to 3-8 columns
has to actually choose. The CDC's own XPT files are unreachable from here (wwwn.cdc.gov
answers with its homepage HTML instead of the file), so this reads the copy shipped in
CRAN's NHANES R package, which is the same survey with the columns already typed.

    curl -L -o NHANES.rda \
      https://raw.githubusercontent.com/cran/NHANES/master/data/NHANES.rda

What is dropped, and why
------------------------
- `ID`, `SurveyYr`          identifiers, not measurements
- >30% missing              Testosterone, TVHrsDay, CompHrsDay
- restatements              BMI_WHO (of BMI), AgeDecade (of Age),
                            BPSys1..3 / BPDia1..3 (of BPSysAve / BPDiaAve)

Restatements matter more than they look: leaving BPSys1 beside BPSysAve gives the
hypothesis stage three ways to say "systolic blood pressure", which inflates any
count of how often a concept was chosen.

Adults only (Age >= 20), and rows where the outcome is known.

Usage::

    Rscript -e 'load("NHANES.rda"); write.csv(NHANES, "nhanes_raw.csv", row.names=FALSE)'
    python -m memstara.prep.nhanes --raw nhanes_raw.csv


==============================================================================
 How to read this file
==============================================================================

 It turns **the public NHANES survey** (the US National Health and Nutrition
 Examination Survey) into a single CSV the pipeline can read directly. Adults
 only, with the mostly-empty columns and the columns that restate another column
 taken out. The outcome is `Diabetes`, and about 10.3% of rows are positive.

 There are only two functions.

   build(raw)   does all of the filtering and column work. **The body of this file**
   main()       reads the raw CSV, calls build, saves, and prints what was dropped

 Why this file exists: everything run so far has been synthetic data with the
 answer planted in it. That is evidence the pipeline **works**; it does not show
 what breaks on real data. And a paper needs at least one dataset a reviewer can
 download themselves — reviewer's HIV cohort cannot be published.

 Easy to miss:

   · Dropping **columns that restate another column** (BPSys1 beside BPSysAve)
     matters more than it looks. Left in, the hypothesis stage has three ways to
     say "systolic blood pressure", and every count of how often a concept was
     picked is inflated by exactly that much.
   · Despite the name, build returns not one table but **two things — the table
     and the list of columns it dropped**. That disagrees with the return
     annotation written above the function (pd.DataFrame).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from memstara.paths import DEFAULT_OUTPUT_DIR

OUT_DIR = DEFAULT_OUTPUT_DIR

OUTCOME = "Diabetes"      # what we are trying to predict — has diabetes or not
MIN_AGE = 20              # adults only
MAX_MISSING = 0.30        # discard a column more than 30% blank

# Dropped for the reasons in the module docstring. The two lists are different
# in kind: DROP_IDENTIFIERS is **things that are not measurements** (a serial
# number, the survey year), DROP_RESTATEMENTS is **a column saying again what
# another column already says**.
DROP_IDENTIFIERS = ["ID", "SurveyYr"]
DROP_RESTATEMENTS = [
    "BMI_WHO", "AgeDecade", "BMICatUnder20yrs",   # BMI and Age rewritten as bands
    "BPSys1", "BPDia1", "BPSys2", "BPDia2", "BPSys3", "BPDia3",  # the average is its own column
    "HHIncome",        # HHIncomeMid is the same thing as a number
                       # the same household income written as a band string
    "Length", "HeadCirc",  # infant measurements; empty for adults
                       # once adults only, these are blank all the way down
    "Smoke100n",       # restatement of Smoke100
                       # the same question, worded differently
]


def build(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Adults with a known outcome, measurement columns only.

    It returns **two** things — the cleaned table, and the names of the columns
    dropped for being too empty. The list comes back so that main() can print it:
    without a record of what disappeared quietly, there is no way to explain a
    column count that does not add up later.

    (The return annotation above says only a table, which does not match. It has
    no effect on what runs.)
    """
    # Adults (20 and over) whose outcome is not blank. The .copy() is so that the
    # edits below do not reach back into the caller's raw frame.
    df = raw[(raw["Age"] >= MIN_AGE) & raw[OUTCOME].notna()].copy()

    # Drop only what is actually there — a name on the list that the raw file does
    # not have must not raise.
    df = df.drop(columns=[c for c in DROP_IDENTIFIERS + DROP_RESTATEMENTS if c in df.columns])

    # Columns that are mostly blank cannot support a model, and leaving them in lets the
    # hypothesis stage pick something that quietly becomes a column of NaNs — which only
    # shows up after it has been picked, by which point a trial has already been spent.
    # The outcome itself is exempt from this check.
    missing = df.isna().mean()
    too_empty = sorted(missing[missing > MAX_MISSING].index.difference([OUTCOME]))
    df = df.drop(columns=too_empty)

    # Yes/No -> 1/0. The ML tool expects a numeric target.
    df[OUTCOME] = (df[OUTCOME].astype(str) == "Yes").astype(int)

    # Move the outcome last, the way the synthetic dataset has it. Keeping the column
    # order the same across datasets means a person reads the table the same way even
    # when the data underneath changes.
    cols = [c for c in df.columns if c != OUTCOME] + [OUTCOME]
    return df[cols], too_empty


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(OUT_DIR / "nhanes_raw.csv"),
                    help="CSV exported from NHANES.rda")
    ap.add_argument("--out", default=str(OUT_DIR / "nhanes_adult.csv"))
    args = ap.parse_args()

    # R has to produce the raw CSV first. If it is not there, stop here and say how.
    raw_path = Path(args.raw)
    if not raw_path.exists():
        print(f"not found: {raw_path}\n  export it from R first — see the module docstring",
              file=sys.stderr)
        return 1

    # low_memory=False: stops pandas from guessing a different dtype per chunk when a
    # column mixes numbers and text.
    raw = pd.read_csv(raw_path, low_memory=False)
    df, too_empty = build(raw)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    n_pos = int(df[OUTCOME].sum())
    print(f"  raw            {len(raw):,} rows x {raw.shape[1]} cols")
    print(f"  adult, known   {len(df):,} rows")
    print(f"  dropped over {MAX_MISSING:.0%} missing: "
          f"{', '.join(too_empty) if too_empty else 'none'}")
    print(f"  columns left   {df.shape[1] - 1} + {OUTCOME}")
    print(f"  {OUTCOME}       {n_pos:,} positive / {len(df) - n_pos:,} negative  "
          f"({n_pos / len(df):.1%})")
    print(f"  ->             {args.out}")

    # A column that is entirely one value teaches a model nothing and wastes a pick —
    # one of the 3-8 slots the hypothesis stage has. Warn rather than drop: whether it
    # should go is for someone who knows the data to decide.
    constant = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]
    if constant:
        print(f"  ! single-valued columns: {constant}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
