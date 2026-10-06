"""Real bounded synthetic LR/XGBoost integration; no model API or private data."""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from memstara import evaluation
from memstara import ml_configuration as config
from memstara import paired_ml
from memstara.data_allocation import prepare, VERSION
from memstara.comparisons import write_context


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    rng = np.random.default_rng(22)
    source = tmp_path / 'source.csv'
    pd.DataFrame({**{k:rng.normal(size=100) for k in 'abcd'}, 'Y':[0,1]*50}).to_csv(source,index=False)
    snapshot = {'config_hash':'paired-fixture', 'run_tag':'paired-fixture','y_column':'Y',
                'dataset_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'evaluation':evaluation.validate({'engine':'xgboost'}),
                'ml_configuration_policy':config.policy(),
                'data_allocation_policy':{'version':VERSION},
                'books':{'data':['data_balanced_stratified']},
                'prompts':{'board/data:data_balanced_stratified':{'system_prompt':'synthetic'}},
                'validation_partition':evaluation.discovery_partition(pd.read_csv(source).Y,42),
                'comparison_policy':{'baseline_columns':[]}}
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR',str(tmp_path))
    monkeypatch.setenv('MEMSTARA_DATASET_PATH',str(source))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG',raising=False)
    monkeypatch.setattr(evaluation,'active_plan',lambda:snapshot)
    subset = tmp_path/'subset.csv'
    subset.write_bytes(source.read_bytes())
    task = {'task_id':1,'trial':0,'columns':list('abcd'),'y_column':'Y','evaluation':{}}
    record = prepare({'test_size':.5,'seed':7,'stratify':True},task,snapshot,subset)
    assert record
    write_context(subset,task,snapshot,data_allocation=record)
    effective=record['effective_evaluation']
    proposal=config.context(snapshot,effective)['proposal_template']
    proposal['rationale']='Synthetic paired comparison fixed before fitting'
    proposal['models']['xgboost']['parameters']['n_estimators']=10
    proposal['models']['xgboost']['parameters']['max_depth']=2
    proposal['models']['logistic_regression']['threshold']=.6
    return subset,snapshot,effective,proposal


def test_real_tool_pair_and_replay(experiment, monkeypatch):
    from memstara.mcp_servers.ml import train_and_score, get_ml_configuration
    path,snapshot,effective,proposal=experiment
    context=json.loads(asyncio.run(get_ml_configuration(str(path),'Y')))
    assert context['required'] and context['fixed']['data_seed']==7
    missing=json.loads(train_and_score(str(path),'Y'))
    assert 'error' in missing and not path.with_suffix('.ml-plan.json').exists()
    result=json.loads(train_and_score(str(path),'Y',seed=999,ml_plan=proposal))
    assert not result.get('error'),result
    assert result['paired_models']['same_splits']
    assert result['model']=='logistic_regression'
    assert result['data_allocation']['agent_plan']['seed']==7
    assert result['ml_configuration']['requested']==proposal
    assert result['ml_resource_usage']['threads']==1
    assert result['ml_resource_usage']['peak_rss_bytes']>0
    assert set(result['model_results'])==set(config.MODELS)
    for name,model in result['model_results'].items():
        run=model['evaluation']['replicates'][0]
        assert (run['n_train'],run['n_test'],run['seed'])==(40,40,7)
        assert model['features']==list('abcd')
        assert all(key in run for key in ('brier_score','f1','pr_auc','log_loss'))
        assert run['operating_point']['probability_cutoff']==proposal['models'][name]['threshold']
        assert model['evaluation']['reproducibility']['status']=='verified'
        bundle=Path(model['evaluation']['reproducibility']['bundle_path'])
        arrays=np.load(bundle/'split-0.npz')
        assert not set(result['data_allocation']['reserved_rows']) & set(arrays['train'])
        manifest=json.loads((bundle/'manifest.json').read_text())
        assert manifest['configuration']==proposal['models'][name]
        assert json.loads((bundle/'ml-plan.json').read_text())['requested']==proposal
        # Replay with the same explicitly recorded native-thread settings.
        import subprocess
        env={**os.environ, **{key:'1' for key in (
            'OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS')}}
        replayed=subprocess.run([sys.executable,'-m','memstara.reproducibility',str(bundle)],
                                env=env,capture_output=True,text=True,timeout=60)
        assert replayed.returncode==0,replayed.stdout
        assert json.loads(replayed.stdout)['status']=='verified'
    again=json.loads(train_and_score(str(path),'Y',ml_plan=proposal))
    assert again==result
    changed=copy.deepcopy(proposal)
    changed['models']['logistic_regression']['parameters']['C']=2.
    refusal=json.loads(train_and_score(str(path),'Y',ml_plan=changed))
    assert 'cannot change' in refusal['error']
    assert json.loads(path.with_suffix('.evaluation.json').read_text())==result
    # The existing blackboard transition preserves both models for Interpretation.
    from unittest.mock import AsyncMock, MagicMock
    from memstara.mcp_servers import blackboard as bb
    monkeypatch.setattr(bb,'_pipeline_run',lambda:'')
    connection=AsyncMock()
    connection.transaction=MagicMock(return_value=AsyncMock())
    connection.fetchval.return_value=None
    connection.fetchrow.return_value={'task_id':1,'trial':0,'task_type':'ml','status':'in_progress',
        'claimed_by':'ml','subset_path':str(path),'y_column':'Y','perspective':'fixture',
        'hypothesis':'fixture','columns':list('abcd'),'evaluation':{
            'config_hash':snapshot['config_hash'],'data_allocation':result['data_allocation']}}
    monkeypatch.setattr(bb.asyncpg,'connect',AsyncMock(return_value=connection))
    submitted=json.loads(asyncio.run(bb.submit_result(1,worker='ml')))
    assert submitted.get('ok'),submitted
    payloads=[json.loads(c.args[2]) for c in connection.execute.call_args_list
              if c.args[0].startswith('UPDATE memstara_blackboard SET evaluation=')]
    assert payloads[0]['model_results']==result['model_results']



