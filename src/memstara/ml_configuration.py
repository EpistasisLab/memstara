"""Agent-proposed paired models with explicit, server-owned safety constraints."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

VERSION = 'agent_paired_ml_v1'
MODELS = ('logistic_regression', 'xgboost')
MODEL_SKILLS = {'ml_logistic_regression': 'logistic_regression', 'ml_xgboost': 'xgboost'}


def for_dataset(snapshot, path):
    """Resolve the selected model from this task's saved combination, not another loop."""
    if not snapshot:
        return snapshot
    from memstara.combinations import task_books
    handoff = path.with_suffix('.comparison.json')
    record = json.loads(handoff.read_text()) if handoff.exists() else {}
    names = task_books(snapshot, record.get('trial', 0)).get('ml', [])
    primary = next((MODEL_SKILLS[name] for name in names if name in MODEL_SKILLS), None)
    if primary and snapshot.get('combination_plan') and 'trial' not in record:
        raise ValueError('Selected ML skill requires the saved task trial identity')
    return {**snapshot, '_selected_ml_primary': primary}
# All other installed-library parameters are explicitly returned as fixed defaults.
# Arbitrary callbacks, GPU execution and unconstrained parallelism are never accepted.
RANGES = {
    'logistic_regression': {'C': (1e-5, 1e4), 'max_iter': (50, 2000), 'tol': (1e-6, .01)},
    'xgboost': {'n_estimators': (10, 400), 'max_depth': (1, 8), 'learning_rate': (.005, .5),
                'min_child_weight': (0, 100), 'subsample': (.5, 1), 'colsample_bytree': (.5, 1),
                'reg_alpha': (0, 100), 'reg_lambda': (0, 100), 'gamma': (0, 100),
                'scale_pos_weight': (.01, 100), 'max_bin': (32, 256)},
}
CHOICES: dict[str, dict[str, list[str | bool | None]]] = {
    'logistic_regression': {
        'solver': ['lbfgs', 'liblinear'], 'penalty': ['l2', 'l1'],
        'class_weight': [None, 'balanced'], 'fit_intercept': [True, False],
    },
    'xgboost': {},
}
INTEGERS = {'max_iter', 'n_estimators', 'max_depth', 'max_bin'}


def override_schema():
    """The UI consumes the same bounded parameter contract as execution."""
    return {'version': 1, 'models': {
        name: {'parameters': {
            **{key: {'type': 'integer' if key in INTEGERS else 'number', 'min': low, 'max': high}
               for key, (low, high) in RANGES[name].items()},
            **{key: {'type': 'choice', 'choices': values} for key, values in CHOICES[name].items()},
        }} for name in MODELS},
        'folds': [0, 2, 3, 4, 5], 'threshold': {'min': .05, 'max': .95},
        'resource_limits': policy()}


