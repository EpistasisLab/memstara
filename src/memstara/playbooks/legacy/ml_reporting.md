## How to report a model

You are working to a reporting standard. It qualifies everything below it.

**Report what the tool returned, not what you expected it to return.** If a number looks
wrong, say that it looks wrong and give it anyway. A corrected number with no note is
indistinguishable from a measurement.

**An importance map means nothing without the engine that produced it.** There are two routes
and they are not the same quantity. `random_forest` and `xgboost` return impurity decrease or
gain: non-negative, summing to about 1. `sklearn_hgb` has no `feature_importances_`, so the
tool falls back to permutation importance and returns a drop in AUC: no fixed scale, and
negative for a column whose removal helped. Pass the engine through with the map every time.

**Never rank a column from one map against a column from another** unless both maps came from
the same engine. Doing it compares a fraction of impurity with a change in AUC.

**Say what the AUC is an AUC of.** The outcome column travels on the task; carry it into the
result rather than leaving a reader to infer it.

**Do not treat one engine's number as the answer.** No engine dominated across the four
sub-datasets this was measured on — the random forest beat the default on one and lost on the
other three, by up to 0.037 either way. A single fit is one observation and should be reported
as one.
