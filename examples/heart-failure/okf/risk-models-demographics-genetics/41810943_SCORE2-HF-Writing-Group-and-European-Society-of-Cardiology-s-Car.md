---
type: "Literature Evidence"
title: "Prediction of incident heart failure in individuals without prior cardiovascular disease: the SCORE2-HF risk model."
description: "SCORE2-HF, a sex-specific competing-risk model for 10- and 30-year incident HF in Europeans over 40 without CVD, derived in 25 cohorts; external validation C-indices 0.827-0.874."
resource: "https://pubmed.ncbi.nlm.nih.gov/41810943/"
domain: "risk-models-demographics-genetics"
id: "41810943"
pmid: "41810943"
journal: "European heart journal"
authors: "SCORE2-HF Writing Group and European Society of Cardiology’s Cardiovascular Risk Collaboration (CRC) Unit"
published: "2026"
tags: ["heart failure", "risk score", "SCORE2-HF", "competing risk", "external validation", "Europe", "primary prevention"]
study_design: "Individual-participant-data derivation from 25 prospective cohorts, recalibration with national statistics and linked records, and external validation in three cohorts"
strength: "strong"
strength_score: "0.71"
text_basis: "abstract"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:34Z"}
sources: [{id: "pmid:41810943", resource: "https://pubmed.ncbi.nlm.nih.gov/41810943/"}, {id: "pmc:PMC13549722", resource: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13549722/"}, {id: "doi:10.1093/eurheartj/ehag154", resource: "https://doi.org/10.1093/eurheartj/ehag154"}]
---

# Bottom line

SCORE2-HF, using age, smoking, SBP, antihypertensive treatment, BMI, eGFR and diabetes, discriminated well in three external cohorts (C-index 0.827-0.874). Estimated risk varied strongly by risk factor burden and European risk region.

- **Design** — Individual-participant-data derivation from 25 prospective cohorts, recalibration with national statistics and linked records, and external validation in three cohorts
- **Population** — European adults aged over 40 years without prior cardiovascular disease
- **Outcome** — Incident heart failure (10-year and 30-year risk, competing-risk adjusted)
- **Read from** — the abstract only
- **Evidence strength** — strong (0.71) — nothing to score on size

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | SCORE2-HF model (age, smoking, SBP, antihypertensive treatment, BMI, eGFR, type 2 diabetes incl. age at diagnosis and HbA1c) | Sex-specific competing risk-adjusted model; discrimination by C-index in external validation | Baseline predictors, 10-year and 30-year follow-up | Incident heart failure | association | unverified | — | increases | medium | strong 0.71 | — |
| 2 | Four adverse risk factors vs none (smoking, T2DM, hypertension, BMI ≥30) in 70-year-old men, low-risk region | Average 10-year SCORE2-HF risk | Baseline, 10-year risk | Incident heart failure | association | 8% vs 24% in men | — | increases | medium | moderate 0.61 | — |

Quoted from the paper, by row:

1. Results: In the three external validation cohorts, C-indices (95% confidence interval) were .827 (.824-.829), .839 (.827-.850), and .874 (.863-.884).
2. For example, in the low-risk region, the average 10-year risk for 70-year-old individuals with zero vs four adverse risk factors (smoking, type 2 diabetes mellitus, hypertension, and BMI ≥ 30 kg/m2), was 8% vs 24% in men and 6% vs 20% in women.

# Null or non-significant findings

None reported — the paper states no null or non-significant finding.

# Vocabulary hints

- **systolic blood pressure**
- **estimated glomerular filtration rate**
- **type 2 diabetes mellitus age at diagnosis and glycated haemoglobin**
- **body mass index**
- **antihypertensive treatment**

# Caveats

Only the abstract was read, so effect sizes, calibration and coefficients are not captured. Only some of the validation C-indices are recorded, and genetic and family history predictors were not included in the model.
