# Logistic Regression (LR)

This skill selects Logistic Regression (`primary_model=logistic_regression`). It is the only model configured, fitted, evaluated and interpreted for this pipeline combination.

For each new pipeline run, choose fresh values for LR's editable parameters: `C`, `max_iter`, `tol`, `random_state`, `solver`, `penalty`, `class_weight`, and `fit_intercept`. Also choose LR's numeric-scaling setting and probability threshold. Use only the ranges and choices returned by `get_ml_configuration`; do not copy template defaults. Include a concise rationale for the LR-specific choices.

The `l1` penalty requires the `liblinear` solver.