@pytest.mark.parametrize('change', ['threads','trees','depth','gpu','unknown','missing','solver','bool','nan','seed'])
def test_invalid_plans_never_start(experiment,change):
    path,snapshot,evaluation_plan,proposal=experiment
    lr=proposal['models']['logistic_regression']['parameters']
    xgb=proposal['models']['xgboost']['parameters']
    if change=='threads':xgb['n_jobs']=-1
    if change=='trees':xgb['n_estimators']=100000
    if change=='depth':xgb['max_depth']=0
    if change=='gpu':xgb['device']='cuda'
    if change=='unknown':xgb['callbacks']=[]
    if change=='missing':del lr['C']
    if change=='solver':lr.update(solver='lbfgs',penalty='l1')
    if change=='bool':lr['C']=True
    if change=='nan':lr['C']=float('nan')
    if change=='seed':lr['random_state']=999
    with pytest.raises(ValueError):paired_ml.execute(path,'Y',evaluation_plan,snapshot,proposal)
    assert not path.with_suffix('.ml-plan.json').exists()


def test_watchdog_kills_timed_out_worker():
    with pytest.raises(RuntimeError,match='wall-time'):
        paired_ml.supervise([sys.executable,'-c','import time; time.sleep(10)'],env=os.environ.copy(),
                            limits={'memory_bytes':512*1024**2,'wall_seconds':.2})


def test_failed_pair_is_saved_and_never_silently_retried(experiment,monkeypatch):
    path,snapshot,effective,proposal=experiment
    calls=[]
    def fail(*args,**kwargs):
        calls.append(True)
        raise RuntimeError('Paired ML exceeded its memory budget')
    monkeypatch.setattr(paired_ml,'supervise',fail)
    result=paired_ml.execute(path,'Y',effective,snapshot,proposal)
    assert result['status']=='failed' and 'memory budget' in result['error']
    assert paired_ml.execute(path,'Y',effective,snapshot,proposal)==result
    assert len(calls)==1
    assert result['partial_progress']=={'phase':'starting','completed_models':{}}


def test_global_lock_is_retryable_before_accepting_plan(experiment):
    import fcntl
    path,snapshot,effective,proposal=experiment
    with (path.parent/'.paired-ml.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert paired_ml.execute(path,'Y',effective,snapshot,proposal)['retryable']
    assert not path.with_suffix('.ml-plan.json').exists()


def test_watchdog_kills_memory_overrun(monkeypatch):
    import psutil
    original = psutil.Process.memory_info
    def overrun(process):
        info = original(process)
        return info._replace(rss=1024**3)
    monkeypatch.setattr(psutil.Process, 'memory_info', overrun)
    with pytest.raises(RuntimeError, match='memory budget'):
        paired_ml.supervise([sys.executable,'-c','import time; time.sleep(10)'],env=os.environ.copy(),
                            limits={'memory_bytes':512*1024**2,'wall_seconds':10})


def test_fit_budget_rejection_does_not_freeze(experiment):
    path,snapshot,effective,proposal=experiment
    snapshot['ml_configuration_policy']['max_fits']=1
    with pytest.raises(ValueError,match='fit count'):
        paired_ml.execute(path,'Y',effective,snapshot,proposal)
    assert not path.with_suffix('.ml-plan.json').exists()


def test_second_model_failure_preserves_first_model_artifact(experiment,monkeypatch):
    from memstara import comparisons
    path,snapshot,effective,proposal=experiment
    def controlled_fit(path,target,plan,snapshot,**kwargs):
        if plan['engine']=='xgboost':
            raise RuntimeError('synthetic worker failure')
        return {'auc':.6,'model':'logistic_regression','artifact':'synthetic-bundle-reference'}
    monkeypatch.setattr(comparisons,'score_comparisons',controlled_fit)
    request={'path':str(path),'target':'Y','evaluation':effective,'snapshot':snapshot,
             'proposal':proposal,'record':config.identity(path,snapshot,effective,proposal)}
    with pytest.raises(RuntimeError,match='synthetic'):
        paired_ml.fit(request)
    progress=json.loads(path.with_suffix('.paired-progress.json').read_text())
    assert progress['phase']=='xgboost'
    assert progress['completed_models']['logistic_regression']['artifact']=='synthetic-bundle-reference'
