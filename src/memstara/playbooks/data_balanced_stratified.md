# Balanced train/test allocation with stratification

Allocate 50% of rows to training and 50% to held-out evaluation, stratified by the binary target.
Balanced means equal partition sizes; it does not mean altering the observed class prevalence.
Choose and record an integer split seed. Do not oversample, undersample, impute labels, or change rows.
In the web pipeline, follow claim_task.data_allocation_request and pass the plan as data_plan to submit_result with the extracted subset. In a JSON-only experimental protocol, return the requested data-plan JSON. The program performs and records the actual split.

In the web pipeline, these fractions apply to exploration rows after the independently reserved validation set. Preserve the reserve. For odd row counts, evaluation uses the ceiling of the requested fraction; both classes must be represented in each partition.
