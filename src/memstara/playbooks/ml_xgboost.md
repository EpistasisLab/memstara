# XGBoost

This skill selects XGBoost (`primary_model=xgboost`). It is the only model configured, fitted, evaluated and interpreted for this pipeline combination.

For each new pipeline run, choose fresh values for XGBoost's editable parameters: `n_estimators`, `max_depth`, `learning_rate`, `min_child_weight`, `subsample`, `colsample_bytree`, `reg_alpha`, `reg_lambda`, `gamma`, `scale_pos_weight`, `max_bin`, and `random_state`. Also choose XGBoost's numeric-scaling setting and probability threshold. Use only the ranges returned by `get_ml_configuration`; do not copy template defaults. Include a concise rationale for the XGBoost-specific choices.
