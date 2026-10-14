---
type: "Literature Evidence"
title: "Diabetes Mellitus and Heart Failure."
description: "Narrative review: diabetes raises new-onset HF risk (pooled RR 2.14 across 69 studies; HbA1c +1% ups HF risk 30% in T1DM, 8% in T2DM); HF also causes new T2DM; SGLT2i prevent both."
resource: "https://pubmed.ncbi.nlm.nih.gov/34441977/"
domain: "metabolic-renal-comorbidity"
id: "34441977"
pmid: "34441977"
journal: "Journal of clinical medicine"
authors: "Triposkiadis F, Xanthopoulos A, Bargiota A, Kitai T, Katsiki N, Farmakis D, et al."
published: "2021"
tags: ["diabetes", "heart failure", "narrative review", "obesity", "insulin resistance", "SGLT2 inhibitors", "diabetic cardiomyopathy", "CKD"]
study_design: "Narrative review of epidemiology, pathogenesis and prevention of heart failure in diabetes and of cardiogenic diabetes"
strength: "moderate"
strength_score: "0.58"
text_basis: "full_text"
license: "CC BY"
export_safe: "true"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:33Z"}
sources: [{id: "pmid:34441977", resource: "https://pubmed.ncbi.nlm.nih.gov/34441977/"}, {id: "pmc:PMC8396967", resource: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8396967/"}, {id: "doi:10.3390/jcm10163682", resource: "https://doi.org/10.3390/jcm10163682"}]
---

# Bottom line

Diabetes is a strong, independent risk factor for new-onset HF (pooled RR 2.14), mediated by hyperglycemia, insulin resistance, obesity and comorbid HTN/CAD/CKD. The relationship is bidirectional, and SGLT-2 inhibitors are the best antidiabetic agents for preventing HF.

- **Design** — Narrative review of epidemiology, pathogenesis and prevention of heart failure in diabetes and of cardiogenic diabetes
- **Population** — Adults with type 1 or type 2 diabetes, and patients with heart failure (literature summary)
- **Outcome** — New-onset heart failure (HFpEF and HFrEF) in diabetes; no study-specific definition.
- **Read from** — the full text
- **Evidence strength** — moderate (0.58) — nothing to score on size

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Diabetes mellitus | Presence vs absence of DM; pooled across 69 studies in a meta-analysis | DM precedes new-onset HF | New-onset heart failure | association | 2.14 (1.96–2.34) | — | increases | high | moderate 0.67 | Obesity |
| 2 | Diabetes mellitus | Presence vs absence of DM; 38 studies of recurrent HF | Prior DM | Recurrent heart failure | association | 1.39 (1.33–1.45) | — | increases | high | moderate 0.68 | — |
| 3 | HbA1c (per 1% increase) | Glycated hemoglobin A1c, each 1% increase | Before HF | Heart failure risk | association | unverified | — | increases | medium | moderate 0.54 | — |
| 4 | Diabetes in women vs men (Framingham) | DM, sex-specific HF incidence | 18-year follow-up | Incident heart failure | association | higher incidence of HF in women (5-fold) than men (2.4-fold) | — | increases | medium | moderate 0.64 | — |
| 5 | Dapagliflozin vs placebo (SGLT2i) | Randomized dapagliflozin in HF patients (DAPA-HF) | During trial follow-up | Incident type 2 diabetes in HF | intervention | unverified | 0.019 | decreases | medium | moderate 0.54 | — |
| 6 | Obesity | Overweight/obesity as background for T2DM-related HF; impaired natriuretic peptide function | Precedes HF | Heart failure development | association | — | — | increases | medium | moderate 0.54 | Diabetes mellitus |
| 7 | Insulin resistance | Hallmark of T2DM; causes hyperglycemia, dyslipidemia | Precedes HF | Cardiovascular disease/HF | association | — | — | increases | low | moderate 0.54 | — |

Quoted from the paper, by row:

1. For new-onset HF, the pooled risk ratio (RR) 95% confidence interval (CI) of 69 studies that examined HF as a whole (both HF with preserved ejection fraction (HFpEF) and HF with reduced ejection fraction (HFrEF)) was 2.14 (1.96–2.34).
2. The risk magnitudes between HFpEF and HFrEF were not significantly different in studies that examined the risk in both syndromes (p = 0.86), whereas for recurrent HF, the pooled RR (95% CI) of 38 studies was 1.39 (1.33–1.45).
3. Each 1% increase in glycated hemoglobin A1c is associated with a 30% increase for risk of HF in Type 1 DM (T1DM) and an 8% increase for HF risk in T2DM, the most common type of DM occurring in approximately 90% of diabetes patients.
4. The Framingham Heart Study, which enrolled 5209 men and women who were followed up for 18 years, reported a higher incidence of HF in women (5-fold) than men (2.4-fold) with DM after adjustment for other risk factors, including age, coronary artery disease (CAD), and hypertension (HTN).
5. Incidence of new-onset type 2 diabetes mellitus (T2DM) in dapagliflozin vs. placebo groups in the Dapagliflozin and Prevention of Adverse Outcomes in Heart Failure (DAPA-HF) trial.
6. Obesity is a major risk factor for the development of T2DM, HTN, CAD, and HF.
7. Insulin resistance (IR), which is a hallmark of T2DM, contributes to the development of CV disease (Figure 4).

# Interactions

| # | Predictor | Interacts with | Type | Magnitude | Evidence |
|---|---|---|---|---|---|
| 1 | Diabetes mellitus | Obesity | correlated | stated | unverified (mirrored from row 6) |
| 6 | Obesity | Diabetes mellitus | correlated | stated | unverified |

# Null or non-significant findings

| # | Predictor | Outcome | Detail |
|---|---|---|---|
| 1 | DM type of HF (HFpEF vs HFrEF) | New-onset HF | Risk magnitudes between HFpEF and HFrEF not significantly different (p = 0.86). |
| 2 | DM vs no DM on LVEF, LV mass, RVEF | Cardiac structure (UK Biobank CMR) | No difference in LVEF, LV mass or RVEF. |

Quoted from the paper, by row:

1. The risk magnitudes between HFpEF and HFrEF were not significantly different in studies that examined the risk in both syndromes (p = 0.86), whereas for recurrent HF, the pooled RR (95% CI) of 38 studies was 1.39 (1.33–1.45).
2. Likewise, in the UK Biobank Cardiovascular Magnetic Resonance Substudy, a community cohort study which enrolled 3984 individuals without known CV disease and LVEF ≥ 50%, no difference was observed between individuals with DM and those without DM regarding, LVEF, LV mass, or RVEF, whereas LV and RV volumes (end-diastolic, stroke) as well as LA and RA emptying fractions were lower in DM.

# Vocabulary hints

- **glycated hemoglobin A1c**
- **diabetes mellitus (type 1, type 2)**
- **insulin resistance**
- **chronic kidney disease**
- **obesity**
- **dyslipidemia**

# Caveats

Narrative review without systematic search; most data are secondary citations, and the text provided is partial (prevention and cardiogenic diabetes sections are headings only). Risk estimates are from cited studies and not clearly adjusted.
