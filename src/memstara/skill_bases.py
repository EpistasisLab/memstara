"""Executable policies for custom Data/ML instructions, frozen with each run."""

CHOICES = {
    "data": ("data_training_heavy", "data_balanced_stratified"),
    "ml": ("ml_logistic_regression", "ml_xgboost"),
}


def validate(stage, value):
    if not isinstance(value, str) or value not in CHOICES.get(stage, ()):
        raise ValueError("Choose a supported Data split or ML algorithm for this skill.")
    return value


def base_for(snapshot, name):
    return (snapshot or {}).get("skill_bindings", {}).get(name, name)
