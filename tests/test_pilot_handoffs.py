from copy import deepcopy
import pytest
from memstara.pilot_handoffs import explanation_input, interpretation_input

SCOPE = {'run_id': 'fixture', 'combination_id': 1, 'question_id': 1}


def results():
    return [{'scope': SCOPE, 'status': 'completed', 'result_id': name, 'model': name,
             'split_id': 'same-split', 'target': 'outcome', 'features': ['a', 'b', 'c', 'd'],
             'metrics': {'auc': .6}, 'patient_rows': 'MUST_NOT_PASS',
             'attributions': {'shap': {'summary': name}, 'lime': {'summary': name}}}
            for name in ('logistic_regression', 'xgboost')]


@pytest.mark.parametrize('method', ['shap', 'lime'])
def test_each_method_receives_both_models_and_only_requested_xai(method):
    payload = interpretation_input(SCOPE, results(), method)
    assert len(payload['models']) == 2
    for model, row in payload['models'].items():
        assert row['attribution']['method'] == method
        assert row['attribution']['data']['summary'] == model
        assert 'patient_rows' not in row


@pytest.mark.parametrize('key,value', [('scope', {}), ('split_id', 'other'), ('features', ['z']),
                                      ('target', 'other'), ('status', 'failed')])
def test_mixed_or_incomplete_results_are_rejected(key, value):
    rows = deepcopy(results())
    rows[1][key] = value
    with pytest.raises(ValueError):
        interpretation_input(SCOPE, rows, 'shap')


def test_missing_xai_is_not_fabricated():
    rows = results()
    rows[0]['attributions'] = {}
    payload = interpretation_input(SCOPE, rows, 'lime')
    assert payload['models']['logistic_regression']['attribution']['status'] == 'not_available'


def test_explicit_unavailable_xai_is_not_mislabelled_as_available():
    rows = results()
    rows[0]['attributions']['shap'] = {'status': 'not_available', 'reason': 'No calculation'}
    payload = interpretation_input(SCOPE, rows, 'shap')
    assert payload['models']['logistic_regression']['attribution']['status'] == 'not_available'


def reports():
    return [{'scope': SCOPE, 'status': 'completed', 'method': method, 'output': 'Recorded interpretation',
             'invocation_id': method, 'model_result_ids': {'logistic_regression': 'lr', 'xgboost': 'xgb'}}
            for method in ('shap', 'lime')]


@pytest.mark.parametrize('expert', ['addiction', 'hiv'])
def test_expert_gets_its_binding_and_interpretations(expert):
    bindings = {name: {'database_id': name, 'password': 'MUST_NOT_PASS'} for name in ('addiction', 'hiv')}
    payload = explanation_input(SCOPE, reports(), expert, bindings)
    assert payload['knowledge_binding'] == {'database_id': expert}
    assert len(payload['interpretations']) == 2


def test_no_database_fallback_or_cross_run_reports():
    with pytest.raises(ValueError):
        explanation_input(SCOPE, reports(), 'hiv', {'addiction': {'database_id': 'other'}})
    rows = reports()
    rows[0]['scope'] = {}
    with pytest.raises(ValueError):
        explanation_input(SCOPE, rows, 'hiv', {'hiv': {'database_id': 'hiv'}})
