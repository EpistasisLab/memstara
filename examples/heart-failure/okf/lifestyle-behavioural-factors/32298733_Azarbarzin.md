---
type: "Literature Evidence"
title: "The Sleep Apnea-Specific Hypoxic Burden Predicts Incident Heart Failure."
description: "In SHHS and MrOS cohorts, sleep apnea-specific hypoxic burden predicted incident HF in men (adjusted HR ~1.2 per SD) while AHI did not; no significant association in women."
resource: "https://pubmed.ncbi.nlm.nih.gov/32298733/"
domain: "lifestyle-behavioural-factors"
id: "32298733"
pmid: "32298733"
journal: "Chest"
authors: "Azarbarzin A, Sands SA, Taranto-Montemurro L, Vena D, Sofer T, Kim SW, et al."
published: "2020"
tags: ["sleep apnea", "hypoxic burden", "heart failure", "AHI", "cohort", "sex differences"]
study_design: "Two prospective cohort studies (Sleep Heart Health Study and MrOS Sleep) analysed with Cox models"
strength: "strong"
strength_score: "0.71"
text_basis: "abstract"
export_safe: "false"
generated: {by: "okf-loremaster/extract/claude-sonnet-5-5", at: "2026-10-08T00:17:34Z"}
sources: [{id: "pmid:32298733", resource: "https://pubmed.ncbi.nlm.nih.gov/32298733/"}, {id: "pmc:PMC7417383", resource: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7417383/"}, {id: "doi:10.1016/j.chest.2020.03.053", resource: "https://doi.org/10.1016/j.chest.2020.03.053"}]
---

# Bottom line

Hypoxic burden from sleep apnea (SASHB) predicted incident heart failure in men in two cohorts, beyond AHI, including at low and high AHI. Associations were not significant in women.

- **Design** — Two prospective cohort studies (Sleep Heart Health Study and MrOS Sleep) analysed with Cox models
- **Population** — Middle-aged and older adults in SHHS (n=4,881) and older men in MrOS (n=2,653)
- **Outcome** — Incident heart failure during follow-up (ascertainment details not given in abstract)
- **Read from** — the abstract only
- **Evidence strength** — strong (0.71) — nothing to score on size

# Predictors reported

| # | Predictor | Operationalization | Timing | Outcome | Type | Effect | p | Direction | Confidence | Strength | Interacts with |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Sleep apnea-specific hypoxic burden (SASHB), men in SHHS | Sleep apnea-specific area under the desaturation curve from pre-event baseline, ln-transformed, per 1 SD | Measured at baseline polysomnography, before incident HF | Incident heart failure | association | 1.18 (95% CI, 1.02-1.37) | — | increases | high | strong 0.82 | Apnea-hypopnea index |
| 2 | Sleep apnea-specific hypoxic burden (SASHB), men in MrOS | ln-transformed SASHB, per 1 SD | Baseline sleep study before incident HF | Incident heart failure | association | 1.22 (95% CI, 1.02-1.45) | — | increases | high | strong 0.81 | — |

Quoted from the paper, by row:

1. Men in SHHS and MrOS had adjusted HRs (per 1SD increase in SASHB) of 1.18 (95% CI, 1.02-1.37) and 1.22 (95% CI, 1.02-1.45), respectively.
2. Men in SHHS and MrOS had adjusted HRs (per 1SD increase in SASHB) of 1.18 (95% CI, 1.02-1.37) and 1.22 (95% CI, 1.02-1.45), respectively.

# Interactions

| # | Predictor | Interacts with | Type | Magnitude | Evidence |
|---|---|---|---|---|---|
| 1 | Sleep apnea-specific hypoxic burden (SASHB), men in SHHS | Apnea-hypopnea index | correlated | stated | associations observed in men with both low and high AHI levels |

# Null or non-significant findings

| # | Predictor | Outcome | Detail |
|---|---|---|---|
| 1 | Apnea-hypopnea index | Incident heart failure in men | AHI did not predict incident HF in men in either cohort |
| 2 | SASHB in women | Incident heart failure | Associations were not significant in women |

Quoted from the paper, by row:

1. Results: The SASHB predicted incident HF in men in both cohorts, whereas AHI did not.
2. Associations were not significant in women.

# Vocabulary hints

- **sleep apnea-specific hypoxic burden (SASHB)**
- **apnea-hypopnea index (AHI)**
- **incident heart failure**

# Caveats

Based on abstract only; covariate list and HF ascertainment are not detailed. Sex-specific findings may reflect lower power in women. Observational design.
