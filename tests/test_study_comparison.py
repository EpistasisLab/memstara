import hashlib
import json
import pytest
from memstara.study_comparison import resolve_comparison


@pytest.fixture
def study(tmp_path,monkeypatch):
    dataset=tmp_path/'data.csv';dataset.write_text('Y,LAB__CD4,MED__BIKTARVY,signal\n0,1,0,1\n1,2,1,0\n')
    policy=tmp_path/'study_comparison_policy.json'
    policy.write_text(json.dumps(dict(version=1,target='Y',dataset_sha256=hashlib.sha256(dataset.read_bytes()).hexdigest(),
        baseline_columns=['LAB__CD4','MED__BIKTARVY'],timing_status='unverified',decision='User-approved exploratory baseline')))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR',str(tmp_path))
    monkeypatch.delenv('MEMSTARA_COMPARISON_POLICY_PATH',raising=False)
    return dataset,policy


def test_local_policy_never_adds_predictors(study, monkeypatch):
    dataset,path=study
    for explicit_path in (False, True):
        if explicit_path:
            monkeypatch.setenv('MEMSTARA_COMPARISON_POLICY_PATH',str(path))
        frozen=resolve_comparison([], 'Y', dataset)
        assert frozen['baseline_columns']==[]
        assert frozen['baseline_source']=='prevalence_reference'
        assert 'study_policy_sha256' not in frozen
        assert resolve_comparison(['signal'],'Y',dataset)['baseline_columns']==['signal']
    # Obsolete policy files do not govern new runs, even if malformed.
    path.write_text('invalid historical policy')
    assert resolve_comparison([], 'Y', dataset)['baseline_columns']==[]


def test_explicit_baseline_still_validated(study):
    dataset,_=study
    for columns in (['missing'], ['Y']):
        with pytest.raises(ValueError): resolve_comparison(columns,'Y',dataset)


def test_snapshot_freezes_policy_with_run_hash(study,monkeypatch,tmp_path):
    from types import SimpleNamespace
    from memstara.pipeline import snapshot
    dataset,path=study
    dataset.write_text('Y,LAB__CD4,MED__BIKTARVY,signal,extra\n'+
                       ''.join(f'{i%2},{i},{i%2},{i%3},{i%5}\n' for i in range(40)))
    policy=json.loads(path.read_text());policy['dataset_sha256']=hashlib.sha256(dataset.read_bytes()).hexdigest()
    path.write_text(json.dumps(policy))
    monkeypatch.setenv('MEMSTARA_DATASET_PATH',str(dataset))
    monkeypatch.setattr(snapshot,'load_prompt',lambda *args:{'goal':'test', 'system_prompt':'test prompt'})
    args=SimpleNamespace(evaluation='{}',y_column='Y',baseline_columns='[]',run_tag='fixture',
        question='',hypothesis_agents=1,trials=1,waves=1)
    run_dir=tmp_path/'run';run_dir.mkdir()
    frozen=snapshot.freeze(args,run_dir,{})
    assert frozen['comparison_policy']['baseline_source']=='prevalence_reference'
    assert frozen['comparison_policy']['baseline_columns']==[]
    assert json.loads((run_dir/'config.json').read_text())['comparison_policy']==frozen['comparison_policy']
