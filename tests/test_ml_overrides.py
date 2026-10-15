"""Bounded user settings through persistence, launch and model-plan resolution."""
import copy
import json

import pytest

from memstara import ml_configuration as ml
from memstara.evaluation import validate as evaluation_plan
from memstara.control.request import build_argv
from memstara.control.workspace import PipelineWorkspace

OVERRIDES={'version':1,'models':{'logistic_regression':{'parameters':{'C':.25,'solver':'liblinear','penalty':'l1'},'scale_numeric':False,'threshold':.6},'xgboost':{'parameters':{'n_estimators':40,'learning_rate':.05},'threshold':.4}},'folds':2}


def plan():
    evaluation=evaluation_plan({'engine':'xgboost'})
    snapshot={'ml_configuration_policy':ml.policy(),'config_hash':'synthetic','_selected_ml_primary':'logistic_regression'}
    proposal=ml.context(snapshot,evaluation)['proposal_template']
    proposal['rationale']='Synthetic, predeclared model settings'
    return snapshot,evaluation,proposal


def test_partial_user_values_win_and_unset_values_remain_agent_selected(tmp_path):
    snapshot,evaluation,proposal=plan()
    snapshot['ml_overrides']=copy.deepcopy(OVERRIDES)
    proposal['models']['logistic_regression']['parameters']['C']=5
    proposal['models']['xgboost']['parameters']['max_depth']=3
    context=ml.context(snapshot,evaluation)
    assert context['proposal_template']['models']['logistic_regression']['parameters']['C']==.25
    assert 'C' not in context['editable_parameter_ranges']['logistic_regression']
    effective,resolution=ml.resolve(proposal,snapshot,evaluation)
    assert effective['models']['logistic_regression']['parameters']['C']==.25
    assert effective['models']['xgboost']['parameters']['max_depth']==3
    assert effective['folds']==2
    assert effective['models']['logistic_regression']['scale_numeric'] is False
    assert proposal['models']['logistic_regression']['parameters']['C']==5
    assert resolution['source']=='user_overrides_and_agent_proposal'
    snapshot['_ml_plan_resolution']=resolution
    data=tmp_path/'synthetic.csv';data.write_text('a,Y\n0,0\n1,1\n')
    receipt=ml.identity(data,snapshot,evaluation,effective)
    assert receipt['user_overrides']==OVERRIDES
    assert receipt['proposal_resolution']['agent_proposal']==proposal
    sources=receipt['setting_sources']['models']['logistic_regression']['parameters']
    assert sources['C']=='user' and sources['max_iter']=='agent' and sources['random_state']=='agent'
    wrong=copy.deepcopy(effective);wrong['models']['logistic_regression']['parameters']['C']=7
    with pytest.raises(ValueError,match='fixed advanced'):
        ml.validate(wrong,snapshot,evaluation)


@pytest.mark.parametrize('model,parameter,value',[
 ('logistic_regression','C',0),('logistic_regression','max_iter',2001),
 ('logistic_regression','max_iter',True),('logistic_regression','tol',float('nan')),
 ('xgboost','n_estimators',401),('xgboost','max_depth',9),('xgboost','n_jobs',64),
 ('xgboost','device','cuda'),('logistic_regression','solver','saga'),
 ('logistic_regression','random_state',2147483648),('xgboost','learning_rate',None)])
def test_rejects_invalid_or_server_owned_settings(model,parameter,value):
    with pytest.raises(ValueError):
        ml.validate_overrides({'version':1,'models':{model:{'parameters':{parameter:value}}}})


@pytest.mark.parametrize('value',[None,[],{'version':True},{'version':1,'gpu':True},
 {'version':1,'folds':1},{'version':1,'folds':True},
 {'version':1,'models':{'random_forest':{}}},
 {'version':1,'models':{'xgboost':{'threshold':1}}},
 {'version':1,'models':{'xgboost':{'scale_numeric':'yes'}}},
 {'version':1,'models':{'logistic_regression':{'parameters':{'penalty':'l1','solver':'lbfgs'}}}}])
def test_bad_advanced_structures_rejected(value):
    with pytest.raises(ValueError):ml.validate_overrides(value)


def test_selected_skill_and_fit_budget_checked_before_persistence_or_launch(monkeypatch):
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER','openai');monkeypatch.setenv('MEMSTARA_LLM_MODEL','synthetic')
    monkeypatch.setattr('memstara.stage_models.deployment_profiles',lambda:{})
    settings={'version':1,'models':{'logistic_regression':OVERRIDES['models']['logistic_regression']}}
    body={'playbook_ml':'ml_logistic_regression','ml_overrides':settings}
    stored=PipelineWorkspace.configuration(body)
    assert stored['ml_overrides']==settings
    argv=build_argv(body,[],['ml_logistic_regression'],['ml'])
    assert json.loads(argv[argv.index('--ml-overrides')+1])==settings
    with pytest.raises(ValueError,match='selected ML skills'):
        PipelineWorkspace.configuration({**body,'playbook_ml':'ml_xgboost'})
    with pytest.raises(ValueError,match='fit budget'):
        PipelineWorkspace.configuration({**body,'evaluation':{'replicates':10},'ml_overrides':{**settings,'folds':5}})
    with pytest.raises(ValueError,match='selected ML skills'):
        build_argv({**body,'playbook_ml':'ml_xgboost'},[],['ml_xgboost'],['ml'])


def test_controlled_comparison_cannot_be_changed_by_user_overrides():
    snapshot,evaluation,proposal=plan()
    snapshot.update(ml_overrides=OVERRIDES,controlled_comparison={'ml_plan':proposal})
    with pytest.raises(ValueError,match='Controlled comparisons'):
        ml.resolve(proposal,snapshot,evaluation)


@pytest.mark.parametrize('value', [None, [], 'invalid'])
def test_malformed_evaluation_cannot_crash_advanced_settings_save(value):
    with pytest.raises(ValueError, match='must be an object'):
        PipelineWorkspace.configuration({'evaluation': value})
