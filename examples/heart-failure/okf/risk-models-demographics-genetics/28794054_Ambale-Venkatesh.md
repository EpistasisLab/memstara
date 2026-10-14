---
type: "Literature Evidence"
title: "Cardiovascular Event Prediction by Machine Learning: The Multi-Ethnic Study of Atherosclerosis."
description: "In MESA (n=6814), random survival forests with 735 variables ranked NT-proBNP, TNF-α SR, CAC, LV volumes and troponin-T as top predictors of incident HF; RF-20 C-index 0.84 at 12 years, beating…"
resource: "https://pubmed.ncbi.nlm.nih.gov/28794054/"
domain: "risk-models-demographics-genetics"
id: "28794054"
pmid: "28794054"
journal: "Circulation research"
authors: "Ambale-Venkatesh B, Yang X, Wu CO, Liu K, Hundley WG, McClelland R, et al."
published: "2017"
tags: ["heart failure", "random survival forest", "machine learning", "MESA", "NT-proBNP", "risk prediction", "coronary artery calcium", "cardiac MRI"]
study_design: "Prospective population-based cohort (MESA) with random survival forest machine learning, train/test split, comparison with Cox, Lasso-Cox, AIC-Cox and published risk scores"
n: "6814"
strength: "strong"
strength_score: "0.7"
text_basis: "full_text"
license: "author_manuscript"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:34Z"}
sources: [{id: "pmid:28794054", resource: "https://pubmed.ncbi.nlm.nih.gov/28794054/"}, {id: "pmc:PMC5640485", resource: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5640485/"}, {id: "doi:10.1161/CIRCRESAHA.117.311312", resource: "https://doi.org/10.1161/CIRCRESAHA.117.311312"}]
---

# Bottom line

Random survival forest on deep phenotyping data identified NT-proBNP, TNF-α SR, CAC, LV volume/function and troponin-T as leading predictors of incident HF, with C-index 0.84 versus 0.80 for the MESA-HF risk score. RF-20 outperformed Cox-based models on Brier score for most outcomes.

- **Design** — Prospective population-based cohort (MESA) with random survival forest machine learning, train/test split, comparison with Cox, Lasso-Cox, AIC-Cox and published risk scores
- **N** — 6,814
- **Population** — Adults aged 45-84 free of clinical cardiovascular disease at baseline, four ethnic groups, six US centers
- **Outcome** — Incident heart failure (259 cases) over median 11.2 years follow-up; discrimination by C-index and Brier score at 12 years
- **Read from** — the full text
- **Evidence strength** — strong (0.70) — nothing to score on adjustment

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | N-terminal pro-BNP | Baseline serum level; RF minimal depth of maximal subtree rank | Baseline, before incident HF over ~12 years | incident heart failure | association | unverified | — | increases | medium | moderate 0.60 | — |
| 2 | Tissue necrosis factor-α soluble receptor | Baseline serum level | Baseline | incident heart failure | association | 0·07 | — | unclear | medium | moderate 0.60 | — |
| 3 | Coronary artery calcium score | Baseline CT Agatston score | Baseline | incident heart failure | association | unverified | — | unclear | low | moderate 0.60 | — |
| 4 | LV end-systolic volume | Cardiac MRI at baseline | Baseline | incident heart failure | association | unverified | — | increases | low | moderate 0.60 | — |
| 5 | Cardiac troponin T | Baseline serum level | Baseline | incident heart failure | association | unverified | — | increases | low | moderate 0.60 | — |
| 6 | LV ejection fraction | Cardiac MRI | Baseline | incident heart failure | association | unverified | — | decreases | low | moderate 0.60 | — |
| 7 | Waist-to-hip ratio | Baseline anthropometry | Baseline | incident heart failure | association | unverified | — | increases | low | moderate 0.60 | — |
| 8 | RF-20 model vs MESA-HF risk score | Random survival forest with top 20 variables, C-index at 12 years | Baseline predictors, 12-year horizon | incident heart failure | association | unverified | — | unclear | medium | moderate 0.60 | — |

Quoted from the paper, by row:

1. For incident HF as the endpoint, cardiac chamber stress (increased LV volume, and increased NT-proBNP levels), and decreased LV function from MRI were the most important markers.
2. Rank Heart Failure RVI Atrial Fibrillation RVI 1 N-Terminal pro-Brain Natriuretic Peptide 0·00 N-Terminal pro-Brain Natriuretic Peptide 0·00 2 Tissue Necrosis Factor-α soluble receptor 0·07 Coronary Artery Calcium score 0·23 3 Coronary Artery Calcium score 0·07 Age 0·27 4 End-systolic left ventricular volume 0·10 Creatinine 0·31 5 Cardiac Troponin-T 0·20 Ankle-Brachial Index 0·36 6 End-diastolic left ventricular volume 0·21 Interleukin-2 soluble receptor 0·39 7 Left ventricular ejection fraction 0·24 Tissue Necrosis Factor-α soluble receptor 0·41 8 QTC INTERVAL 0·32 Common
3. For incident HF as the endpoint, cardiac chamber stress (increased LV volume, and increased NT-proBNP levels), and decreased LV function from MRI were the most important markers.
4. For incident HF as the endpoint, cardiac chamber stress (increased LV volume, and increased NT-proBNP levels), and decreased LV function from MRI were the most important markers.
5. For incident HF as the endpoint, cardiac chamber stress (increased LV volume, and increased NT-proBNP levels), and decreased LV function from MRI were the most important markers.
6. For incident HF as the endpoint, cardiac chamber stress (increased LV volume, and increased NT-proBNP levels), and decreased LV function from MRI were the most important markers.
7. Increased pulse pressure and increased waist-to-hip ratio were also among the top risk factors for incident HF reflecting the role of obesity and hypertension on incident HF development.
8. The performance of the RF-20 model for incident CHF prediction was better than the MESA-HF risk score (C-index: 0·80, BS: 0·038) with a higher C-index and lower BS.

# Null or non-significant findings

| # | Predictor | Outcome | Detail |
|---|---|---|---|
| 1 | Questionnaires and medication exposures | cardiovascular outcomes | Of lower prediction importance than imaging and biomarkers |
| 2 | Adding variables beyond 30 | C-index | Minimal improvement if any |

Quoted from the paper, by row:

1. In general, variables from imaging markers, ABI, and serum biomarkers were of intermediate-to-high prediction importance while questionnaires and medication exposures were of lower importance.
2. Addition of more variables into the model beyond 30 resulted in minimal improvement of the C-index, if any.

# Vocabulary hints

- **incident heart failure**
- **N-Terminal pro-Brain Natriuretic Peptide**
- **coronary artery calcium score**
- **left ventricular volume and ejection fraction by MRI**

# Caveats

Predictor ranks are importance values from forests, not effect sizes or directions, and no covariate adjustment applies. Internal train/test split only, no external validation; HF cases are few (259). Outcome adjudication details are not given in the text provided.
