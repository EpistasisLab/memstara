import asyncio
from types import SimpleNamespace
import pytest
from memstara.pipeline.ablation import filter_tools
from memstara.pipeline.question_contract import make_contract, question_text, validate_saved, validate_mapping

PLAN={'y_column':'Y','hypothesis_policy':{'question_contract':'fixed_target_v1'},
      'recovery_policy':{'version':'artifact_checked_v1'},'knowledge_policy':{'mode':'no_okf'}}


def test_no_okf_contract_keeps_target_and_mapping_without_fake_sources():
    contract=make_contract({'predictor_concepts':['age'],'rationale':'Age may carry predictive information.',
                            'source_ids':[],'okf_tags':[]},PLAN)
    assert contract['evidence_mode']=='no_okf' and contract['source_ids']==[]
    validate_saved(contract,question_text(contract),PLAN)
    validate_mapping([{'concept':'age','column':'AGE','source_id':'','rationale':'Recorded age'}],contract,['AGE'],[])
    with pytest.raises(ValueError):
        make_contract({'predictor_concepts':['age'],'rationale':'Reason','source_ids':['fabricated']},PLAN)
    with pytest.raises(ValueError):
        make_contract({'predictor_concepts':['age'],'rationale':'Reason','source_ids':[]},
                      {**PLAN,'knowledge_policy':{'mode':'okf'}})


def test_normal_tools_unchanged_ablation_removes_all_knowledge_surface():
    tools=[{'server':'okf','tool_name':'get_concept'}, {'server':'other','tool_name':'okf_read'},
           {'server':'memstara-data','tool_name':'describe_dataset'}]
    assert filter_tools(tools,{})==tools
    assert filter_tools(tools,PLAN)==tools[2:]


def test_ablation_never_hydrates_persisted_knowledge_servers(monkeypatch):
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.pipeline import board
    from memstara import evaluation
    seen=[]
    class Registry:
        async def register(self,**kw):
            seen.append(kw['name']);return SimpleNamespace(error=None)
        async def disconnect_all(self):pass
    monkeypatch.setattr(evaluation,'active_plan',lambda:PLAN)
    monkeypatch.setattr(board,'MCPServerRegistry',Registry)
    monkeypatch.setattr(board,'launch_table',lambda:[('okf','unused'),('memstara-data','command')])
    async def forbidden(**kw):raise AssertionError('Persistent server hydration must not occur')
    monkeypatch.setattr(board,'hydrate_registry',forbidden)
    asyncio.run(board.setup_tools())
    assert seen==['memstara-data']
