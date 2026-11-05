"""Provider-facing references preserve evidence and isolate historical runs."""
import asyncio
import copy
import json
import stat
from types import SimpleNamespace as NS

import pytest

from memstara.pipeline import context_payloads as payloads


def sample():
    return {"ok": True, "task_id": 17, "seed": 42, "auc": .73,
            "limits": "Exploratory only", "values": list(range(15000)),
            "a/b": {"~key": "exact evidence"}}


def test_full_history_and_call_pairs_unchanged_but_provider_data_is_bounded(tmp_path):
    original = [{"role": "system", "content": "Keep the run contract"},
                {"role": "assistant", "tool_calls": [{"id": "call1", "function": {"name": "train_and_score", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call1", "content": json.dumps(sample())},
                {"role": "user", "content": "Repair only the rejected submission"}]
    before = copy.deepcopy(original)
    prepared = payloads.prepare(original, (tmp_path, "agent1", "ml#1"))
    assert original == before
    assert prepared[:2] == original[:2] and prepared[-1] == original[-1]
    assert prepared[2]["tool_call_id"] == "call1"
    saved = json.loads(prepared[2]["content"])
    assert saved["partial_view"] and saved["index"]["seed"] == 42
    assert len(prepared[2]["content"]) < 4000
    ref = saved["context_reference"]
    assert json.loads(payloads.read(tmp_path, ref, "/values/14999")["content"]) == 14999
    assert json.loads(payloads.read(tmp_path, ref, "/a~1b/~0key")["content"]) == "exact evidence"
    assert stat.S_IMODE((tmp_path / "context_payloads" / (ref + ".json")).stat().st_mode) == 0o600


def test_full_payload_can_be_reconstructed_with_pages(tmp_path):
    body = json.dumps(sample())
    ref = json.loads(payloads.reference(tmp_path, "agent", body))["context_reference"]
    pages = []
    offset = 0
    while offset is not None:
        page = payloads.read(tmp_path, ref, offset=offset, limit=1234)
        pages.append(page["content"])
        offset = page["next_offset"]
    assert json.loads("".join(pages)) == sample()


def test_catalog_is_referenced_without_losing_surrounding_instructions(tmp_path):
    text = "Use only approved features.\n" + json.dumps(sample()) + "\nNever change the target."
    result = payloads.structured_text(text, tmp_path, "agent")
    assert result.startswith("Use only approved features.\n")
    assert result.endswith("\nNever change the target.")
    assert "context_reference" in result
    assert payloads.structured_text("Keep {invalid JSON} instructions", tmp_path, "agent") == "Keep {invalid JSON} instructions"


def test_scope_integrity_and_traversal(tmp_path):
    ref = json.loads(payloads.reference(tmp_path, "agent", json.dumps(sample())))["context_reference"]
    with pytest.raises(FileNotFoundError):
        payloads.read(tmp_path / "other-run", ref)
    with pytest.raises(ValueError):
        payloads.read(tmp_path, "../outside")
    with pytest.raises(ValueError):
        payloads.read(tmp_path, ref, limit=12001)
    path = tmp_path / "context_payloads" / (ref + ".json")
    data = json.loads(path.read_text())
    data["content"] = "tampered"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="integrity"):
        payloads.read(tmp_path, ref)


def test_symlink_and_storage_failure_do_not_silently_discard_evidence(tmp_path):
    (tmp_path / "context_payloads").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        payloads.reference(tmp_path, "agent", json.dumps(sample()))


@pytest.mark.parametrize("policy,tool,compact", [(None, True, False), (payloads.VERSION, False, False), (payloads.VERSION, True, True)])
def test_service_only_compacts_frozen_new_runs_with_retrieval_tool(tmp_path, monkeypatch, policy, tool, compact):
    from memstara.pipeline.llm import PipelineLLMService
    from memstara.pipeline.diagnostics import call_context
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: {"context_payload_policy": policy})
    monkeypatch.setattr("memstara.stage_models.validate_call", lambda *args: None)
    messages = [{"role": "tool", "tool_call_id": "call1", "content": json.dumps(sample())}]
    tools = [{"function": {"name": "read_context_payload"}}] if tool else []
    async def fake(config, prepared, available):
        assert ("context_reference" in prepared[0]["content"]) is compact
        assert available == tools
        return "done"
    token = call_context.set((tmp_path, "agent", "ml#1"))
    try:
        assert asyncio.run(PipelineLLMService()._request(fake, NS(model="synthetic"), messages, tools)) == "done"
    finally:
        call_context.reset(token)


def test_mcp_reader_uses_only_active_execution_root(tmp_path, monkeypatch):
    from memstara.mcp_servers.blackboard import read_context_payload
    ref = json.loads(payloads.reference(tmp_path, "agent", json.dumps(sample())))["context_reference"]
    monkeypatch.setenv("MEMSTARA_RUN_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: {"context_payload_policy": payloads.VERSION})
    result = json.loads(asyncio.run(read_context_payload(ref, "/seed")))
    assert result["content"] == "42"
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: {})
    assert "error" in json.loads(asyncio.run(read_context_payload(ref)))


def test_retrieval_tool_is_selected_and_primary_boundary_is_preserved(monkeypatch):
    from memstara.pipeline.core import tools_for
    from memstara.pipeline.scientific_policy import check_primary_tools
    from unittest.mock import Mock
    registry = NS(servers={"board": NS(name="memstara-blackboard", owner_id=None)},
                  get_all_tools=Mock(return_value=[{"server": "memstara-blackboard", "tool_name": name}
                                                   for name in ("read_context_payload", "read_board", "propose_questions")]))
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: {"context_payload_policy": payloads.VERSION})
    selected = tools_for(registry, {"memstara-blackboard"}, only={"propose_questions"})
    assert {t["tool_name"] for t in selected} == {"propose_questions", "read_context_payload"}
    check_primary_tools("question0", selected)
    with pytest.raises(ValueError):
        check_primary_tools("question0", [{"tool_name": "read_board"}])
    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: {})
    assert [t["tool_name"] for t in tools_for(registry, {"memstara-blackboard"}, only={"propose_questions"})] == ["propose_questions"]
    with pytest.raises(ValueError):
        check_primary_tools("question0", selected)


