## Reproducible model evaluation

Use the run's saved model and evaluation plan. Train only on the supplied features and target.
Report the measured hold-out AUC, validation results, seed, split and model parameters unchanged.
Hyperparameter selection must use training data only. Never optimize on the final hold-out set.
Report failed evaluations and uncertainty; do not turn a failed tool call into a successful result.

The evaluator requires an already-clean CSV and preserves its rows and values.
Do not impute predictors or labels, remove rows, group rare categories or manufacture
samples. Scaling and categorical encoding are fitted only on training partitions.
Check class counts, average
precision and balanced accuracy alongside AUC. Reduced CV folds and skipped search
must be disclosed. Exploratory model thresholds are not clinical recommendations.
After train_and_score returns a measured failure, still call submit_result with the
claimed task and worker: it records the failure and releases the task without an AUC.
