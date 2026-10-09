"""The temporary pilot must not silently claim 64 executable combinations."""
import pytest
from memstara.pilot_design import draft, preview


def test_unresolved_design_has_no_schedule():
    result = preview(draft())
    assert result['actual_combinations'] is None
    assert not result['execution_ready']
    assert 'model_deployments.explanation_agent' in result['blockers']
    assert 'feature_policy' in result['blockers']


@pytest.mark.parametrize('feature,data_count,layout,count', [
    ('range', 2, 'paired', 16), ('range', 3, 'paired', 24),
    ('range', 2, 'separate', 32), ('endpoints', 2, 'paired', 32),
    ('endpoints', 2, 'separate', 64), ('endpoints', 3, 'separate', 96),
])
def test_counts_come_from_factors(feature, data_count, layout, count):
    plan = draft()
    plan.update(feature_policy=feature, ml_layout=layout,
                data_variants=['training_heavy', 'balanced_stratified'] if data_count == 2
                else ['training_heavy', 'balanced', 'stratified'])
    result = preview(plan)
    assert result['actual_combinations'] == count
    assert not result['execution_ready']
    assert ('requested_combination_count_mismatch' in result['blockers']) == (count != 64)
    if layout == 'paired':
        assert all(len(row['estimators']) == 2 for row in result['candidate_schedule'])
    else:
        assert 'cross_model_interpretation_join_not_defined' in result['blockers']


def test_feature_bounds_cannot_silently_change():
    plan = draft()
    plan['feature_bounds'] = [1, 30]
    with pytest.raises(ValueError):
        preview(plan)
