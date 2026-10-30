"""Agent-proposed configuration for the user-selected model."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

VERSION = "agent_selected_ml_v2"
MODELS = ("logistic_regression", "xgboost")
DEFAULT_SKILL = "ml_default_logistic_regression"
MODEL_SKILLS = {
    DEFAULT_SKILL: "logistic_regression",
    "ml_logistic_regression": "logistic_regression",
    "ml_xgboost": "xgboost",
}


def for_dataset(snapshot, path):
    """Resolve the selected model from this task's saved combination, not another loop."""
    if not snapshot:
        return snapshot
    from memstara.combinations import task_books

    handoff = path.with_suffix(".comparison.json")
    record = json.loads(handoff.read_text()) if handoff.exists() else {}
    names = task_books(snapshot, record.get("trial", 0)).get("ml", [])
    from memstara.skill_bases import base_for

    bases = [base_for(snapshot, name) for name in names]
    primary = next((MODEL_SKILLS[name] for name in bases if name in MODEL_SKILLS), None)
    if primary and snapshot.get("combination_plan") and "trial" not in record:
        raise ValueError("Selected ML skill requires the saved task trial identity")
    return {**snapshot, "_selected_ml_primary": primary, "_default_ml": names == [DEFAULT_SKILL]}


def uses_default(snapshot):
    snapshot = snapshot or {}
    return snapshot.get("_default_ml", snapshot.get("books", {}).get("ml") == [DEFAULT_SKILL])


def default_plan():
    from sklearn.linear_model import LogisticRegression

    return {
        "primary_model": "logistic_regression",
        "folds": 0,
        "models": {
            "logistic_regression": {
                "parameters": LogisticRegression().get_params(),
                "scale_numeric": False,
                "threshold": 0.5,
            }
        },
        "rationale": "No ML skill selected: installed scikit-learn LogisticRegression defaults.",
    }


def selected_model(snapshot):
    snapshot = snapshot or {}
    selected = snapshot.get("_selected_ml_primary")
    if selected is None:
        from memstara.skill_bases import base_for

        bases = [base_for(snapshot, name) for name in snapshot.get("books", {}).get("ml", [])]
        from_books = [MODEL_SKILLS[name] for name in bases if name in MODEL_SKILLS]
        selected = from_books[0] if len(from_books) == 1 else None
    if selected not in MODELS:
        raise ValueError("Choose exactly one supported ML model skill for this task")
    return selected


# Non-editable installed-library parameters remain server-owned system defaults.
# Arbitrary callbacks, GPU execution and unconstrained parallelism are never accepted.
RANGES = {
    "logistic_regression": {
        "C": (1e-5, 1e4),
        "max_iter": (50, 2000),
        "tol": (1e-6, 0.01),
        "random_state": (0, 2147483647),
    },
    "xgboost": {
        "n_estimators": (10, 400),
        "max_depth": (1, 8),
        "learning_rate": (0.005, 0.5),
        "min_child_weight": (0, 100),
        "subsample": (0.5, 1),
        "colsample_bytree": (0.5, 1),
        "reg_alpha": (0, 100),
        "reg_lambda": (0, 100),
        "gamma": (0, 100),
        "scale_pos_weight": (0.01, 100),
        "max_bin": (32, 256),
        "random_state": (0, 2147483647),
    },
}
CHOICES: dict[str, dict[str, list[str | bool | None]]] = {
    "logistic_regression": {
        "solver": ["lbfgs", "liblinear"],
        "penalty": ["l2", "l1"],
        "class_weight": [None, "balanced"],
        "fit_intercept": [True, False],
    },
    "xgboost": {},
}
INTEGERS = {"max_iter", "n_estimators", "max_depth", "max_bin", "random_state"}


def override_schema():
    """The UI consumes the same bounded parameter contract as execution."""
    return {
        "version": 1,
        "models": {
            name: {
                "parameters": {
                    **{
                        key: {"type": "integer" if key in INTEGERS else "number", "min": low, "max": high}
                        for key, (low, high) in RANGES[name].items()
                    },
                    **{key: {"type": "choice", "choices": values} for key, values in CHOICES[name].items()},
                }
            }
            for name in MODELS
        },
        "folds": [0, 2, 3, 4, 5],
        "threshold": {"min": 0.05, "max": 0.95},
        "resource_limits": policy(),
    }


