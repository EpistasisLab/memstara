---
type: "Search Strategy"
title: "Search strategy — 20261008-000746-59bb"
description: "Every PubMed query this bundle was built from, why it was asked, and what PubMed actually ran — enough to repeat the search by hand."
---

# Search strategy — 20261008-000746-59bb

10 queries ran against PubMed through NCBI's E-utilities on 2026-10-08. Between them they matched 4,565 papers, retrieved 1,905, and kept 1,261 — the rest were the same paper found twice, retracted, or carried no abstract to screen. Screening, curation and extraction narrowed those to the 100 papers in this bundle; that part of the story is in [log.md](log.md).

No web page was scraped. Every search went to `esearch.fcgi` and every record came back from `efetch.fcgi`, so any term below can be repeated in a browser by pasting it into the PubMed search box.

## How to read a query

- **Why** — what the query was reaching for. Written by the model that planned it, before it knew what it would find.
- **Sent** — the term exactly as it left this tool. Copy it whole.
- **PubMed ran** — what PubMed made of that term. It is checked for every query, because PubMed does not reject a field tag it does not recognize: it silently rewrites `x[nosuchfield]` into `"x"[All Fields]`, returns far more papers than intended, and reports no error at all. When the expansion only writes out tags the term already carried, this line says so in one sentence. When PubMed reached for a field or a MeSH heading the term did not ask for, the expansion is printed in full and the query is marked **suspect**.
- **Result** — how many papers matched, and how many of them were actually taken. Retrieval was capped at 200 per query, ordered by `sort=relevance`, so a query that matched more than the cap contributed only the top slice of what it found.

## Will this reproduce?

The terms will. The corpus may not, and it is worth knowing why before you compare two runs.

1. **The terms are exact.** They are stored as sent, and PubMed's query syntax is stable. Pasting one into PubMed today asks the same question it asked here.
2. **The cap is not a tie-breaker, it is a filter.** 2 queries matched 200 papers or fewer and so were taken whole — those are exact. 8 queries matched more, and only the first 200 were kept.
3. **PubMed's relevance ranking is not frozen.** It is recomputed as the index grows, so for the capped queries above, repeating the search later can return a different set of the same size. The uncapped ones are unaffected. This is the reason a bundle records the date it was searched rather than only the terms.

## The queries

### 1. Across the whole task

**Why** — Broad query on risk factors and predictors of incident heart failure in general.

**Sent**

```text
(("incident heart failure"[tiab] OR "new-onset heart failure"[tiab] OR "development of heart failure"[tiab]) AND ("risk factors"[tiab] OR predictors[tiab] OR "risk prediction"[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 703 papers matched. The first 200 were retrieved (the cap is 200); the other 503 were never seen by this run.

### 2. Across the whole task

**Why** — Broad query for population cohort studies of heart failure onset.

**Sent**

```text
(("incident heart failure"[tiab] OR "heart failure risk"[tiab]) AND (cohort[tiab] OR prospective[tiab]) AND (adults[tiab] OR community[tiab] OR population[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 604 papers matched. The first 200 were retrieved (the cap is 200); the other 404 were never seen by this run.

### 3. Hypertension and ischemic heart disease

**Why** — Hypertension and ischemic heart disease as predictors of heart failure onset.

**Sent**

```text
((hypertension[tiab] OR "blood pressure"[tiab] OR "myocardial infarction"[tiab] OR "coronary artery disease"[tiab] OR "left ventricular hypertrophy"[tiab]) AND ("incident heart failure"[tiab] OR "new-onset heart failure"[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 851 papers matched. The first 200 were retrieved (the cap is 200); the other 651 were never seen by this run.

### 4. Arrhythmia, valvular and other cardiac conditions

**Why** — Arrhythmia, valve disease and cardiomyopathy preceding heart failure.

**Sent**

```text
(("atrial fibrillation"[tiab] OR "valvular heart disease"[tiab] OR "aortic stenosis"[tiab] OR cardiomyopathy[tiab] OR myocarditis[tiab]) AND ("incident heart failure"[tiab] OR "new-onset heart failure"[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 437 papers matched. The first 200 were retrieved (the cap is 200); the other 237 were never seen by this run.

### 5. Metabolic and renal comorbidities

**Why** — Metabolic and renal comorbidities as predictors of heart failure.

**Sent**

```text
(("diabetes mellitus"[tiab] OR obesity[tiab] OR "chronic kidney disease"[tiab] OR "insulin resistance"[tiab] OR dyslipidemia[tiab] OR "thyroid dysfunction"[tiab]) AND ("incident heart failure"[tiab] OR "new-onset heart failure"[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 417 papers matched. The first 200 were retrieved (the cap is 200); the other 217 were never seen by this run.

### 6. Biomarkers and subclinical cardiac dysfunction

**Why** — Biomarkers and subclinical dysfunction predicting heart failure.

**Sent**

```text
(("natriuretic peptide"[tiab] OR "NT-proBNP"[tiab] OR "high-sensitivity troponin"[tiab] OR "diastolic dysfunction"[tiab] OR echocardiography[tiab] OR "C-reactive protein"[tiab]) AND ("incident heart failure"[tiab] OR "future heart failure"[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 381 papers matched. The first 200 were retrieved (the cap is 200); the other 181 were never seen by this run.

### 7. Lifestyle and behavioural factors

**Why** — Lifestyle and behavioural predictors of heart failure.

**Sent**

```text
((smoking[tiab] OR alcohol[tiab] OR "physical activity"[tiab] OR "cardiorespiratory fitness"[tiab] OR diet[tiab] OR "sodium intake"[tiab] OR "sleep apnea"[tiab]) AND ("incident heart failure"[tiab] OR "risk of heart failure"[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 485 papers matched. The first 200 were retrieved (the cap is 200); the other 285 were never seen by this run.

### 8. Social, psychosocial and healthcare-access determinants

**Why** — Social and psychosocial determinants of heart failure onset.

**Sent**

```text
(("socioeconomic status"[tiab] OR "social determinants"[tiab] OR education[tiab] OR depression[tiab] OR "social isolation"[tiab] OR "racial disparities"[tiab] OR neighborhood[tiab]) AND ("incident heart failure"[tiab] OR "risk of heart failure"[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 169 papers matched, and all 169 were retrieved.

### 9. Cardiotoxic drugs, inflammatory and environmental exposures

**Why** — Drug, inflammatory, infectious and environmental exposures preceding heart failure.

**Sent**

```text
((cardiotoxicity[tiab] OR anthracycline[tiab] OR "nonsteroidal anti-inflammatory"[tiab] OR "HIV infection"[tiab] OR "air pollution"[tiab] OR "autoimmune disease"[tiab]) AND ("incident heart failure"[tiab] OR "risk of heart failure"[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 136 papers matched, and all 136 were retrieved.

### 10. Risk prediction models, demographics and genetics

**Why** — Risk models, demographics and genetic risk for incident heart failure.

**Sent**

```text
(("risk prediction"[tiab] OR "risk score"[tiab] OR "machine learning"[tiab] OR "polygenic risk"[tiab] OR "family history"[tiab] OR "sex differences"[tiab]) AND ("incident heart failure"[tiab] OR "heart failure risk"[tiab]))
```

**PubMed ran** — the same term, with each field tag written out in full. Nothing was substituted, expanded or reinterpreted.

**Result** — 382 papers matched. The first 200 were retrieved (the cap is 200); the other 182 were never seen by this run.
