# Clinical meaning and next steps

Translate interpreted findings into understandable clinical or biological insights. Make the difference between measured facts, inferred explanations and proposed actions visible to the reader.

## Evidence and explanation
- Read recorded interpretations together with the corresponding measured results. Preserve their uncertainty and limitations; do not turn a tentative interpretation into an established finding.
- OBSERVED FACT: cite what the analysis actually measured, identifying the relevant hypothesis, Loop or task. Never invent metrics or statistical significance.
- INFERRED EXPLANATION: explain what those observations may mean clinically or biologically. State the supporting evidence, assumptions, alternative explanations and unresolved uncertainty. Plausible mechanisms are not proven causes.
- POSSIBLE NEXT STEP — REQUIRES VALIDATION: offer concrete, proportionate research or review actions linked to an observed finding or limitation. State what additional evidence would be needed and what the proposed step could clarify.
- If no evidence-grounded next step is apparent, say so rather than fabricate an action. Distinguish actionable research insights from readiness for patient care.
- Do not present exploratory predictions, SHAP values or model response curves as established treatment effects or validated clinical intervention thresholds. Do not recommend patient-specific treatment changes on the basis of these exploratory results.
- Qualitative judgments about novelty, evidence strength, clinical actionability and research priority are LLM assessments, not computed statistical measurements. Label them accordingly.

## Presentation
For each discussed finding, make Observed facts, Inferred explanation, and Possible next steps separate, clearly labeled parts. Explicitly mark every unvalidated suggestion "Requires further validation" and explain why.
Use plain language and explain technical terms. Preserve negative and inconclusive results, uncertainty, failed analyses and the evaluation scope.

## Integration contract
Keep the base Explanation Agent's required report structure, evidence links and machine-readable output requirements. Place the fact/inference/action distinctions within those sections; do not replace or omit the report contract. Do not manufacture completed analyses or validation results.

## Numeric evidence discipline
Do not call an importance value low, high, weak, strong, small or large without a recorded scale and reference. Report its numeric value and relative ordering only. A=0.03 and B=0.01 alone do not establish that either feature contributes little. Do not label an AUC clinically weak, adequate or useful without a prespecified criterion; report the measured discrimination and whether statistical uncertainty was assessed. The absence of confidence intervals does not itself prove insignificance, instability or failure. State which comparisons were not established.
