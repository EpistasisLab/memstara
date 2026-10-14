---
type: "Literature Evidence"
title: "Atrial fibrillation patterns are associated with arrhythmia progression and clinical outcomes."
description: "In the PREFER in AF registry (n=3223), permanent AF at baseline was associated with incident heart failure at 1 year versus paroxysmal AF (OR 1.80); 17% of patients progressed to more persistent AF."
resource: "https://pubmed.ncbi.nlm.nih.gov/29550771/"
domain: "arrhythmia-valvular-cardiac"
id: "29550771"
pmid: "29550771"
journal: "Heart (British Cardiac Society)"
authors: "B Schnabel R, Pecen L, Engler D, Lucerna M, Sellal JM, Ojeda FM, et al."
published: "2018"
tags: ["atrial fibrillation", "AF pattern", "permanent AF", "heart failure", "registry", "AF progression"]
study_design: "Prospective multicentre European registry (PREFER in AF prolongation) with 1-year follow-up"
n: "3223"
strength: "moderate"
strength_score: "0.59"
text_basis: "abstract"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:33Z"}
sources: [{id: "pmid:29550771", resource: "https://pubmed.ncbi.nlm.nih.gov/29550771/"}, {id: "doi:10.1136/heartjnl-2017-312569", resource: "https://doi.org/10.1136/heartjnl-2017-312569"}]
---

# Bottom line

Permanent AF versus paroxysmal AF was associated with incident heart failure at 1 year (OR 1.80, 95% CI 1.06-3.07), confirmed in the full cohort. AF progression predictors had modest discrimination (AUC 0.60).

- **Design** — Prospective multicentre European registry (PREFER in AF prolongation) with 1-year follow-up
- **N** — 3,223
- **Population** — Patients with atrial fibrillation in European registry, mean age 72, 40% women
- **Outcome** — Incident heart failure at 1-year follow-up; AF progression to more persistent type
- **Read from** — the abstract only
- **Evidence strength** — moderate (0.59) — nothing to score on adjustment

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Permanent AF at baseline (vs paroxysmal AF) | AF pattern classified as permanent vs paroxysmal at baseline | baseline, outcome at 1 year | incident heart failure at 1 year | association | OR 1.80, 95% CI 1.06 to 3.07, p=0.03 | 0.03 | increases | high | moderate 0.56 | — |

Quoted from the paper, by row:

1. Permanent AF was associated with development of heart failure at 1 year (OR 1.80, 95% CI 1.06 to 3.07, p=0.03) compared with paroxysmal AF, which was confirmed in the entire cohort.

# Null or non-significant findings

| # | Predictor | Outcome | Detail |
|---|---|---|---|
| 1 | AF progression | clinical outcomes | AF progression itself was not strongly related to outcome, apart from coronary events. |

Quoted from the paper, by row:

1. AF progression itself was not strongly related to outcome and may indicate the need to refine the current classification of AF types to enhance clinical utility.

# Vocabulary hints

- **AF pattern (paroxysmal, persistent, permanent)**
- **AF progression to more persistent types**

# Caveats

Read from abstract only; adjustment covariates for the heart failure estimate are not stated. Only 1-year follow-up and few heart failure events; AF progression model discrimination was poor (AUC 0.60). Baseline heart failure status handling is unclear.
