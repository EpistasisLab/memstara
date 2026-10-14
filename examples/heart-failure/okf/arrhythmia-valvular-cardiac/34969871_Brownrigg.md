---
type: "Literature Evidence"
title: "Epidemiology of cardiomyopathies and incident heart failure in a population-based cohort study."
description: "Linked EHR cohort (n=4116 cardiomyopathy): amyloidosis and DCM carry highest incident HF among those HF-free at diagnosis; HCM and ARVC more often develop HF after diagnosis."
resource: "https://pubmed.ncbi.nlm.nih.gov/34969871/"
domain: "arrhythmia-valvular-cardiac"
id: "34969871"
pmid: "34969871"
journal: "Heart (British Cardiac Society)"
authors: "Brownrigg JR, Leo V, Rose J, Low E, Richards S, Carr-White G, et al."
published: "2022"
tags: ["cardiomyopathy", "heart failure", "amyloidosis", "dilated cardiomyopathy", "hypertrophic cardiomyopathy", "electronic health records", "prevalence"]
study_design: "Population-based cohort study using linked electronic health records (~9 million individuals, 2000-2018)"
n: "4116"
strength: "moderate"
strength_score: "0.53"
text_basis: "abstract"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:33Z"}
sources: [{id: "pmid:34969871", resource: "https://pubmed.ncbi.nlm.nih.gov/34969871/"}, {id: "doi:10.1136/heartjnl-2021-320181", resource: "https://doi.org/10.1136/heartjnl-2021-320181"}]
---

# Bottom line

Among cardiomyopathy patients free of HF at diagnosis, annualised HF incidence was greatest in cardiac amyloidosis and DCM. HF often pre-existed the cardiomyopathy diagnosis (CA 66%, RCM 62%, DCM 56%, ARVC 29%, HCM 27%).

- **Design** — Population-based cohort study using linked electronic health records (~9 million individuals, 2000-2018)
- **N** — 4,116
- **Population** — People with diagnosed cardiomyopathy (HCM, DCM, ARVC, RCM, cardiac amyloidosis) in linked English EHR
- **Outcome** — Symptomatic heart failure diagnosis recorded in linked electronic health records; timing relative to cardiomyopathy diagnosis
- **Read from** — the abstract only
- **Evidence strength** — moderate (0.53) — nothing to score on adjustment

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Cardiac amyloidosis diagnosis | Cardiomyopathy phenotype recorded in linked EHR | Diagnosis of cardiomyopathy precedes HF in those HF-free at diagnosis | Incident heart failure | association | — | — | increases | medium | moderate 0.51 | — |
| 2 | Dilated cardiomyopathy diagnosis | Cardiomyopathy phenotype recorded in linked EHR | Diagnosis precedes HF in those HF-free at diagnosis | Incident heart failure | association | — | — | increases | medium | moderate 0.51 | — |

Quoted from the paper, by row:

1. Among those free of HF at diagnosis of cardiomyopathy, annualised HF incidence was greatest in CA and DCM.
2. Among those free of HF at diagnosis of cardiomyopathy, annualised HF incidence was greatest in CA and DCM.

# Null or non-significant findings

None reported — the paper states no null or non-significant finding.

# Vocabulary hints

- **hypertrophic cardiomyopathy**
- **dilated cardiomyopathy**
- **arrhythmogenic right ventricular cardiomyopathy**
- **cardiac amyloidosis**
- **symptomatic heart failure**

# Caveats

Abstract only; no adjusted effect estimates reported. Diagnoses clustered around HF onset, so cardiomyopathy recording may reflect HF workup (detection bias). EHR-coded diagnoses are subject to misclassification.
