---
type: "Build Log"
title: "Build log — 20261008-000746-59bb"
description: "What ran, what it found, and what it cost for run 20261008-000746-59bb."
---

# Build log — 20261008-000746-59bb

## Request

- **Prompt** — clinical predictors of chronic heart failure in adults
- **Task** — Identify and weigh the clinical, biological, behavioural, social and environmental factors that predict the development of chronic heart failure in adults, to support risk assessment.
- **Started** — 2026-10-08T00:07:48Z
- **Finished** — 2026-10-08T00:17:34Z
- **Duration** — 9m 45s
- **Abstracts** — omitted from every document by --no-abstract. Every paper was still screened and read from the text this run had; only the section is gone.

## Queries

| # | term | hits | retrieved | note |
|---|---|---|---|---|
| 1 | (("incident heart failure"[tiab] OR "new-onset heart failure"[tiab] OR "development of heart failure"[tiab]) AND ("risk factors"[tiab] OR predictors[tiab] OR "risk prediction"[tiab])) | 703 | 200 | — |
| 2 | (("incident heart failure"[tiab] OR "heart failure risk"[tiab]) AND (cohort[tiab] OR prospective[tiab]) AND (adults[tiab] OR community[tiab] OR population[tiab])) | 604 | 200 | — |
| 3 | ((hypertension[tiab] OR "blood pressure"[tiab] OR "myocardial infarction"[tiab] OR "coronary artery disease"[tiab] OR "left ventricular hypertrophy"[tiab]) AND ("incident heart failure"[tiab] OR "new-onset heart failure"[tiab])) | 851 | 200 | — |
| 4 | (("atrial fibrillation"[tiab] OR "valvular heart disease"[tiab] OR "aortic stenosis"[tiab] OR cardiomyopathy[tiab] OR myocarditis[tiab]) AND ("incident heart failure"[tiab] OR "new-onset heart failure"[tiab])) | 437 | 200 | — |
| 5 | (("diabetes mellitus"[tiab] OR obesity[tiab] OR "chronic kidney disease"[tiab] OR "insulin resistance"[tiab] OR dyslipidemia[tiab] OR "thyroid dysfunction"[tiab]) AND ("incident heart failure"[tiab] OR "new-onset heart failure"[tiab])) | 417 | 200 | — |
| 6 | (("natriuretic peptide"[tiab] OR "NT-proBNP"[tiab] OR "high-sensitivity troponin"[tiab] OR "diastolic dysfunction"[tiab] OR echocardiography[tiab] OR "C-reactive protein"[tiab]) AND ("incident heart failure"[tiab] OR "future heart failure"[tiab])) | 381 | 200 | — |
| 7 | ((smoking[tiab] OR alcohol[tiab] OR "physical activity"[tiab] OR "cardiorespiratory fitness"[tiab] OR diet[tiab] OR "sodium intake"[tiab] OR "sleep apnea"[tiab]) AND ("incident heart failure"[tiab] OR "risk of heart failure"[tiab])) | 485 | 200 | — |
| 8 | (("socioeconomic status"[tiab] OR "social determinants"[tiab] OR education[tiab] OR depression[tiab] OR "social isolation"[tiab] OR "racial disparities"[tiab] OR neighborhood[tiab]) AND ("incident heart failure"[tiab] OR "risk of heart failure"[tiab])) | 169 | 169 | — |
| 9 | ((cardiotoxicity[tiab] OR anthracycline[tiab] OR "nonsteroidal anti-inflammatory"[tiab] OR "HIV infection"[tiab] OR "air pollution"[tiab] OR "autoimmune disease"[tiab]) AND ("incident heart failure"[tiab] OR "risk of heart failure"[tiab])) | 136 | 136 | — |
| 10 | (("risk prediction"[tiab] OR "risk score"[tiab] OR "machine learning"[tiab] OR "polygenic risk"[tiab] OR "family history"[tiab] OR "sex differences"[tiab]) AND ("incident heart failure"[tiab] OR "heart failure risk"[tiab])) | 382 | 200 | — |

## Stages

| stage | papers |
|---|---|
| found | 1,905 |
| unique | 1,261 |
| screened | 400 |
| included | 327 |
| curated | 100 |
| full text fetched | 46 |
| extracted | 100 |
| emitted | 100 |

## Numeric verification

559 row(s) checked; 138 effect(s) dropped, 8 interval(s) dropped, 3 code(s) dropped, 26 sample size(s) dropped, 1 interaction value(s) dropped

## Cost

- **Calls** — 510
- **Tokens** — 2,342,381
- **Spend** — $5.7655

## Warnings

- screen budget of 400 reached: 400 pooled paper(s) were not screened
- numeric verification removed 138 effect size(s) not found in the source text; those rows keep their claim at a lower confidence — 19854330 'Hypertension': 1.44 (1.18–1.76) is not in the source text; 19854330 'Hypertension population attributable risk, overall': 0.20 (0.10, 0.30) is not in the source text; 19854330 'Coronary heart disease population attributable risk, overall': 0.20 (0.16, 0.24) is not in the source text; 19854330 'Hypertension PAR in women': 0.28 (0.14, 0.42) is not in the source text; 19854330 'Coronary heart disease PAR in men': 0.23 (0.16, 0.30) is not in the source text
- numeric verification removed 8 confidence interval(s) not found in the source text; the point estimates were kept — 28624486 'New-onset atrial fibrillation': the interval around HR 9.03 [95% CI: 7.52-10.85] is not in the source text; 30007554 'Triglyceride to HDL ratio': the interval around 1.13 (1.04 – 1.23) is not in the source text; 34056865 'Copeptin top quartile vs quartile 1': the interval around 2.00 (1.09–3.68) is not in the source text; 33228398 'Hypertension (PAR comparison)': the interval around 24.1 (18.3, 29.5) is not in the source text; 33228398 'Total SB >9.5 h/d (PAR)': the interval around 7.3 (3.0, 11.3) is not in the source text
- numeric verification removed 1 interaction value(s) not found in the source text; those interactions were kept and now read as stated rather than measured — 33228398 'Total SB >9.5 h/d within high physical activity (>=7.5 MET-hr/wk)': .66, not significant against 'Baseline recreational physical activity' is not in the source text
- 3 vocabulary code(s) were not printed in the source text and were dropped; the concepts they were attached to were kept — 29661945 'HF hospitalization': icd9cm primary HF diagnoses (codes not printed) is not in the source text; 28953453 'Heart failure': icd8 4270 is not in the source text; 28953453 'Myocardial infarction': icd10 I21 is not in the source text
- 26 sample size(s) were not in the source text and were dropped
- 31 length budget(s) cut something: 40889512 description truncated to 200 characters; 24656111 description truncated to 200 characters; 22258189 description truncated to 200 characters; 39874177 description truncated to 200 characters; 36035738 description truncated to 200 characters; and 26 more
