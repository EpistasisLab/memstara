"""Four real method/model paths, saved-model replay and scoped specialist handoffs."""
import asyncio
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from memstara import specialist_xai as xai
from test_paired_ml import experiment  # noqa: F401


@pytest.fixture
def skills(tmp_path, monkeypatch):
    from memstara.control import catalog
    root = tmp_path/'shared'
    root.mkdir()
    (root/'old').mkdir()
    monkeypatch.setattr(catalog,'specialist_dir',lambda:root)
    for name, method in xai.SKILLS.items():
        filename = catalog.SPECIALIST_SKILLS[name][0]
        (root/filename).write_text(f'# Interpretation Skill\n## Feature Attribution ({method.upper()})\nSynthetic instructions')
        (root/'old'/filename).write_text('ARCHIVED MUST NEVER LOAD')
    return root


@pytest.fixture
def specification(experiment, skills):
    path,snapshot,effective,proposal=experiment
    snapshot['books']['interpreter']=list(xai.SKILLS)
    snapshot['prompts'].update({f'board/interpreter:{key}':{'system_prompt':f'Synthetic {key} instructions'}
                                for key in xai.SKILLS})
    snapshot['specialist_xai_policy']=xai.freeze(snapshot['books'],snapshot['prompts'])
    snapshot['specialist_xai_policy'].update(explained_rows=2,background_rows=8,lime_samples=100)
    return experiment


def test_current_skill_freeze_excludes_old_and_checks_method(specification,skills):
    _,snapshot,_,_=specification
    policy=snapshot['specialist_xai_policy']
    assert set(policy['skills'])==set(xai.SKILLS)
    assert all('ARCHIVED' not in v['source_text'] for v in policy['skills'].values())
    (skills/'SHAP-Interpretation.md').unlink()
    with pytest.raises(FileNotFoundError,match='no archive fallback'):
        xai.freeze(snapshot['books'],snapshot['prompts'])
    (skills/'SHAP-Interpretation.md').write_text('# Wrong skill')
    with pytest.raises(ValueError,match='expected the current'):
        xai.freeze(snapshot['books'],snapshot['prompts'])