def test_legacy_snapshot_resume_does_not_adopt_new_policy(tmp_path, monkeypatch):
    import hashlib
    from memstara.pipeline.snapshot import freeze
    monkeypatch.setenv("MEMSTARA_RUN_CONFIG", "")
    source = tmp_path / "data.csv"
    source.write_text("a,b,c,d,y\n" + "".join(f"{i},{i + 1},{i * 2},{i * 3},{i % 2}\n" for i in range(100)))
    monkeypatch.setenv("MEMSTARA_DATASET_PATH", str(source))
    args = NS(run_tag="test", question="Predict y", hypothesis_agents=1, y_column="y",
              evaluation=json.dumps({"engine": "logistic_regression", "seed": 7}), trials=1, waves=1)
    state = freeze(args, tmp_path, {})
    assert state["context_payload_policy"] == payloads.VERSION
    state.pop("context_payload_policy")
    state.pop("config_hash")
    state["config_hash"] = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(state))
    before = path.read_bytes()
    args.resume = True
    assert freeze(args, tmp_path, {}) == state
    assert path.read_bytes() == before


def test_reader_pages_never_become_nested_references_and_history_stays_bounded(tmp_path):
    body = json.dumps({"evaluation": {"rows": list(range(20000))}})
    ref = json.loads(payloads.reference(tmp_path, "agent", body))["context_reference"]
    messages = []
    for n in range(8):
        messages += [
            {"role": "assistant", "tool_calls": [{"id": str(n), "function": {
                "name": "memstara-blackboard.read_context_payload",
                "arguments": json.dumps({"reference": ref, "pointer": "/evaluation", "offset": n * 8000})}}]},
            {"role": "tool", "tool_call_id": str(n), "content": json.dumps(
                payloads.read(tmp_path, ref, "/evaluation", offset=n * 8000))},
        ]
    before = copy.deepcopy(messages)
    prepared = payloads.prepare(messages, (tmp_path, "agent", "interpret#1"))
    assert messages == before
    assert prepared[-1] == messages[-1]
    pages = [json.loads(m["content"]) for m in prepared if m["role"] == "tool"]
    assert any(p.get("content_omitted") for p in pages)
    assert all(p["reference"] == ref and "context_reference" not in p for p in pages)
    assert sum(len(m["content"]) for m in prepared if m["role"] == "tool") < payloads.READ_WINDOW + 4000
    # Only the source payload exists: repeated preparation does not create wrappers.
    assert len(list((tmp_path / "context_payloads").glob("*.json"))) == 1
    old = pages[0]
    reread = payloads.read(tmp_path, old["reference"], old["pointer"], old["offset"])
    assert reread["content"] == json.loads(messages[1]["content"])["content"]


def test_serialized_interpretation_input_supports_direct_nested_json_pointers(tmp_path):
    evidence = {"models": [{"shap": {"feature/a": [0.25, -0.5]}, "limitations": "Not causal"}],
                "method": "shap"}
    claim = {"task_id": 33, "interpretation_input": json.dumps(evidence),
             "evaluation": {"irrelevant_large_array": list(range(20000))}}
    ref = json.loads(payloads.reference(tmp_path, "agent", json.dumps(claim)))["context_reference"]
    page = payloads.read(tmp_path, ref, "/interpretation_input/models/0/shap/feature~1a")
    assert json.loads(page["content"]) == [0.25, -0.5]
    page = payloads.read(tmp_path, ref, "/interpretation_input")
    assert json.loads(page["content"]) == evidence
    assert page["index"]["models"]["$pointer"] == "/interpretation_input/models"
    assert "irrelevant_large_array" not in page["content"]