def validate_overrides(value, skills=None, *, replicates=None):
    if value == {}:
        return {}
    if not isinstance(value, dict) or set(value) - {"version", "models", "folds"}:
        raise ValueError("ML advanced settings accept only version, models and folds")
    if type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("ML advanced settings require version=1")
    models = value.get("models", {})
    if not isinstance(models, dict) or set(models) - set(MODELS):
        raise ValueError("ML advanced settings support only LR and XGBoost")
    selected = {MODEL_SKILLS[s] for s in skills if s in MODEL_SKILLS} if skills is not None else set(MODELS)
    if set(models) - selected or ("folds" in value and not selected):
        raise ValueError("Advanced model settings must match the selected ML skills")
    for name, settings in models.items():
        if not isinstance(settings, dict) or set(settings) - {"parameters", "scale_numeric", "threshold"}:
            raise ValueError("Each advanced model accepts parameters, scale_numeric and threshold")
        parameters = settings.get("parameters", {})
        if not isinstance(parameters, dict) or set(parameters) - (set(RANGES[name]) | set(CHOICES[name])):
            raise ValueError(f"{name}: unsupported or server-owned model parameter")
        for key, item in parameters.items():
            if key in RANGES[name]:
                number(item, *RANGES[name][key], key)
                if key in INTEGERS and type(item) is not int:
                    raise ValueError(f"{key} must be an integer")
            elif not any(type(item) is type(option) and item == option for option in CHOICES[name][key]):
                raise ValueError(f"{name}.{key} is outside the supported choices")
        if "scale_numeric" in settings and type(settings["scale_numeric"]) is not bool:
            raise ValueError("scale_numeric must be boolean")
        if "threshold" in settings:
            number(settings["threshold"], 0.05, 0.95, "threshold")
        if parameters.get("penalty") == "l1" and parameters.get("solver") == "lbfgs":
            raise ValueError("LR l1 requires liblinear")
    if "folds" in value and (type(value["folds"]) is not int or value["folds"] not in (0, 2, 3, 4, 5)):
        raise ValueError("Training CV folds must be 0 or 2–5")
    return copy.deepcopy(value)


def apply_overrides(proposal, overrides):
    chosen = copy.deepcopy(proposal)
    if not isinstance(chosen, dict) or not isinstance(chosen.get("models"), dict):
        return chosen  # Complete-plan validation supplies the actionable error.
    if "folds" in overrides:
        chosen["folds"] = overrides["folds"]
    for name, settings in overrides.get("models", {}).items():
        model = chosen["models"].get(name)
        if not isinstance(model, dict) or not isinstance(model.get("parameters"), dict):
            continue
        model["parameters"].update(settings.get("parameters", {}))
        for key in ("scale_numeric", "threshold"):
            if key in settings:
                model[key] = settings[key]
    return chosen


def policy():
    # Null ceilings mean no resource-based rejection for new executions.
    # Serial scheduling and one native thread avoid parallel oversubscription.
    return {
        "version": VERSION,
        "threads": 1,
        "concurrent_jobs": 1,
        "memory_bytes": None,
        "wall_seconds": None,
        "max_fits": None,
        "max_csv_bytes": None,
        "max_dense_cells": None,
        "max_encoded_columns": None,
    }


def enabled(snapshot):
    return (snapshot or {}).get("ml_configuration_policy", {}).get("version") in {VERSION, "agent_paired_ml_v1"}


