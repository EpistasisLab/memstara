---
type: "Literature Evidence"
title: "Heart Failure, Atrioventricular Block, and Ventricular Tachycardia in Sarcoidosis."
description: "In 22.4M California patients, sarcoidosis was the strongest predictor of incident heart failure (HR 11.2), AV block (HR 117.7) and VT (HR 26.1); ~22% of excess sarcoid mortality was explained by…"
resource: "https://pubmed.ncbi.nlm.nih.gov/33599141/"
domain: "cardiotoxic-inflammatory-environmental"
id: "33599141"
pmid: "33599141"
journal: "Journal of the American Heart Association"
authors: "Rosenthal DG, Fang CD, Groh CA, Nah G, Vittinghoff E, Dewland TA, et al."
published: "2021"
tags: ["sarcoidosis", "heart failure", "atrioventricular block", "ventricular tachycardia", "administrative data", "California", "cardiac sarcoidosis", "mortality"]
study_design: "Community-based cohort study using California OSHPD administrative databases (ambulatory surgery, ED, inpatient) 2005-2015 with Social Security Death Index linkage"
strength: "moderate"
strength_score: "0.7"
text_basis: "full_text"
license: "CC BY-NC-ND"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:34Z"}
sources: [{id: "pmid:33599141", resource: "https://pubmed.ncbi.nlm.nih.gov/33599141/"}, {id: "pmc:PMC8174291", resource: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8174291/"}, {id: "doi:10.1161/JAHA.120.017692", resource: "https://doi.org/10.1161/JAHA.120.017692"}]
---

# Bottom line

Sarcoidosis carried a far higher adjusted hazard of incident heart failure (HR 11.2) than conventional risk factors, plus huge hazards for AV block and VT. Among those with sarcoidosis, AV block and VT were the strongest predictors of HF.

- **Design** — Community-based cohort study using California OSHPD administrative databases (ambulatory surgery, ED, inpatient) 2005-2015 with Social Security Death Index linkage
- **Population** — California residents aged 21 or older with hospital, ED or ambulatory surgery encounters, 19,762 with sarcoidosis
- **Outcome** — Incident heart failure by ICD-9 codes at an encounter (acute or chronic, systolic or diastolic counted), excluding prevalent HF at first encounter
- **Read from** — the full text
- **Evidence strength** — moderate (0.70) — nothing to score on size

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Sarcoidosis | Sarcoidosis diagnosis code at any time, applied to entire follow-up | Diagnosis at any time, carried across follow-up; precedes incident HF | Incident heart failure | association | HR, 11.2; 95% CI, 10.7–11.7 | — | increases | high | strong 0.84 | — |
| 2 | Sarcoidosis | Sarcoidosis diagnosis code | Prior to incident AV block | Incident atrioventricular block | association | HR, 117.7; 95% CI, 103.3–134.0 | — | increases | high | strong 0.82 | — |
| 3 | Sarcoidosis | Sarcoidosis diagnosis code | Prior to incident VT | Incident ventricular tachycardia | association | unverified | — | increases | medium | moderate 0.70 | — |
| 4 | Sarcoidosis | Sarcoidosis diagnosis code | Precedes death | All-cause mortality | association | 2.29 times (95% CI, 2.14–2.46) | <0.001 | increases | medium | strong 0.83 | Incident HF, AV block or VT |
| 5 | Sarcoidosis | Sarcoidosis diagnosis code | Precedes transplantation | Heart transplantation | association | unverified | <0.001 | increases | medium | moderate 0.70 | — |
| 6 | Sarcoidosis | Rate comparison, per 1000 patient-years | Follow-up | Incident heart failure rate | association | 240 per 1000 patient‐years | <0.001 | increases | high | moderate 0.54 | — |
| 7 | Atrioventricular block and VT (in sarcoidosis patients) | Time-dependent diagnosis codes | Accrued before incident HF | Incident heart failure among those with sarcoidosis | association | — | — | increases | medium | moderate 0.70 | — |

Quoted from the paper, by row:

1. After adjustment for those same covariates, sarcoidosis exhibited the highest relative risk of HF (hazard ratio [HR], 11.2; 95% CI, 10.7–11.7) of any established risk factor for the disease that was measurable in this data set (Figure 2).
2. Sarcoidosis was associated with a stronger relative risk for atrioventricular block (HR, 117.7; 95% CI, 103.3–134.0) than any other measured covariate (Figure 2).
3. After adjusting for age, sex, race/ethnicity, hypertension, diabetes mellitus, coronary heart disease, obesity, atrioventricular block, VT, alcohol abuse, tobacco use, and income, those with sarcoidosis had a substantially higher risk of developing HF than the rest of the population (Figure 1).
4. After adjustment for potential confounders, those with sarcoidosis demonstrated a 2.29 times (95% CI, 2.14–2.46) increased risk of death compared with those without sarcoidosis (P<0.001).
5. After adjusting for age, sex, race/ethnicity, hypertension, diabetes mellitus, coronary heart disease, obesity, atrioventricular block, VT, alcohol abuse, tobacco use, and income, those with sarcoidosis had a substantially higher risk of developing HF than the rest of the population (Figure 1).
6. The incidence rate of HF was 240 per 1000 patient‐years in patients with sarcoidosis and 12 per 1000 patient‐years in those without sarcoidosis (P<0.001).
7. Atrioventricular block and VT were the strongest predictors of incident HF in those with sarcoidosis, while conventional cardiovascular risk factors exhibited the highest HRs in those without sarcoidosis (Figure 3).

# Interactions

| # | Predictor | Interacts with | Type | Magnitude | Evidence |
|---|---|---|---|---|---|
| 4 | Sarcoidosis | Incident HF, AV block or VT | mediated by | stated | 22% (95 CI, 18%–26%) |

# Null or non-significant findings

| # | Predictor | Outcome | Detail |
|---|---|---|---|
| 1 | Alcohol dependence | Incident HF, AV block, VT in sarcoidosis | No significant difference in sarcoidosis patients with vs without outcomes (P=0.45, 0.90, 0.26) |
| 2 | Sex | HF, AV block, VT in sarcoidosis | Female proportion did not differ significantly (P=0.14, 0.10, 0.11) |

# Vocabulary hints

- **Sarcoidosis**
- **Heart failure (acute or chronic, systolic or diastolic)**
- **Atrioventricular block (Mobitz II or third-degree)**
- **Ventricular tachycardia (sustained VT or ventricular fibrillation)**

# Caveats

Administrative ICD-9 codes without validation; HF not distinguished as chronic; surveillance/detection bias likely because sarcoidosis patients get more cardiac workup. Comorbidities carried forward from encounters, and only hospital-based patients captured.
