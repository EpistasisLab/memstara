"""Opt-in frozen settings for a selected-model guided versus random comparison."""
import copy
import json


def validate(value):
    value = json.loads(value) if isinstance(value, str) else value
    if value == {}:
        return {}
    if not isinstance(value, dict) or set(value) != {'feature_count', 'ml_plan'}:
        raise ValueError('Controlled comparison requires feature_count and ml_plan')
    if type(value['feature_count']) is not int or not 4 <= value['feature_count'] <= 20:
        raise ValueError('Controlled comparison feature_count must be an integer from 4 to 20')
    if not isinstance(value['ml_plan'], dict):
        raise ValueError('Controlled comparison requires an explicit ML plan')
    return copy.deepcopy(value)


def freeze(value, snapshot):
    controls = validate(value)
    if not controls:
        return {}
    from memstara.ml_configuration import validate as validate_ml
    if not snapshot.get('combination_plan') or not snapshot.get('ml_configuration_policy'):
        raise ValueError('Controlled comparison requires a model-selected combination pipeline')
    controls['ml_plan'] = validate_ml(controls['ml_plan'], snapshot, snapshot['evaluation'])
    if len(controls['ml_plan']['models']) != 1:
        raise ValueError('Controlled comparisons must configure only the selected ML model')
    if controls['feature_count'] > len(snapshot['feature_context']['features']):
        raise ValueError('Insufficient eligible predictors for the fixed feature count')
    return controls