def context(snapshot, evaluation):
    if uses_default(snapshot):
        if snapshot.get("controlled_comparison") or snapshot.get("ml_overrides"):
            raise ValueError("Default Logistic Regression does not accept model overrides")
        return {
            "version": VERSION,
            "required": True,
            "plan_source": "server_frozen",
            "configuration_source": "sklearn_default",
            "proposal_template": default_plan(),
            "editable_parameter_ranges": {},
            "editable_parameter_choices": {},
            "editable_common_settings": {},
            "fixed": {
                "primary_model": "logistic_regression",
                "data_seed": evaluation["seed"],
                "test_size": evaluation["test_size"],
            },
            "instructions": "Call train_and_score without ml_plan. The server applies installed-library defaults.",
        }
    controls = (snapshot or {}).get("controlled_comparison")
    if controls:
        base = context({k: v for k, v in snapshot.items() if k != "controlled_comparison"}, evaluation)
        base.update(
            proposal_template=copy.deepcopy(controls["ml_plan"]),
            editable_parameter_ranges={},
            editable_parameter_choices={},
            editable_common_settings={},
            plan_source="server_frozen",
            instructions="Matched comparison: the server applies proposal_template directly. "
            "Call train_and_score with path and y_column; omit ml_plan. "
            "Any supplied ml_plan is recorded but cannot override the frozen plan.",
        )
        base["fixed"]["controlled_comparison"] = True
        base["fixed"]["primary_model"] = controls["ml_plan"]["primary_model"]
        return base
    from memstara.evaluation import model_for
    from memstara.preprocessing_policy import analysis_ready

    prepared_input = analysis_ready(snapshot)
    chosen_model = selected_model(snapshot)
    models = {}
    for name in (chosen_model,):
        model = model_for(name, evaluation["seed"])
        if name == "logistic_regression":
            model.set_params(penalty="l2")
        if name == "xgboost":
            model.set_params(
                tree_method="hist",
                device="cpu",
                learning_rate=0.1,
                min_child_weight=1,
                subsample=1.0,
                colsample_bytree=1.0,
                reg_alpha=0.0,
                reg_lambda=1.0,
                gamma=0.0,
                scale_pos_weight=1.0,
                max_bin=256,
            )
        params = json.loads(json.dumps(model.get_params(), default=str), parse_constant=str)
        models[name] = {
            "parameters": params,
            "scale_numeric": not prepared_input and name == "logistic_regression",
            "threshold": 0.5,
        }
    specification = {
        "version": VERSION,
        "required": enabled(snapshot),
        "proposal_template": {"primary_model": chosen_model, "folds": 0, "models": models, "rationale": ""},
        "editable_parameter_ranges": {chosen_model: RANGES[chosen_model]},
        "editable_parameter_choices": {chosen_model: CHOICES[chosen_model]},
        "editable_common_settings": {
            "scale_numeric": [False] if prepared_input else [True, False],
            "threshold": [0.05, 0.95],
            "folds": [0, 2, 3, 4, 5],
        },
        "fixed": {
            "primary_model": snapshot.get("_selected_ml_primary"),
            "data_seed": evaluation["seed"],
            "test_size": evaluation["test_size"],
            "replicates": evaluation["replicates"],
            "search_trials": 1,
            "resource_limits": (snapshot or {}).get("ml_configuration_policy"),
            "system_parameters": "CPU execution, one worker/thread, binary-classification objective, "
            "and the installed-library compatibility contract remain server-owned.",
        },
        "preprocessing_contract": "No row cleaning or imputation. LR requires complete predictors. "
        "Categoricals use training-fold one-hot encoding. "
        "Numeric scaling is agent-selected.",
        "instructions": "Return the complete proposal_template with fresh stochastic choices and rationale. "
        "For every new pipeline execution, choose new values for every editable statistical "
        "parameter, numeric scaling, threshold, and CV folds; do not copy template defaults. "
        "Configure only the selected model before seeing results. "
        "Preserve upstream features/splits. "
        "LR l1 requires liblinear. No hold-out tuning; accepted proposals are immutable.",
    }
    from memstara.evaluation import classifier_seed_policy, CLASSIFIER_SEED_POLICY

    if classifier_seed_policy(snapshot) == CLASSIFIER_SEED_POLICY:
        specification["fixed"]["classifier_seed_policy"] = CLASSIFIER_SEED_POLICY
        specification["instructions"] += (
            " The server applies each recorded split seed as classifier random_state "
            "before fitting; any proposed random_state is recorded but cannot override the split seed."
        )
    if prepared_input:
        specification["preprocessing_contract"] = (
            "Require prepared numeric predictors. No automatic encoding or scaling. "
            "Missing values block execution for every classifier; no imputation is permitted."
        )
        specification["instructions"] = (
            specification["instructions"].replace("parameter, numeric scaling, threshold", "parameter, threshold")
            + " Keep scale_numeric false."
        )
    from memstara.missing_values import resolve_policy

    if resolve_policy(snapshot) == "impute_train_v1":
        specification["preprocessing_contract"] = (
            "User approved imputation: training-only mean for continuous predictors and mode for binary or "
            "declared categorical predictors, fitted inside each CV fold and applied to test data. "
            "Never impute before splitting, alter rows or impute target labels. "
            + ("No automatic encoding or scaling." if prepared_input else "Encoding follows the frozen policy.")
        )
    from memstara.preprocessing_policy import typed_predictors

    if typed_predictors(snapshot):
        specification["preprocessing_contract"] = (
            "User-approved training-only mean/mode imputation when enabled. "
            "Use the frozen predictor_types: continuous means, categorical/binary modes. "
            "Fit categorical encoding inside each training/CV fold; never on test data. "
            "No scaling, row removal or target imputation."
        )
    overrides = validate_overrides(snapshot.get("ml_overrides", {}))
    if prepared_input and any(v.get("scale_numeric") for v in overrides.get("models", {}).values()):
        raise ValueError("Automatic scaling is disabled; remove scale_numeric overrides")
    if overrides:
        specification["proposal_template"] = apply_overrides(specification["proposal_template"], overrides)
        params = specification["proposal_template"]["models"][chosen_model]["parameters"]
        if chosen_model == "logistic_regression" and params["penalty"] == "l1" and params["solver"] == "lbfgs":
            params["solver"] = "liblinear"  # Compatible automatic solver suggestion.
        specification["user_overrides"] = overrides
        specification["editable_parameter_ranges"] = {chosen_model: copy.deepcopy(RANGES[chosen_model])}
        specification["editable_parameter_choices"] = {chosen_model: copy.deepcopy(CHOICES[chosen_model])}
        for name, settings in overrides.get("models", {}).items():
            if name != chosen_model:
                continue
            for key in settings.get("parameters", {}):
                specification["editable_parameter_ranges"][name].pop(key, None)
                specification["editable_parameter_choices"][name].pop(key, None)
        specification["fixed"]["user_overrides"] = overrides
        specification["instructions"] += (
            " User overrides are fixed and take precedence. "
            "Choose only remaining automatic settings; do not replace fixed user values."
        )
    return specification


