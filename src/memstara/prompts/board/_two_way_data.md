CURRENT EXECUTION CONTRACT: TWO-WAY STRATIFIED ALLOCATION

This versioned execution contract replaces earlier reserve and inner-replicate instructions in the selected playbook for this run.
Use the entire registered dataset. Training-heavy means 70% training and 30% test; balanced means 50% training and 50% test. Balanced refers to partition sizes, not class resampling.
Follow claim_task.data_allocation_request exactly. Submit only its requested fields, reusing any recorded seed. Do not create an independent validation reserve, add inner ML replicates, change rows, or inspect test outcomes to choose settings.
The backend splits the data, records row membership, and gives that allocation to ML. Each scheduled replicate is one train/test experiment. Any cross-validation stays inside training data. Report the measured test results; there is no final reserve evaluation or final refit.