def validate_overrides(value, skills=None, *, replicates=None):
    if value == {}:
        return {}
    if not isinstance(value, dict) or set(value) - {'version', 'models', 'folds'}:
        raise ValueError('ML advanced settings accept only version, models and folds')
    if type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('ML advanced settings require version=1')
    models = value.get('models', {})
    if not isinstance(models, dict) or set(models) - set(MODELS):
        raise ValueError('ML advanced settings support only LR and XGBoost')
    selected = {MODEL_SKILLS[s] for s in skills if s in MODEL_SKILLS} if skills is not None else set(MODELS)
    if set(models) - selected or ('folds' in value and not selected):
        raise ValueError('Advanced model settings must match the selected ML skills')
    for name, settings in models.items():
        if not isinstance(settings, dict) or set(settings) - {'parameters', 'scale_numeric', 'threshold'}:
            raise ValueError('Each advanced model accepts parameters, scale_numeric and threshold')
        parameters = settings.get('parameters', {})
        if not isinstance(parameters, dict) or set(parameters) - (set(RANGES[name]) | set(CHOICES[name])):
            raise ValueError(f'{name}: unsupported or server-owned model parameter')
        for key, item in parameters.items():
            if key in RANGES[name]:
                number(item, *RANGES[name][key], key)
                if key in INTEGERS and type(item) is not int:
                    raise ValueError(f'{key} must be an integer')
            elif not any(type(item) is type(option) and item == option for option in CHOICES[name][key]):
                raise ValueError(f'{name}.{key} is outside the supported choices')
        if 'scale_numeric' in settings and type(settings['scale_numeric']) is not bool:
            raise ValueError('scale_numeric must be boolean')
        if 'threshold' in settings:
            number(settings['threshold'], .05, .95, 'threshold')
        if parameters.get('penalty') == 'l1' and parameters.get('solver') == 'lbfgs':
            raise ValueError('LR l1 requires liblinear')
    if 'folds' in value and (type(value['folds']) is not int or value['folds'] not in (0, 2, 3, 4, 5)):
        raise ValueError('Training CV folds must be 0 or 2–5')
    if 'folds' in value and replicates is not None and 2 * replicates * (value['folds'] + 2) > 120:
        raise ValueError('Reduce split evaluations or training CV folds to remain within the ML fit budget')
    return copy.deepcopy(value)


def apply_overrides(proposal, overrides):
    chosen = copy.deepcopy(proposal)
    if not isinstance(chosen, dict) or not isinstance(chosen.get('models'), dict):
        return chosen  # Complete-plan validation supplies the actionable error.
    if 'folds' in overrides:
        chosen['folds'] = overrides['folds']
    for name, settings in overrides.get('models', {}).items():
        model = chosen['models'].get(name)
        if not isinstance(model, dict) or not isinstance(model.get('parameters'), dict):
            continue
        model['parameters'].update(settings.get('parameters', {}))
        for key in ('scale_numeric', 'threshold'):
            if key in settings:
                model[key] = settings[key]
    return chosen


def policy():
    import psutil
    memory = psutil.virtual_memory()
    # Leave most RAM for the app/OS; the execution-time guard further reduces this.
    return {'version': VERSION, 'threads': 1, 'concurrent_jobs': 1,
            'memory_bytes': min(2 * 1024**3, int(memory.total * .15)),
            'wall_seconds': 600, 'max_fits': 120, 'max_csv_bytes': 64 * 1024**2,
            'max_dense_cells': 4_000_000, 'max_encoded_columns': 4096}


def enabled(snapshot):
    return (snapshot or {}).get('ml_configuration_policy', {}).get('version') == VERSION


