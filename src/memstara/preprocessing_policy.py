"""Versioned feature contract: new runs accept prepared numeric predictors.

Historical frozen runs retain their original transformation contract. This does
not change saved models. Missing values are rejected independently of this version.
"""

VERSION = "analysis_ready_v1"
LEGACY = "legacy_encoding_v1"
TYPED = "typed_predictors_v1"


def resolve(snapshot=None):
    if snapshot is None:
        from memstara.evaluation import active_plan

        snapshot = active_plan()
    if not snapshot:
        return VERSION
    value = snapshot.get("preprocessing_policy", LEGACY)
    if value not in (VERSION, LEGACY, TYPED):
        raise ValueError("Unsupported feature preprocessing policy")
    return value


def analysis_ready(snapshot=None):
    return resolve(snapshot) in (VERSION, TYPED)


def typed_predictors(snapshot=None):
    return resolve(snapshot) == TYPED


def requires_numeric(snapshot=None):
    return analysis_ready(snapshot) and not typed_predictors(snapshot)