def resolve(proposal, snapshot, evaluation):
    """Fixed experiments execute a server-owned plan, never an LLM transcription."""
    controls = (snapshot or {}).get("controlled_comparison")
    overrides = validate_overrides((snapshot or {}).get("ml_overrides", {}))
    if controls and overrides:
        raise ValueError("Controlled comparisons cannot also use advanced ML overrides")
    fallback = uses_default(snapshot)
    if fallback and (controls or overrides):
        raise ValueError("Default Logistic Regression does not accept model overrides")
    chosen = default_plan() if fallback else controls["ml_plan"] if controls else proposal
    if overrides:
        chosen = apply_overrides(chosen, overrides)
    effective = validate(chosen, snapshot, evaluation)
    return effective, {
        "source": (
            "sklearn_default"
            if fallback
            else "server_frozen"
            if controls
            else "user_overrides_and_agent_proposal"
            if overrides
            else "agent_proposal"
        ),
        "agent_proposal_supplied": proposal is not None,
        "agent_proposal": copy.deepcopy(proposal),
        "agent_proposal_ignored": bool(controls or fallback) and proposal is not None,
        "effective_plan": copy.deepcopy(effective),
        **({"user_overrides": overrides} if overrides else {}),
    }


def validate(proposal, snapshot, evaluation):
    if uses_default(snapshot):
        expected = context(snapshot, evaluation)["proposal_template"]
        if proposal != expected:
            raise ValueError("Default Logistic Regression must preserve installed-library defaults")
        return copy.deepcopy(expected)
    controls = (snapshot or {}).get("controlled_comparison")
    if controls:
        if proposal != controls["ml_plan"]:
            raise ValueError("ML settings must equal the frozen controlled-comparison plan; no tuning is permitted")
        snapshot = {k: v for k, v in snapshot.items() if k != "controlled_comparison"}
    spec = context(snapshot, evaluation)
    if not isinstance(proposal, dict) or set(proposal) != {"primary_model", "folds", "models", "rationale"}:
        raise ValueError("ml_plan requires primary_model, folds, models and rationale")
    if proposal["primary_model"] not in MODELS:
        raise ValueError("primary_model must be logistic_regression or xgboost")
    if (
        not controls
        and snapshot.get("_selected_ml_primary")
        and (proposal["primary_model"] != snapshot["_selected_ml_primary"])
    ):
        raise ValueError("primary_model must match the selected ML skill")
    if type(proposal["folds"]) is not int or proposal["folds"] not in (0, 2, 3, 4, 5):
        raise ValueError("folds must be 0 or 2–5")
    if not isinstance(proposal["rationale"], str) or not 1 <= len(proposal["rationale"].strip()) <= 8000:
        raise ValueError("Provide a non-empty rationale (up to 8000 characters)")
    expected = {selected_model(snapshot)}
    if not isinstance(proposal["models"], dict) or set(proposal["models"]) != expected:
        raise ValueError("ml_plan must configure only the selected ML model")
    for name in expected:
        choice = proposal["models"][name]
        if not isinstance(choice, dict) or set(choice) != {"parameters", "scale_numeric", "threshold"}:
            raise ValueError("Each model requires parameters, scale_numeric and threshold")
        if type(choice["scale_numeric"]) is not bool:
            raise ValueError("scale_numeric must be boolean")
        from memstara.preprocessing_policy import analysis_ready

        if analysis_ready(snapshot) and choice["scale_numeric"]:
            raise ValueError("Automatic scaling is disabled; scale_numeric must be false")
        number(choice["threshold"], 0.05, 0.95, "threshold")
        parameters = choice["parameters"]
        defaults = spec["proposal_template"]["models"][name]["parameters"]
        if not isinstance(parameters, dict) or set(parameters) != set(defaults):
            raise ValueError("Supply the complete installed-library parameter dictionary from get_ml_configuration")
        for key, value in parameters.items():
            if key in RANGES[name]:
                number(value, *RANGES[name][key], key)
                if key in INTEGERS and type(value) is not int:
                    raise ValueError(f"{key} must be an integer")
            elif key in CHOICES[name]:
                if not any(type(value) is type(item) and value == item for item in CHOICES[name][key]):
                    raise ValueError(f"{key} is outside the supported choices")
            elif type(value) is not type(defaults[key]) or value != defaults[key]:
                raise ValueError(f"{name}.{key} is fixed by the server contract")
        if name == "logistic_regression" and parameters["penalty"] == "l1" and parameters["solver"] != "liblinear":
            raise ValueError("LR l1 requires liblinear")
    overrides = validate_overrides(snapshot.get("ml_overrides", {}))
    if overrides and apply_overrides(proposal, overrides) != proposal:
        raise ValueError("ML settings must preserve the fixed advanced user settings")
    return copy.deepcopy(proposal)


