"""Offline hybrid protocol: real mapping/receipts, no provider or private data."""
import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from memstara.combinations import build_plan
from memstara.pipeline import hybrid, no_knowledge
from memstara.pipeline import feature_selection as fs
from memstara.pipeline.question_contract import make_contract, question_text, hypothesis_text, validate_saved


@pytest.fixture
def protocol(tmp_path, monkeypatch):
    schedule=build_plan({'hypothesis':[hybrid.SKILL], 'data':['data_training_heavy'],
        'ml':['ml_logistic_regression'], 'interpreter':['shared-shap'], 'report':['shared-hiv']},1)
    plan={'books':{'hypothesis':[hybrid.SKILL]}, 'combination_plan':schedule,
          'run_tag':'hybrid-test','pipeline_id':'p','config_hash':'frozen','dataset_sha256':'synthetic',
          'y_column':'Y','trials':1,'waves':1,'hypotheses':1,
          'evaluation':{'engine':'logistic_regression','seed':42,'test_size':.3,'folds':2,'replicates':1,'search_trials':1},
          'knowledge_mode':'okf','knowledge_policy':{'mode':'okf'},'knowledge_hashes':{'source.md':'hash'},
          'no_knowledge_isolation':no_knowledge.VERSION,
          'comparison_policy':{'baseline_columns':[]},
          'hypothesis_policy':{'question_contract':'fixed_target_v1','version':'knowledge_only_v1'},
          'question_feasibility_policy':'explicit_columns_v1','recovery_policy':{'version':'artifact_checked_v1'},
          'feature_context':{'features':[{'column':f'x{i}','meaning':'Recorded measurement'} for i in range(8)]}}
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG',raising=False)
    hybrid.freeze_policy(plan)
    plan['feature_selection_policy']=fs.freeze(plan)
    path=tmp_path/'config.json'
    path.write_text(json.dumps(plan))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG',str(path))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR',str(tmp_path))
    monkeypatch.setattr('memstara.evaluation.active_plan',lambda:plan)
    return plan,tmp_path


def proposal():
    return {'predictor_concepts':[f'measure {i}' for i in range(4)],'rationale':'General model knowledge about measured physiology.',
            'source_ids':[],'okf_tags':[], 'proposed_mapping':[
                {'concept':f'measure {i}','column':f'x{i}','source_id':'','rationale':'Recorded eligible measurement'} for i in range(4)]}


def expanded(plan):
    hybrid.save_baseline(plan,0,proposal())
    candidate=proposal()
    candidate['predictor_concepts'].append('additional measure')
    candidate['proposed_mapping'].append({'concept':'additional measure','column':'x4','source_id':'source',
                                        'rationale':'A concrete source-supported complementary measurement'})
    candidate.update(source_ids=['source'],okf_tags=['mechanisms'],origin_wave=0)
    return candidate


def test_baseline_freezes_before_retrieval_and_cannot_change_on_retry(protocol):
    plan,root=protocol
    first=hybrid.save_baseline(plan,0,proposal())
    assert first==hybrid.save_baseline(plan,0,proposal())
    assert first['contract']['evidence_mode']=='no_okf'
    changed=proposal();changed['rationale']='A different candidate'
    with pytest.raises(ValueError,match='immutable'):
        hybrid.save_baseline(plan,0,changed)
    record=json.loads((root/'hybrid_baseline_0.json').read_text());record['columns'][0]='x7'
    (root/'hybrid_baseline_0.json').write_text(json.dumps(record))
    with pytest.raises(ValueError,match='checksum'):
        hybrid.read_baseline(plan,0)


def test_hybrid_contract_keeps_general_and_graph_provenance_separate(protocol):
    plan,_=protocol
    candidate=expanded(plan)
    contract=make_contract(candidate,plan)
    assert contract['evidence_mode']=='hybrid'
    assert contract['hybrid']['baseline_columns']==[f'x{i}' for i in range(4)]
    assert contract['hybrid']['augmentation_columns']==['x4']
    assert validate_saved(contract,question_text(contract),plan)==contract
    for change in ['baseline_source','baseline_rationale','unrooted_addition','invented_column','duplicate_column']:
        invalid=copy.deepcopy(candidate)
        if change=='baseline_source':invalid['proposed_mapping'][0]['source_id']='source'
        elif change=='baseline_rationale':invalid['proposed_mapping'][0]['rationale']='Rewritten after graph exposure'
        elif change=='unrooted_addition':invalid['proposed_mapping'][-1]['source_id']=''
        elif change=='invented_column':invalid['proposed_mapping'][-1]['column']='absent'
        else:invalid['proposed_mapping'][-1]['column']='x0'
        with pytest.raises(ValueError):make_contract(invalid,plan)


