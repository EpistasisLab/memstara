"""Real bounded synthetic selected-model integration; no model API or private data."""
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
from memstara import data_allocation as allocation
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
                'data_allocation_policy':{'version':allocation.PREVIOUS_VERSION},
                'books':{'data':['data_balanced_stratified'],'ml':['ml_xgboost']},
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
    proposal['rationale']='Synthetic selected-model plan fixed before fitting'
    proposal['models']['xgboost']['parameters']['n_estimators']=10
    proposal['models']['xgboost']['parameters']['max_depth']=2
    return subset,snapshot,effective,proposal


def test_paused_fit_survives_parent_process_death(experiment, monkeypatch, tmp_path):
    import subprocess
    from memstara.pipeline.paused_recovery import VERSION, fit_path, saved_fit
    path, snapshot, effective, proposal = experiment
    snapshot.update(pause_policy='fresh_request_and_ml_restart_v2', pause_recovery_policy=VERSION)
    frozen = tmp_path/'config.json'
    frozen.write_text(json.dumps(snapshot))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(frozen))
    request = tmp_path/'test-request.json'
    request.write_text(json.dumps({'path':str(path), 'snapshot':snapshot, 'evaluation':effective, 'proposal':proposal}))
    script = '''
import json, os, sys
from pathlib import Path
from memstara import paired_ml
from memstara.pipeline import pause_runtime
r=json.loads(Path(sys.argv[1]).read_text())
def stop(command, **kwargs):
    kwargs['pause_marker'].touch()
    raise paired_ml.FitPaused()
paired_ml.supervise=stop
pause_runtime.wait_for_ml_resume=lambda *args: os._exit(137)
paired_ml.execute(Path(r['path']), 'Y', r['evaluation'], r['snapshot'], r['proposal'])
'''
    assert subprocess.run([sys.executable, '-c', script, str(request)]).returncode == 137
    assert fit_path(tmp_path, path).exists()
    assert not path.with_suffix('.paired-evaluation.json').exists()
    original = path.read_bytes()
    path.write_bytes(original + b'\n')
    with pytest.raises(ValueError, match='integrity'):
        saved_fit(path, snapshot)
    path.write_bytes(original)
    (tmp_path/'pause.request').unlink()
    changed = copy.deepcopy(proposal)
    changed['models']['xgboost']['parameters']['n_estimators'] = 20
    result = paired_ml.execute(path, 'Y', effective, snapshot, changed)
    assert result.get('status') != 'failed', result
    assert result['ml_resource_usage']['pause_restarts'] == 1
    assert not fit_path(tmp_path, path).exists()
    assert paired_ml.execute(path, 'Y', effective, snapshot, proposal) == result


def test_paused_fit_restarts_with_identical_inputs(experiment, monkeypatch, tmp_path):
    import threading
    import time
    from memstara.pipeline.pause_runtime import ml_pause_count
    path, snapshot, effective, proposal = experiment
    snapshot['pause_policy'] = 'fresh_request_and_ml_restart_v2'
    frozen = tmp_path/'config.json'
    frozen.write_text(json.dumps(snapshot))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(frozen))
    real = paired_ml.supervise
    calls = []
    def interrupted_once(command, **kwargs):
        calls.append(json.loads(Path(command[-2]).read_text()))
        if len(calls) == 1:
            kwargs['pause_marker'].touch()
            raise paired_ml.FitPaused()
        return real(command, **kwargs)
    monkeypatch.setattr(paired_ml, 'supervise', interrupted_once)
    def resume():
        deadline = time.monotonic()+10
        while not ml_pause_count(tmp_path) and time.monotonic()<deadline:
            time.sleep(.02)
        (tmp_path/'pause.request').unlink(missing_ok=True)
    thread = threading.Thread(target=resume)
    thread.start()
    result = paired_ml.execute(path, 'Y', effective, snapshot, proposal)
    thread.join()
    assert result.get('status') != 'failed', result
    assert calls[0] == calls[1]
    assert result['ml_resource_usage']['pause_restarts'] == 1
    # A completed evaluation is returned as-is, never fitted again.
    again = paired_ml.execute(path, 'Y', effective, snapshot, proposal)
    assert again == result and len(calls) == 2


