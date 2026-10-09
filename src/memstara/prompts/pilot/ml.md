---
goal: Specify both LR and XGBoost configurations before fitting either model.
---
Return exactly one JSON object with models, scale_numeric, threshold, xai_rows, lime_samples and seed.
models contains logistic_regression and xgboost. For each, return every parameter in parameter_defaults,
including parameters whose default you intentionally retain. JSON null for XGBoost missing means its NaN sentinel.
Choose integer random_state values explicitly. Use compatible solver and regularization settings for LR.
XGBoost must use objective binary:logistic, booster gbtree or null, device cpu or null, and n_jobs=1.
Do not configure callbacks or early stopping: held-out rows must not guide training.
scale_numeric is a boolean; it controls training-fitted scaling shared by the two estimators.
threshold is a probability strictly between 0 and 1 chosen now, never tuned on held-out results.
xai_rows is an integer from 1 to 50; lime_samples is an integer from 100 to 10000;
seed is an integer from 0 to 2147483647 for reproducible SHAP-background and LIME sampling.
No historical frozen ML policy overrides your returned parameters. The selected ML skill is additional context.
