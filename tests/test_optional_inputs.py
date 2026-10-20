"""All four availability modes, planning handoffs and fail-before-inference guards."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from memstara.research_inputs import register, prepare, activate


@pytest.fixture
def example(tmp_path, monkeypatch):
    pytest.importorskip('motoro')
    from memstara.paths import REPO_ROOT
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path / 'registry'))
    return json.loads((REPO_ROOT / 'examples/research-inputs/research.json').read_text())


@pytest.mark.parametrize('knowledge_mode', ['okf', 'llm_only'])
@pytest.mark.parametrize('data_mode', ['dataset', 'proposal'])
def test_all_four_profiles_prepare_without_unselected_input_access(example, monkeypatch, knowledge_mode, data_mode):
    config = {**example, 'knowledge_mode': knowledge_mode, 'data_mode': data_mode}
    if knowledge_mode == 'llm_only':
        config['knowledge_path'] = '/absent-do-not-access/corpus'
    if data_mode == 'proposal':
        config['dataset_path'] = '/absent-do-not-access/data.csv'
        config['target'] = {'description': 'Investigate simulated baseline predictors of a future toy event'}
    record = register(config)
    assert record['input_checks_passed']
    profile = prepare(record['id'])
    root = Path(profile['root'])
    assert (root / 'dataset.csv').exists() == (data_mode == 'dataset')
    assert (root / 'okf').exists() == (knowledge_mode == 'okf')
    with monkeypatch.context() as context:
        context.setattr(os, 'environ', dict(os.environ))
        activate(profile)
        assert bool(os.environ['MEMSTARA_DATASET_PATH']) == (data_mode == 'dataset')
        assert bool(os.environ['AGENTIC_OKF_BUNDLE_DIR']) == (knowledge_mode == 'okf')


@pytest.mark.parametrize('knowledge_mode', ['okf', 'llm_only'])
def test_no_csv_full_workflow_records_six_handoffs_and_no_empirical_metrics(example, tmp_path, monkeypatch, knowledge_mode):
    from memstara.pipeline.proposal import run, STAGES
    for role in ('QUESTION', 'HYPOTHESIS', 'DATA', 'ML', 'INTERPRETATION', 'EXPLANATION'):
        monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER', 'openai')
        monkeypatch.setenv(f'MEMSTARA_{role}_MODEL', 'fixture')
    config = {**example, 'data_mode': 'proposal', 'knowledge_mode': knowledge_mode}
    record = register(config)
    profile = prepare(record['id'])
    args = SimpleNamespace(resume=False, research_profile=profile,
        research_input_id=record['id'], research_objective=config['target']['description'],
        ablate_okf=knowledge_mode == 'llm_only', skill='', stage_models={}, combination_plan='',
        run_tag='proposal-fixture', pipeline_id='', pipeline_name='Synthetic proposal',
        provider='openai', model='fixture', waves=1,
        playbook_hypothesis='hypothesis_research',playbook_data='',playbook_ml='',
        playbook_interpreter='',playbook_explanation='report_clinical_explanations')
    requests=[]
    async def invoke(profile, system, payload):
        requests.append(payload)
        ids = [row['id'] for row in payload['evidence']]
        return json.dumps({'summary':'Synthetic research plan, not observed findings',
                           'items':['Proposed baseline pressure','Proposed pulse','Proposed activity','Proposed marker'],
                           'source_ids':ids}), {'input_tokens':1,'output_tokens':1}
    async def persist(*args, **kwargs):
        assert kwargs['evidence'] is False
    root=tmp_path / 'run'; root.mkdir()
    with monkeypatch.context() as context:
        context.setattr(os,'environ',dict(os.environ))
        activate(profile)
        assert asyncio.run(run(args,root,invoke=invoke,persist=persist)) == 0
    assert len(requests)==6
    assert [len(r['prior_stages']) for r in requests]==list(range(6))
    state=json.loads((root/'pipeline_status.json').read_text())
    assert state['status']=='completed' and state['mode']=='proposal'
    assert state['empirical_evaluation']['metrics'] is None
    calls=json.loads((root/'execution.json').read_text())['calls']
    assert [c['stage'] for c in calls]==list(STAGES)
    assert all(c['computation_status']=='not_executed' for c in calls)
    assert ('No external knowledge source' in (root/'report.md').read_text()) == (knowledge_mode=='llm_only')
    assert not (Path(profile['root'])/'derived/matcher_catalog.json').exists()
    assert (root/'proposal_io/loop-0001/report.output.json').exists()


def test_no_input_request_requires_objective_and_preserves_modes(monkeypatch):
    from memstara.control.request import build_argv
    from memstara import stage_models
    for role in ('QUESTION', 'HYPOTHESIS', 'DATA', 'ML', 'INTERPRETATION', 'EXPLANATION'):
        monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER', 'openai')
        monkeypatch.setenv(f'MEMSTARA_{role}_MODEL', 'fixture')
    monkeypatch.setattr(stage_models,'resolve_run_profiles',lambda _: {})
    request={'knowledge_mode':'llm_only','data_mode':'proposal'}
    with pytest.raises(ValueError,match='research objective'):
        build_argv(request,[])
    argv=build_argv({**request,'research_objective':'Investigate a toy future event'},[])
    assert argv[argv.index('--data-mode')+1]=='proposal'
    assert argv[argv.index('--knowledge-mode')+1]=='llm_only'


@pytest.mark.parametrize('text', [
    '{"summary":"Claim","items":["Plan"],"source_ids":["invented-paper"]}',
    '{"summary":"Claim","items":["Plan"],"source_ids":[],"AUROC":0.99}',
    '{"summary":"","items":[],"source_ids":[]}',
])
def test_unfounded_structured_evidence_is_rejected(text):
    from memstara.pipeline.proposal import validate_output
    with pytest.raises(ValueError):
        validate_output(text,'report',set())