@pytest.mark.parametrize('submission', ['omitted', 'missing_rationale', 'changed_settings'])
def test_frozen_tool_uses_server_plan_and_saves_resolution(experiment, monkeypatch, submission):
    from memstara.mcp_servers.ml import train_and_score
    path, snapshot, effective, proposal = experiment
    snapshot['controlled_comparison'] = {'ml_plan': copy.deepcopy(proposal)}
    from memstara import data_allocation
    monkeypatch.setattr(data_allocation, 'load_effective', lambda *args: (effective, None))
    supplied = copy.deepcopy(proposal)
    if submission == 'omitted':
        supplied = None
    elif submission == 'missing_rationale':
        supplied.pop('rationale')
    else:
        supplied['models']['xgboost']['parameters']['max_depth'] = 8
    executed = []

    def execute(*args, **kwargs):
        executed.append((args, kwargs))
        return {'model': 'xgboost'}

    monkeypatch.setattr(paired_ml, 'execute', execute)
    result = json.loads(train_and_score(str(path), 'Y', ml_plan=supplied))
    assert not result.get('error'), result
    assert len(executed) == 1
    assert executed[0][0][4] == proposal
    receipt = result['ml_plan_resolution']
    assert receipt['source'] == 'server_frozen'
    assert receipt['effective_plan'] == proposal
    assert receipt['agent_proposal'] == supplied
    assert json.loads(path.with_suffix('.evaluation.json').read_text()) == result


def test_real_tool_pair_and_replay(experiment, monkeypatch):
    from memstara.mcp_servers.ml import train_and_score, get_ml_configuration
    path,snapshot,effective,proposal=experiment
    context=json.loads(asyncio.run(get_ml_configuration(str(path),'Y')))
    assert context['required'] and context['fixed']['data_seed']==7
    missing=json.loads(train_and_score(str(path),'Y'))
    assert 'error' in missing and not path.with_suffix('.ml-plan.json').exists()
    result=json.loads(train_and_score(str(path),'Y',seed=999,ml_plan=proposal))
    assert not result.get('error'),result
    assert 'paired_models' not in result
    assert result['model']=='xgboost'
    assert result['data_allocation']['agent_plan']['seed']==7
    assert result['ml_configuration']['requested']==proposal
    assert result['ml_resource_usage']['threads']==1
    assert result['ml_resource_usage']['peak_rss_bytes']>0
    assert set(result['model_results'])=={'xgboost'}
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
    changed['models']['xgboost']['parameters']['max_depth']=3
    refusal=json.loads(train_and_score(str(path),'Y',ml_plan=changed))
    assert 'cannot change' in refusal['error']
    assert json.loads(path.with_suffix('.evaluation.json').read_text())==result
    # The blackboard transition preserves the selected model for Interpretation.
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



def test_ml_agent_random_states_are_editable_and_recorded(experiment):
    path, snapshot, effective, proposal = experiment
    proposal = copy.deepcopy(proposal)
    for model in proposal['models']:
        proposal['models'][model]['parameters']['random_state'] = 987654
    accepted = config.validate(proposal, snapshot, effective)
    record = config.identity(path, snapshot, effective, accepted)
    assert record['requested'] == proposal
    assert record['setting_sources']['models']['xgboost']['parameters']['random_state'] == 'agent'


@pytest.mark.parametrize('change', ['threads','trees','depth','gpu','unknown','missing','solver','bool','nan','seed'])
def test_invalid_plans_never_start(experiment,change):
    path,snapshot,evaluation_plan,proposal=experiment
    xgb=proposal['models']['xgboost']['parameters']
    if change=='threads':xgb['n_jobs']=-1
    if change=='trees':xgb['n_estimators']=100000
    if change=='depth':xgb['max_depth']=0
    if change=='gpu':xgb['device']='cuda'
    if change=='unknown':xgb['callbacks']=[]
    if change=='missing':del xgb['max_depth']
    if change=='solver':xgb['learning_rate']=float('nan')
    if change=='bool':xgb['n_estimators']=True
    if change=='nan':xgb['learning_rate']=float('nan')
    if change=='seed':xgb['random_state']=2147483648
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


def test_selected_model_fits_only_one_estimator(experiment,monkeypatch):
    from memstara import comparisons
    path,snapshot,effective,proposal=experiment
    calls=[]
    def controlled_fit(path,target,plan,snapshot,**kwargs):
        calls.append(plan['engine'])
        return {'auc':.6,'model':plan['engine'],'artifact':'synthetic-bundle-reference',
                'evaluation':{'replicates':[]}}
    monkeypatch.setattr(comparisons,'score_comparisons',controlled_fit)
    request={'path':str(path),'target':'Y','evaluation':effective,'snapshot':snapshot,
             'proposal':proposal,'record':config.identity(path,snapshot,effective,proposal)}
    result=paired_ml.fit(request)
    assert calls == ['xgboost']
    assert set(result['model_results']) == {'xgboost'}


