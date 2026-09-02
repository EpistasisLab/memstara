#!/usr/bin/env python3
"""Generate a synthetic dataset and a sample OKF bundle. Run once.

There is no real dataset and no real OKF bundle yet, so this makes both, which is
what lets the pipeline be validated now. When real data arrives, point
MEMSTARA_DATASET_PATH and AGENTIC_OKF_BUNDLE_DIR at it — the pipeline code does not
change.

Two properties of this data are deliberate, and the pipeline is worthless without
them.

**Column names are opaque codes.** Everything is an NHANES-style identifier —
LBXGH, BMXBMI, BPXSY1 — including the non-predictive columns. An earlier version
named them bmi / hba1c / noise_01, which let the hypothesis agent pick correctly
from the names alone and reduced the knowledge source to after-the-fact
justification. Opaque codes mean the ONLY route from a column to its meaning runs
through OKF.

**The knowledge source offers more candidates than a hypothesis can use.** Roughly
18 of the dataset's columns are described by a concept, but only six carry signal.
With the agent limited to 3-8 columns it has to choose, so different perspectives
select different subsets — which is the precondition for overlap across trials to
carry any information. If OKF pointed only at the six real ones, "take everything
OKF mentions" would win trivially and every trial would return the same set.

A real signal is still planted: LBXGH / BMXBMI / RIDAGEYR / BPXSY1 genuinely predict
the outcome. Measured one at a time the univariate AUC is 0.73 / 0.66 / 0.63 / 0.60,
against 0.51 for a noise column — a coin toss. If those four rise to the top of an
aggregate, the pipeline works. It is **an exam paper that comes with its answer key**.

Usage::

    python -m memstara.prep.sample
    python -m memstara.prep.sample --rows 1700 --seed 42

This file makes **one sheet of fake clinical data (dataset.csv)** and **one fake
bundle of knowledge (an OKF bundle, 31 .md files)** in a single go and puts them under
outputs/. Real data and a real knowledge bundle do not exist yet, so validating the
pipeline now means inventing both. When the real ones arrive, only the two environment
variables (MEMSTARA_DATASET_PATH, AGENTIC_OKF_BUNDLE_DIR) are pointed at them; the
pipeline code is not touched.

There are three functions.

    build_dataset(n_rows, seed)       makes one table (a dataframe). It draws the
                                      columns first, then combines six of them into
                                      the outcome variable Y
    write_okf_bundle(okf_dir, stamp)  writes the 31 concepts as 31 markdown files,
                                      with index.md and log.md added on top
    main()                            reads the arguments, calls the two above, and
                                      prints a summary

Easy to miss:

  1. **The answer is planted on purpose.** hba1c (LBXGH) · bmi (BMXBMI) · age
     (RIDAGEYR) · systolic pressure (BPXSY1) genuinely predict Y. Measured on their
     own the univariate AUC is 0.73 / 0.66 / 0.63 / 0.60, against 0.51 for a noise
     column — a coin toss. Because the answer is fixed, "did the pipeline find the
     right one" can be scored. That is why this file exists.
  2. **Column names were made opaque on purpose.** From a code like LBXGH alone
     there is no telling that it is glycated haemoglobin. Only if the one route to
     meaning is OKF does whether the agent actually read OKF show up in the result.
     (reviewer's real cohort, though, has column names a person can read. This
     encoding is a device used in the synthetic data only, not a property of the
     real data.)
  3. **This bundle is flat.** No per-domain subfolders — the 31 .md files sit at the
     root as they are. A bundle with a hierarchy has not been tried yet.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from memstara.paths import DEFAULT_OUTPUT_DIR

OUT_DIR = DEFAULT_OUTPUT_DIR
# Bundle folders are named okf_<source>_<what it holds> so the folder name alone
# says where the knowledge came from — see outputs/README.md. Here it is
# `okf_synthetic_sample` — a sample made up synthetically.
#
# This bundle is **flat**: no per-domain subfolders, just the 31 .md files sitting
# in the root. Whether a bundle split across folders also works has not been checked.
OKF_DIR = OUT_DIR / "okf_synthetic_sample"
DATASET = OUT_DIR / "dataset.csv"

Y_COLUMN = "outcome"
# The name of the column being predicted. It holds 0 or 1.

# Columns that actually generate Y, and their weights. These four are the answer this
# file plants, and the standard the pipeline is scored against. A larger weight means
# a stronger hand in Y — LBXGH (1.10) is the strongest, BPXSY1 (0.60) the weakest.
TRUE_SIGNAL: dict[str, float] = {
    "LBXGH": 1.10,      # glycated haemoglobin
    "BMXBMI": 0.90,     # body mass index
    "RIDAGEYR": 0.70,   # age in years
    "BPXSY1": 0.60,     # systolic blood pressure
}
# Contribute only weakly — there to see whether the aggregate separates strong from
# weak rather than merely present from absent. They should be picked up, but they
# should rank below the four in TRUE_SIGNAL.
WEAK_SIGNAL: dict[str, float] = {
    "LBDLDL": 0.25,     # LDL cholesterol
    "LBXCRP": 0.20,     # C-reactive protein
}

# Non-predictive, but indistinguishable from the above by name. Each is drawn from a
# plausible clinical distribution so that inspecting values gives nothing away
# either. Naming these VAR_001... would put the old giveaway back in a new costume.
#
#   code -> (mean, sd, low, high, decimals)
#
# Read one row like this: BPXDI1 is drawn from a normal distribution with mean 74 and
# standard deviation 11, clipped so it never leaves 40-120, and rounded to 0 decimals.
DECOY_COLUMNS: dict[str, tuple[float, float, float, float, int]] = {
    "BPXDI1": (74, 11, 40, 120, 0),        # diastolic blood pressure
    "BMXWAIST": (98, 15, 55, 160, 1),      # waist circumference
    "BMXHT": (167, 10, 140, 200, 1),       # standing height
    "LBXTC": (190, 38, 90, 340, 0),        # total cholesterol
    "LBDHDD": (53, 15, 20, 120, 0),        # HDL cholesterol
    "LBXTR": (135, 70, 30, 600, 0),        # triglycerides
    "LBXSAL": (4.2, 0.35, 2.5, 5.5, 2),    # serum albumin
    "LBXSATSI": (24, 11, 5, 120, 0),       # alanine aminotransferase
    "LBXSASSI": (23, 9, 6, 110, 0),        # aspartate aminotransferase
    "LBXSCR": (0.9, 0.25, 0.3, 3.0, 2),    # serum creatinine
    "LBXSUA": (5.5, 1.4, 2.0, 12.0, 1),    # uric acid
    "LBXWBCSI": (7.2, 2.0, 2.0, 18.0, 1),  # white blood cell count
    "LBXHGB": (14.0, 1.5, 8.0, 19.0, 1),   # haemoglobin
    "LBXPLTSI": (250, 60, 80, 500, 0),     # platelet count
    "LBXSNASI": (139, 2.5, 128, 150, 0),   # serum sodium
    "LBXSKSI": (4.1, 0.4, 2.8, 6.0, 1),    # serum potassium
    "URXUMA": (18, 45, 1, 900, 1),         # urinary albumin
    "LBXSTB": (0.7, 0.3, 0.1, 3.0, 2),     # total bilirubin
}

# Extra unnamed noise, to keep the column count up without inventing more codes that
# would need concepts written for them. Sixteen more columns, XVAR001 ... XVAR016,
# numbered noise. No concept describes any of them, so they are columns the agent can
# never reach by way of the OKF.
N_UNLABELLED_NOISE = 16


def build_dataset(n_rows: int, seed: int) -> pd.DataFrame:
    """Build a synthetic table shaped like clinical data.

    Precise realism is not the goal — recovering the planted variables is — so each
    variable only has to be plausible. A cohort whose mean age is 58 does not have to
    match any real hospital exactly.

    Args:
        n_rows: how many rows (patients) to make.
        seed: the random seed. The same value always produces the same table.

    Returns:
        A dataframe including the outcome column `outcome`.
    """
    # A generator with a fixed seed. The same seed gives the same sequence of numbers,
    # so a re-run produces the same data it did yesterday — which is the precondition
    # for comparing results at all.
    rng = np.random.default_rng(seed)

    # The four true signals plus the two weak ones. These values imitate the ranges
    # commonly seen in a real adult cohort. `.clip(low, high)` cuts off the values the
    # tails of a normal distribution produce that could not be real — a BMI of 3, an
    # age of -4.
    df = pd.DataFrame(
        {
            "RIDAGEYR": rng.normal(58, 13, n_rows).clip(18, 95).round(0),
            "BMXBMI": rng.normal(28.5, 5.8, n_rows).clip(15, 55).round(1),
            "LBXGH": rng.normal(6.1, 1.3, n_rows).clip(4.0, 14.0).round(1),
            "BPXSY1": rng.normal(131, 18, n_rows).clip(85, 210).round(0),
            "LBDLDL": rng.normal(115, 33, n_rows).clip(35, 260).round(0),
            "LBXCRP": rng.lognormal(0.4, 0.9, n_rows).clip(0.1, 60).round(2),
        }
    )

    # Decoys — described by OKF concepts, so the agent can find them, but unrelated to
    # Y, because they appear nowhere in the formula that builds it below.
    for code, (mean, sd, low, high, dec) in DECOY_COLUMNS.items():
        df[code] = rng.normal(mean, sd, n_rows).clip(low, high).round(dec)

    # Unlabelled noise — no concept describes these. Pure random numbers, mean 0 and
    # standard deviation 1.
    for i in range(1, N_UNLABELLED_NOISE + 1):
        df[f"XVAR{i:03d}"] = rng.normal(0, 1, n_rows).round(3)

    # Y: standardise the signal columns and combine them logistically. **This is where
    # the answer gets planted.** In order:
    #
    #   1. `logit` starts at -0.30. That value roughly sets the overall positive rate
    #      (negative, so a little under half).
    #   2. Each of the six signal columns is **standardised** — subtract the mean,
    #      divide by the standard deviation, turning it into "how many standard
    #      deviations from the mean (z)". This is so values in different units
    #      (%, kg/m^2, mmHg) can be measured on one ruler.
    #   3. Each z is multiplied by its weight and added. LBXGH, with the largest
    #      weight, moves Y the most.
    #   4. The logistic function 1/(1+e^-logit) turns the sum into a **probability**
    #      between 0 and 1.
    #   5. A coin is flipped with that probability to decide 0 or 1. Because there is
    #      a second flip rather than using the probability directly, an imperfect,
    #      realistic amount of noise is left in — which is why AUC settles near 0.7
    #      rather than 1.0.
    #
    # The decoy columns and the XVAR noise appear nowhere in this formula. That is what
    # makes them non-predictive.
    logit = np.full(n_rows, -0.30)
    for col, weight in {**TRUE_SIGNAL, **WEAK_SIGNAL}.items():
        z = (df[col] - df[col].mean()) / df[col].std()
        logit += weight * z
    prob = 1.0 / (1.0 + np.exp(-logit))
    df[Y_COLUMN] = (rng.random(n_rows) < prob).astype(int)

    return df


# --------------------------------------------------------------------------- #
#  OKF bundle
# --------------------------------------------------------------------------- #
#
# Each entry: (id, type, title, tags, variables, description, body)
#
# `variables` is the code-to-concept mapping and the reason this design works.
# get_concept returns the whole frontmatter (mcp_servers/okf.py:331), so the key
# survives — but search_concepts and list_concepts return only id/type/title/tags.
# An agent can therefore FIND a concept by searching, and can only learn which column
# it refers to by opening it. Reading the knowledge source is unavoidable.
#
# Four kinds are mixed together:
#   1. Signal    — map to columns that genuinely predict Y
#   2. Decoy     — map to real columns with no predictive value
#   3. Trap      — map to codes absent from the dataset
#   4. Metadata  — map to nothing (a cohort description, a measurement protocol)
#
# One entry is a 7-slot tuple:
#   (id, type, title, tags, variable codes, one-line description, body)
#
# A Trap concept is the interesting one: picking it produces the situation "the concept
# exists but the column does not", which is how it becomes visible whether the pipeline
# survives that or reports it properly.

_CONCEPTS: list[tuple[str, str, str, list[str], list[str], str, str]] = [
    # -- 1. Signal -------------------------------------------------------
    #
    # Six signal concepts. The first four (glycemic_control, obesity_adiposity,
    # hypertension_systolic, aging_demographics) point at TRUE_SIGNAL; the last two
    # (lipid_ldl, inflammatory_burden) point at WEAK_SIGNAL. The clinical prose in the
    # bodies is written close to the facts, but it does not hand over the answer by
    # itself — the agent still has to choose among candidates.
    (
        "glycemic_control",
        "risk_factor",
        "Glycemic control and adverse outcome risk",
        ["metabolic", "diabetes", "strong-evidence"],
        ["LBXGH"],
        "Glycated haemoglobin is the most consistently reported correlate of outcome risk across cohorts.",
        "Glycated haemoglobin reflects average blood glucose over the preceding two to three "
        "months. Observational studies repeatedly find outcome risk rising monotonically with "
        "each percentage point, and an independent contribution persists after adjusting for "
        "other metabolic markers.\n\n"
        "Related: [adiposity](obesity_adiposity), [inflammation](inflammatory_burden)",
    ),
    (
        "obesity_adiposity",
        "risk_factor",
        "Adiposity as a modifiable risk factor",
        ["metabolic", "anthropometric", "strong-evidence"],
        ["BMXBMI"],
        "Body mass index is the archetypal modifiable factor raising outcome risk through metabolic pathways.",
        "Body mass index is derived from height and weight and is present in almost every "
        "clinical record. It acts on outcome through insulin resistance and chronic "
        "inflammation. It overlaps with glycaemic markers but retains independent explanatory "
        "power.\n\nRelated: [glycemic control](glycemic_control)",
    ),
    (
        "hypertension_systolic",
        "risk_factor",
        "Systolic blood pressure and vascular risk",
        ["cardiovascular", "vital-sign", "strong-evidence"],
        ["BPXSY1"],
        "Systolic pressure indexes vascular load and is associated with outcome.",
        "Systolic blood pressure is a basic element of cardiovascular risk stratification. In "
        "older populations the systolic value discriminates outcome better than the diastolic "
        "one. Single readings vary considerably.",
    ),
    (
        "aging_demographics",
        "risk_factor",
        "Chronological age as a baseline risk axis",
        ["demographic", "baseline", "strong-evidence"],
        ["RIDAGEYR"],
        "Age explains baseline risk in nearly every outcome model.",
        "Age correlates broadly with the other risk factors, so omitting it inflates their "
        "apparent effects. For prediction it carries substantial explanatory power on its own.",
    ),
    (
        "lipid_ldl",
        "risk_factor",
        "LDL cholesterol in risk models",
        ["cardiovascular", "laboratory", "moderate-evidence"],
        ["LBDLDL"],
        "LDL cholesterol is associated with cardiovascular outcome, though the effect is moderate.",
        "LDL cholesterol has been studied for decades, but its independent contribution often "
        "shrinks once other metabolic markers enter the model. Statin use is a common "
        "confounder.",
    ),
    (
        "inflammatory_burden",
        "biomarker",
        "Systemic inflammation",
        ["inflammation", "laboratory", "moderate-evidence"],
        ["LBXCRP"],
        "C-reactive protein reflects systemic inflammatory burden and shows a weak association with outcome.",
        "C-reactive protein is heavily skewed, so a log transform is customary. It rises sharply "
        "during acute infection, which makes a single reading hard to interpret.",
    ),
    # -- 2. Decoys — real columns, no predictive value --------------------
    #
    # 16 decoy concepts. The column each one points at really is in the data, and the
    # description is clinically sensible, but none of them has anything to do with Y.
    # They are what stops an agent from winning by "take everything the OKF mentions":
    # with these present, it has to actually choose.
    (
        "diastolic_pressure",
        "risk_factor",
        "Diastolic blood pressure",
        ["cardiovascular", "vital-sign"],
        ["BPXDI1"],
        "Diastolic pressure is part of the standard blood pressure pair.",
        "Diastolic pressure is recorded alongside systolic. Its prognostic value is weaker in "
        "older cohorts, where arterial stiffening lowers it while risk rises.",
    ),
    (
        "central_adiposity",
        "risk_factor",
        "Waist circumference as central adiposity",
        ["metabolic", "anthropometric"],
        ["BMXWAIST"],
        "Waist circumference is proposed as a measure of central fat distribution.",
        "Waist circumference is argued to capture visceral fat better than body mass index. "
        "Measurement protocols differ between studies, which limits comparability.",
    ),
    (
        "stature",
        "descriptor",
        "Standing height",
        ["anthropometric"],
        ["BMXHT"],
        "Standing height, a component of body mass index.",
        "Height is recorded as a component of body mass index. On its own it is rarely treated "
        "as a risk factor.",
    ),
    (
        "total_cholesterol",
        "risk_factor",
        "Total cholesterol",
        ["cardiovascular", "laboratory"],
        ["LBXTC"],
        "Total cholesterol aggregates the lipid fractions into one figure.",
        "Total cholesterol sums the lipid fractions and so obscures the opposing directions of "
        "the HDL and LDL components. Fraction-specific measures are usually preferred.",
    ),
    (
        "hdl_cholesterol",
        "risk_factor",
        "HDL cholesterol",
        ["cardiovascular", "laboratory"],
        ["LBDHDD"],
        "HDL cholesterol is conventionally described as protective.",
        "HDL cholesterol is inversely associated with cardiovascular events in observational "
        "data, though trials raising it have not reduced events.",
    ),
    (
        "triglycerides",
        "risk_factor",
        "Serum triglycerides",
        ["metabolic", "laboratory"],
        ["LBXTR"],
        "Triglycerides reflect recent dietary intake as much as chronic state.",
        "Triglycerides vary strongly with fasting status and recent meals, so a single "
        "measurement is noisy.",
    ),
    (
        "serum_albumin",
        "biomarker",
        "Serum albumin",
        ["laboratory", "nutrition"],
        ["LBXSAL"],
        "Albumin is used as a nutritional and hepatic synthetic marker.",
        "Albumin falls in inflammation and in liver disease, so it is nonspecific as a marker of "
        "any one condition.",
    ),
    (
        "liver_enzymes",
        "biomarker",
        "Hepatic transaminases",
        ["laboratory", "hepatic"],
        ["LBXSATSI", "LBXSASSI"],
        "Alanine and aspartate aminotransferase indicate hepatocellular injury.",
        "The transaminases rise with hepatocellular injury of any cause. Their ratio is sometimes "
        "used to suggest aetiology, with weak discrimination.",
    ),
    (
        "renal_function",
        "biomarker",
        "Serum creatinine",
        ["laboratory", "renal"],
        ["LBXSCR"],
        "Creatinine is the routine index of glomerular filtration.",
        "Creatinine depends on muscle mass as well as filtration, so it misclassifies at the "
        "extremes of body composition.",
    ),
    (
        "uric_acid",
        "biomarker",
        "Serum uric acid",
        ["laboratory", "metabolic"],
        ["LBXSUA"],
        "Uric acid has been proposed as a cardiometabolic marker.",
        "Uric acid is associated with metabolic syndrome components, but whether the association "
        "is causal remains contested.",
    ),
    (
        "leukocyte_count",
        "biomarker",
        "White blood cell count",
        ["laboratory", "inflammation"],
        ["LBXWBCSI"],
        "Leukocyte count is a coarse inflammatory index.",
        "White cell count rises in infection, in smoking and under stress, making it a blunt "
        "inflammatory marker compared with specific acute-phase proteins.",
    ),
    (
        "haemoglobin",
        "biomarker",
        "Haemoglobin concentration",
        ["laboratory", "haematology"],
        ["LBXHGB"],
        "Haemoglobin defines anaemia and varies with sex.",
        "Haemoglobin is used to define anaemia. Thresholds differ by sex, so an unadjusted value "
        "is hard to interpret.",
    ),
    (
        "platelets",
        "biomarker",
        "Platelet count",
        ["laboratory", "haematology"],
        ["LBXPLTSI"],
        "Platelet count relates to thrombotic and inflammatory states.",
        "Platelet count is elevated as an acute-phase response and reduced in hypersplenism, so "
        "it moves for many unrelated reasons.",
    ),
    (
        "electrolytes",
        "biomarker",
        "Serum sodium and potassium",
        ["laboratory"],
        ["LBXSNASI", "LBXSKSI"],
        "Sodium and potassium are the routine electrolyte pair.",
        "Electrolytes are tightly regulated, so values outside the reference range usually "
        "reflect acute illness or medication rather than chronic risk.",
    ),
    (
        "urinary_albumin",
        "biomarker",
        "Urinary albumin",
        ["laboratory", "renal"],
        ["URXUMA"],
        "Urinary albumin indicates glomerular leakage.",
        "Urinary albumin is highly variable between collections, so single untimed samples are "
        "unreliable.",
    ),
    (
        "bilirubin",
        "biomarker",
        "Total bilirubin",
        ["laboratory", "hepatic"],
        ["LBXSTB"],
        "Bilirubin reflects haem turnover and hepatic conjugation.",
        "Bilirubin rises in haemolysis and in hepatic dysfunction, and is mildly elevated in "
        "Gilbert syndrome, which is benign and common.",
    ),
    # -- 3. Traps — codes absent from the dataset -------------------------
    #
    # 4 trap concepts. Physical activity, sodium intake, sleep, income — all clinically
    # plausible, all of them variables that turn up in real papers. But the matching
    # column is **not in this dataset**. The "not present in every dataset" line at the
    # end of each body is the only warning. If an agent picks one, the pipeline is asked
    # for a column that does not exist, and what it does next — pass over it quietly, or
    # report it properly — is exactly what this is here to reveal (it lands in the
    # summary's `columns_missing_seen`).
    (
        "physical_activity",
        "risk_factor",
        "Weekly physical activity volume",
        ["lifestyle", "behavioral"],
        ["PAQ620"],
        "Weekly minutes of moderate activity are repeatedly reported to lower outcome risk.",
        "Activity volume shows a protective effect across cohorts, though self-report introduces "
        "considerable measurement error.\n\n"
        "**Note**: this variable is not present in every dataset.",
    ),
    (
        "dietary_sodium",
        "risk_factor",
        "Dietary sodium intake",
        ["lifestyle", "nutrition"],
        ["DR1TSODI"],
        "Daily sodium intake is thought to affect outcome through blood pressure.",
        "Twenty-four-hour urinary excretion is the reference measurement but is almost never "
        "present in clinical records.\n\n"
        "**Note**: this variable is not present in every dataset.",
    ),
    (
        "sleep_quality",
        "risk_factor",
        "Sleep duration and efficiency",
        ["lifestyle", "behavioral"],
        ["SLD012"],
        "Reduced sleep efficiency has been linked to worse metabolic outcomes.",
        "Sleep efficiency is measured by actigraphy or polysomnography. Most studies are small, "
        "so the evidence is weak.\n\n"
        "**Note**: this variable is not present in every dataset.",
    ),
    (
        "socioeconomic_status",
        "risk_factor",
        "Socioeconomic position",
        ["demographic", "social"],
        ["INDFMPIR"],
        "Income-to-poverty ratio is frequently named as a social determinant of outcome.",
        "Income position acts on outcome through access to care and health behaviours. "
        "Definitions differ between cohorts.\n\n"
        "**Note**: this variable is not present in every dataset.",
    ),
    # -- 4. Metadata — map to nothing -------------------------------------
    #
    # 3 metadata concepts. `variables` is empty, so they point at no column at all.
    # Cohort composition, measurement protocol, missingness pattern — documents that give
    # **context** but are no basis for choosing a variable. Real bundles have documents
    # like these mixed in with the rest, so they are here to see what an agent does when
    # one comes back in its search results.
    (
        "cohort_description",
        "metadata",
        "Cohort composition",
        ["study-design"],
        [],
        "Summary of the cohort this bundle refers to.",
        "A retrospective cohort of adult outpatients. Children and pregnant patients were "
        "excluded. Context, not grounds for selecting a variable.",
    ),
    (
        "measurement_protocol",
        "metadata",
        "Measurement protocol notes",
        ["study-design", "quality"],
        [],
        "How and when measurements were taken.",
        "Blood was drawn fasting. Blood pressure is the mean of two seated readings after five "
        "minutes of rest. Not grounds for selecting a variable.",
    ),
    (
        "missingness_notes",
        "metadata",
        "Missingness patterns",
        ["quality"],
        [],
        "Observations about the pattern of missing values.",
        "Laboratory tests are ordered on clinical indication, so missingness is unlikely to be at "
        "random. Not grounds for selecting a variable.",
    ),
]

_TRAP_IDS = {"physical_activity", "dietary_sodium", "sleep_quality", "socioeconomic_status"}
# The ids of the trap concepts, collected here so that a later step can decide whether a
# given trial took the bait.


def write_okf_bundle(okf_dir: Path, stamp: str) -> None:
    """Write the concepts as OKF-shaped markdown files.

    One concept becomes one file, named `<concept id>.md`. Each file has two parts.

      - Frontmatter: the YAML between the two `---` lines at the top. The keys core's
        OKF server actually reads are type / title / description / tags / generated /
        status, with `variables` added on top. The server does not interpret
        `variables`, but get_concept passes it back untouched, so an agent that opens
        the concept does see it.
      - Body: a `#` heading and the descriptive paragraphs.

    Args:
        okf_dir: the folder to write the files into. Created if it does not exist.
        stamp: the timestamp string to put in the frontmatter's `generated.at`.
    """
    okf_dir.mkdir(parents=True, exist_ok=True)

    # Unpack each 7-slot tuple and assemble it into one markdown string.
    for cid, ctype, title, tags, variables, description, body in _CONCEPTS:
        # Lay the tags out as a YAML list, one "  - tag" per line.
        tag_lines = "\n".join(f"  - {t}" for t in tags)
        # The metadata concepts have an empty `variables`. When it is empty the key is
        # left out entirely — an empty list leaves room to be read as "the list is
        # empty" rather than "this points at no column".
        var_block = ""
        if variables:
            var_lines = "\n".join(f"  - {v}" for v in variables)
            var_block = f"variables:\n{var_lines}\n"
        text = (
            "---\n"
            f"type: {ctype}\n"
            f"title: {title}\n"
            f"description: {description}\n"
            "tags:\n"
            f"{tag_lines}\n"
            f"{var_block}"
            "generated:\n"
            "  by: process:make_sample_data\n"
            f"  at: {stamp}\n"
            "status: draft\n"
            "---\n\n"
            f"# {title}\n\n"
            f"{body}\n"
        )
        (okf_dir / f"{cid}.md").write_text(text, encoding="utf-8")

    # index.md (the table of contents) and log.md (the change record) are the spec's
    # special files. The OKF server does not count either as a concept
    # (_RESERVED_ROOT_STEMS), so writing them cannot pollute search results — the count
    # stays at 31 concepts.
    listing = "\n".join(f"- [{t}]({c}) — {d}" for c, _tp, t, _tg, _v, d, _b in _CONCEPTS)
    (okf_dir / "index.md").write_text(
        f"# Sample OKF bundle\n\nSynthetic bundle holding {len(_CONCEPTS)} concepts.\n\n{listing}\n",
        encoding="utf-8",
    )
    (okf_dir / "log.md").write_text(
        f"# Change log\n\n- {stamp} · process:make_sample_data · bundle created "
        f"({len(_CONCEPTS)} concepts)\n",
        encoding="utf-8",
    )


def main() -> int:
    """Take the command-line arguments, build the dataset and the OKF bundle, and report
    what was made.

    Returns:
        The exit code. Always 0 (success).
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1700, help="dataset row count")
    ap.add_argument("--seed", type=int, default=42)
    # Taken as an argument rather than read from the clock. Reading the clock would make
    # the files differ on every run, so a diff would show a change where the content is
    # the same. Fixed by an argument, a re-run produces **byte-identical** output.
    ap.add_argument("--stamp", default="2026-08-10T00:00:00Z", help="OKF generated.at timestamp")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Build the table, save it as a CSV, then write the concept files.
    df = build_dataset(args.rows, args.seed)
    df.to_csv(DATASET, index=False)
    write_okf_bundle(OKF_DIR, args.stamp)

    # The next three lines are a cross-check. Collect every column code the concepts
    # mention (described), then split it into the ones that really are in the data
    # (in_data) and the ones that are not (absent = the traps). `c[4]` is the fifth slot
    # of the 7-slot tuple, which is `variables`.
    described = {v for c in _CONCEPTS for v in c[4]}
    in_data = described & set(df.columns)
    absent = described - set(df.columns)

    # What follows is a summary printed for a person to read. It does give away which
    # columns are signal and which are decoys, but the output stays in the terminal and
    # never reaches an agent.
    print(f"dataset: {DATASET}")
    print(f"  {len(df)} rows x {len(df.columns)} columns (Y included)")
    print(f"  Y='{Y_COLUMN}' positive rate: {df[Y_COLUMN].mean():.1%}")
    print(f"  true signal  : {', '.join(TRUE_SIGNAL)}")
    print(f"  weak signal  : {', '.join(WEAK_SIGNAL)}")
    print(f"  decoys       : {len(DECOY_COLUMNS)} described, non-predictive")
    print(f"  unlabelled   : XVAR001 ... XVAR{N_UNLABELLED_NOISE:03d}")
    print()
    print(f"OKF bundle: {OKF_DIR}")
    print(f"  {len(_CONCEPTS)} concepts + index.md + log.md")
    print(f"  describing {len(in_data)} columns that exist, {len(absent)} that do not (traps)")
    print()
    # This single line is the whole design intent of this dataset: a column name carries
    # no meaning of its own, and OKF is the only route from a code to what it means.
    print("Column names carry no meaning — the only route from a code to its meaning is OKF.")
    print()
    # What to do next. Exporting the three variables below is what lets the pipeline find
    # the dataset and the bundle that were just written.
    print("Next — export the environment:")
    print(f'  export AGENTIC_OKF_BUNDLE_DIR="{OKF_DIR}"')
    print(f'  export MEMSTARA_DATASET_PATH="{DATASET}"')
    print(f'  export MEMSTARA_OUTPUT_DIR="{OUT_DIR}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
