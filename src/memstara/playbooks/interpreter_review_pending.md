## Provisional explainability contract — replace with reviewer original

reviewer ORIGINAL REQUIRED. This is an integration placeholder written by reviewer, not
material supplied or approved by reviewer. Replace this skill with reviewer's actual file
when available. Preserve this notice in interpretations and downstream reports.

Use the actual selected features, fixed target, knowledge provenance and measured
evaluation to explain whether a hypothesis merits further investigation.

Describe three separate kinds of evidence:
- SHAP or permutation importance: how strongly the fitted model used each feature.
- Feature response ranges: the recorded before/after predicted probabilities and
  direction over the measured range. These are exploratory model effects, not
  causal effects or validated patient treatment cutoffs.
- The fixed probability operating point: sensitivity, specificity, precision,
  false positives and false negatives on the held-out cohort. State that the 0.5
  cutoff was fixed before evaluation and has not been clinically validated.

For actionability, name the proposed follow-up research question, prerequisites
for interpreting the feature (units, timing, population and biological meaning),
and the evidence still required. Do not invent missing definitions, thresholds,
clinical utility, interventions or external validation. Distinguish an interesting
testable hypothesis from a recommendation ready for clinical practice.