def test_hybrid_can_keep_baseline_when_no_supported_addition_exists(protocol):
    plan,_=protocol
    hybrid.save_baseline(plan,0,proposal())
    contract=make_contract({**proposal(),'origin_wave':0},plan)
    assert contract['hybrid']['augmentation_columns']==[] and contract['source_ids']==[]
    ordinary={**plan,'books':{'hypothesis':['hiv-okf-whole-graph']},'combination_plan':None}
    ordinary.pop('feature_selection_policy')
    with pytest.raises(ValueError):make_contract({**proposal(),'origin_wave':0},ordinary)


def test_prepare_baseline_reuses_receipt_without_another_agent_call(protocol,monkeypatch):
    plan,_=protocol
    create=AsyncMock(return_value=NS(id='baseline-agent'))
    monkeypatch.setattr('memstara.pipeline.core._ensure_agent',create)
    monkeypatch.setattr('memstara.stage_models.deployment_profiles',lambda:{})
    monkeypatch.setattr('memstara.stage_models.for_stage',lambda *args:{'provider':'openai','model':'synthetic'})
    seen=[]
    async def invoke(agent,prompt,**kwargs):
        assert hybrid.BASE_CALL.get()
        seen.append(kwargs['tools'])
        hybrid.save_baseline(plan,0,proposal())
    tools=[{'tool_name':name} for name in [*hybrid.BASE_TOOLS,'okf_read','read_results']]
    first=asyncio.run(hybrid.prepare_baseline(plan,0,None,tools,invoke))
    assert {t['tool_name'] for t in seen[0]}==hybrid.BASE_TOOLS
    assert first==asyncio.run(hybrid.prepare_baseline(plan,0,None,tools,invoke))
    assert len(seen)==1 and not hybrid.BASE_CALL.get()
    assert 'okf_read' not in create.call_args.kwargs['system_prompt']


def test_actual_baseline_call_receives_no_graph_metadata_or_retrieval_tools(protocol, monkeypatch):
    from memstara.pipeline import board
    plan, _ = protocol
    plan['research_profile'] = {'configuration': {
        'target': {'column': 'Y', 'description': 'Synthetic target'},
        'knowledge_mode': 'okf', 'knowledge_path': '/private/okf'}}
    monkeypatch.setattr(board, 'require_ownership', lambda: None)
    monkeypatch.setattr(board, '_TRACE_DIR', None)
    monkeypatch.setattr(board, '_CALLS', [])
    monkeypatch.setattr(board, '_trace_one', AsyncMock())
    monkeypatch.setattr('memstara.pipeline.reporting.show_console_summary', AsyncMock())
    monkeypatch.setattr('memstara.stage_models.call_overrides', lambda *args: {})
    create = AsyncMock(return_value=NS(id='synthetic', owner_id='synthetic'))
    execute = AsyncMock(return_value=NS(status='completed', error=None, output='done'))
    monkeypatch.setattr(board, 'create_run', create)
    monkeypatch.setattr(board, 'execute_run', execute)
    token = board._CURRENT_LOOP.set(1)
    baseline = hybrid.BASE_CALL.set(True)
    try:
        tools = [{'server': 'memstara-blackboard', 'tool_name': name}
                 for name in (*hybrid.BASE_TOOLS, 'okf_read', 'read_results', 'read_context_payload')]
        _, entry = asyncio.run(board._call_agent_uncontrolled('agent', 'Generate the baseline.',
                               tools=tools, registry=None, stage='question-hybrid-baseline'))
    finally:
        hybrid.BASE_CALL.reset(baseline)
        board._CURRENT_LOOP.reset(token)
    assert set(entry['allowed_tools']) == hybrid.BASE_TOOLS
    assert entry['knowledge_condition'] == 'no_okf' and entry['hybrid_phase'] == 'isolated_baseline'
    assert {t['tool_name'] for t in execute.call_args.kwargs['available_tools']} == hybrid.BASE_TOOLS
    user_input = create.call_args.kwargs['user_input']
    assert '/private/okf' not in user_input and 'No OKF corpus is attached' in user_input
    assert plan['research_profile']['configuration']['knowledge_path'] == '/private/okf'


def test_mcp_proposal_and_task_persist_verified_mixed_provenance(protocol,monkeypatch):
    from memstara.mcp_servers import blackboard as bb
    plan,_=protocol
    candidate=expanded(plan)
    contract=make_contract(candidate,plan)
    monkeypatch.setattr(bb,'_pipeline_run',lambda:plan['run_tag'])
    monkeypatch.setattr('memstara.pipeline.question_repair.preflight_mapping',AsyncMock(return_value=None))
    conn=AsyncMock();conn.transaction=MagicMock(return_value=AsyncMock());conn.fetch.return_value=[];conn.fetchval.return_value=7
    monkeypatch.setattr(bb.asyncpg,'connect',AsyncMock(return_value=conn))
    reply=json.loads(asyncio.run(bb.propose_questions([candidate],plan['run_tag'],0)))
    assert reply['added'] and not reply['rejected'],reply
    conn.fetchrow.side_effect=[{'text':question_text(contract),'question_contract':contract,
                               'origin_run':plan['run_tag'],'claimed_run':plan['run_tag']},None]
    reply=json.loads(asyncio.run(bb.create_task(plan['run_tag'],0,question_text(contract),hypothesis_text(contract),
        [r['column'] for r in candidate['proposed_mapping']],'Y',['source'],7,candidate['proposed_mapping'])))
    assert reply.get('task_id')==7,reply
    saved=json.loads(conn.fetchval.call_args.args[-1])
    assert saved['hybrid']==contract['hybrid']
    assert saved['feature_mapping'][0]['source_id']=='' and saved['feature_mapping'][-1]['source_id']=='source'