@pytest.mark.parametrize('prepared_input', [False, True])
def test_both_specialists_selected_saved_model_and_offline_replay(specification,monkeypatch,prepared_input):
    from memstara.mcp_servers.ml import train_and_score
    from memstara import paired_ml
    path,snapshot,_,proposal=specification
    if prepared_input:
        snapshot['preprocessing_policy'] = 'analysis_ready_v1'
    # Real child process has no access to pytest mocks; all frozen skills are in its request.
    result=json.loads(train_and_score(str(path),'Y',ml_plan=proposal))
    assert not result.get('error'),result
    all_ids=set()
    for name,model in result['model_results'].items():
        evidence=model['specialist_xai']
        assert evidence['status']=='completed',evidence
        assert {v['method'] for v in evidence['items']}=={'shap','lime'}
        bundle=Path(model['evaluation']['reproducibility']['bundle_path'])
        manifest=json.loads((bundle/'manifest.json').read_text())
        assert 'specialist_xai.py' in manifest['code']
        for item in evidence['items']:
            assert item['model']==name
            assert item['explanation_id'] not in all_ids
            all_ids.add(item['explanation_id'])
            document=json.loads(Path(item['artifact_path']).read_text())
            local=document['evidence']
            train=set(result['data_allocation']['replicates'][0]['train_rows'])
            test=set(result['data_allocation']['replicates'][0]['test_rows'])
            reserve=set(result['data_allocation']['reserved_rows'])
            assert set(local['background_rows'])<=train
            assert set(local['explained_rows'])<=test
            assert not reserve & set(local['background_rows']+local['explained_rows'])
            assert 'values_original' not in item and 'model_outputs' not in item
            if item['method']=='shap':assert local['max_additivity_error']<1e-4
            else:assert len(local['local_diagnostics'])==2
        import os,subprocess,sys
        env={**os.environ,**{key:'1' for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS',
                                               'MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS')}}
        process=subprocess.run([sys.executable,'-m','memstara.reproducibility',str(bundle)],
                               env=env,capture_output=True,text=True,timeout=60)
        assert process.returncode==0,process.stdout
        # No estimator.fit is used by attribution replay.
        from sklearn.linear_model import LogisticRegression
        from xgboost import XGBClassifier
        with monkeypatch.context() as m:
            def no_fit(*a,**kw):raise AssertionError('Must not retrain for explanation replay')
            m.setattr(LogisticRegression,'fit',no_fit)
            m.setattr(XGBClassifier,'fit',no_fit)
            assert xai.replay(bundle)['status']=='verified'
    task={'task_id':1,'trial':0,'subset_path':str(path),'evaluation':result}
    for slot,method in enumerate(('shap','lime'),1):
        value=xai.handoff(snapshot,task,f'interpret#{slot}')
        assert value['method']==method and set(value['models'])=={'xgboost'}
        assert all(i['method']==method for m in value['models'].values() for i in m['attributions'])
        incoming=xai.record_io(snapshot,task,f'interpret#{slot}',value)
        outgoing=xai.record_io(snapshot,task,f'interpret#{slot}',value,interpretation='Measured synthetic findings')
        assert incoming['sha256']!=outgoing['sha256']
        assert set(outgoing['model_explanation_ids'])=={'xgboost'}
        assert json.loads(Path(outgoing['path']).read_text())['interpretation']=='Measured synthetic findings'
    from unittest.mock import AsyncMock,MagicMock
    from memstara.mcp_servers import blackboard as bb
    connection=AsyncMock()
    connection.transaction=MagicMock(return_value=AsyncMock())
    connection.fetchval.return_value=None
    current={**task,'task_type':'interpret','status':'in_progress','claimed_by':'interpret#1',
             'columns':list('abcd'),'columns_used':list('abcd')+['Y'],'okf_concept_ids':[],
             'feature_importance':{},'y_column':'Y','hypothesis':'Synthetic hypothesis','perspective':'fixture'}
    raw={k:json.dumps(v) if k in ('columns','columns_used','okf_concept_ids','feature_importance','evaluation')
         else v for k,v in current.items()}
    connection.fetchrow.return_value=raw
    monkeypatch.setattr(bb,'_pipeline_run',lambda:'')
    monkeypatch.setattr(bb.asyncpg,'connect',AsyncMock(return_value=connection))
    received=json.loads(asyncio.run(bb.claim_task('interpret',worker='interpret#1')))
    assert received['interpretation_input']['method']=='shap'
    assert 'model_results' not in received['evaluation']
    record=json.loads(Path(received['interpretation_input_record']['path']).read_text())
    assert record['task']['hypothesis']=='Synthetic hypothesis'
    assert record['task']['interpretation_input']==received['interpretation_input']
    config_path=path.parent/'config.json'
    config_path.write_text(json.dumps(snapshot))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG',str(config_path))
    submitted=json.loads(asyncio.run(bb.submit_result(1,worker='interpret#1',interpretation='Selected model findings')))
    assert submitted.get('ok'),submitted
    records=[json.loads(c.args[2]) for c in connection.execute.call_args_list
             if c.args[0].startswith('UPDATE memstara_blackboard SET evaluation=')]
    assert records[0]['specialist_interpretation']['method']=='shap'
    assert json.loads(Path(records[0]['specialist_interpretation']['path']).read_text())['interpretation']=='Selected model findings'
    corrupted=copy.deepcopy(task)
    corrupted['evaluation']['model_results']['xgboost']['specialist_xai']['items'][0]['model']='logistic_regression'
    with pytest.raises(ValueError,match='Explanation artifact belongs to another model'):
        xai.handoff(snapshot,corrupted,'interpret#2' if result['model_results']['xgboost']['specialist_xai']['items'][0]['method']=='lime' else 'interpret#1')
    item=result['model_results']['xgboost']['specialist_xai']['items'][0]
    artifact=Path(item['artifact_path'])
    original=artifact.read_bytes()
    artifact.write_text('{}')
    with pytest.raises(ValueError,match='identity/hash'):
        xai.handoff(snapshot,task,'interpret#2' if item['method']=='lime' else 'interpret#1')
    artifact.write_bytes(original)
    # Persisted explanation artifacts survive cached retries without recomputation.
    monkeypatch.setattr(paired_ml,'supervise',lambda *a,**k:pytest.fail('Unexpected retraining'))
    assert json.loads(train_and_score(str(path),'Y',ml_plan=proposal))==result


@pytest.mark.parametrize('name', ['logistic_regression','xgboost'])
def test_real_categorical_mapping_and_signed_attributions(name):
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder,StandardScaler
    from sklearn.pipeline import Pipeline
    from memstara.evaluation import model_for
    X=pd.DataFrame({'numeric':[float(i%11) for i in range(60)],
                    'numeric_A':['B_A','A_B']*30,'flag':[True,False]*30})
    y=np.array([0,1]*30)
    pre=ColumnTransformer([('numeric',StandardScaler(),['numeric']),
                           ('categorical',OneHotEncoder(handle_unknown='ignore',sparse_output=False),
                            ['numeric_A','flag'])],verbose_feature_names_out=False)
    estimator=model_for(name,7)
    if name=='xgboost':estimator.set_params(n_estimators=10,max_depth=2)
    fitted=Pipeline([('encode',pre),('model',estimator)]).fit(X.iloc[:40],y[:40])
    policy={'explained_rows':4,'background_rows':8,'lime_samples':100,'max_original_features':64}
    for method in ('shap','lime'):
        row=xai.calculate(fitted,X,np.arange(40),np.arange(40,60),7,name,method,policy)
        assert set(row['feature_summary'])==set(X.columns)
        values=np.asarray(row['values_original'])
        assert values.shape==(4,3)
        assert any(v<0 for v in values.flat) and any(v>0 for v in values.flat)
        assert all(row['feature_summary'][c]['mean_absolute']==pytest.approx(abs(values[:,i]).mean())
                   for i,c in enumerate(X.columns))
        if method=='shap':
            assert row['encoded_to_original']==['numeric','numeric_A','numeric_A','flag','flag']
            assert np.allclose(np.asarray(row['values_encoded']).sum(axis=1),values.sum(axis=1))


