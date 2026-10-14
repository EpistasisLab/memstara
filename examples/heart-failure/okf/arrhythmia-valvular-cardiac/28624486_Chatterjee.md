---
type: "Literature Evidence"
title: "Modifiable Risk Factors for Incident Heart Failure in Atrial Fibrillation."
description: "In 34,736 women, new-onset AF raised HF risk ninefold (HR 9.03); among 1495 with AF, obesity, SBP>120, smoking and diabetes drove HF (62% PAR) and optimal control cut HR to 0.14."
resource: "https://pubmed.ncbi.nlm.nih.gov/28624486/"
domain: "arrhythmia-valvular-cardiac"
id: "28624486"
pmid: "28624486"
journal: "JACC. Heart failure"
authors: "Chatterjee NA, Chae CU, Kim E, Moorthy MV, Conen D, Sandhu RK, et al."
published: "2017"
tags: ["atrial fibrillation", "heart failure", "women", "modifiable risk factors", "obesity", "blood pressure", "population attributable risk", "Women's Health Study"]
study_design: "Observational follow-up of Women's Health Study (post-RCT) cohort with time-varying Cox models"
n: "34736"
strength: "strong"
strength_score: "0.87"
text_basis: "full_text"
license: "author_manuscript"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:33Z"}
sources: [{id: "pmid:28624486", resource: "https://pubmed.ncbi.nlm.nih.gov/28624486/"}, {id: "pmc:PMC5873947", resource: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5873947/"}, {id: "doi:10.1016/j.jchf.2017.04.004", resource: "https://doi.org/10.1016/j.jchf.2017.04.004"}]
---

# Bottom line

New-onset AF carried a ninefold higher risk of incident HF in women. Among those with AF, four modifiable factors (SBP>120, BMI≥30, current smoking, diabetes) explained an estimated 62% of population attributable HF risk.

- **Design** — Observational follow-up of Women's Health Study (post-RCT) cohort with time-varying Cox models
- **N** — 34,736
- **Population** — US female health professionals aged 45+ free of CVD at baseline; subcohort of 1495 with new-onset AF without prevalent HF
- **Outcome** — Incident HF confirmed by adjudicated Framingham or CHS criteria; subtyped HFpEF (LVEF≥50%) vs HFrEF (<50%)
- **Read from** — the full text
- **Evidence strength** — strong (0.87)

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | New-onset atrial fibrillation | Time-varying adjudicated incident AF | AF diagnosis precedes HF (most HF after AF) | Incident HF | association | HR 9.03 [95% CI: 7.52-10.85] | <0.0001 | increases | medium | strong 0.79 | — |
| 2 | New-onset AF (excluding HF within 30 days) | Censoring HF events <30 days after AF | after AF | Incident HF | association | HR 4.99 [95% CI: 4.05-6.13] | <0.0001 | increases | high | strong 0.88 | — |
| 3 | Obesity (BMI ≥30 vs <25) in AF | Time-updated BMI category | after AF diagnosis | Incident HF | association | HR 1.62 [95% CI: 1.10-2.40] | 0.02 | increases | high | strong 0.83 | — |
| 4 | Systolic BP 120-139 vs <120 mmHg in AF | Time-updated SBP category | after AF diagnosis | Incident HF | association | unverified | 0.002 | increases | medium | strong 0.79 | — |
| 5 | Systolic BP per 10 mmHg in AF | continuous SBP | after AF diagnosis | Incident HF | association | HR 1.16 [95% CI: 1.05-1.28] | 0.003 | increases | high | strong 0.91 | — |
| 6 | Current smoking (vs never) in AF | Time-updated smoking status | after AF diagnosis | Incident HF | association | unverified | 0.02 | increases | medium | strong 0.79 | — |
| 7 | Diabetes mellitus in AF | Time-updated self-reported diabetes | after AF diagnosis | Incident HF | association | unverified | 0.0001 | increases | low | strong 0.79 | — |
| 8 | Chronic kidney disease in AF | Time-updated CKD | after AF diagnosis | Incident HF | association | unverified | <0.0001 | increases | medium | strong 0.79 | — |
| 9 | Incident coronary heart disease in AF | MI and/or revascularization after AF | after AF diagnosis | Incident HF | association | unverified | <0.0001 | increases | medium | strong 0.79 | — |
| 10 | Age in AF | per year | at AF diagnosis | Incident HF | association | unverified | <0.0001 | increases | medium | strong 0.79 | — |
| 11 | 0 vs 3-4 modifiable risk factors | Score: SBP>120, BMI≥30, smoking, diabetes; time-updated | after AF diagnosis | Incident HF | association | 0.14 [95% CI: 0.07-0.29] | <0.0001 | decreases | high | strong 0.75 | — |
| 12 | Four modifiable risk factors combined | Population attributable risk | after AF diagnosis | Incident HF | association | 62% (95% CI: 23-83) | — | increases | high | strong 0.86 | — |

Quoted from the paper, by row:

1. In multivariable-adjusted analyses, AF was associated with 9-fold increased risk of incident HF (HR 9.03 [95% CI: 7.52-10.84], p<0.0001), with similar risk estimates for incident HFpEF (HR 9.63 [95% CI: 7.67-12.86], p<0.0001) and HFrEF (HR 10.02 [95% CI: 7.38-13.61], p<0.001).
2. After censoring HF events occurring within 30 days of AF diagnosis (N=61), the association between AF and incident HF was attenuated, but remained significant in multivariable-adjusted models (HR 4.99 [95% CI: 4.05-6.13], p<0.0001) (Supplementary Table 1).
3. Increasing BMI was associated with a significant increased risk of incident HF (multivariable-adjusted HR: 1.15 per 5 kg/m2 [95% CI: 1.01-1.28]; p, continuous=0.04), with the most significant risk confined to those with BMI ≥ 30 kg/m2 (HR 1.62 [95% CI: 1.10-2.40], p=0.02) when compared to normal weight (BMI <25 kg/m2) women.
4. In addition, increasing systolic blood pressure (SBP) was associated with an increased risk of incident HF (HR 1.16 [95% CI: 1.05-1.28] per 10 mmHg increase, p=0.003).
5. In addition, increasing systolic blood pressure (SBP) was associated with an increased risk of incident HF (HR 1.16 [95% CI: 1.05-1.28] per 10 mmHg increase, p=0.003).
6. Risk Factors for Incident HF after AF Diagnosis
7. Risk Factors for Incident HF after AF Diagnosis
8. Risk Factors for Incident HF after AF Diagnosis
9. Risk Factors for Incident HF after AF Diagnosis
10. Risk Factors for Incident HF after AF Diagnosis
11. For example, women with optimal levels of all 4 modifiable risk factors (SBP < 120 mmHg, BMI < 30 kg/m2, absent smoking, absent diabetes) were at 86% lower risk of incident HF (HR 0.14 [95% CI: 0.07-0.29]) compared to women with the least favorable risk factor profile (3-4 risk factors).
12. Assuming a causal relationship between modifiable risk factors and HF, an estimated 62% (95% CI: 23-83) of the population attributable risk of incident HF after new-onset AF was attributable to these 4 directly modifiable risk factors, with the greatest contributing risk factor being SBP (Supplemental Table 3).

# Null or non-significant findings

| # | Predictor | Outcome | Detail |
|---|---|---|---|
| 1 | Physical activity ≥7.5 METS/week | Incident HF in AF | HR 0.95 [0.70-1.28], p=0.71 |
| 2 | Alcohol ≥2 drinks/day | Incident HF in AF | HR 1.37 [0.75-2.50], p=0.30 |
| 3 | Hyperlipidemia | Incident HF in AF | HR 1.06, p=0.77 |
| 4 | Prior smoking | Incident HF in AF | HR 0.99, p=0.94 |

Quoted from the paper, by row:

1. Risk Factors for Incident HF after AF Diagnosis
2. Risk Factors for Incident HF after AF Diagnosis
3. Risk Factors for Incident HF after AF Diagnosis
4. Risk Factors for Incident HF after AF Diagnosis

# Vocabulary hints

- **incident atrial fibrillation**
- **heart failure (Framingham/CHS criteria)**
- **systolic blood pressure >120 mmHg**
- **BMI ≥30 kg/m2**
- **chronic kidney disease**

# Caveats

Self-reported risk factors and AF/HF reporting; women only, 97% white, with exclusions of those lost to follow-up. PAR assumes causality; HF within 30 days of AF may reflect detection. Observational; risk factor modification not tested.
