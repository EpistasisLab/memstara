import pytest

from memstara.pilot_execution import feature_input, validate_hypothesis, validate_data_plan, schedule


def test_random_sizes_are_bounded_distinct_reproducible_and_reach_both_endpoints():
    columns = [f'x{i}' for i in range(30)]
    contexts = [feature_input(columns, seed=seed, random_selection=True) for seed in range(200)]
    assert min(len(row['required_features']) for row in contexts) == 4
    assert max(len(row['required_features']) for row in contexts) == 20
    for row in contexts:
        assert len(row['required_features']) == len(set(row['required_features']))
        assert row == feature_input(columns, seed=row['seed'], random_selection=True)


def test_llm_cannot_replace_random_features_or_exceed_bounds():
    context = feature_input(list('abcdef'), seed=5, random_selection=True)
    value = {'question': 'Q', 'hypothesis': 'H', 'rationale': 'R', 'features': context['required_features']}
    assert validate_hypothesis(value, context) == value
    value['features'] = value['features'][::-1]
    with pytest.raises(ValueError, match='preserve'):
        validate_hypothesis(value, context)
    context = feature_input(list('abcdef'), seed=5, random_selection=False)
    value['features'] = list('abc')
    with pytest.raises(ValueError, match='4–20'):
        validate_hypothesis(value, context)


@pytest.mark.parametrize('skill,fraction', [('data_training_heavy', .2), ('data_balanced_stratified', .5)])
def test_data_skill_enforces_actual_partition_contract(skill, fraction):
    value = {'test_size': fraction, 'seed': 42, 'stratify': True}
    assert validate_data_plan(value, skill) == value
    value['stratify'] = False
    with pytest.raises(ValueError):
        validate_data_plan(value, skill)


def test_schedule_cannot_pad_sixteen_conditions_to_sixty_four():
    config = {'choices': {'hypothesis': ['guided', 'random'], 'data': ['heavy', 'balanced'],
                           'ml': ['paired'], 'interpreter': ['shap', 'lime'], 'report': ['hiv', 'addiction']},
              'repetitions': 1, 'expected_combinations': 64}
    with pytest.raises(ValueError, match='16 distinct'):
        schedule(config)
    config['choices']['hypothesis'] = ['a', 'b', 'c', 'random']
    config['choices']['ml'] = ['lr_focus', 'xgb_focus']
    rows = schedule(config)
    assert len(rows) == 64
    assert len({tuple(row.items()) for row in rows}) == 64
