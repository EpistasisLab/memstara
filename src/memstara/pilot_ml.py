"""Paired LR/XGBoost fitting and measured SHAP/LIME for the specialist pilot.

No frozen board evaluation settings are consulted. The supplied JSON is the ML
agent's decision. Both estimators use the Data agent's identical recorded split.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from memstara.pilot_handoffs import MODELS


def estimators():
    from sklearn.linear_model import LogisticRegression
    from xgboost import XGBClassifier

    return {"logistic_regression": LogisticRegression, "xgboost": XGBClassifier}


def parameter_context() -> dict:
    """Installed-library defaults are disclosed, rather than silently overriding the LLM."""
    return json.loads(
        json.dumps({name: cls().get_params() for name, cls in estimators().items()}), parse_constant=lambda _: None
    )


def validate_ml_plan(plan: dict) -> dict:
    if set(plan) != {"models", "scale_numeric", "threshold", "xai_rows", "lime_samples", "seed"}:
        raise ValueError("ML plan must contain models, scale_numeric, threshold, xai_rows, lime_samples and seed")
    if set(plan["models"]) != MODELS or type(plan["scale_numeric"]) is not bool:
        raise ValueError("Explicit LR and XGBoost parameters and a scaling decision are required")
    if type(plan["threshold"]) not in (int, float) or not 0 < plan["threshold"] < 1:
        raise ValueError("Choose an operating threshold strictly between 0 and 1 before evaluation")
    for key, low, high in (("xai_rows", 1, 50), ("lime_samples", 100, 10000), ("seed", 0, 2147483647)):
        if type(plan[key]) is not int or not low <= plan[key] <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")
    for name, cls in estimators().items():
        params = plan["models"][name]
        defaults = cls().get_params()
        if not isinstance(params, dict) or set(params) != set(defaults):
            raise ValueError(f"{name}: explicitly return every disclosed parameter, including unchanged defaults")
        if type(params.get("random_state")) is not int:
            raise ValueError(f"{name}: choose an integer random_state")
        if name == "xgboost":
            if params.get("objective") != "binary:logistic" or params.get("booster") not in (None, "gbtree"):
                raise ValueError("This binary paired study requires XGBoost binary:logistic with gbtree")
            if params.get("device") not in (None, "cpu") or params.get("n_jobs") != 1:
                raise ValueError("The local pilot requires CPU execution and n_jobs=1")
            if params.get("callbacks") or params.get("early_stopping_rounds"):
                raise ValueError("Hold-out driven early stopping and executable callbacks are not supported")
        cls(**params)  # Constructor validation without fitting or consulting labels.
    return plan


def classification_metrics(y, probability, threshold):
    from sklearn.metrics import (
        roc_auc_score,
        average_precision_score,
        brier_score_loss,
        confusion_matrix,
        precision_recall_curve,
        auc,
        log_loss,
        matthews_corrcoef,
        cohen_kappa_score,
    )

    predicted = probability >= threshold
    tn, fp, fn, tp = (int(v) for v in confusion_matrix(y, predicted, labels=[0, 1]).ravel())

    def divide(a, b):
        return a / b if b else None

    sensitivity, specificity = divide(tp, tp + fn), divide(tn, tn + fp)
    precision, npv = divide(tp, tp + fp), divide(tn, tn + fn)
    pr_precision, recall, _ = precision_recall_curve(y, probability)
    return {
        "auroc": float(roc_auc_score(y, probability)),
        "average_precision": float(average_precision_score(y, probability)),
        "pr_auc_trapezoidal": float(auc(recall, pr_precision)),
        "brier": float(brier_score_loss(y, probability)),
        "log_loss": float(log_loss(y, probability)),
        "threshold": threshold,
        "n_test": tn + fp + fn + tp,
        "confusion_matrix": {
            "labels": [0, 1],
            "rows": "actual",
            "columns": "predicted",
            "values": [[tn, fp], [fn, tp]],
        },
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "tp": tp,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "precision": precision,
        "npv": npv,
        "f1": divide(2 * tp, 2 * tp + fp + fn),
        "accuracy": divide(tp + tn, tn + fp + fn + tp),
        "balanced_accuracy": (sensitivity + specificity) / 2,
        "false_positive_rate": divide(fp, fp + tn),
        "false_negative_rate": divide(fn, fn + tp),
        "false_discovery_rate": divide(fp, fp + tp),
        "false_omission_rate": divide(fn, fn + tn),
        "positive_likelihood_ratio": divide(sensitivity, 1 - specificity),
        "negative_likelihood_ratio": divide(1 - sensitivity, specificity),
        "diagnostic_odds_ratio": divide(tp * tn, fp * fn),
        "prevalence": divide(tp + fn, tn + fp + fn + tp),
        "predicted_positive_rate": divide(tp + fp, tn + fp + fn + tp),
        "youden_j": sensitivity + specificity - 1,
        "markedness": precision + npv - 1 if precision is not None and npv is not None else None,
        "mcc": float(matthews_corrcoef(y, predicted)),
        "cohen_kappa": float(cohen_kappa_score(y, predicted)),
        "undefined_values": "null means a zero denominator, not zero performance",
        "scope": "held-out evaluation; no training rows; not external validation",
    }


def attributions(model, train, held_out, names, family, plan):
    """Both methods explain the same preselected held-out cases for each estimator."""
    import numpy as np
    import shap
    from lime.lime_tabular import LimeTabularExplainer

    rng = np.random.default_rng(plan["seed"])
    background = train[rng.choice(len(train), min(100, len(train)), replace=False)]
    positions = np.sort(rng.choice(len(held_out), min(plan["xai_rows"], len(held_out)), replace=False))
    samples = held_out[positions]
    if family == "logistic_regression":
        explainer = shap.LinearExplainer(model, background)
        shap_values = np.asarray(explainer.shap_values(samples), dtype=float)
        expected_value = np.asarray(explainer.expected_value).tolist()
        shap_method = "LinearSHAP with independent training-background features"
    else:
        from xgboost import DMatrix

        contributions = model.get_booster().predict(DMatrix(samples), pred_contribs=True)
        shap_values = np.asarray(contributions[:, :-1], dtype=float)
        expected_value = contributions[:, -1].tolist()
        shap_method = "Native XGBoost TreeSHAP; tree-path-dependent training cover"
    if shap_values.shape != samples.shape or not np.isfinite(shap_values).all():
        raise ValueError("SHAP did not produce a finite contribution for every feature and explained row")
    lime = LimeTabularExplainer(
        train,
        feature_names=names,
        class_names=["0", "1"],
        mode="classification",
        discretize_continuous=False,
        random_state=plan["seed"],
    )
    local = []
    for position, row in zip(positions, samples, strict=True):
        result = lime.explain_instance(
            row, model.predict_proba, labels=(1,), num_features=len(names), num_samples=plan["lime_samples"]
        )
        local.append(
            {
                "held_out_position": int(position),
                "weights": {names[i]: float(weight) for i, weight in result.local_exp[1]},
                "surrogate_r2": float(result.score),
                "intercept": float(result.intercept[1]),
                "local_prediction": float(result.local_pred[0]),
                "model_probability": float(model.predict_proba(row.reshape(1, -1))[0, 1]),
            }
        )
    return {
        "shap": {
            "status": "completed",
            "units": "log-odds",
            "features": names,
            "held_out_positions": positions.tolist(),
            "values": shap_values.tolist(),
            "expected_value": expected_value,
            "method": shap_method,
            "mean_absolute": dict(zip(names, np.abs(shap_values).mean(axis=0).tolist(), strict=True)),
            "background_rows": len(background) if family == "logistic_regression" else None,
            "background_source": "training only",
        },
        "lime": {
            "status": "completed",
            "units": "local probability surrogate coefficients",
            "rows": local,
            "training_rows": len(train),
            "num_samples": plan["lime_samples"],
            "limitation": "Independent perturbations of encoded features may be off-manifold; "
            "local coefficients are not causal or directly comparable to SHAP log-odds.",
        },
    }


def fit_pair(
    dataset: Path,
    target: str,
    features: list[str],
    data_plan: dict,
    ml_plan: dict,
    scope: dict,
    output: Path,
    *,
    explain=attributions,
) -> list[dict]:
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from memstara.evaluation import validate_clean_dataset
    from memstara.pilot_final import _save

    validate_ml_plan(ml_plan)
    if target in features or not 4 <= len(features) <= 20 or len(set(features)) != len(features):
        raise ValueError("The pilot requires 4–20 distinct non-target predictors")
    source = dataset.read_bytes()
    frame = validate_clean_dataset(dataset, target, allow_missing=True)
    if not set(features) <= set(frame.columns):
        raise ValueError("Selected predictors are absent from the dataset")
    X, y = frame[features], frame[target]
    if X.isna().any().any():
        raise ValueError("Paired LR/XGBoost input contains missing predictors; no rows or values were changed")
    train, test = train_test_split(
        np.arange(len(frame)), test_size=data_plan["test_size"], stratify=y, random_state=data_plan["seed"]
    )
    if min(y.iloc[train].nunique(), y.iloc[test].nunique()) != 2:
        raise ValueError("Both classes must occur in the training and held-out partitions")
    output.mkdir(parents=True, exist_ok=False)
    split_id = hashlib.sha256(source + train.tobytes() + test.tobytes()).hexdigest()
    _save(
        output / "split.json",
        {
            "split_id": split_id,
            "train_rows": train.tolist(),
            "test_rows": test.tolist(),
            "data_plan": data_plan,
            "dataset_sha256": hashlib.sha256(source).hexdigest(),
        },
    )
    X.to_csv(output / "predictors.csv", index=False)
    numeric = X.select_dtypes(include="number").columns.tolist()
    categorical = [name for name in features if name not in numeric]
    encoder = ColumnTransformer(
        [
            ("numeric", StandardScaler() if ml_plan["scale_numeric"] else "passthrough", numeric),
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),
        ],
        verbose_feature_names_out=False,
    )
    transformed_train = np.asarray(encoder.fit_transform(X.iloc[train]), dtype=float)
    transformed_test = np.asarray(encoder.transform(X.iloc[test]), dtype=float)
    names = encoder.get_feature_names_out().tolist()
    joblib.dump(encoder, output / "encoder.joblib")
    rows = []
    for family, cls in estimators().items():
        parameters = dict(ml_plan["models"][family])
        if family == "xgboost" and parameters.get("missing") is None:
            parameters["missing"] = np.nan
        model = cls(**parameters)
        model.fit(transformed_train, y.iloc[train])
        probability = model.predict_proba(transformed_test)[:, 1]
        measured_xai = explain(model, transformed_train, transformed_test, names, family, ml_plan)
        if any(measured_xai.get(method, {}).get("status") != "completed" for method in ("shap", "lime")):
            raise ValueError("Both SHAP and LIME must be computed before interpretation")
        result = {
            "scope": scope,
            "status": "completed",
            "model": family,
            "result_id": f"{scope['run_id']}:{scope['combination_id']}:{family}",
            "split_id": split_id,
            "target": target,
            "features": features,
            "metrics": classification_metrics(y.iloc[test], probability, ml_plan["threshold"]),
            "settings": {
                "parameters": json.loads(json.dumps(model.get_params()), parse_constant=lambda _: None),
                "data": data_plan,
                "scale_numeric": ml_plan["scale_numeric"],
                "xai_seed": ml_plan["seed"],
            },
            "attributions": measured_xai,
        }
        if family == "logistic_regression":
            result["native_importance"] = {
                "kind": "signed coefficients in encoded/scaled feature space",
                "values": dict(zip(names, model.coef_[0].tolist(), strict=True)),
                "intercept": model.intercept_.tolist(),
                "iterations": model.n_iter_.tolist(),
            }
        else:
            result["native_importance"] = {
                "kind": "XGBoost feature_importances_",
                "values": dict(zip(names, model.feature_importances_.tolist(), strict=True)),
            }
            _save(output / "xgboost.effective-config.json", json.loads(model.get_booster().save_config()))
        _save(output / f"{family}.json", result)
        joblib.dump(model, output / f"{family}.joblib")
        pd.DataFrame(
            {
                "row_position": test,
                "actual": y.iloc[test].to_numpy(),
                "probability": probability,
                "predicted": probability >= ml_plan["threshold"],
            }
        ).to_csv(output / f"{family}.predictions.csv", index=False)
        rows.append(result)
    if dataset.read_bytes() != source:
        raise ValueError("Dataset changed during evaluation")
    _save(output / "paired-results.json", {"scope": scope, "results": rows})
    return rows
