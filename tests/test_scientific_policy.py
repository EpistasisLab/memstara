import asyncio
import json
from unittest.mock import AsyncMock

import pytest
pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")

from memstara.pipeline.scientific_policy import check_primary_tools
from memstara.pipeline import board
from memstara.mcp_servers import blackboard as bb


@pytest.mark.parametrize('stage', ['question2-1', 'hypothesis1'])
@pytest.mark.parametrize('tool', ['read_results', 'read_questions', 'read_board', 'train_and_score'])
def test_primary_turns_reject_feedback_tools(stage, tool):
    with pytest.raises(ValueError, match='boundary'):
        check_primary_tools(stage, [{'tool_name': tool}])


def test_reporting_keeps_result_access():
    check_primary_tools('report', [{'tool_name': 'read_results'}])


def test_primary_catalog_fails_closed_for_legacy_runs(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {'run_tag': 'old'})
    connect = AsyncMock()
    monkeypatch.setattr(bb.asyncpg, 'connect', connect)
    assert 'error' in json.loads(asyncio.run(bb.read_question_catalog()))
    connect.assert_not_called()


def test_catalog_excludes_scores_rationales_and_old_runs(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {
        'run_tag': 'primary', 'hypothesis_policy': {'version': 'knowledge_only_v1'}})
    conn = AsyncMock()
    conn.fetch.return_value = [{'question_id': 1, 'text': 'Knowledge question', 'okf_tags': '["path"]',
                                'best_auc': .99, 'rationale': 'reuse successful features'}]
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    data = json.loads(asyncio.run(bb.read_question_catalog()))
    assert set(data['questions'][0]) == {'question_id', 'text', 'okf_tags'}
    query, tag, limit = conn.fetch.call_args.args
    assert 'origin_run=$1' in query and tag == 'primary' and limit == 200
    assert "status <> 'cleared'" in query
    conn.close.assert_awaited_once()


def test_later_waves_do_not_request_ml_feedback(monkeypatch):
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': []}))
    call = AsyncMock()
    monkeypatch.setattr(board, 'call_agent', call)
    asyncio.run(board.questions_for_wave(None, {'hypothesis': 'h'}, {'question': []},
                                        run_tag='new', wave=3, want=1))
    prompt = call.call_args.args[1]
    assert 'Call read_results' not in prompt
    assert 'primary, knowledge-driven' in prompt


def test_real_namespaced_tool_metadata_is_accepted():
    check_primary_tools('question1-1', [{'server': 'memstara-blackboard',
                        'name': 'memstara-blackboard.read_question_catalog',
                        'tool_name': 'read_question_catalog'}])


def test_primary_policy_scopes_cli_runs_without_pipeline_id(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {
        'run_tag': 'cli-primary', 'hypothesis_policy': {'version': 'knowledge_only_v1'}})
    assert bb._pipeline_run() == 'cli-primary'


def test_catalog_is_registered_as_an_mcp_tool():
    tools = asyncio.run(bb.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert 'read_question_catalog' in names
