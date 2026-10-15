# Logistic Regression (LR)

Configure Logistic Regression (LR) as the predeclared primary model: primary_model=logistic_regression.
Choose Logistic Regression as the primary model for this skill. For each new pipeline run, make fresh stochastic choices for every editable LR parameter, random_state, numeric scaling, probability threshold and training-only CV setting shown by get_ml_configuration. Do not copy template defaults. Keep only the server-owned CPU, binary-outcome and library-compatibility settings; record your rationale before either model is fitted.
The shared paired-evaluation contract also requires a complete XGBoost comparator configuration.
Both fitted models and their measured results must reach Interpretation; selecting this skill does not remove the comparator.
Use training data only to choose settings. Follow the returned resource limits and immutable split contract.
