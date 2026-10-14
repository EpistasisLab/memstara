---
type: "Literature Evidence"
title: "Nationwide Study of Sex Differences in Incident Heart Failure in Newly Diagnosed Nonvalvular Atrial Fibrillation."
description: "Among 68,909 Canadians aged 65+ with new nonvalvular AF, 1-year HF hospitalization was 30.0% in women vs 25.6% in men; sex difference vanished after medication adjustment except in women 75+ (HR…"
resource: "https://pubmed.ncbi.nlm.nih.gov/36035738/"
domain: "arrhythmia-valvular-cardiac"
id: "36035738"
pmid: "36035738"
journal: "CJC open"
authors: "Yogasundaram H, Islam S, Dover DC, Hawkins NM, Ezekowitz J, Kaul P, et al."
published: "2022"
tags: ["atrial fibrillation", "heart failure", "sex differences", "older adults", "administrative data", "cardioversion"]
study_design: "Retrospective cohort study using Canadian national administrative data (DAD, NPDUIS), 2010-2018"
n: "68909"
strength: "strong"
strength_score: "0.78"
text_basis: "full_text"
license: "CC BY-NC-ND"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:33Z"}
sources: [{id: "pmid:36035738", resource: "https://pubmed.ncbi.nlm.nih.gov/36035738/"}, {id: "pmc:PMC9402965", resource: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9402965/"}, {id: "doi:10.1016/j.cjco.2022.04.010", resource: "https://doi.org/10.1016/j.cjco.2022.04.010"}]
---

# Bottom line

Women with incident NVAF had more HF hospitalization at 1 year, but the difference was attenuated after full adjustment; women aged 75+ remained at higher risk (HR 1.10) while women 65-74 had lower risk (HR 0.91). Age-sex interaction was significant.

- **Design** — Retrospective cohort study using Canadian national administrative data (DAD, NPDUIS), 2010-2018
- **N** — 68,909
- **Population** — Adults aged 65+ hospitalized with incident nonvalvular AF without prior HF, Canada excluding Quebec
- **Outcome** — Incident HF hospitalization within 1 year of NVAF diagnosis (HF secondary diagnosis at index or any later hospitalization); composite with all-cause mortality
- **Read from** — the full text
- **Evidence strength** — strong (0.78)

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Female sex | Women vs men | Baseline, before 1-year follow-up | Incident HF hospitalization at 1 year | association | unverified | <0.001 | increases | medium | moderate 0.58 | — |
| 2 | Female sex | Women vs men, model 2 with medications | Baseline | Incident HF hospitalization at 1 year | association | 1.01 (0.98-1.04) | 0.48 | none | high | strong 0.88 | Age category |
| 3 | Female sex, age 75+ | Women vs men aged 75+, full adjustment | Baseline | Incident HF hospitalization at 1 year | association | HR 1.10, 95% CI 1.06-1.13 | <0.001 | increases | high | strong 0.88 | — |
| 4 | Female sex, age 65-74 | Women vs men aged 65-74 | Baseline | Incident HF hospitalization at 1 year | association | unverified | <0.001 | decreases | medium | strong 0.74 | — |
| 5 | Female sex, age 75+ | Women vs men aged 75+, model 2 | Baseline | HF hospitalization or all-cause death at 1 year | association | unverified | 0.009 | increases | medium | strong 0.74 | — |
| 6 | Electrical cardioversion | Within 30 days of NVAF diagnosis | Within 30 days of index | Incident HF hospitalization at 1 year | association | HR 0.89, 95% CI 0.85-0.94 | <0.001 | decreases | high | strong 0.88 | — |
| 7 | Chronic kidney disease, diabetes, increasing age, lower income, CAD | Comorbidities in prior 5 years; income quintile | Before index NVAF | Incident HF hospitalization at 1 year | association | — | — | increases | medium | strong 0.74 | — |

Quoted from the paper, by row:

1. The association between sex and outcomes is shown in Table 2. In age-adjusted analysis, women had a 7% increase in the risk of incident HF, compared with that for men.
2. When medications were accounted for, the difference in HF risk between men and women was no longer significant (hazard ratio [HR] 1.01, 95% confidence interval [CI] 0.98-1.04), P = 0.51).
3. In model 1, we found a 22% increased HF risk for women age ≥ 75 years, which remained elevated after full adjustment (model 2; HR 1.10, 95% CI 1.06-1.13, P < 0.001).
4. In model 1, we found a 22% increased HF risk for women age ≥ 75 years, which remained elevated after full adjustment (model 2; HR 1.10, 95% CI 1.06-1.13, P < 0.001).
5. In both age-adjusted analysis and multivariable analysis without adjusting for medication (model 1), the risk of the composite outcome was similar for women and men.
6. Chronic kidney disease, diabetes, increasing age, lower income, and CAD were associated with increased HF risk, and electrical cardioversion was associated with an 11% lower risk of HF hospitalization (HR 0.89, 95% CI 0.85-0.94, P < 0.001; Supplemental Table S2).
7. Chronic kidney disease, diabetes, increasing age, lower income, and CAD were associated with increased HF risk, and electrical cardioversion was associated with an 11% lower risk of HF hospitalization (HR 0.89, 95% CI 0.85-0.94, P < 0.001; Supplemental Table S2).

# Interactions

| # | Predictor | Interacts with | Type | Magnitude | Evidence |
|---|---|---|---|---|---|
| 2 | Female sex | Age category | modified by | stated | unverified |

# Null or non-significant findings

| # | Predictor | Outcome | Detail |
|---|---|---|---|
| 1 | Female sex (full adjustment incl. medications) | Incident HF hospitalization overall | HR 1.01, 0.98-1.04; sex difference no longer significant |
| 2 | Female sex (age-adjusted) | HF or death composite | HR 0.99, 0.97-1.01, P=0.32 |

Quoted from the paper, by row:

1. When medications were accounted for, the difference in HF risk between men and women was no longer significant (hazard ratio [HR] 1.01, 95% confidence interval [CI] 0.98-1.04), P = 0.51).
2. In both age-adjusted analysis and multivariable analysis without adjusting for medication (model 1), the risk of the composite outcome was similar for women and men.

# Vocabulary hints

- **Nonvalvular atrial fibrillation** — icd10 `I48`
- **Income quintile**
- **Electrical cardioversion**

# Caveats

Administrative ICD-coded data risk misclassification; AF type and HF phenotype (EF) unavailable. Medications were captured only within 30 days after index, which may mediate rather than confound, and out-of-hospital death was algorithmically inferred.