def test_candidate_choice_never_reads_held_out_results():
    from memstara.hybrid_evaluation import choose
    candidates=[{'id':'baseline','training_cv_auroc':[.7],'auc':.1},
                {'id':'expanded','training_cv_auroc':[.71],'auc':.99}]
    assert choose(candidates)=='expanded'
    candidates[0]['auc']=1; candidates[1]['auc']=0
    assert choose(candidates)=='expanded'
    candidates[1]['training_cv_auroc']=[.7]
    assert choose(candidates)=='baseline'
    candidates[1]['training_cv_auroc']=[None]
    with pytest.raises(ValueError):choose(candidates)


def test_real_synthetic_paired_evaluation_selects_and_preserves_replay_bundle(protocol,monkeypatch):
    from memstara import evaluation
    from memstara.hybrid_evaluation import score_hybrid,validate_receipt
    from memstara.reproducibility import digest
    plan,root=protocol
    contract=make_contract(expanded(plan),plan)
    rng=np.random.default_rng(123)
    frame=pd.DataFrame({f'x{i}':rng.normal(size=180) for i in range(5)})
    frame['Y']=(frame.x4>0).astype(int)
    path=root/'subset.csv';frame.to_csv(path,index=False)
    context={'hybrid':contract['hybrid'],'trial':0,'config_hash':plan['config_hash'],'target':'Y',
        'baseline_columns':[],'hypothesis_columns':list(frame.columns[:-1]),'groups':{},
        'dataset_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix('.comparison.json').write_text(json.dumps(context))
    configuration={'parameters':{'max_iter':200,'class_weight':'balanced'},'scale_numeric':False,'threshold':.5}
    result=score_hybrid(path,'Y',plan['evaluation'],plan,configuration=configuration)
    assert result['hybrid_selection']['selected_candidate']=='expanded'
    assert result['auc']>.9
    runs=[v['replicates'][0] for v in result['comparison']['variants']]
    assert len({(r['seed'],r['train_split_id'],r['split_id']) for r in runs})==1
    receipt=result['hybrid_selection']
    assert validate_receipt(result['features'],contract['hybrid'],context['hypothesis_columns'],receipt)==result['features']
    bad=copy.deepcopy(receipt);bad['selected_candidate']='baseline'
    with pytest.raises(ValueError):validate_receipt(result['features'],contract['hybrid'],context['hypothesis_columns'],bad)
    replay=result['evaluation']['reproducibility']
    assert digest(__import__('pathlib').Path(replay['bundle_path'])/'manifest.json')==replay['manifest_sha256']
    saved=json.loads((__import__('pathlib').Path(replay['bundle_path'])/'hybrid-selection.json').read_text())
    assert saved['selection']==receipt


def test_real_worker_runs_the_hybrid_and_reuses_the_accepted_result(protocol):
    from memstara import paired_ml,ml_configuration as ml
    plan,root=protocol
    contract=make_contract(expanded(plan),plan)
    rng=np.random.default_rng(17)
    frame=pd.DataFrame({f'x{i}':rng.normal(size=120) for i in range(5)})
    frame['Y']=(frame.x4>0).astype(int)
    path=root/'worker.csv';frame.to_csv(path,index=False)
    handoff={'hybrid':contract['hybrid'],'trial':0,'config_hash':plan['config_hash'],'target':'Y',
        'baseline_columns':[],'hypothesis_columns':list(frame.columns[:-1]),'groups':{},
        'dataset_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix('.comparison.json').write_text(json.dumps(handoff))
    plan['ml_configuration_policy']=ml.policy()
    snapshot=ml.for_dataset(plan,path)
    proposed=ml.context(snapshot,plan['evaluation'])['proposal_template']
    proposed.update(folds=2,rationale='Fixed settings for an offline synthetic paired comparison')
    result=paired_ml.execute(path,'Y',plan['evaluation'],snapshot,proposed)
    assert result.get('status')!='failed',result
    assert result['hybrid_selection']['selected_candidate']=='expanded'
    assert 'hybrid_selection' in result['model_results']['logistic_regression']
    assert paired_ml.execute(path,'Y',plan['evaluation'],snapshot,proposed)==result