def number(value, low, high, name):
    if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and within [{low}, {high}]")


def identity(path: Path, snapshot, evaluation, proposal):
    handoff = path.with_suffix(".comparison.json")
    record = {
        "version": VERSION,
        "requested": proposal,
        "effective": proposal,
        "config_hash": snapshot["config_hash"],
        "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "handoff_sha256": hashlib.sha256(handoff.read_bytes()).hexdigest() if handoff.exists() else None,
        "evaluation": evaluation,
        "resource_limits": snapshot["ml_configuration_policy"],
    }
    overrides = snapshot.get("ml_overrides", {})
    record["proposal_resolution"] = copy.deepcopy(snapshot.get("_ml_plan_resolution"))
    record["setting_sources"] = {
        "primary_model": "selected_ml_skill",
        "folds": "user" if "folds" in overrides else "agent",
        "models": {},
    }
    for name, model in proposal["models"].items():
        fixed = overrides.get("models", {}).get(name, {})
        record["setting_sources"]["models"][name] = {
            "parameters": {
                key: "user"
                if key in fixed.get("parameters", {})
                else "agent"
                if key in RANGES[name] or key in CHOICES[name]
                else "server"
                for key in model["parameters"]
            },
            **{key: "user" if key in fixed else "agent" for key in ("scale_numeric", "threshold")},
        }
    if uses_default(snapshot):
        import sklearn

        record["sklearn_version"] = sklearn.__version__
        record["configuration_source"] = "sklearn_default"
        record["setting_sources"] = {
            "primary_model": "sklearn_default",
            "folds": "server_default",
            "models": {
                "logistic_regression": {
                    "parameters": {
                        key: "sklearn_default" for key in proposal["models"]["logistic_regression"]["parameters"]
                    },
                    "scale_numeric": "server_default",
                    "threshold": "server_default",
                }
            },
        }
    if overrides:
        record["user_overrides"] = copy.deepcopy(overrides)
    return record
