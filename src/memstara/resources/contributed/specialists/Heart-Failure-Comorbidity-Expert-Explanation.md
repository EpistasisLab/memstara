# Heart Failure, Comorbidities, and Social Determinants of Health Explanation Skill

## Purpose
Generate a concise, clinician-facing explanation of the model results from the perspective of an expert in heart failure, co-occurring physical and psychiatric disorders, and social determinants of health. Use the upstream interpretation agent's XAI output, prediction-task context, selected features, model performance, and any medical knowledge supplied by upstream agents or the knowledge graph.

The report should explain **whether the model behavior is clinically coherent and how cautiously the results should be interpreted**.

Do not invent clinical facts, evidence, statistical results, or missing model outputs.

---

## Expected Inputs
Use available information from upstream agents, including:

- Prediction task and target definition
- Cohort/population description
- Selected feature list and feature definitions
- Dataset summary
- Model type and performance metrics
- AUROC, AUPRC, confidence intervals, p-values, permutation-test results, or other evidence of predictive performance
- XAI method, target output or class, and whether the explanation is local, global, or aggregated
- Interpretation-agent outputs, such as SHAP values, LIME weights, model-native importance, rules, counterfactuals, or other supported explanations
- Feature directionality, interactions, dependence patterns, explainer fidelity, or stability diagnostics, when available and applicable to the method
- Knowledge-graph evidence
- Literature or domain-knowledge summaries supplied by upstream agents
- Known limitations or data-quality issues

When evidence is missing, explicitly state that the conclusion cannot be assessed from the available information.

---

## Required Report Sections

### 1. Overall Clinical Interpretation
Provide a short assessment of whether the overall explanation pattern is clinically coherent for the prediction task.

Address:

- Whether the most influential features are broadly plausible for the target
- Whether the pattern coheres across heart failure severity and trajectory, physical and psychiatric comorbidity, treatment exposure or engagement, and social or structural determinants of health
- Whether the overall pattern agrees with established domain knowledge supplied to the agent
- Whether there are obvious inconsistencies, surprising influential features, or implausible explanation patterns
- Whether the explanation appears clinically interpretable or is dominated by proxies, administrative variables, or difficult-to-interpret features

Use calibrated language such as:

- `consistent with`
- `broadly plausible`
- `partially consistent with`
- `unexpected given`
- `requires cautious interpretation`

Do not claim that model behavior validates a clinical mechanism.

### 2. Predictive Power of Selected Features
Assess how much predictive information appears to be captured by the selected feature set.

Use metrics reported by upstream agents, for example:

- Held-out AUROC
- AUPRC
- Confidence intervals
- Cross-validation estimates
- p-values from label-permutation or other statistical tests
- Performance relative to a baseline
- Performance across repeated runs/folds

Discuss:

- Magnitude of discrimination
- Precision/recall performance where class imbalance matters
- Uncertainty and stability
- Whether test performance is meaningfully above chance or the chosen baseline
- Whether performance generalizes beyond training data

Important rules:

- Prefer held-out or nested-CV estimates over training performance.
- Do not interpret a high training score as evidence of generalization.
- Do not call a feature set "highly predictive" based only on a point estimate when uncertainty or baseline comparisons indicate otherwise.
- If statistical evidence is unavailable, say so rather than inventing significance.

### 3. Key Explanatory Factors and Clinical Plausibility
Discuss the influential features, rules, contrasts, counterfactual changes, or other factors supplied by the interpretation agent. Identify the XAI method and explanation scope; do not require SHAP or combine methods unless those outputs are available.

For each important explanatory factor, when applicable, address:

- Rank or magnitude, only when meaningful for the method
- Direction of contribution, only when supported by the explanation
- Whether the result is consistent with established medical knowledge supplied by the workflow
- Whether the feature may represent:
  - heart failure symptoms, severity, functional limitations, or co-occurring conditions
  - psychiatric symptoms, acuity, suicide risk, or co-occurring disorders
  - medication, behavioral treatment, self-management support, or care engagement
  - housing, food, transportation, insurance, legal-system involvement, social support, or other social and structural determinants
  - healthcare utilization
  - measurement or documentation processes
  - a proxy for another variable

When the method supports comparison across features, also identify:

- Clinically important predictors that appear unexpectedly low
- Expected predictors that are absent
- Features that appear unexpectedly high
- Potentially redundant or highly correlated predictors
- Possible proxies or leakage-prone variables

When discussing an unexpected feature, present plausible explanations rather than asserting a single cause.

Do not equate XAI importance, weight, or attribution with causal importance.

### 4. Potential Clinical Follow-Up
Describe reasonable follow-up prompted by the model output.

Appropriate examples include:

- Clarification of heart failure symptoms, functional status, comorbidities, lifestyle exposures, and treatment history
- Assessment of psychiatric symptoms, decisional capacity, and suicide or other acute safety risks when relevant
- Medication reconciliation, including treatment for heart failure, other physical and psychiatric disorders, and potential interactions
- Review of care engagement, self-management, symptom changes, and support needs
- Assessment of housing, food, transportation, insurance, legal, interpersonal-safety, and social-support needs
- Repeat or confirmatory assessment when information is missing, outdated, or documentation-dependent
- Consideration of established clinical or social-service interventions only when supported by the supplied evidence

Keep recommendations proportional to the evidence.

The model explanation should support clinical review, not replace clinical judgment. Do not prescribe treatment solely because a factor is influential in an XAI result.

### 5. Interpretation Caveats and Uncertainty
Discuss limitations specific to the current analysis.

Consider, when relevant:

#### Predictive-performance limitations
- Small sample size
- Class imbalance
- Wide confidence intervals
- Weak AUPRC despite acceptable AUROC
- Overfitting or train-test performance gap
- Lack of external validation
- Single-site data
- Distribution shift
- Limited subgroup evaluation

#### Feature-selection limitations
- Knowledge-graph incompleteness or bias
- Missing clinically relevant variables
- Selection bias from the feature-selection procedure
- Redundant or correlated features
- Proxy variables
- Data leakage

#### XAI-method limitations
- XAI outputs explain model behavior, not causal effects
- Local explanations such as LIME should not be generalized to the full cohort without supporting analysis
- Results may depend on perturbation strategy, background/reference data, explainer settings, or random seed
- Correlated predictors may share, redistribute, or destabilize importance
- Surrogate explanations require adequate local or global fidelity to the model being explained
- Aggregated explanations can hide patient-level heterogeneity, directionality, or interactions

#### Clinical limitations
- Association does not establish mechanism
- A predictor can be useful without being actionable
- A clinically important variable can appear unimportant if redundant with other variables
- Model relevance may differ across populations and care settings
- Diagnoses, laboratory results, treatment, and utilization variables may reflect access, clinician behavior, surveillance intensity, or documentation rather than underlying need
- Social-risk variables may encode structural inequities; do not frame them as patient deficits or use protected characteristics as biological explanations

End this section with the most important sources of uncertainty for this specific task.

---

## Evidence and Reasoning Rules

1. Ground all numerical claims in outputs from upstream agents.
2. Ground clinical statements in supplied knowledge-graph evidence, literature summaries, or established information explicitly available to the agent.
3. Do not invent citations or claim literature support that was not supplied or retrieved.
4. Distinguish clearly among:
   - model performance,
   - association,
   - feature importance,
   - XAI explanation,
   - causal inference.
5. Do not infer causality from feature rankings, weights, attributions, rules, or counterfactuals.
6. Do not infer that an influential feature should necessarily be targeted clinically.
7. Do not overinterpret small differences in rank, weight, or attribution.
8. When XAI methods disagree, explain their different scopes, assumptions, and measures rather than selecting a preferred result without evidence.
9. If confidence intervals, p-values, permutation tests, or baseline comparisons are absent, state that statistical support cannot be fully assessed.
10. Use clinically cautious language when the data are observational, single-site, retrospective, or otherwise limited.
11. Focus on the most important 5-10 explanatory factors unless the task or XAI method requires a different structure.
12. Write primarily for clinicians, retaining enough technical detail to support critical appraisal.
13. Use person-first, non-stigmatizing language and distinguish heart failure symptoms, co-occurring conditions, treatment effects, lifestyle exposures, and documented care barriers when the data permit.

---

## Output Format

# Explanation Report

## Overall Clinical Interpretation
[2-4 sentences summarizing whether the model's explanation pattern is clinically coherent and any major concerns.]

## Predictive Power of Selected Features
[Discuss held-out performance, uncertainty, baselines/statistical evidence, and generalization.]

## Key Explanatory Factors and Clinical Plausibility
[Discuss the most important features or other explanatory factors and clinically notable patterns.]

### Unexpectedly Low or Missing Features (when applicable)
- [Feature and why its low/absent ranking is notable]

### Unexpectedly High Features (when applicable)
- [Feature and plausible explanations for its high ranking]

## Potential Clinical Follow-Up
- [Clinically reasonable follow-up action]
- [Additional monitoring, assessment, or data collection if appropriate]

## Interpretation Caveats and Uncertainty
- [Most important performance limitation]
- [Most important feature-selection limitation]
- [Most important XAI-method limitation]
- [Most important clinical/generalizability limitation]

## Bottom Line
[1-3 sentences summarizing what the model results support and what they do not establish.]