def test_explanation_budgets_are_enforced_before_computation():
    from types import SimpleNamespace
    model=SimpleNamespace(classes_=np.array([0,1]))
    X=pd.DataFrame({'x':[1,2,3,4]})
    policy={'explained_rows':9,'background_rows':8,'lime_samples':100,'max_original_features':64}
    with pytest.raises(ValueError,match='row budget'):
        xai.calculate(model,X,np.array([0,1]),np.array([2,3]),7,'logistic_regression','shap',policy)
    policy.update(explained_rows=2,lime_samples=10000)
    with pytest.raises(ValueError,match='sample budget'):
        xai.calculate(model,X,np.array([0,1]),np.array([2,3]),7,'logistic_regression','lime',policy)


def test_one_method_failure_is_explicit_and_preserves_other_evidence(tmp_path,monkeypatch):
    (tmp_path/'model-0.joblib').write_bytes(b'synthetic-model-identity')
    def controlled(model,X,train,test,seed,name,method,policy):
        if method=='lime':raise RuntimeError('Sensitive raw value MUST NOT LEAK')
        return {'explainer':'synthetic','output_scale':'log-odds','feature_summary':{},
                'explained_rows':[2],'background_rows':[0],'limitation':'synthetic'}
    monkeypatch.setattr(xai,'calculate',controlled)
    result={'model':'logistic_regression','evaluation':{'dataset_sha256':'input','replicates':[
        {'seed':7,'split_id':'test','train_split_id':'train'}]}}
    spec={'policy':{},'methods':['shap','lime'],'run_tag':'fixture','trial':0,'config_hash':'fixture'}
    xai.save(tmp_path,pd.DataFrame({'x':[1,2,3,4]}),[(None,np.array([0,1]),np.array([2,3]),None)],result,spec)
    assert result['specialist_xai']['status']=='failed'
    assert [i['status'] for i in result['specialist_xai']['items']]==['completed','failed']
    assert (tmp_path/'xai-shap-0.json').is_file()
    assert 'Sensitive raw value' not in json.dumps(result)


def test_specialist_web_configuration_freezes_exact_sources(specification,monkeypatch,tmp_path):
    from types import SimpleNamespace
    from memstara.pipeline.snapshot import freeze
    from memstara.pipeline import prompts
    from memstara.control import catalog
    from memstara.control.request import build_argv
    from memstara.control.workspace import PipelineWorkspace
    # Build a NEW run rather than reusing the fixture's frozen agent prompt.
    monkeypatch.setattr('memstara.evaluation.active_plan',lambda:None)
    original_resolve=catalog.resolve
    original_prompt=prompts.load_prompt
    def resolve(key):
        if key in xai.SKILLS:return original_resolve(key)
        return {'id':key,'title':key,'hash':key,'stage':key}
    monkeypatch.setattr(catalog,'resolve',resolve)
    monkeypatch.setattr('memstara.pipeline.snapshot.load_prompt',
        lambda name,book:original_prompt(name,book) if book in xai.SKILLS else {'goal':name,'system_prompt':book})
    choices={s:list(xai.SKILLS) if s=='interpreter' else [s]
             for s in ('hypothesis','data','ml','interpreter','report')}
    for role in ('QUESTION', 'HYPOTHESIS', 'DATA', 'ML', 'INTERPRETATION', 'EXPLANATION'):
        monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER', 'openai')
        monkeypatch.setenv(f'MEMSTARA_{role}_MODEL', 'synthetic')
    value=PipelineWorkspace.configuration({'combination_skills':choices})
    argv=build_argv(value,[],[v for values in choices.values() for v in values],list(choices))
    args=SimpleNamespace(run_tag='web',question='',hypothesis_agents=1,y_column='Y',
                         evaluation='{}',trials=1,waves=2,combination_plan=argv[argv.index('--combination-plan')+1])
    run=tmp_path/'web-run';run.mkdir()
    snapshot=freeze(args,run,{})
    assert snapshot['ml_configuration_policy']['version']=='agent_selected_ml_v2'
    assert xai.request(snapshot,0)['methods']==['shap']
    assert xai.request(snapshot,1)['methods']==['lime']
    assert snapshot['combination_plan']['total_loops']==2
    for item in snapshot['specialist_xai_policy']['skills'].values():
        assert 'Synthetic instructions' in item['source_text']
        assert 'Synthetic instructions' in item['prompt']['system_prompt']
        assert 'ARCHIVED' not in json.dumps(item)
