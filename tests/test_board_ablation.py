import asyncio
import uuid
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


@pytest.mark.parametrize("existing_command", [None, "command", "old-command"])
def test_ablation_never_hydrates_persisted_knowledge_servers(monkeypatch, existing_command):
    pytest.importorskip("motoro", reason="Requires the installed Motoro runtime")
    from memstara.pipeline import board
    from memstara import evaluation
    from motoro.services import mcp_service
    from unittest.mock import create_autospec

    server_id = uuid.uuid4()
    server = SimpleNamespace(id=server_id, command=existing_command)
    seen = []

    class Registry:
        servers = {}
        async def disconnect_all(self):
            pass

    async def get(name):
        assert name == 'memstara-data', "OKF must never be looked up or connected"
        return server if existing_command is not None else None

    async def connected(*args, **kwargs):
        seen.append((args, kwargs))
        kwargs['registry'].servers[server_id] = SimpleNamespace(error=None)
        return server

    register = create_autospec(board.register_server, side_effect=connected)
    update = create_autospec(board.update_server, side_effect=connected)
    reconnect = create_autospec(mcp_service.reconnect_server, side_effect=connected)
    monkeypatch.setattr(evaluation, 'active_plan', lambda: PLAN)
    monkeypatch.setattr(board, 'MCPServerRegistry', Registry)
    monkeypatch.setattr(board, 'launch_table', lambda: [('okf', 'unused'), ('memstara-data', 'command')])
    monkeypatch.setattr(board, 'get_server_by_name', get)
    monkeypatch.setattr(board, 'register_server', register)
    monkeypatch.setattr(board, 'update_server', update)
    monkeypatch.setattr(mcp_service, 'reconnect_server', reconnect)
    async def forbidden(**kwargs):
        raise AssertionError('Persistent server hydration must not occur')
    monkeypatch.setattr(board, 'hydrate_registry', forbidden)
    registry = asyncio.run(board.setup_tools())
    assert set(registry.servers) == {server_id}
    assert len(seen) == 1
    if existing_command is None:
        register.assert_awaited_once_with(name='memstara-data', transport='stdio', command='command', registry=registry)
    elif existing_command == 'command':
        reconnect.assert_awaited_once_with(server_id, registry=registry)
    else:
        update.assert_awaited_once_with(server_id, command='command', registry=registry)
