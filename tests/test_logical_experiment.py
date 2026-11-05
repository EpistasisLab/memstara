"""64 original combinations, three attempts, no models or production DB calls."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import asyncio
from unittest.mock import AsyncMock,MagicMock

from memstara.logical_experiment import report_index, lineage
from memstara.specialist_explanation import assemble
from memstara.rebuild_report import rebuild, recovered


def save_report(root,config,loop,text=None):
    directory=root/'explanation_io';directory.mkdir(exist_ok=True)
    provenance={'status':'completed','loop':loop,'expert':'hiv','task_ids':[loop]}
    record={'run_tag':config['run_tag'],'config_hash':config['config_hash'],'loop':loop,
        'execution':{'status':'completed'},'output':text or f'Explanation for original combination {loop}.',
        'provenance':provenance}
    path=directory/f'output-{loop}.json'
    path.write_text(json.dumps(record))
    receipt={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (directory/f'loop-{loop}.json').write_text(json.dumps({'receipt':receipt,'summary':{**provenance,'output':receipt}}))


@pytest.fixture
def experiment(tmp_path,monkeypatch):
    outputs=tmp_path/'outputs';runs=outputs/'runs';runs.mkdir(parents=True)
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR',str(outputs))
    configs=[];directories=[]
    for i,(start,end) in enumerate([(1,28),(29,49),(50,64)]):
        root=runs/f'attempt-{i}';root.mkdir()
        config={'run_tag':f'run-{i}','pipeline_id':'p','pipeline_name':'test-hiv-1',
            'dataset_sha256':'same-dataset','y_column':'Y','config_hash':f'frozen-{i}',
            'combination_plan':{'total_loops':64},'knowledge_hashes':{'source':'same'},
            'specialist_explanation_policy':{'version':'scoped_explanation_v1'}}
        if i:config['retry_selection']={'source_run_tag':f'run-{i-1}','loops':list(range(start,end+1))}
        (root/'config.json').write_text(json.dumps(config))
        (root/'control_record.json').write_text(json.dumps({'run_tag':config['run_tag'],'pipeline_id':'p','exit_code':1}))
        (root/'iteration_outcomes.json').write_text(json.dumps({str(n):{'outcome':'completed'} for n in range(start,end+1)}))
        for n in range(start,end+1):save_report(root,config,n)
        configs.append(config);directories.append(root)
    root=directories[-1]
    failure={'status':'failed','code':'agent_execution_failed','stage':'report','loop':None,
             'message':'Old generic agent error'}
    (root/'pipeline_failure.json').write_text(json.dumps(failure))
    (root/'pipeline_status.json').write_text(json.dumps(failure))
    (root/'report_status.json').write_text(json.dumps({'status':'failed','error':'Missing per-condition Explanation reports'}))
    (root/'report.md').write_text('Previous partial report')
    return configs,directories


def test_64_reports_are_indexed_under_one_experiment_without_moving_originals(experiment):
    configs,roots=experiment
    originals={path:path.read_bytes() for root in roots for path in root.rglob('*.json')}
    index,reports=report_index(configs[-1],roots[-1])
    assert index['id']=='run-0' and index['name']=='test-hiv-1'
    assert index['status']=='completed' and index['missing_loops']==[]
    assert list(reports)==list(range(1,65)) and len(index['attempts'])==3
    assert [reports[n]['run_tag'] for n in [1,28,29,49,50,64]]==['run-0','run-0','run-1','run-1','run-2','run-2']
    text,entry=assemble(configs[-1],roots[-1]/'explanation_io')
    assert entry['status']=='completed' and len(entry['specialist_explanation']['reports'])==64
    assert text.count('Explanation for original combination ')==64
    assert all(path.read_bytes()==value for path,value in originals.items())
    assert (roots[-1]/'experiment_index.json').is_file()


def test_report_only_recovery_retains_original_failure_and_costs(experiment):
    from memstara.pipeline.failures import visible_failure
    _,roots=experiment;root=roots[-1]
    (root/'cost_ledger.jsonl').write_text('unchanged request receipts')
    before={name:(root/name).read_bytes() for name in ('pipeline_failure.json','control_record.json','cost_ledger.jsonl')}
    assert visible_failure(root)['code']=='final_report_assembly_failed'
    result=rebuild(root)
    assert result['combinations']==64 and result['model_calls']==result['analyses_recomputed']==0
    assert recovered(root) and visible_failure(root) is None
    assert json.loads((root/'pipeline_status.json').read_text())['status']=='completed'
    assert json.loads((root/'control_record.json').read_text())['exit_code']==1
    assert (root/'report-before-rebuild.json').exists()
    assert all((root/name).read_bytes()==value for name,value in before.items())
    assert rebuild(root)['combinations']==64  # Idempotent, no re-execution.
    receipt=json.loads((root/'experiment_index.json').read_text())['reports'][0]['receipt']
    Path(receipt['path']).write_text('tampered after recovery')
    assert not recovered(root)


@pytest.mark.parametrize('key,value',[('pipeline_id','different'),('dataset_sha256','different'),
    ('y_column','different'),('knowledge_hashes',{'other':'hash'}),('combination_plan',{'total_loops':32})])
def test_different_study_or_schedule_is_not_silently_merged(experiment,key,value):
    configs,roots=experiment
    parent=json.loads((roots[1]/'config.json').read_text());parent[key]=value
    (roots[1]/'config.json').write_text(json.dumps(parent))
    with pytest.raises(ValueError,match='different study|frozen schedule'):lineage(configs[-1],roots[-1])


def test_missing_output_does_not_become_a_successful_rebuild(experiment):
    _,roots=experiment;root=roots[-1]
    before=(root/'pipeline_status.json').read_bytes()
    (roots[0]/'explanation_io/loop-1.json').unlink()
    with pytest.raises(ValueError,match='missing for original combinations: 1'):rebuild(root)
    assert not (root/'report_rebuild.json').exists()
    assert (root/'pipeline_status.json').read_bytes()==before


def test_cyclic_history_and_unknown_sources_are_refused(experiment):
    configs,roots=experiment
    cfg=json.loads((roots[0]/'config.json').read_text())
    cfg['retry_selection']={'source_run_tag':'run-2','loops':list(range(1,29))}
    (roots[0]/'config.json').write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='cyclic'):lineage(configs[-1],roots[-1])
    changed=copy.deepcopy(configs[-1]);changed['retry_selection']['source_run_tag']='missing'
    with pytest.raises(ValueError,match='missing or ambiguous'):lineage(changed,roots[-1])


def test_same_pipeline_name_without_explicit_continuation_remains_a_new_experiment(experiment):
    configs,roots=experiment
    fresh=copy.deepcopy(configs[-1]);fresh.pop('retry_selection')
    index,_=report_index(fresh,roots[-1])
    assert index['id']=='run-2' and len(index['attempts'])==1
    assert index['missing_loops']==list(range(1,50))


def test_receipts_cannot_be_redirected_to_a_different_attempt(experiment):
    configs,roots=experiment
    index=roots[1]/'explanation_io/loop-29.json'
    item=json.loads(index.read_text())
    item['receipt']['path']=str(roots[0]/'explanation_io/output-1.json')
    index.write_text(json.dumps(item))
    with pytest.raises(ValueError,match='escapes its original execution'):
        report_index(configs[-1],roots[-1])


def test_interrupted_report_publication_is_retryable_without_rerunning_analyses(experiment,monkeypatch):
    import memstara.rebuild_report as recovery
    _,roots=experiment;root=roots[-1]
    actual=recovery.atomic_json
    def fail_receipt(path,value,**kwargs):
        if path.name=='report_rebuild.json':raise OSError('simulated publication interruption')
        actual(path,value,**kwargs)
    monkeypatch.setattr(recovery,'atomic_json',fail_receipt)
    with pytest.raises(OSError):rebuild(root)
    assert not recovered(root)
    monkeypatch.setattr(recovery,'atomic_json',actual)
    assert rebuild(root)['model_calls']==0 and recovered(root)


def test_registry_recovery_updates_only_report_status_and_verified_artifacts(experiment,monkeypatch):
    import asyncpg
    from memstara.rebuild_report import publish
    _,roots=experiment;root=roots[-1]
    rebuild(root)
    connection=AsyncMock();connection.transaction=MagicMock(return_value=AsyncMock())
    connection.fetchval.return_value='run-2'
    monkeypatch.setenv('MEMSTARA_DATABASE_URL','postgresql://synthetic')
    monkeypatch.setattr(asyncpg,'connect',AsyncMock(return_value=connection))
    asyncio.run(publish(root))
    assert 'configuration=$4::jsonb' in connection.fetchval.call_args.args[0]
    assert connection.execute.await_count==5
    assert all('memstara_execution_artifacts' in call.args[0] for call in connection.execute.call_args_list)
    assert all(call.args[1]=='run-2' for call in connection.execute.call_args_list)
    assert connection.close.await_count==1


def test_malformed_receipts_fail_with_a_reviewable_error_and_do_not_break_status_polling(experiment):
    _,roots=experiment;root=roots[-1]
    (root/'explanation_io/loop-50.json').write_text('{}')
    with pytest.raises(ValueError,match='metadata is incomplete or invalid'):rebuild(root)
    (root/'report_rebuild.json').write_text('[]')
    (root/'pipeline_status.json').write_text('[]')
    assert not recovered(root)