@pytest.mark.parametrize('skill,primary', [('ml_logistic_regression', 'logistic_regression'),
                                          ('ml_xgboost', 'xgboost')])
def test_selected_model_contract_reaches_tool_and_fits_selected_model_only(experiment, skill, primary):
    from memstara.mcp_servers.ml import get_ml_configuration, train_and_score
    path, snapshot, _, _ = experiment
    snapshot['books']['ml'] = [skill]
    spec = json.loads(asyncio.run(get_ml_configuration(str(path), 'Y')))
    assert spec['fixed']['primary_model'] == primary
    plan = spec['proposal_template']
    assert set(plan['models']) == {primary}
    plan['rationale'] = 'Synthetic selected-model contract'
    if primary == 'xgboost':
        plan['models']['xgboost']['parameters']['n_estimators'] = 10
        plan['models']['xgboost']['parameters']['max_depth'] = 2
    wrong = copy.deepcopy(plan)
    wrong['primary_model'] = 'xgboost' if primary == 'logistic_regression' else 'logistic_regression'
    rejected = json.loads(train_and_score(str(path), 'Y', ml_plan=wrong))
    assert 'selected ML skill' in rejected['error']
    assert not path.with_suffix('.ml-plan.json').exists()
    extra = copy.deepcopy(plan)
    unselected = 'xgboost' if primary == 'logistic_regression' else 'logistic_regression'
    extra['models'][unselected] = copy.deepcopy(plan['models'][primary])
    rejected = json.loads(train_and_score(str(path), 'Y', ml_plan=extra))
    assert 'only the selected ML model' in rejected['error']
    assert not path.with_suffix('.ml-plan.json').exists()
    result = json.loads(train_and_score(str(path), 'Y', ml_plan=plan))
    assert set(result.get('model_results', {})) == {primary}, result
    assert result['ml_configuration']['requested']['primary_model'] == primary
    assert result['model'] == primary


