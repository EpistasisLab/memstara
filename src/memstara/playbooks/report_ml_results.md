<!-- Adapted from shared/skills/ml-results.md. -->

Use this reporting standard when communicating ML evaluation results.

- Identify the task, evaluation source, sample size, outcome prevalence, comparator, threshold, and uncertainty when available. Never invent missing metrics, clinical impact, confidence intervals, or thresholds.
- Distinguish discrimination, calibration, and threshold-dependent performance. For imbalanced classification, report AUROC with average precision, class counts, balanced accuracy, and threshold-dependent metrics when available.
- Prefer held-out or external validation over training performance. State whether calibration, subgroup performance, leakage checks, and distribution shift were evaluated.
- Never interpret predictive performance, feature importance, or model associations as causal evidence.
- State one readiness judgment: `READY FOR FURTHER DEPLOYMENT VALIDATION`, `ITERATE / OPTIMIZE`, `PERFORMANCE INADEQUATE`, or `INSUFFICIENT EVIDENCE TO ASSESS DEPLOYMENT READINESS`.
- End with concrete limitations and next actions. Do not hide poor or conflicting metrics.
