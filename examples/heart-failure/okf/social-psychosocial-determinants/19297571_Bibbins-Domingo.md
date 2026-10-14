---
type: "Literature Evidence"
title: "Racial differences in incident heart failure among young adults."
description: "In CARDIA (n=5115, 20y), incident HF before 50 was nearly all in blacks (~1%) vs ~0 in whites; BP, BMI, low HDL, CKD and systolic dysfunction in young adulthood predicted HF in blacks."
resource: "https://pubmed.ncbi.nlm.nih.gov/19297571/"
domain: "social-psychosocial-determinants"
id: "19297571"
pmid: "19297571"
journal: "The New England journal of medicine"
authors: "Bibbins-Domingo K, Pletcher MJ, Lin F, Vittinghoff E, Gardin JM, Arynchyn A, et al."
published: "2009"
tags: ["heart failure", "young adults", "race", "CARDIA", "hypertension", "education", "kidney disease"]
study_design: "Prospective cohort (CARDIA), Cox proportional hazards models restricted to blacks"
n: "5115"
strength: "strong"
strength_score: "0.77"
text_basis: "full_text"
license: "author_manuscript"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:34Z"}
sources: [{id: "pmid:19297571", resource: "https://pubmed.ncbi.nlm.nih.gov/19297571/"}, {id: "pmc:PMC2829671", resource: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2829671/"}, {id: "doi:10.1056/NEJMoa0807265", resource: "https://doi.org/10.1056/NEJMoa0807265"}]
---

# Bottom line

Incident HF before age 50 occurred almost exclusively in black adults (about 1% vs ~0% in whites). In blacks, young-adult diastolic BP, BMI, HDL, CKD and echo systolic dysfunction predicted HF 10-15 years later.

- **Design** — Prospective cohort (CARDIA), Cox proportional hazards models restricted to blacks
- **N** — 5,115
- **Population** — Black and white men and women aged 18-30 at baseline in four US cities, followed 20 years
- **Outcome** — Hospitalization for HF (physician diagnosis plus HF treatment) or HF-associated death (cardiovascular cause with ICD-9 428xx or 425xx contributory), adjudicated by Endpoints Committee
- **Read from** — the full text
- **Evidence strength** — strong (0.77)

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Race (black vs white) | Self-reported race | baseline, HF over 20 years | Incident heart failure | association | unverified | 0.001 | increases | high | moderate 0.57 | — |
| 2 | Diastolic blood pressure | per SD 10.0 mmHg at age 18-30, blacks | baseline, HF about 15 years later | Incident heart failure | association | 2.1 (1.4–3.1) | <0.001 | increases | high | strong 0.78 | Systolic blood pressure |
| 3 | Body mass index | per SD 5.7 kg/m2 at baseline, blacks | baseline | Incident heart failure | association | 1.4 (1.0–1.9) | 0.02 | increases | high | strong 0.80 | — |
| 4 | HDL cholesterol | per SD 13.3 mg/dL at baseline, blacks | baseline | Incident heart failure | association | 0.6 (0.4–1.0) | 0.05 | decreases | high | strong 0.77 | — |
| 5 | Chronic kidney disease | GFR<60 ml/min by MDRD at baseline | baseline | Incident heart failure | association | unverified | <0.001 | increases | medium | strong 0.73 | — |
| 6 | Lower education (less than high school vs more than) | self-reported education at baseline | baseline | Incident heart failure | association | unverified | 0.06 | increases | low | moderate 0.57 | — |
| 7 | Abnormal systolic function (EF<40%) | Year 5 echocardiogram | age 23-35, HF about 10 years later | Incident heart failure | association | unverified | <0.001 | increases | medium | strong 0.73 | — |
| 8 | Borderline systolic function (EF 40-60%) | Year 5 echocardiogram | HF about 10 years later | Incident heart failure | association | unverified | 0.02 | increases | medium | strong 0.73 | — |
| 9 | Left ventricular hypertrophy | LV mass index >=51 g/m2.7 at Year 5 | HF about 10 years later | Incident heart failure | association | unverified | 0.33 | unclear | low | strong 0.73 | — |
| 10 | Diabetes (time-varying) | FBS>=126 or medication, updated each exam | time-varying over 20 years | Incident heart failure | association | 4.9, 2.1–12 | <0.001 | increases | high | moderate 0.66 | — |

Quoted from the paper, by row:

1. In 20 years of follow-up of 5115 participants, incident HF was more common than MI (observed in 16 participants).
2. Diastolic blood pressure (mmHg)2 (per SD, 10.0 mmHg) 2.5 (1.8–3.5) < 0.001 2.1 (1.4–3.1) <0.001 Systolic blood pressure (mmHg)2 (per SD, 10.9 mmHg) 1.9 (1.4–2.6) < 0.001 Body mass index (kg/m2) (per SD, 5.7 kg/m2) 2.0 (1.6–2.5) < 0.001 1.4 (1.0–1.9) 0.02 Diabetes 6.7(2.0–22) 0.002 HDL cholesterol (mg/dL) (per SD, 13.3 mg/dL) 0.4 (0.2–0.7) < 0.001 0.6 (0.4–1.0) 0.05 LDL cholesterol (mg/dL) (per SD, 32.4 mg/dL) 1.1(0.7–1.6) 0.70 Chronic kidney disease 13.8 (3.2–59) < 0.001 19.8 (4.5–87) < 0.001 Family
3. Body mass index (kg/m2) (per SD, 5.7 kg/m2) 2.0 (1.6–2.5) < 0.001 1.4 (1.0–1.9) 0.02 Diabetes 6.7(2.0–22) 0.002 HDL cholesterol (mg/dL) (per SD, 13.3 mg/dL) 0.4 (0.2–0.7) < 0.001 0.6 (0.4–1.0) 0.05 LDL cholesterol (mg/dL) (per SD, 32.4 mg/dL) 1.1(0.7–1.6) 0.70 Chronic kidney disease 13.8 (3.2–59) < 0.001 19.8 (4.5–87) < 0.001 Family history premature coronary disease 1.6 (0.5–4.6) 0.40 Current tobacco use 1.4 (0.6–3.1) 0.41 Excessive alcohol use 0.9 (0.2–3.8) 0.88 Prior pregnancy (among women) 1.3 (0.4–3.7) 0.63
4. HDL cholesterol (mg/dL) (per SD, 13.3 mg/dL) 0.4 (0.2–0.7) < 0.001 0.6 (0.4–1.0) 0.05 LDL cholesterol (mg/dL) (per SD, 32.4 mg/dL) 1.1(0.7–1.6) 0.70 Chronic kidney disease 13.8 (3.2–59) < 0.001 19.8 (4.5–87) < 0.001 Family history premature coronary disease 1.6 (0.5–4.6) 0.40 Current tobacco use 1.4 (0.6–3.1) 0.41 Excessive alcohol use 0.9 (0.2–3.8) 0.88 Prior pregnancy (among women) 1.3 (0.4–3.7) 0.63
5. Creatinine was measured at Year 0, 10, 15, and 20; glomerular filtration rate (GFR) was estimated using the Modification of Diet in Renal Disease equation and chronic kidney disease (CKD) defined as GFR<60 ml/min.
6. Education- Less than high school 6% 13% 23% 0.03 0.31 High school graduate 21% 38% 38.5% More than high school 73% 49% 38.5% CLINICAL characteristics4 Diastolic blood pressure (mmHg) 68.4 ± 9.2 68.7 ± 9.6 78.7 ± 11.5 <0.001 <0.001 Systolic blood pressure (mmHg) 109.3 ± 109 111.4 ± 10.9 120.6 ± 10.8 <0.001 <0.001 Clinical hypertension 2% 3% 19% <0.001 <0.001 Body mass index (kg/m2) 23.6 ± 4.0 25.2 ± 5.6 32.0 ± 9.7 <0.001 0.001 Obesity 6% 16%
7. Systolic function was assessed as a continuous measure of ejection fraction (EF, in %) in 1893 participants, and as a qualitative EF rating in the remainder; we categorized systolic function as “abnormal” (EF<40% or qualitative rating abnormal), “borderline” (EF 40–60% or qualitative rating borderline) or “normal.” Left ventricular mass in grams was derived from the formula of Devereux, indexed to height in meters2.7 and expressed as left ventricular mass index (gm/m2.7).
8. Systolic function was assessed as a continuous measure of ejection fraction (EF, in %) in 1893 participants, and as a qualitative EF rating in the remainder; we categorized systolic function as “abnormal” (EF<40% or qualitative rating abnormal), “borderline” (EF 40–60% or qualitative rating borderline) or “normal.” Left ventricular mass in grams was derived from the formula of Devereux, indexed to height in meters2.7 and expressed as left ventricular mass index (gm/m2.7).
9. Left ventricular hypertrophy (LVH) was defined as left ventricular mass index ≥51 gm/m2.7, a cutpoint that has been previously validated for both blacks and whites.
10. In multivariate models, SBP (HR per 10.9 mmHg=1.7, 1.4–2.0, p<0.001) and diabetes (HR=4.9, 2.1–12, p<0.001) each remained independently associated with HF, as was DBP in models substituting DBP for SBP (HR per 10 mmHg=1.8, 1.5–2.2, p<0.001).

# Interactions

| # | Predictor | Interacts with | Type | Magnitude | Evidence |
|---|---|---|---|---|---|
| 2 | Diastolic blood pressure | Systolic blood pressure | correlated | stated | Systolic blood pressure and diastolic blood pressure are collinear |

# Null or non-significant findings

| # | Predictor | Outcome | Detail |
|---|---|---|---|
| 1 | Alcohol use | Incident heart failure | Not associated in time-varying bivariate model |
| 2 | Illicit drug use | Incident heart failure | HR 1.1, 0.5-2.4, p=0.82 |
| 3 | Myocardial infarction | Incident heart failure | No HF records noted prior or concurrent MI |
| 4 | Current tobacco use | Incident heart failure | HR 1.4 (0.6-3.1), p=0.41 |
| 5 | Sex | Incident heart failure | HR 0.9 (0.4-2.0), p=0.81 |

Quoted from the paper, by row:

1. Neither alcohol (HR=1.0, 0.4–2.5, p=0.97) nor drug use (HR=1.1, 0.5–2.4, p=0.82) was associated with HF.
2. Neither alcohol (HR=1.0, 0.4–2.5, p=0.97) nor drug use (HR=1.1, 0.5–2.4, p=0.82) was associated with HF.
3. Coronary disease was uncommon; none of the HF records noted concurrent or prior MI, and most of the cardiac catheterizations and autopsy records (8/9) noted mild or absent coronary disease.
4. Current tobacco use 27% 34% 38% 0.40 0.67 Excessive alcohol use 16% 9% 8% 0.76 1.0 Illicit drug use 52% 29% 35% 0.69 0.52 Prior pregnancy5 40% 63% 69% 0.21 0.80 ECHOCARDIOGRAPHIC characteristics6 Ejection fraction 0.63 ± 0.06 0.63 ± 0.15 0.54 ± 0.09 0.02 0.07 Systolic dysfunction7 Borderline 9% 10% 19% <0.001 <0.001 Abnormal 0.2% 0.3% 8% Left ventricular mass index (gm/m2.7) 33.5 ± 8.5 36.5 ± 9.6 47.4 ± 19.6 <0.001 <0.001 % with left ventricular hypertrophy 4%
5. Sex (% male) 47% 44% 38% 0.56 0.69 Education- Less than high school 6% 13% 23% 0.03 0.31 High school graduate 21% 38% 38.5% More than high school 73% 49% 38.5% CLINICAL characteristics4 Diastolic blood pressure (mmHg) 68.4 ± 9.2 68.7 ± 9.6 78.7 ± 11.5 <0.001 <0.001 Systolic blood pressure (mmHg) 109.3 ± 109 111.4 ± 10.9 120.6 ± 10.8 <0.001 <0.001 Clinical hypertension 2% 3% 19% <0.001 <0.001 Body mass index (kg/m2) 23.6 ± 4.0 25.2 ± 5.6

# Vocabulary hints

- **Heart failure hospitalization/death** — icd9 `428xx`, icd9 `425xx`
- **Chronic kidney disease**
- **Education**
- **Systolic dysfunction**

# Caveats

Only 27 HF events (26 in blacks), so estimates are imprecise with very wide CIs and forward selection risks overfitting. Race is a self-reported social category and no socioeconomic mediators were examined beyond education; HF outcome may be misclassified.