def test_advanced_user_values_reach_real_models_and_replay_with_provenance(experiment):
    from memstara.mcp_servers.ml import train_and_score, get_ml_configuration
    import os
    import subprocess
    import sys
    path,snapshot,plan,proposal=experiment
    snapshot['books']['ml']=['ml_logistic_regression']
    overrides={'version':1,'models':{
        'logistic_regression':{'parameters':{'C':.25,'solver':'liblinear'},'threshold':.65,'scale_numeric':False},
        },'folds':0}
    snapshot['ml_overrides']=overrides
    specification=json.loads(asyncio.run(get_ml_configuration(str(path),'Y')))
    assert specification['user_overrides']==overrides
    proposal=specification['proposal_template']
    proposal['rationale']='Synthetic selected LR plan with one fixed user value'
    proposal['models']['logistic_regression']['parameters']['C']=5
    result=json.loads(train_and_score(str(path),'Y',ml_plan=proposal))
    assert not result.get('error'),result
    assert result['ml_configuration']['user_overrides']==overrides
    assert result['ml_plan_resolution']['agent_proposal']['models']['logistic_regression']['parameters']['C']==5
    assert result['ml_configuration']['setting_sources']['models']['logistic_regression']['parameters']['C']=='user'
    assert result['ml_configuration']['setting_sources']['models']['logistic_regression']['parameters']['random_state']=='agent'
    for name in ('logistic_regression',):
        model=result['model_results'][name]
        bundle=Path(model['evaluation']['reproducibility']['bundle_path'])
        manifest=json.loads((bundle/'manifest.json').read_text())
        assert manifest['configuration']['threshold']==overrides['models'][name]['threshold']
        for key,value in overrides['models'][name]['parameters'].items():
            assert manifest['configuration']['parameters'][key]==value
        receipt=json.loads((bundle/'ml-plan.json').read_text())
        assert receipt['user_overrides']==overrides
        assert receipt['proposal_resolution']['agent_proposal']==proposal
        env={**os.environ,**{key:'1' for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS')}}
        replayed=subprocess.run([sys.executable,'-m','memstara.reproducibility',str(bundle)],env=env,capture_output=True,text=True,timeout=60)
        assert replayed.returncode==0,replayed.stdout+replayed.stderr
        assert json.loads(replayed.stdout)['status']=='verified'
    assert json.loads(train_and_score(str(path),'Y',ml_plan=proposal))==result


def test_unlimited_policy_accepts_large_fit_estimates():
    limits = config.policy()
    for key in ('max_fits', 'wall_seconds', 'memory_bytes', 'max_csv_bytes',
                'max_dense_cells', 'max_encoded_columns'):
        assert limits[key] is None
        assert not paired_ml.exceeds_limit(limits, key, 10**12)
    assert not paired_ml.exceeds_limit(limits, 'max_fits', 3 * 2 * 21)
    assert paired_ml.exceeds_limit({'max_fits': 120}, 'max_fits', 126)


def test_unlimited_supervisor_records_usage_without_memory_rejection(monkeypatch):
    import psutil
    original = psutil.Process.memory_info

    def large_usage(process):
        return original(process)._replace(rss=4 * 1024**3)

    monkeypatch.setattr(psutil.Process, 'memory_info', large_usage)
    result = paired_ml.supervise(
        [sys.executable, '-c', 'import time; time.sleep(.3)'],
        env=os.environ.copy(), limits=config.policy())
    assert result['memory_ceiling_bytes'] is None
    assert result['peak_rss_bytes'] >= 4 * 1024**3
    assert result['duration_seconds'] >= .3


def test_default_lr_tool_trains_library_defaults_and_records_provenance(experiment):
    from sklearn.linear_model import LogisticRegression
    from memstara.mcp_servers.ml import train_and_score, get_ml_configuration
    path, snapshot, effective, _ = experiment
    snapshot['books']['ml'] = [config.DEFAULT_SKILL]
    spec = json.loads(asyncio.run(get_ml_configuration(str(path), 'Y')))
    assert spec['plan_source'] == 'server_frozen'
    assert spec['proposal_template']['models']['logistic_regression']['parameters'] == LogisticRegression().get_params()
    result = json.loads(train_and_score(str(path), 'Y', ml_plan={'unexpected': 'ignored'}))
    assert not result.get('error'), result
    assert result.get('status') != 'failed', result
    assert set(result['model_results']) == {'logistic_regression'}
    receipt = result['ml_configuration']
    assert receipt['configuration_source'] == 'sklearn_default'
    assert receipt['sklearn_version']
    assert receipt['effective']['models']['logistic_regression']['parameters'] == LogisticRegression().get_params()
    assert receipt['effective']['folds'] == 0
    assert receipt['effective']['models']['logistic_regression']['scale_numeric'] is False
    assert result['ml_plan_resolution']['agent_proposal_ignored'] is True
    assert result['evaluation']['reproducibility']['status'] == 'verified'
    assert json.loads(path.with_suffix('.ml-plan.json').read_text()) == receipt


def test_default_lr_rejects_parameter_changes_and_user_overrides(experiment):
    path, snapshot, effective, _ = experiment
    snapshot['books']['ml'] = [config.DEFAULT_SKILL]
    plan = config.default_plan()
    plan['models']['logistic_regression']['parameters']['C'] = 2
    with pytest.raises(ValueError, match='defaults'):
        config.validate(plan, snapshot, effective)
    snapshot['ml_overrides'] = {'version': 1, 'folds': 2}
    with pytest.raises(ValueError, match='overrides'):
        config.resolve(None, snapshot, effective)


def test_completed_fit_winning_pause_race_is_not_replayed(experiment, monkeypatch, tmp_path):
    path, snapshot, effective, proposal = experiment
    snapshot['pause_policy'] = 'fresh_request_and_ml_restart_v2'
    frozen = tmp_path/'config.json'
    frozen.write_text(json.dumps(snapshot))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(frozen))
    calls = []
    complete = {'status': 'completed', 'fixture': 'already-published'}
    def published_then_paused(command, **kwargs):
        calls.append(command)
        kwargs['pause_marker'].touch()
        kwargs['output_path'].write_text(json.dumps(complete))
        raise paired_ml.FitPaused()
    monkeypatch.setattr(paired_ml, 'supervise', published_then_paused)
    result = paired_ml.execute(path, 'Y', effective, snapshot, proposal)
    assert result['fixture'] == complete['fixture']
    assert result['ml_resource_usage']['completed_during_pause'] is True
    assert result['ml_resource_usage']['pause_restarts'] == 0
    assert len(calls) == 1
