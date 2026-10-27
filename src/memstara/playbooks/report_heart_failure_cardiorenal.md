# Heart failure — Cardiometabolic and renal expert explanation

## Purpose and provenance

Produce a concise clinician-facing explanation from the perspective of cardiometabolic and renal comorbidity, lifestyle and care context.
This is a project-authored HeartFailure adaptation of the report structure and
reasoning rules in the contributed `HIV-Expert-Explanation.md`; this adaptation
is project-authored and is not a clinically validated HeartFailure skill. The original contributed file is unchanged.
Use the upstream Interpretation output, the selected research contract and the
HeartFailure OKF evidence supplied or retrieved by this workflow.

## Expected inputs and study contract

Read the prediction task, target definition and label mapping, cohort description,
selected CSV feature names and definitions, data preparation/split records, the selected
model identity and its measured metrics. Read only that model's interpretation artifact.
Identify SHAP or LIME,
the explained class/output, local/global scope, and any fidelity or stability evidence.
Use the registered contract as authoritative: for the included demonstration the
outcome is `chronic_heart_failure`, positive `1`, negative `0`. Do not change it to
incident disease, hospitalization or mortality. Verify measurement timing and horizon;
if unavailable, describe an exploratory association, not prospective prediction.
Do not assume a predictor, biomarker, clinical phenotype, unit or measurement is in
the CSV merely because an OKF document mentions it. State missing inputs explicitly.

## Specialty focus

Examine metabolic and renal comorbidities, adiposity, smoking, physical activity and social or care-access context only where supplied evidence supports them. Distinguish measured variables from imperfect proxies and distinguish comorbidity from consequences of established heart failure. Do not infer behaviors or barriers from demographic attributes alone.

Keep this specialty lens while assessing all actual selected predictors. Do not
require a specialty feature to be present or replace the upstream hypothesis.

## Required explanation content

Include the following topics within the pipeline-required report structure. Keep
its executive recommendation, ranked hypotheses and output-saving contract; these
specialty topics supplement that structure rather than replacing it.

### 1. Overall Clinical Interpretation

In 2–4 sentences assess whether model behavior is coherent with the supplied
HeartFailure evidence. Identify surprising patterns, proxies and unsupported claims.
Use calibrated terms such as consistent with, plausible or requires cautious
interpretation. Predictive coherence does not validate a clinical mechanism.

### 2. Predictive Power of Selected Features

Report only available held-out AUROC, PR-AUC, calibration/Brier, F1, confusion-matrix
metrics, uncertainty, baselines or statistical tests. Identify the evaluated split,
threshold and sample size. Distinguish training performance, exploration hold-out
performance and separately evaluated reserved/external validation. An unevaluated
reserve is not validation evidence. Do not compare against an unrun model or claim
model superiority from results that were not produced in this execution.
If intervals, significance tests, baseline comparisons or subgroup results are
missing, state that the relevant conclusion cannot be assessed.

### 3. Key Explanatory Factors and Clinical Plausibility

Discuss the most important 5–10 factors actually supplied, or fewer if fewer exist.
For each, identify the model, XAI method/scope, supported rank/magnitude/direction,
CSV definition and supporting OKF document or path. Absolute SHAP magnitudes alone
do not establish direction; LIME explanations remain local unless aggregation is
explicitly provided. Explain disagreement across models or methods in terms of
scope and evidence rather than choosing a preferred narrative. Discuss unexpectedly
high, low or missing factors, correlated predictors, leakage and documentation proxies.
Never equate feature importance or model attribution with a causal effect.

### 4. Potential Clinical Follow-Up

Describe proportionate review of target coding, timing, source definitions,
measurement completeness and any clinical questions supported by the supplied
knowledge. Separate research validation/data collection from patient-care decisions.
Do not prescribe treatment, diagnose a patient, or recommend a new intervention
solely from a feature ranking. If knowledge is insufficient, name the evidence
needed rather than inventing a recommendation or citation.

### 5. Interpretation Caveats and Uncertainty

Cover limitations that apply: selection and missing-data handling, class imbalance,
sample size, overfitting, uncertainty, knowledge-source coverage, feature selection,
leakage or temporal ambiguity, proxy variables, correlated features, XAI background
or perturbation choices, fidelity and random seeds. Explain the limits of any
complete-case preparation recorded for the included demonstration. Do not assume
missing values were imputed. Do not infer external validity or clinical readiness
from this software demonstration. State the largest remaining uncertainties.

### 6. Summary

Conclude in 1–3 sentences with what the evidence supports, what it cannot establish,
and the most useful next validation step.

## Evidence and execution rules

Ground all numeric claims in saved upstream results and all clinical claims in
available knowledge evidence. Cite document identifiers/paths actually read; never
invent literature, metrics, cases, graph paths or retrieval results. This MVP has
no separate specialty database connection; the pipeline-selected OKF is the
knowledge source. Preserve its selection and the dataset/target contract.
If no CSV is selected, explain the analysis proposal conditionally: report no fitted
performance or computed SHAP/LIME results. If no knowledge is supplied, identify
that gap rather than claiming corpus-backed conclusions. Keep performance,
association, explanation and causality distinct. Use precise, non-stigmatizing
language. Follow the pipeline's required report schema and output-saving tools;
save the final report rather than returning prose alone.
