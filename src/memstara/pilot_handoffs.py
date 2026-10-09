"""Validated paired-model payloads for the experimental final-stage adapter.

These functions assemble inputs only. They never fetch unscoped board history,
connect to knowledge stores, calculate XAI or claim that an agent has executed.
"""
from copy import deepcopy

MODELS = {'logistic_regression', 'xgboost'}
METHODS = {'shap', 'lime'}
EXPERTS = {'addiction', 'hiv'}


def interpretation_input(scope: dict, results: list[dict], method: str) -> dict:
    """Both methods receive both estimators from exactly the same experiment."""
    if method not in METHODS:
        raise ValueError('Interpretation must select shap or lime')
    if set(scope) != {'run_id', 'combination_id', 'question_id'} or any(v is None for v in scope.values()):
        raise ValueError('A complete run/combination/question scope is required')
    if len(results) != 2 or {r.get('model') for r in results} != MODELS:
        raise ValueError('Exactly one LR and one XGBoost result are required')
    for row in results:
        if row.get('scope') != scope or row.get('status') != 'completed':
            raise ValueError('Only completed results from the selected experiment may be paired')
        if not row.get('result_id'):
            raise ValueError('Each model result requires its recorded identity')
    if len({r['result_id'] for r in results}) != 2:
        raise ValueError('Model result identities must be distinct')
    for key in ('split_id', 'target', 'features'):
        if not results[0].get(key) or results[0][key] != results[1].get(key):
            raise ValueError(f'Paired models must share recorded {key}')
    models = {}
    for row in results:
        # Allowlisted aggregate artifacts, not a raw task/dataset dump.
        models[row['model']] = {key: deepcopy(row.get(key)) for key in (
            'result_id', 'split_id', 'target', 'features', 'metrics', 'settings', 'native_importance')}
        xai = row.get('attributions', {}).get(method)
        available = bool(xai) and (not isinstance(xai, dict) or
                                  xai.get('status') not in ('not_available', 'failed'))
        models[row['model']]['attribution'] = {
            'method': method, 'status': 'available' if available else 'not_available', 'data': deepcopy(xai)}
    return {'scope': deepcopy(scope), 'method': method, 'models': models}


def explanation_input(scope: dict, interpretations: list[dict], expert: str,
                      knowledge_bindings: dict) -> dict:
    """Require explicit expert-specific knowledge binding and completed interpretations."""
    if expert not in EXPERTS:
        raise ValueError('Explanation must select addiction or hiv')
    binding = knowledge_bindings.get(expert)
    if not isinstance(binding, dict) or not binding.get('database_id'):
        raise ValueError(f'Explicit knowledge database binding is missing for {expert}')
    if not interpretations:
        raise ValueError('Explanation requires an interpretation output')
    seen = set()
    for report in interpretations:
        if report.get('scope') != scope or report.get('status') != 'completed':
            raise ValueError('Interpretation output belongs to another experiment or is incomplete')
        if report.get('method') not in METHODS or report['method'] in seen:
            raise ValueError('Interpretation methods must be valid and distinct')
        seen.add(report['method'])
        if not report.get('output') or not report.get('invocation_id'):
            raise ValueError('Recorded interpretation text and invocation identity are required')
        if set(report.get('model_result_ids', {})) != MODELS:
            raise ValueError('Interpretation must identify both model results')
    if any(r['model_result_ids'] != interpretations[0]['model_result_ids'] for r in interpretations):
        raise ValueError('Interpretations must refer to the same paired model results')
    return {'scope': deepcopy(scope), 'expert': expert,
            'knowledge_binding': {'database_id': binding['database_id']},
            'interpretations': [{key: deepcopy(row[key]) for key in (
                'method', 'invocation_id', 'model_result_ids', 'output')} for row in interpretations]}
