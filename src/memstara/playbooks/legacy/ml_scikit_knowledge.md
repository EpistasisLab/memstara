Apply this operational knowledge to the ML stage.

- Define the target first, then split the data. Fit preprocessing inside a pipeline and inside each training fold; never impute labels or preprocess the complete dataset before validation.
- Use stratified splitting for binary classification when appropriate. Use group-aware or time-aware splitting when observations are clustered, repeated, or temporal.
- Tune hyperparameters only on training data with cross-validation. Keep the final hold-out set untouched until model selection is complete.
- Compare the selected model with a simple baseline when possible. For rare outcomes, report AUROC together with average precision and class counts; evaluate calibration when probabilities are interpreted as risk.
- Record model, preprocessing, seed, split, folds, hyperparameters, metrics, and software version. Predictive performance and feature importance are associations, not causal evidence.
