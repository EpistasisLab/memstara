---
type: "Literature Evidence"
title: "Association of Left Ventricular Systolic Function With Incident Heart Failure in Late Life."
description: "In ARIC elders, subtle LV systolic impairment (LVEF<60%, low longitudinal/circumferential strain) independently predicted incident HF; guideline LVEF cutoffs missed most at-risk people."
resource: "https://pubmed.ncbi.nlm.nih.gov/33729428/"
domain: "biomarkers-subclinical-dysfunction"
id: "33729428"
pmid: "33729428"
journal: "JAMA cardiology"
authors: "Reimer Jensen AM, Zierath R, Claggett B, Skali H, Solomon SD, Matsushita K, et al."
published: "2021"
tags: ["subclinical systolic dysfunction", "LVEF", "global longitudinal strain", "echocardiography", "incident heart failure", "ARIC", "older adults", "population-attributable risk"]
study_design: "Prospective community-based cohort (ARIC) time-to-event analysis with validation in the Copenhagen City Heart Study"
n: "4960"
strength: "strong"
strength_score: "0.73"
text_basis: "abstract"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:34Z"}
sources: [{id: "pmid:33729428", resource: "https://pubmed.ncbi.nlm.nih.gov/33729428/"}, {id: "pmc:PMC7970394", resource: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7970394/"}, {id: "doi:10.1001/jamacardio.2021.0131", resource: "https://doi.org/10.1001/jamacardio.2021.0131"}]
---

# Bottom line

Worse LVEF, longitudinal strain and circumferential strain were each independently associated with incident HF in late life, even at levels above guideline thresholds. LVEF<60% had greater population-attributable risk (11%) than guideline limits (5%).

- **Design** — Prospective community-based cohort (ARIC) time-to-event analysis with validation in the Copenhagen City Heart Study
- **N** — 4,960
- **Population** — Community-dwelling older adults without heart failure in ARIC visit 5 (mean age 75), validated in CCHS
- **Outcome** — Incident adjudicated heart failure, including HF with preserved and reduced LVEF, median follow-up 5.5 years
- **Read from** — the abstract only
- **Evidence strength** — strong (0.73)

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Left ventricular ejection fraction (per SD decrease) | 2D echocardiography LVEF, continuous, per SD decrease | Measured at ARIC visit 5, before follow-up for incident HF | Incident HF | association | 1.41 (95% CI, 1.29-1.55) | — | increases | high | strong 0.84 | — |
| 2 | LVEF less than 60% | Dichotomized at ARIC-based lower limit | Baseline echo before follow-up | Incident HF | association | 2.59 (95% CI, 1.99-3.37) | — | increases | high | strong 0.80 | — |
| 3 | Longitudinal strain (continuous, per SD decrease) | Speckle-tracking echocardiography LS, continuous | Baseline echo | Incident HF | association | HR, 1.37; 95% CI, 1.22-1.53 | — | increases | high | strong 0.83 | — |
| 4 | Longitudinal strain less than 16.0% | Dichotomized at lower 10th percentile of healthy reference group | Baseline echo | Incident HF | association | HR, 1.93; 95% CI, 1.46-2.55 | — | increases | high | strong 0.79 | — |
| 5 | Circumferential strain (continuous, per SD decrease) | Echocardiographic CS, continuous | Baseline echo | Incident HF | association | HR, 1.39; 95% CI, 1.22-1.57 | — | increases | high | strong 0.83 | — |
| 6 | Circumferential strain less than 23.7% | Dichotomized at lower 10th percentile of healthy reference group | Baseline echo | Incident HF | association | HR, 2.30; 95% CI, 1.64-3.22 | — | increases | high | strong 0.78 | — |
| 7 | Impaired LVEF by guideline limits | Guideline thresholds (104 participants, 2.1%) | Baseline echo | Incident HF or death | association | HR, 2.99; 95% CI, 2.19-4.09 | — | increases | medium | moderate 0.68 | — |
| 8 | Impaired LVEF by ARIC-based limits (<60%) | LVEF<60% (692 participants, 13.9%) | Baseline echo | Incident HF or death | association | HR, 1.88; 95% CI, 1.58-2.25 | — | increases | medium | strong 0.72 | — |

Quoted from the paper, by row:

1. The adjusted hazard ratio (HR) per SD decrease in LVEF was 1.41 (95% CI, 1.29-1.55); the HR for LVEF less than 60% was 2.59 (95% CI, 1.99-3.37).
2. The adjusted hazard ratio (HR) per SD decrease in LVEF was 1.41 (95% CI, 1.29-1.55); the HR for LVEF less than 60% was 2.59 (95% CI, 1.99-3.37).
3. Similar findings were observed for continuous LS (HR, 1.37; 95% CI, 1.22-1.53) and dichotomized LS (HR, 1.93; 95% CI, 1.46-2.55) and for continuous CS (HR, 1.39; 95% CI, 1.22-1.57) and dichotomized CS (HR, 2.30; 95% CI, 1.64-3.22).
4. Similar findings were observed for continuous LS (HR, 1.37; 95% CI, 1.22-1.53) and dichotomized LS (HR, 1.93; 95% CI, 1.46-2.55) and for continuous CS (HR, 1.39; 95% CI, 1.22-1.57) and dichotomized CS (HR, 2.30; 95% CI, 1.64-3.22).
5. Similar findings were observed for continuous LS (HR, 1.37; 95% CI, 1.22-1.53) and dichotomized LS (HR, 1.93; 95% CI, 1.46-2.55) and for continuous CS (HR, 1.39; 95% CI, 1.22-1.57) and dichotomized CS (HR, 2.30; 95% CI, 1.64-3.22).
6. Similar findings were observed for continuous LS (HR, 1.37; 95% CI, 1.22-1.53) and dichotomized LS (HR, 1.93; 95% CI, 1.46-2.55) and for continuous CS (HR, 1.39; 95% CI, 1.22-1.57) and dichotomized CS (HR, 2.30; 95% CI, 1.64-3.22).
7. Although the magnitude of risk for incident HF or death associated with impaired LVEF was greater using guideline (HR, 2.99; 95% CI, 2.19-4.09) compared with ARIC-based limits (HR, 1.88; 95% CI, 1.58-2.25), the number of participants classified as impaired was less (104 [2.1%] based on guideline thresholds compared with 692 [13.9%] based on LVEF <60%).
8. Although the magnitude of risk for incident HF or death associated with impaired LVEF was greater using guideline (HR, 2.99; 95% CI, 2.19-4.09) compared with ARIC-based limits (HR, 1.88; 95% CI, 1.58-2.25), the number of participants classified as impaired was less (104 [2.1%] based on guideline thresholds compared with 692 [13.9%] based on LVEF <60%).

# Null or non-significant findings

None reported — the paper states no null or non-significant finding.

# Vocabulary hints

- **left ventricular ejection fraction**
- **longitudinal strain**
- **circumferential strain**
- **incident adjudicated heart failure**
- **population-attributable risk**

# Caveats

Read from abstract only; p-values and interaction details unavailable. Older cohort with short 5.5-year follow-up; thresholds derived from only 374 healthy participants. Few participants had LVEF<50%.
