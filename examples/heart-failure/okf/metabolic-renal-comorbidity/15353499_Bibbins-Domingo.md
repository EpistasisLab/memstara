---
type: "Literature Evidence"
title: "Predictors of heart failure among women with coronary disease."
description: "In 2391 postmenopausal women with coronary disease (HERS), diabetes was the strongest predictor of incident heart failure (aHR 3.1); 9 predictors identified; estrogen/progestin had no effect."
resource: "https://pubmed.ncbi.nlm.nih.gov/15353499/"
domain: "metabolic-renal-comorbidity"
id: "15353499"
pmid: "15353499"
journal: "Circulation"
authors: "Bibbins-Domingo K, Lin F, Vittinghoff E, Barrett-Connor E, Hulley SB, Grady D, et al."
published: "2004"
tags: ["heart failure", "diabetes", "women", "coronary disease", "renal function", "obesity", "HERS"]
study_design: "Prospective cohort analysis of HERS randomized trial plus open-label follow-up (HERS II)"
n: "2391"
strength: "strong"
strength_score: "0.71"
text_basis: "abstract"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:33Z"}
sources: [{id: "pmid:15353499", resource: "https://pubmed.ncbi.nlm.nih.gov/15353499/"}, {id: "doi:10.1161/01.CIR.0000141726.01302.83", resource: "https://doi.org/10.1161/01.CIR.0000141726.01302.83"}]
---

# Bottom line

Among postmenopausal women with coronary disease, diabetes was the strongest of nine predictors of incident heart failure (adjusted HR 3.1), especially with poor glycemic control, renal insufficiency or obesity. Estrogen/progestin randomization was not associated with heart failure.

- **Design** — Prospective cohort analysis of HERS randomized trial plus open-label follow-up (HERS II)
- **N** — 2,391
- **Population** — Postmenopausal women with established coronary disease and no baseline heart failure, 20 US centers
- **Outcome** — Incident heart failure defined by hospital admission or death from heart failure
- **Read from** — the abstract only
- **Evidence strength** — strong (0.71)

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Diabetes | Self-reported history of diabetes on treatment | Baseline, before follow-up | Incident heart failure | association | adjusted hazard ratio=3.1; 95% CI, 2.3 to 4.2 | — | increases | high | strong 0.78 | Creatinine clearance <40 mL/min |
| 2 | Fasting glucose >300 mg/dL among diabetic women | Fasting glucose >300 vs 80 to 150 mg/dL | Baseline | Incident heart failure | association | adjusted hazard ratio=3.0; 95% CI, 1.2 to 7.5 | — | increases | high | moderate 0.62 | — |
| 3 | Creatinine clearance <40 mL/min | Creatinine clearance <40 mL/min | Baseline | Incident heart failure | association | — | — | increases | medium | strong 0.70 | Diabetes |
| 4 | Body mass index >35 kg/m2 | BMI >35 kg/m2 | Baseline | Incident heart failure | association | — | — | increases | medium | strong 0.70 | — |
| 5 | Estrogen/progestin randomization | Randomized assignment in HERS | Baseline randomization | Incident heart failure | intervention | hazard ratio=1.0; 95% CI, 0.7 to 1.3 | — | none | high | moderate 0.67 | — |

Quoted from the paper, by row:

1. Diabetes was the strongest risk factor (adjusted hazard ratio=3.1; 95% CI, 2.3 to 4.2).
2. Among diabetic women, hyperglycemia was associated with heart failure risk (adjusted hazard ratio=3.0; 95% CI, 1.2 to 7.5 for fasting glucose >300 mg/dL compared with fasting glucose 80 to 150 mg/dL).
3. Nine predictors were identified: diabetes (defined as a self-reported history of diabetes on treatment), atrial fibrillation, myocardial infarction, creatinine clearance <40 mL/min, systolic blood pressure >120 mm Hg, current smoking, body mass index >35 kg/m2, left bundle-branch block, and left ventricular hypertrophy.
4. Nine predictors were identified: diabetes (defined as a self-reported history of diabetes on treatment), atrial fibrillation, myocardial infarction, creatinine clearance <40 mL/min, systolic blood pressure >120 mm Hg, current smoking, body mass index >35 kg/m2, left bundle-branch block, and left ventricular hypertrophy.
5. Randomization to estrogen/progestin was not associated with heart failure (hazard ratio=1.0; 95% CI, 0.7 to 1.3).

# Interactions

| # | Predictor | Interacts with | Type | Magnitude | Evidence |
|---|---|---|---|---|---|
| 1 | Diabetes | Creatinine clearance <40 mL/min | modifies | stated | unverified (mirrored from row 3) |
| 3 | Creatinine clearance <40 mL/min | Diabetes | modified by | stated | unverified |

# Null or non-significant findings

| # | Predictor | Outcome | Detail |
|---|---|---|---|
| 1 | Estrogen/progestin randomization | Incident heart failure | HR 1.0 (95% CI 0.7 to 1.3) |

Quoted from the paper, by row:

1. Randomization to estrogen/progestin was not associated with heart failure (hazard ratio=1.0; 95% CI, 0.7 to 1.3).

# Vocabulary hints

- **diabetes (self-reported history on treatment)**
- **creatinine clearance <40 mL/min**
- **body mass index >35 kg/m2**
- **fasting glucose**

# Caveats

Abstract only; full multivariable model and covariates not shown. Women with coronary disease in a trial population, so generalizability is limited. Diabetes was self-reported on treatment.
