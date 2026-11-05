"""No model or DB calls: verify the scheduled control's actual execution boundary."""

import asyncio
import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline import no_knowledge as nk, feature_selection as fs
from memstara.pipeline.question_contract import make_contract, question_text, validate_saved


def plan():
    return {"no_knowledge_isolation": nk.VERSION, "run_tag": "test", "y_column": "Y", "trials": 1,
            "books": {"hypothesis": [nk.SKILL]},
            "knowledge_policy": {"mode": "okf", "retrieval_enabled": True},
            "knowledge_hashes": {"anchors/hiv.md": "digest"}, "knowledge_path": "/private/okf",
            "hypothesis_policy": {"question_contract": "fixed_target_v1", "version": "iterative_discovery_v1"},
            "recovery_policy": {"version": "artifact_checked_v1"},
            "question_feasibility_policy": "explicit_columns_v1",
            "feature_context": {"features": [{"column": "AGE", "meaning": "Recorded age"}]},
            "research_profile": {"configuration": {"target": {"column": "Y"}, "knowledge_mode": "okf"}}}


def proposal():
    return {"predictor_concepts": ["age"], "rationale": "General model knowledge; no retrieved evidence.",
            "source_ids": [], "okf_tags": [], "origin_wave": 0,
            "proposed_mapping": [{"concept": "age", "column": "AGE", "source_id": "", "rationale": "Recorded age"}]}


def test_scope_is_per_scheduled_condition_and_does_not_mutate_frozen_plan(monkeypatch):
    p = plan()
    p["combination_plan"] = {"test": True}
    monkeypatch.setattr("memstara.combinations.loop_flavors", lambda schedule, loop: {
        "agents": [{"stage": "hypothesis", "id": nk.SKILL if loop == 1 else "hiv-okf-whole-graph"}]})
    before = copy.deepcopy(p)
    scoped = nk.scope(p, 0)
    assert scoped["knowledge_policy"] == {"mode": "no_okf", "retrieval_enabled": False}
    assert scoped["knowledge_hashes"] == {} and scoped["knowledge_path"] == ""
    assert nk.scope(p, 1) is p and p == before
    from memstara.pipeline.iteration_learning import enabled
    assert not enabled(scoped)


def test_historical_unisolated_controls_cannot_resume_under_new_label():
    p = plan()
    p.pop("no_knowledge_isolation")
    with pytest.raises(ValueError, match="Start a new execution"):
        nk.scope(p, 0)


def test_control_has_no_knowledge_reader_catalog_memory_or_arbitrary_reference_tools():
    names = ["okf_read", "okf_search", "okf_list_domains", "read_context_payload", "read_question_catalog",
             "read_board", "read_results", "claim_question", "match_concepts", "describe_dataset",
             "web_search", "memory_search", "lookup_predictor_catalog", "propose_questions", "create_task"]
    tools = [{"server": "memstara-blackboard", "tool_name": name} for name in names]
    allowed = fs.hypothesis_tools(tools, plan(), 0)
    assert {t["tool_name"] for t in allowed} == {"lookup_predictor_catalog", "propose_questions", "create_task"}
    ordinary = {**plan(), "books": {"hypothesis": ["hiv-okf-whole-graph"]}}
    assert fs.hypothesis_tools(tools, ordinary, 0) == tools


def test_control_contract_uses_csv_and_rejects_retrieved_lineage():
    p = plan()
    contract = make_contract(proposal(), p)
    assert contract["evidence_mode"] == "no_okf" and contract["source_ids"] == []
    validate_saved(contract, question_text(contract), p)
    for change in ({"source_ids": ["anchors/hiv"]}, {"okf_tags": ["anchors"]},
                   {"path_uses": [{"source_id": "anchors/hiv", "path_id": "x"}]},
                   {"parent_task_ids": [1]}, {"learning_goal": "Reuse earlier result"}):
        with pytest.raises(ValueError):
            make_contract({**proposal(), **change}, p)
    bad = proposal()
    bad["proposed_mapping"][0]["column"] = "INVENTED"
    with pytest.raises(ValueError):
        make_contract(bad, p)


def test_control_prompt_retains_skill_verbatim_without_graph_workflow(monkeypatch):
    from memstara.pipeline.prompts import load_prompt
    from memstara.paths import PLAYBOOKS_DIR
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: None)
    prompt = load_prompt("board/hypothesis", nk.SKILL)["system_prompt"]
    assert (PLAYBOOKS_DIR / (nk.SKILL + ".md")).read_text().strip() in prompt
    assert "Read actual Instances" not in prompt and "Call okf" not in prompt
    assert "controller has already claimed" in prompt
    normal = load_prompt("board/hypothesis", "hiv-okf-whole-graph")["system_prompt"]
    assert "okf_read" in normal


def test_control_create_task_rejects_path_evidence_before_db(monkeypatch):
    from memstara.mcp_servers import blackboard as bb
    monkeypatch.setattr("memstara.evaluation.active_plan", plan)
    monkeypatch.setattr(bb, "_pipeline_run", lambda: "test")
    connect = AsyncMock(side_effect=AssertionError("DB must not be touched"))
    monkeypatch.setattr(bb.asyncpg, "connect", connect)
    result = json.loads(asyncio.run(bb.create_task(run_tag="test", trial=0, columns=["AGE"],
        y_column="Y", perspective="Age association", hypothesis="age",
        path_uses=[{"source_id": "anchors/hiv", "path_id": "x"}])))
    assert "must not contain" in result["error"]
    connect.assert_not_called()


def test_actual_agent_execution_receives_only_control_tools_and_no_corpus_metadata(monkeypatch):
    from memstara.pipeline import board
    p = plan()
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: p)
    monkeypatch.setattr(board, "require_ownership", lambda: None)
    monkeypatch.setattr(board, "_TRACE_DIR", None)
    monkeypatch.setattr(board, "_CALLS", [])
    monkeypatch.setattr(board, "_trace_one", AsyncMock())
    monkeypatch.setattr("memstara.pipeline.reporting.show_console_summary", AsyncMock())
    monkeypatch.setattr("memstara.stage_models.call_overrides", lambda *args: {})
    create = AsyncMock(return_value=NS(id="synthetic", owner_id="synthetic"))
    monkeypatch.setattr(board, "create_run", create)
    execute = AsyncMock(return_value=NS(status="completed", error=None, output="done"))
    monkeypatch.setattr(board, "execute_run", execute)
    token = board._CURRENT_LOOP.set(1)
    try:
        tools = [{"server": "okf", "tool_name": "okf_read"},
                 {"server": "memstara-blackboard", "tool_name": "read_context_payload"},
                 {"server": "memstara-blackboard", "tool_name": "propose_questions"}]
        _, entry = asyncio.run(board._call_agent_uncontrolled("agent", "Generate a question.",
                            tools=tools, registry=None, stage="question0-1"))
    finally:
        board._CURRENT_LOOP.reset(token)
    assert entry["allowed_tools"] == ["propose_questions"] and entry["knowledge_condition"] == "no_okf"
    assert [t["tool_name"] for t in execute.call_args.kwargs["available_tools"]] == ["propose_questions"]
    assert "Use only the selected corpus" not in create.call_args.kwargs["user_input"]
    assert "No OKF corpus is attached" in create.call_args.kwargs["user_input"]
