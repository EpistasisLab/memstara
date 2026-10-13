## Common training, evaluation and result contract

The selected skill declares the primary model, not a winner chosen after scoring.
Configure and train both LR and XGBoost on the same supplied predictors, target and
saved split. Preserve both model artifacts and model_results for SHAP/LIME access.
Follow a server_frozen plan when present; never override a precommitted experiment.

Use only training partitions for fitting preprocessing and tuning. Do not impute
labels or predictors, remove rows, manufacture samples, or change upstream splits.
Inspect class counts and report reduced CV folds or skipped search. Respect the
server's CPU, memory, fit-count and time limits; do not request unrestricted jobs.

Save the accepted parameters, preprocessing, seed, split identity, threshold,
software provenance and all returned metrics unchanged. Distinguish exploratory
test results from reserved validation and training results. Preserve missing or
undefined metrics as such. Include AUROC, average precision, calibration and
threshold-dependent metrics only when returned by the evaluator. Retain the
confusion matrix's partition, positive class and threshold identity.

Pass result identities and the engine alongside feature importance: gain,
permutation score changes and SHAP values have different meanings and units.
Do not manufacture metrics, confidence intervals or causal interpretations.
After a measured failure, submit the recorded error without an AUC and stop.
Clinical presentation and readiness judgments belong to downstream reporting;
the ML stage supplies faithful structured evidence, not a deployment decision.