def context(snapshot, evaluation):
    controls = (snapshot or {}).get('controlled_comparison')
    if controls:
        base = context({k: v for k, v in snapshot.items() if k != 'controlled_comparison'}, evaluation)
        base.update(proposal_template=copy.deepcopy(controls['ml_plan']),
                    editable_parameter_ranges={}, editable_parameter_choices={}, editable_common_settings={},
                    plan_source='server_frozen',
                    instructions='Matched comparison: the server applies proposal_template directly. '
                                 'Call train_and_score with path and y_column; omit ml_plan. '
                                 'Any supplied ml_plan is recorded but cannot override the frozen plan.')
        base['fixed']['controlled_comparison'] = True
        base['fixed']['primary_model'] = controls['ml_plan']['primary_model']
        return base
    from memstara.evaluation import model_for
    models = {}
    for name in MODELS:
        model = model_for(name, evaluation['seed'])
        if name == 'logistic_regression':
            model.set_params(penalty='l2')
        if name == 'xgboost':
            model.set_params(tree_method='hist', device='cpu', learning_rate=.1, min_child_weight=1,
                             subsample=1., colsample_bytree=1., reg_alpha=0., reg_lambda=1.,
                             gamma=0., scale_pos_weight=1., max_bin=256)
        params = json.loads(json.dumps(model.get_params(), default=str), parse_constant=str)
        models[name] = {'parameters': params, 'scale_numeric': name == 'logistic_regression',
                        'threshold': .5}
    specification = {'version': VERSION, 'required': enabled(snapshot),
            'proposal_template': {'primary_model': snapshot.get('_selected_ml_primary') or 'logistic_regression',
                                  'folds': 0,
                                  'models': models, 'rationale': ''},
            'editable_parameter_ranges': RANGES, 'editable_parameter_choices': CHOICES,
            'editable_common_settings': {'scale_numeric': [True, False], 'threshold': [.05, .95],
                                         'folds': [0, 2, 3, 4, 5]},
            'fixed': {'primary_model': snapshot.get('_selected_ml_primary'),
                      'data_seed': evaluation['seed'], 'test_size': evaluation['test_size'],
                      'replicates': evaluation['replicates'], 'search_trials': 1,
                      'resource_limits': (snapshot or {}).get('ml_configuration_policy'),
                      'other_parameters': 'Keep all parameters outside the editable lists exactly as returned.'},
            'preprocessing_contract': 'No row cleaning or imputation. LR requires complete predictors. '
                                      'Categoricals use training-fold one-hot encoding. '
                                      'Numeric scaling is agent-selected.',
            'instructions': 'Return the complete proposal_template with your choices and rationale. '
                            'Choose both models before seeing results. Preserve upstream features/splits. '
                            'LR l1 requires liblinear. No hold-out tuning; accepted proposals are immutable.'}
    overrides = validate_overrides(snapshot.get('ml_overrides', {}))
    if overrides:
        specification['proposal_template'] = apply_overrides(specification['proposal_template'], overrides)
        params = specification['proposal_template']['models']['logistic_regression']['parameters']
        if params['penalty'] == 'l1' and params['solver'] == 'lbfgs':
            params['solver'] = 'liblinear'  # Compatible automatic solver suggestion.
        specification['user_overrides'] = overrides
        specification['editable_parameter_ranges'] = copy.deepcopy(RANGES)
        specification['editable_parameter_choices'] = copy.deepcopy(CHOICES)
        for name, settings in overrides.get('models', {}).items():
            for key in settings.get('parameters', {}):
                specification['editable_parameter_ranges'][name].pop(key, None)
                specification['editable_parameter_choices'][name].pop(key, None)
        specification['fixed']['user_overrides'] = overrides
        specification['instructions'] += (' User overrides are fixed and take precedence. '
            'Choose only remaining automatic settings; do not replace fixed user values.')
    return specification


def resolve(proposal, snapshot, evaluation):
    """Fixed experiments execute a server-owned plan, never an LLM transcription."""
    controls = (snapshot or {}).get('controlled_comparison')
    overrides = validate_overrides((snapshot or {}).get('ml_overrides', {}))
    if controls and overrides:
        raise ValueError('Controlled comparisons cannot also use advanced ML overrides')
    chosen = controls['ml_plan'] if controls else proposal
    if overrides:
        chosen = apply_overrides(chosen, overrides)
    effective = validate(chosen, snapshot, evaluation)
    return effective, {
        'source': ('server_frozen' if controls else
                   'user_overrides_and_agent_proposal' if overrides else 'agent_proposal'),
        'agent_proposal_supplied': proposal is not None,
        'agent_proposal': copy.deepcopy(proposal),
        'agent_proposal_ignored': bool(controls) and proposal is not None,
        'effective_plan': copy.deepcopy(effective),
        **({'user_overrides': overrides} if overrides else {}),
    }


