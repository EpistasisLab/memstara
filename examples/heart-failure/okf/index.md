---
type: "Bundle Index"
title: "Identify and weigh the clinical, biological, behavioural, social and environmental factors that predict the development of chronic heart failure in adults, to support risk assessment."
description: "100 paper(s) across 8 topic/topics, built from PubMed and PMC by okf-loremaster/0.4.1."
---

# Identify and weigh the clinical, biological, behavioural, social and environmental factors that predict the development of chronic heart failure in adults, to support risk assessment.

clinical predictors of chronic heart failure in adults

## Topics

| topic | title | papers | full text | abstract only | scope |
|---|---|---|---|---|---|
| [hypertension-ischemic-disease](hypertension-ischemic-disease/index.md) | Hypertension and ischemic heart disease | 10 | 4 | 6 | Blood pressure, hypertension control, coronary artery disease and myocardial infarction as predictors of heart failure onset. Excludes arrhythmia, valvular disease and metabolic conditions. |
| [arrhythmia-valvular-cardiac](arrhythmia-valvular-cardiac/index.md) | Arrhythmia, valvular and other cardiac conditions | 11 | 3 | 8 | Atrial fibrillation, other arrhythmias, valvular heart disease, cardiomyopathy and myocarditis preceding heart failure. Excludes hypertension and coronary disease. |
| [metabolic-renal-comorbidity](metabolic-renal-comorbidity/index.md) | Metabolic and renal comorbidities | 13 | 8 | 5 | Diabetes, insulin resistance, obesity, dyslipidemia, chronic kidney disease and thyroid dysfunction as predictors of heart failure. Excludes lifestyle behaviours themselves. |
| [biomarkers-subclinical-dysfunction](biomarkers-subclinical-dysfunction/index.md) | Biomarkers and subclinical cardiac dysfunction | 14 | 4 | 10 | Circulating biomarkers (natriuretic peptides, troponin, inflammatory markers) and imaging or ECG evidence of subclinical dysfunction predicting heart failure. Excludes multivariable risk scores. |
| [lifestyle-behavioural-factors](lifestyle-behavioural-factors/index.md) | Lifestyle and behavioural factors | 13 | 5 | 8 | Smoking, alcohol, physical activity, fitness, diet, sodium intake and sleep, including sleep apnea, as predictors of heart failure. Excludes socioeconomic and psychosocial factors. |
| [social-psychosocial-determinants](social-psychosocial-determinants/index.md) | Social, psychosocial and healthcare-access determinants | 13 | 7 | 6 | Socioeconomic status, education, race and ethnicity, neighbourhood, depression, stress, social isolation and access to care as predictors of heart failure. Excludes individual lifestyle behaviours. |
| [cardiotoxic-inflammatory-environmental](cardiotoxic-inflammatory-environmental/index.md) | Cardiotoxic drugs, inflammatory and environmental exposures | 13 | 7 | 6 | Cancer therapy cardiotoxicity, NSAIDs and other drugs, autoimmune and infectious disease such as HIV, air pollution and occupational exposures preceding heart failure. Excludes metabolic comorbidities. |
| [risk-models-demographics-genetics](risk-models-demographics-genetics/index.md) | Risk prediction models, demographics and genetics | 13 | 8 | 5 | Multivariable risk scores and machine-learning models for incident heart failure, plus age, sex, family history and genetic or polygenic risk. Excludes single-biomarker studies. |

## Charter

- **Population** — adults
- **Outcome** — chronic heart failure
- **Languages** — any
- **Target** — 100 papers, 8-40 per topic
- **Full charter** — [charter.yaml](charter.yaml)

## Run

- **Run id** — 20261008-000746-59bb
- **Built** — 2026-10-08T00:17:34Z
- **Duration** — 9m 45s
- **Tool** — okf-loremaster/0.4.1
- **Charter digest** — 2e71c56964e97a86
- **Models** — fast: claude-haiku-4-5, balanced: claude-sonnet-5-5, reasoning: claude-opus-5-5
- **Abstracts** — omitted from every document by --no-abstract. Every paper was still screened and read from the text this run had; only the section is gone.
- **Stale after** — 2027-04-06

## Corpus

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

## Cost

- **Model calls** — 510
- **Tokens** — 2,342,381 (2,092,938 in / 249,443 out)
- **Spend** — $5.7655

## Warnings

- screen budget of 400 reached: 400 pooled paper(s) were not screened
- numeric verification removed 138 effect size(s) not found in the source text; those rows keep their claim at a lower confidence — 19854330 'Hypertension': 1.44 (1.18–1.76) is not in the source text; 19854330 'Hypertension population attributable risk, overall': 0.20 (0.10, 0.30) is not in the source text; 19854330 'Coronary heart disease population attributable risk, overall': 0.20 (0.16, 0.24) is not in the source text; 19854330 'Hypertension PAR in women': 0.28 (0.14, 0.42) is not in the source text; 19854330 'Coronary heart disease PAR in men': 0.23 (0.16, 0.30) is not in the source text
- numeric verification removed 8 confidence interval(s) not found in the source text; the point estimates were kept — 28624486 'New-onset atrial fibrillation': the interval around HR 9.03 [95% CI: 7.52-10.85] is not in the source text; 30007554 'Triglyceride to HDL ratio': the interval around 1.13 (1.04 – 1.23) is not in the source text; 34056865 'Copeptin top quartile vs quartile 1': the interval around 2.00 (1.09–3.68) is not in the source text; 33228398 'Hypertension (PAR comparison)': the interval around 24.1 (18.3, 29.5) is not in the source text; 33228398 'Total SB >9.5 h/d (PAR)': the interval around 7.3 (3.0, 11.3) is not in the source text
- numeric verification removed 1 interaction value(s) not found in the source text; those interactions were kept and now read as stated rather than measured — 33228398 'Total SB >9.5 h/d within high physical activity (>=7.5 MET-hr/wk)': .66, not significant against 'Baseline recreational physical activity' is not in the source text
- 3 vocabulary code(s) were not printed in the source text and were dropped; the concepts they were attached to were kept — 29661945 'HF hospitalization': icd9cm primary HF diagnoses (codes not printed) is not in the source text; 28953453 'Heart failure': icd8 4270 is not in the source text; 28953453 'Myocardial infarction': icd10 I21 is not in the source text
- 26 sample size(s) were not in the source text and were dropped
- 31 length budget(s) cut something: 40889512 description truncated to 200 characters; 24656111 description truncated to 200 characters; 22258189 description truncated to 200 characters; 39874177 description truncated to 200 characters; 36035738 description truncated to 200 characters; and 26 more

## Files

- [predictors.md](predictors.md) — what recurs across the topics, and which row of which paper to read it in
- [search.md](search.md) — every query behind this bundle, why it was asked, and what PubMed made of it
- [log.md](log.md) — how this bundle was built
- `_catalog.jsonl` — one JSON row per document
- [resource_descriptor.yaml](resource_descriptor.yaml) — what a consumer reads on attach
