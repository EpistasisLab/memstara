from memstara.combinations import STAGES, build_plan, validate_plan, execution_label
from memstara.control.workspace import PipelineWorkspace


def test_all_unselected_stages_are_executable_and_frozen():
    choices = {stage: [] for stage in STAGES}
    config = PipelineWorkspace.configuration({'combination_skills': choices,
        'combination_repetitions': 2})
    plan = build_plan(choices, 2, execution_order='all_pipelines_first')
    assert config['waves'] == plan['total_loops'] == 2
    assert plan['combinations'] == 1
    assert validate_plan(plan) == plan
    assert plan['skills']['interpreter'][0]['id'] == 'shared-shap'
    assert plan['skills']['report'][0]['id'] == 'shared-heart-failure-cardiovascular'


def test_console_identity_follows_both_execution_orders():
    choices = {stage: [] for stage in STAGES}
    choices['ml'] = ['ml_logistic_regression', 'ml_xgboost']
    for order, expected in [
        ('all_pipelines_first', ['Pipeline 1 · Replicate 1', 'Pipeline 2 · Replicate 1',
                                'Pipeline 1 · Replicate 2', 'Pipeline 2 · Replicate 2']),
        ('pipeline_replicates_first', ['Pipeline 1 · Replicate 1', 'Pipeline 1 · Replicate 2',
                                      'Pipeline 2 · Replicate 1', 'Pipeline 2 · Replicate 2']),
    ]:
        plan = build_plan(choices, 2, execution_order=order)
        assert [execution_label(i, plan) for i in range(1, 5)] == expected
