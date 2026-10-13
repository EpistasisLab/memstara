# Exact feature extraction

Extract exactly the supplied feature columns and the fixed target using slice_columns.
Preserve column names and order. Report absent columns and extraction errors explicitly.
Do not add predictors, clean data, impute missing values, or change the target.
Record the output path through submit_result so the ML stage receives the verified dataset.
