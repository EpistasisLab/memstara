# Logistic Regression (LR)

Configure Logistic Regression (LR) as the predeclared primary model: primary_model=logistic_regression.
Choose its complete parameters, scaling and probability threshold from get_ml_configuration before fitting.
The shared paired-evaluation contract also requires a complete XGBoost comparator configuration.
Both fitted models and their measured results must reach Interpretation; selecting this skill does not remove the comparator.
Use training data only to choose settings. Follow the returned resource limits and immutable split contract.
