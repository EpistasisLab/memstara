<!--
The first playbook, and it is deliberately a small one.

The governance and reporting standards the meeting of 2026-08-26 meant were posted to the
Slack Asari channel, which this account cannot open (`A-23`). Writing a governance document
from imagination and calling it that would put a standard nobody agreed to into a run record
that reads as though somebody had. So this one claims nothing beyond what was measured in
this repository on 2026-09-08, and it exists mainly so the mechanism has something real to
carry: a run can be started with `--playbook-ml ml_reporting` and the record can be checked.

Every sentence below is traceable. The two importance routes and their scales are
`src/memstara/mcp_servers/ml.py`'s `_importance`, measured across the four `merge_verify`
sub-datasets: `feature_importances_` sums to exactly 1.0000 under random_forest, while the
permutation route summed to 0.0819 and 0.2572 with a minimum entry of -0.0131. That no engine
dominates is `A-23`'s measurement — changing engine moved AUC by up to 0.037 in both
directions across those same four tasks.

When the Asari files arrive this is the file they replace, or the file they sit beside.
-->

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
