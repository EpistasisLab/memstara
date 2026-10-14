# Interpretation Skill

## Purpose
Generate a concise, reproducible technical interpretation of the dataset, trained classifier, model performance, feature importance, and feature attribution results produced by the workflow.

The report should describe **what was analyzed and what the model produced**. Avoid making clinical claims that require external medical knowledge; those belong in the Explanation report.

---

## Expected Inputs
Use any available outputs from upstream agents, including:

- Training and test datasets or dataset metadata
- Selected feature list and feature metadata
- Model type and fitted model parameters
- Random seed / random state
- Training and inference timing
- Training, validation, and/or test performance metrics
- Confidence intervals, standard deviations, or replicate-level metrics, if available
- Model-native feature importance scores, if available
- SHAP values or other feature attribution outputs
- Class labels, positive-class definition, and prediction task description

Do **not** invent values that are missing. If an expected item is unavailable, state `Not reported` or `Not available`.

---

## Required Report Sections

### 1. Dataset Summary
Summarize the data used for model development and evaluation.

Report, when available:

- Prediction target and positive-class definition
- Number of training, validation, and test examples
- Number of selected features
- Feature types:
  - continuous/numeric
  - binary
  - categorical
  - ordinal
  - temporal or derived features
- Class distribution/prevalence in each split
- Missingness:
  - overall missingness
  - features with substantial missingness
  - missing-data handling or imputation method
- Data preprocessing:
  - encoding
  - scaling/normalization
  - transformations
  - feature selection
- Any major train/test differences or data-quality issues identified by upstream agents

Keep this section descriptive. Do not infer clinical meaning from the variables.

### 2. Model Summary
Describe the trained classifier and how it was evaluated.

Report, when available:

- Classifier/algorithm
- Software/library and version
- Hyperparameters
- Random state / seed
- Class weighting or imbalance handling
- Training procedure
- Cross-validation strategy, if used
- Decision threshold, if relevant
- Training time
- Validation/test inference time
- Hardware or execution environment, if supplied

Report performance separately for each available split.

Preferred metrics:

- AUROC
- AUPRC
- Accuracy
- Sensitivity / recall
- Specificity
- Precision / PPV
- F1 score
- Calibration metrics, if available
- Confidence intervals or variability across folds/runs

Clearly identify which metrics are computed on training, validation, cross-validation, and held-out test data.

### 3. Model-Native Feature Importance
Describe briefly and in layman terms what the feature importance scores actually compute. Include this section only when the classifier exposes a meaningful native importance measure.

For each important feature, report:

- Rank
- Feature name
- Importance score
- Importance type, when known

Examples of importance types include:

- XGBoost gain, weight, or cover
- Random forest impurity-based importance
- Linear/logistic regression coefficient magnitude

Do not treat model-native importance as interchangeable with SHAP attribution. Briefly identify the importance definition used.

### 4. Feature Attribution (SHAP)
Describe briefly and in layman terms what SHAP values actually compute. Summarize SHAP-based attribution results.

When available, report:

- SHAP explainer/method
- Background/reference dataset used
- Class/output being explained
- Global attribution ranking, preferably using mean absolute SHAP
- Signed SHAP summaries when direction is meaningful
- Per-instance attribution results if the workflow requests patient- or sample-level interpretation

For each top-ranked feature, provide:

- Rank
- Feature name
- Mean absolute SHAP value
- Mean signed SHAP value, if available
- Direction/pattern of contribution, only when supported by the SHAP output

Distinguish:

- **Mean absolute SHAP**: magnitude/global importance
- **Signed SHAP**: direction of contribution relative to the model output

Do not infer monotonic relationships from a global signed average unless the underlying attribution pattern supports that conclusion.

### 5. Technical Observations
Briefly note any technically relevant findings such as:

- Large train-test performance gap
- Weak or highly variable test performance
- Strong class imbalance
- High missingness
- Very concentrated feature importance
- Disagreement between model-native importance and SHAP rankings
- Unstable rankings across folds/runs
- Possible data leakage signals reported upstream

Do not speculate beyond the available evidence.

---

## Reporting Rules

1. Preserve numerical precision reasonably; avoid unnecessary decimal places.
2. Label every metric with the data split on which it was computed.
3. Report uncertainty whenever available.
4. Never fabricate confidence intervals, p-values, feature rankings, timing values, or model parameters.
5. Do not describe association or attribution as causation.
6. Do not use SHAP values as evidence that a feature is clinically beneficial, harmful, or actionable.
7. Clearly distinguish:
   - predictive performance,
   - model-native importance,
   - SHAP attribution.
8. If multiple model runs/folds are available, summarize central tendency and variability rather than selecting only the best run.
9. If the model was evaluated only on training data or cross-validation, explicitly state that no held-out test estimate is available.
10. Keep the report concise and technical.

---

## Output Format

# Interpretation Report

## Dataset Summary
[Concise dataset description and table of split sizes, feature counts/types, class balance, and missingness.]

## Model Summary
[Classifier, parameters, random state, training setup, timing, and performance.]

### Performance
| Split | N | AUROC | AUPRC | Other Metrics | Uncertainty |
|---|---:|---:|---:|---|---|
| Train |  |  |  |  |  |
| Validation/CV |  |  |  |  |  |
| Test |  |  |  |  |  |

## Model-Native Feature Importance
[Omit if not applicable.]

| Rank | Feature | Importance Score | Importance Type |
|---:|---|---:|---|
| 1 |  |  |  |

## Feature Attribution (SHAP)
[State explainer, reference/background data, and output/class explained.]

| Rank | Feature | Mean \|SHAP\| | Mean Signed SHAP | Notes |
|---:|---|---:|---:|---|
| 1 |  |  |  |  |

## Technical Observations
- [Observation 1]
- [Observation 2]