def validate(proposal, snapshot, evaluation):
    controls = (snapshot or {}).get('controlled_comparison')
    if controls:
        if proposal != controls['ml_plan']:
            raise ValueError('ML settings must equal the frozen controlled-comparison plan; no tuning is permitted')
        snapshot = {k: v for k, v in snapshot.items() if k != 'controlled_comparison'}
    spec = context(snapshot, evaluation)
    if not isinstance(proposal, dict) or set(proposal) != {'primary_model', 'folds', 'models', 'rationale'}:
        raise ValueError('ml_plan requires primary_model, folds, models and rationale')
    if proposal['primary_model'] not in MODELS:
        raise ValueError('primary_model must be logistic_regression or xgboost')
    if not controls and snapshot.get('_selected_ml_primary') and (
            proposal['primary_model'] != snapshot['_selected_ml_primary']):
        raise ValueError('primary_model must match the selected ML skill')
    if type(proposal['folds']) is not int or proposal['folds'] not in (0, 2, 3, 4, 5):
        raise ValueError('folds must be 0 or 2–5')
    if not isinstance(proposal['rationale'], str) or not 1 <= len(proposal['rationale'].strip()) <= 8000:
        raise ValueError('Provide a non-empty rationale (up to 8000 characters)')
    if not isinstance(proposal['models'], dict) or set(proposal['models']) != set(MODELS):
        raise ValueError('Both LR and XGBoost configurations are required')
    for name in MODELS:
        choice = proposal['models'][name]
        if not isinstance(choice, dict) or set(choice) != {'parameters', 'scale_numeric', 'threshold'}:
            raise ValueError('Each model requires parameters, scale_numeric and threshold')
        if type(choice['scale_numeric']) is not bool:
            raise ValueError('scale_numeric must be boolean')
        number(choice['threshold'], .05, .95, 'threshold')
        parameters = choice['parameters']
        defaults = spec['proposal_template']['models'][name]['parameters']
        if not isinstance(parameters, dict) or set(parameters) != set(defaults):
            raise ValueError('Supply the complete installed-library parameter dictionary from get_ml_configuration')
        for key, value in parameters.items():
            if key in RANGES[name]:
                number(value, *RANGES[name][key], key)
                if key in INTEGERS and type(value) is not int:
                    raise ValueError(f'{key} must be an integer')
            elif key in CHOICES[name]:
                if not any(type(value) is type(item) and value == item for item in CHOICES[name][key]):
                    raise ValueError(f'{key} is outside the supported choices')
            elif type(value) is not type(defaults[key]) or value != defaults[key]:
                raise ValueError(f'{name}.{key} is fixed by the server contract')
        if name == 'logistic_regression' and parameters['penalty'] == 'l1' and parameters['solver'] != 'liblinear':
            raise ValueError('LR l1 requires liblinear')
    overrides = validate_overrides(snapshot.get('ml_overrides', {}))
    if overrides and apply_overrides(proposal, overrides) != proposal:
        raise ValueError('ML settings must preserve the fixed advanced user settings')
    return copy.deepcopy(proposal)


def number(value, low, high, name):
    if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be finite and within [{low}, {high}]')


def identity(path: Path, snapshot, evaluation, proposal):
    handoff = path.with_suffix('.comparison.json')
    record = {'version': VERSION, 'requested': proposal, 'effective': proposal,
            'config_hash': snapshot['config_hash'], 'dataset_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'handoff_sha256': hashlib.sha256(handoff.read_bytes()).hexdigest() if handoff.exists() else None,
            'evaluation': evaluation, 'resource_limits': snapshot['ml_configuration_policy']}
    overrides = snapshot.get('ml_overrides', {})
    if overrides:
        record['user_overrides'] = copy.deepcopy(overrides)
        record['proposal_resolution'] = copy.deepcopy(snapshot.get('_ml_plan_resolution'))
        record['setting_sources'] = {'primary_model': 'selected_ml_skill',
            'folds': 'user' if 'folds' in overrides else 'agent', 'models': {}}
        for name, model in proposal['models'].items():
            fixed = overrides.get('models', {}).get(name, {})
            record['setting_sources']['models'][name] = {
                'parameters': {key: 'user' if key in fixed.get('parameters', {}) else
                    'agent' if key in RANGES[name] or key in CHOICES[name] else 'server'
                    for key in model['parameters']},
                **{key: 'user' if key in fixed else 'agent' for key in ('scale_numeric', 'threshold')}}
    return record
