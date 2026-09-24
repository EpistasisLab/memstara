import asyncio
import json
import pytest
from memstara.pipeline.critic import assess, review, VERSION


def plan():
    return {'run_tag':'test','config_hash':'frozen','y_column':'Y',
        'feature_context':{'features':[{'column':'baseline'},{'column':'novel'}]},
        'comparison_policy':{'baseline_columns':['baseline']},'critic_policy':{'version':VERSION}}


@pytest.mark.parametrize('columns,reason',[([], 'no_predictors'),(['novel','novel'],'duplicate_predictors'),
    (['missing'],'unknown_predictors'),(['baseline'],'no_incremental_predictors_beyond_fixed_baseline'),
    (['Y'],'target_as_predictor')])
def test_invalid_candidate_is_rejected(columns,reason):
    assert reason in assess(columns,plan())['reason_codes']


def test_rejection_occurs_before_database_or_training(tmp_path,monkeypatch):
    from memstara import evaluation
    from memstara.mcp_servers import blackboard
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG',str(tmp_path/'config.json'))
    monkeypatch.setattr(evaluation,'active_plan',plan)
    async def forbidden(*a,**kw):raise AssertionError('No DB work should be reached')
    monkeypatch.setattr(blackboard.asyncpg,'connect',forbidden)
    answer=json.loads(asyncio.run(blackboard.create_task('test',0,'question','hypothesis',['baseline'],'Y')))
    assert answer['critic']['verdict']=='rejected'
    event=json.loads((tmp_path/'critic_decisions.jsonl').read_text())
    assert event['question_id']==0 and event['trial']==0
    assert 'columns' not in event


def test_no_critic_activation_for_historical_run(tmp_path,monkeypatch):
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG',raising=False)
    assert review([],{},1,0) is None
    assert assess(['baseline','novel'],plan())['verdict']=='accepted'
