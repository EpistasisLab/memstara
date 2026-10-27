"""Scoped real database retrieval and offline specialist handoff integration."""

import asyncio
import copy
import hashlib
import json
import sqlite3
from unittest.mock import AsyncMock

import pytest

from memstara import expert_knowledge as knowledge
from memstara import specialist_explanation as explanation
from memstara import specialist_xai as xai


@pytest.fixture(params=["file", "inline"])
def sources(tmp_path, monkeypatch, request):
    path = tmp_path / "knowledge.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE documents (id TEXT, text TEXT, domain TEXT)")
    connection.executemany(
        "INSERT INTO documents VALUES (?,?,?)",
        [("a", "Synthetic marker addiction evidence", "addiction"), ("h", "Synthetic marker HIV evidence", "hiv")],
    )
    connection.commit()
    connection.close()
    bindings = {
        name: {
            "expert": name,
            "database_id": name + "-fixture",
            "kind": "sqlite",
            "path": str(path),
            "table": "documents",
            "id_column": "id",
            "text_column": "text",
            "scope_column": "domain",
            "scope_value": name,
        }
        for name in ("addiction", "hiv")
    }
    config = tmp_path / "bindings.json"
    config.write_text(json.dumps(bindings))
    monkeypatch.delenv("MEMSTARA_EXPLANATION_SOURCES_JSON", raising=False)
    monkeypatch.delenv("MEMSTARA_EXPLANATION_SOURCES", raising=False)
    if request.param == "inline":
        monkeypatch.setenv("MEMSTARA_EXPLANATION_SOURCES_JSON", config.read_text())
        config.unlink()
    else:
        monkeypatch.setenv("MEMSTARA_EXPLANATION_SOURCES", str(config))
    monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(tmp_path))
    return bindings


@pytest.mark.parametrize("expert", ["addiction", "hiv"])
def test_real_sqlite_scopes_and_read_only(sources, expert):
    binding = sources[expert]
    before = hashlib.sha256(open(binding["path"], "rb").read()).hexdigest()
    evidence = asyncio.run(knowledge.retrieve(binding, "Synthetic marker"))
    assert [r["id"] for r in evidence["documents"]] == (["a"] if expert == "addiction" else ["h"])
    assert evidence["expert"] == expert and evidence["database_id"] == expert + "-fixture"
    assert "path" not in evidence["binding"] and evidence["query"]["parameters"][0] == expert
    assert hashlib.sha256(open(binding["path"], "rb").read()).hexdigest() == before
    with pytest.raises(knowledge.KnowledgeError, match="no matching"):
        asyncio.run(knowledge.retrieve(binding, "xyzneverfound"))
    with pytest.raises(knowledge.KnowledgeError):
        knowledge.validate({**binding, "expert": "wrong"}, expert)
    with pytest.raises(knowledge.KnowledgeError):
        knowledge.validate({**binding, "table": "documents; DROP TABLE documents"}, expert)


def test_postgres_scoped_parameterized_read_only(sources, monkeypatch):
    from unittest.mock import MagicMock
    import asyncpg

    binding = {k: v for k, v in sources["hiv"].items() if k != "path"} | {
        "kind": "postgres",
        "dsn_env": "TEST_EXPERT_DSN",
    }
    monkeypatch.setenv("TEST_EXPERT_DSN", "synthetic-test-value")
    connection = AsyncMock()
    connection.transaction = MagicMock(return_value=AsyncMock())
    connection.fetch.return_value = [{"id": "h", "text": "marker evidence"}]
    connection.fetchval.return_value = "1:2:"
    connection.get_server_version = MagicMock(return_value="test-version")
    monkeypatch.setattr(asyncpg, "connect", AsyncMock(return_value=connection))
    evidence = asyncio.run(knowledge.retrieve(binding, "marker"))
    connection.transaction.assert_called_once_with(readonly=True, isolation="repeatable_read")
    assert connection.fetch.call_args.args[1:] == ("hiv", "%marker%")
    assert "synthetic-test-value" not in json.dumps(evidence)
    assert connection.close.await_count == 1


@pytest.fixture
def frozen(sources, tmp_path, monkeypatch):
    from memstara.control import catalog

    root = tmp_path / "skills"
    root.mkdir()
    (root / "old").mkdir()
    monkeypatch.setattr(catalog, "specialist_dir", lambda: root)
    for name, title in [
        ("addiction", "Addiction, Psychiatry, and Social Determinants of Health"),
        ("hiv", "HIV and Sexual Health"),
    ]:
        filename = catalog.SPECIALIST_SKILLS["shared-" + name][0]
        (root / filename).write_text("# " + title + " Explanation Skill\nSynthetic instructions")
        (root / "old" / filename).write_text("ARCHIVE")
    books = {"report": list(explanation.SKILLS), "interpreter": list(xai.SKILLS)}
    prompts = {f"board/report:{name}": {"system_prompt": "frozen " + name} for name in explanation.SKILLS}
    policy = explanation.freeze(books, prompts)
    return {
        "run_tag": "fixture",
        "config_hash": "config",
        "books": {"report": ["shared-addiction"]},
        "specialist_explanation_policy": policy,
    }


def test_freeze_current_files_and_required_bindings(frozen, sources, monkeypatch):
    assert set(frozen["specialist_explanation_policy"]["skills"]) == set(explanation.SKILLS)
    assert "ARCHIVE" not in json.dumps(frozen)
    monkeypatch.delenv("MEMSTARA_EXPLANATION_SOURCES", raising=False)
    monkeypatch.delenv("MEMSTARA_EXPLANATION_SOURCES_JSON", raising=False)
    from memstara import okf_expert
    binding = dict(sources["hiv"])
    monkeypatch.setattr(okf_expert, "freeze", lambda expert: binding)
    policy = explanation.freeze(
        {"report": ["shared-hiv"], "interpreter": list(xai.SKILLS)},
        {"board/report:shared-hiv": {"system_prompt": "frozen hiv"}},
    )
    assert policy["bindings"]["hiv"] == binding


@pytest.fixture
def result(frozen, tmp_path, monkeypatch):
    # Recorded upstream contract with real immutable receipts; numerical XAI is
    # separately exercised below with actual fitted models.
    models = {
        name: {"attributions": [{"explanation_id": name + "-id", "method": "shap", "status": "completed"}]}
        for name in ("xgboost",)
    }
    task = {"task_id": 12, "trial": 0, "hypothesis": "Synthetic marker question"}
    value = {
        "source_task_id": 12,
        "run_tag": "fixture",
        "trial": 0,
        "models": models,
        "method": "shap",
        "skill": "shared-shap",
    }
    monkeypatch.setattr(xai, "handoff", lambda *args: value)
    receipt = explanation.write_record(
        tmp_path / "interpretation_io",
        "output",
        {
            "task": task,
            "handoff": value,
            "worker": "interpret#1",
            "interpretation": "Selected model: measured synthetic findings",
        },
    )
    row = {
        "task_id": 12,
        "result_id": 1,
        "trial": 0,
        "run_tag": "fixture",
        "hypothesis": task["hypothesis"],
        "evaluation": {
            "interpretations_complete": True,
            "model_results": {
                name: {"specialist_xai": {"items": item["attributions"]}} for name, item in models.items()
            },
            "interpretations": [
                {"status": "done", "text": "Selected model: measured synthetic findings", "specialist": receipt}
            ],
        },
    }
    return row


@pytest.mark.parametrize("expert", ["addiction", "hiv"])
def test_prepare_actual_interpretation_and_expert_evidence(frozen, result, tmp_path, expert):
    frozen["books"]["report"] = ["shared-" + expert]
    prepared = asyncio.run(explanation.prepare(frozen, [result], 1, tmp_path / "run" / "explanation_io"))
    assert prepared["payload"]["expert"] == expert
    row = prepared["payload"]["results"][0]
    assert row["knowledge"]["database_id"] == expert + "-fixture"
    assert row["interpretations"][0]["text"].startswith("Selected model")
    assert set(row["interpretations"][0]["models"]) == {"xgboost"}
    assert "dsn_env" not in prepared["prompt"]
    assert "[database_id:document_id]" not in prepared["prompt"]
    assert explanation.read_receipt(prepared["receipt"]) == prepared["payload"]
    text = "Synthetic explanation [" + expert + "-fixture:" + ("a" if expert == "addiction" else "h") + "]"
    entry = explanation.finish(
        prepared, text, {"status": "completed", "run_id": "synthetic"}, tmp_path / "run" / "explanation_io"
    )
    assert explanation.read_receipt(entry["specialist_explanation"]["output"])["output"] == text
    uncited = explanation.finish(
        prepared, "Uncited report", {"status": "completed"}, tmp_path / "run" / "explanation_io"
    )
    audit = uncited["specialist_explanation"]["citation_audit"]
    assert audit["status"] == "warning" and audit["warnings"] == ["no_citations_found"]


@pytest.mark.parametrize("change", ["trial", "run", "hypothesis", "text", "models", "missing"])
def test_reject_stale_or_missing_handoffs(frozen, result, change):
    row = copy.deepcopy(result)
    if change == "trial":
        row["trial"] = 1
    elif change == "run":
        row["run_tag"] = "other"
    elif change == "hypothesis":
        row["hypothesis"] = "different"
    elif change == "text":
        row["evaluation"]["interpretations"][0]["text"] = "invented"
    elif change == "models":
        row["evaluation"]["model_results"]["xgboost"]["specialist_xai"]["items"][0]["explanation_id"] = "other"
    else:
        row["evaluation"]["interpretations_complete"] = False
    with pytest.raises(ValueError):
        explanation.handoffs(frozen, [row], 1)


def test_execution_tools_removed_and_output_saved(frozen, result, tmp_path):
    call = AsyncMock(
        return_value=("Measured explanation [addiction-fixture:a]", {"status": "completed", "run_id": "test"})
    )
    read = AsyncMock(return_value={"results": [result]})
    text, entry = asyncio.run(
        explanation.execute(
            frozen,
            1,
            tmp_path / "run",
            ("agent", "old broad prompt"),
            {"registry": None, "tools": ["okf_search", "read_results"], "stage": "report"},
            call,
            read,
        )
    )
    assert entry["status"] == "completed" and text
    assert call.call_args.kwargs["tools"] == []
    assert "old broad prompt" not in call.call_args.args[1]
    assert (tmp_path / "run" / "explanation_io" / "loop-1.json").is_file()
    frozen["combination_plan"] = {"total_loops": 1}
    combined, entry = explanation.assemble(frozen, tmp_path / "run" / "explanation_io")
    assert text == combined and entry["status"] == "completed"
    frozen["combination_plan"]["total_loops"] = 2
    partial, entry = explanation.assemble(frozen, tmp_path / "run" / "explanation_io")
    assert partial == text
    assert entry["status"] == "failed" and entry["specialist_explanation"]["missing_loops"] == [2]


def test_uncited_report_is_saved_and_does_not_stop_its_loop(frozen, result, tmp_path):
    call = AsyncMock(return_value=("Completed report without citations.", {"status": "completed", "run_id": "test"}))
    text, entry = asyncio.run(
        explanation.execute(
            frozen,
            1,
            tmp_path / "run",
            ("agent", "prompt"),
            {"registry": None, "tools": [], "stage": "report"},
            call,
            AsyncMock(return_value={"results": [result]}),
        )
    )
    assert text == "Completed report without citations."
    assert entry["status"] == "completed"
    saved = json.loads((tmp_path / "run" / "explanation_io" / "loop-1.json").read_text())
    audit = saved["summary"]["citation_audit"]
    assert audit["status"] == "warning" and audit["warnings"] == ["no_citations_found"]
    frozen["combination_plan"] = {"total_loops": 1}
    combined, assembled = explanation.assemble(frozen, tmp_path / "run" / "explanation_io")
    assert "Completed report without citations." in combined
    assert assembled["status"] == "completed"


def test_unavailable_database_prevents_llm(frozen, result, tmp_path):
    frozen["specialist_explanation_policy"]["bindings"]["addiction"]["table"] = "missing_table"
    call = AsyncMock()
    text, entry = asyncio.run(
        explanation.execute(
            frozen,
            1,
            tmp_path / "run",
            ("agent", "prompt"),
            {"registry": None, "tools": [], "stage": "report"},
            call,
            AsyncMock(return_value={"results": [result]}),
        )
    )
    assert not text and entry["status"] == "failed"
    assert call.await_count == 0
    assert list((tmp_path / "run" / "explanation_io").glob("failure-*.json"))


def test_report_dispatch_and_saved_status(frozen, result, tmp_path, monkeypatch):
    pytest.importorskip('motoro', reason='Board dispatch requires the optional Motoro runtime')
    from memstara.pipeline import board

    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: frozen)
    trace = tmp_path / "run" / "trace"
    trace.mkdir(parents=True)
    monkeypatch.setattr(board, "_TRACE_DIR", trace)
    token = board._CURRENT_LOOP.set(1)
    call = AsyncMock(return_value=("Expert report without citations", {"status": "completed"}))
    monkeypatch.setattr(board, "call_agent", call)
    monkeypatch.setattr(board, "call_board_tool", AsyncMock(return_value={"results": [result]}))
    try:
        text, entry = asyncio.run(
            board.call_report("agent", "prompt", registry=None, tools=["unscoped"], stage="report")
        )
    finally:
        board._CURRENT_LOOP.reset(token)
    assert call.call_args.kwargs["tools"] == []
    assert board.save_report(tmp_path / "run", text, entry)
    saved = json.loads((tmp_path / "run" / "report_status.json").read_text())
    assert saved["specialist_explanation"]["expert"] == "addiction"
    assert saved["specialist_explanation"]["citation_audit"]["warnings"] == ["no_citations_found"]


from test_specialist_xai import specification, skills  # noqa: F401, E402
from test_paired_ml import experiment  # noqa: F401, E402


def test_real_saved_models_to_both_experts(specification, frozen, tmp_path):  # noqa: F811
    from memstara.mcp_servers.ml import train_and_score

    path, snapshot, _, proposal = specification
    measured = json.loads(train_and_score(str(path), "Y", ml_plan=proposal))
    assert not measured.get("error"), measured
    snapshot["specialist_explanation_policy"] = frozen["specialist_explanation_policy"]
    task = {
        "task_id": 12,
        "trial": 0,
        "hypothesis": "Synthetic marker question",
        "subset_path": str(path),
        "evaluation": measured,
    }
    items = []
    for index, method in enumerate(("shap", "lime"), 1):
        worker = f"interpret#{index}"
        value = xai.handoff(snapshot, task, worker)
        text = f"Synthetic {method} interpretation of both measured models"
        receipt = xai.record_io(snapshot, task, worker, value, interpretation=text)
        items.append({"status": "done", "text": text, "specialist": receipt})
    row = {
        "task_id": 12,
        "result_id": 1,
        "trial": 0,
        "run_tag": snapshot["run_tag"],
        "hypothesis": task["hypothesis"],
        "evaluation": {**measured, "interpretations_complete": True, "interpretations": items},
    }
    for expert in ("addiction", "hiv"):
        snapshot["books"]["report"] = ["shared-" + expert]
        prepared = asyncio.run(explanation.prepare(snapshot, [row], 1, tmp_path / "real-run" / "explanation_io"))
        assert {i["method"] for i in prepared["payload"]["results"][0]["interpretations"]} == {"shap", "lime"}
        assert prepared["payload"]["results"][0]["knowledge"]["database_id"] == expert + "-fixture"


def test_model_identity_records_effective_config_without_credentials(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(tmp_path))
    config = SimpleNamespace(
        provider="synthetic",
        model="model-fixture",
        temperature=0.1,
        max_tokens=123,
        api_key="must-not-appear",
        api_base="private-endpoint",
    )
    receipt = explanation.record_model(config, (str(tmp_path / "run"), "call-id", "report"), 1)
    payload = explanation.read_receipt(receipt)
    assert payload["provider"] == "synthetic" and payload["model"] == "model-fixture"
    assert payload["settings"]["max_tokens"] == 123
    assert "must-not-appear" not in json.dumps(payload) and "private-endpoint" not in json.dumps(payload)


def test_invented_citation_is_recorded_as_warning_without_failing(frozen, result, tmp_path):
    prepared = asyncio.run(explanation.prepare(frozen, [result], 1, tmp_path / "run" / "explanation_io"))
    entry = explanation.finish(
        prepared,
        "Evidence [addiction-fixture:a] and [invented:source]",
        {"status": "completed"},
        tmp_path / "run" / "explanation_io",
    )
    audit = explanation.read_receipt(entry["specialist_explanation"]["output"])["citation_audit"]
    assert entry["status"] == "completed"
    assert audit["status"] == "warning"
    assert audit["unsupported_citations"] == ["[invented:source]"]


def test_literal_citation_template_is_preserved_and_audited(frozen, result, tmp_path):
    prepared = asyncio.run(explanation.prepare(frozen, [result], 1, tmp_path / "run" / "explanation_io"))
    raw = "Summary. Retrieval evidence is cited as [database_id:document_id].\nEvidence [addiction-fixture:a]"
    normalized, changes = explanation.normalize_report_output(raw)
    assert normalized == raw and changes == []
    assert "Evidence [addiction-fixture:a]" in normalized
    entry = explanation.finish(
        prepared, normalized, {"status": "completed"}, tmp_path / "run" / "explanation_io",
        normalization=changes,
    )
    saved = explanation.read_receipt(entry["specialist_explanation"]["output"])
    assert saved["output"] == normalized
    assert saved["output_normalization"] == []
    assert "[database_id:document_id]" in saved["citation_audit"]["unsupported_citations"]


def test_unrecognized_placeholder_citation_is_recorded_not_fatal(frozen, result, tmp_path):
    prepared = asyncio.run(explanation.prepare(frozen, [result], 1, tmp_path / "run" / "explanation_io"))
    raw = "Evidence [database_id:document_id]"
    normalized, changes = explanation.normalize_report_output(raw)
    assert normalized == raw and changes == []
    entry = explanation.finish(prepared, normalized, {"status": "completed"}, tmp_path / "run" / "explanation_io")
    assert entry["status"] == "completed"
    assert entry["specialist_explanation"]["citation_audit"]["warnings"] == [
        "citations_not_in_retrieved_source_set"
    ]


def test_expert_failure_stops_following_pipeline_execution(frozen, result, tmp_path, monkeypatch):
    pytest.importorskip('motoro', reason='Board dispatch requires the optional Motoro runtime')
    from memstara.pipeline import board
    from memstara.pipeline.failures import PipelineExecutionFailure, ensure_not_failed

    monkeypatch.setattr("memstara.evaluation.active_plan", lambda: frozen)
    trace = tmp_path / "run" / "trace"
    trace.mkdir(parents=True)
    monkeypatch.setattr(board, "_TRACE_DIR", trace)
    frozen["specialist_explanation_policy"]["bindings"]["addiction"]["table"] = "missing"
    monkeypatch.setattr(board, "call_board_tool", AsyncMock(return_value={"results": [result]}))
    token = board._CURRENT_LOOP.set(1)
    try:
        with pytest.raises(PipelineExecutionFailure):
            asyncio.run(board.call_report("agent", "prompt", registry=None, tools=[], stage="report"))
    finally:
        board._CURRENT_LOOP.reset(token)
    assert json.loads((tmp_path / "run" / "report_status.json").read_text())["status"] == "failed"
    with pytest.raises(PipelineExecutionFailure):
        ensure_not_failed(tmp_path / "run")


def test_real_database_preflight_and_failure_before_paid_calls(frozen, tmp_path):
    asyncio.run(explanation.preflight(frozen, tmp_path / "run"))
    receipts = list((tmp_path / "run" / "explanation_io").glob("preflight-*.json"))
    assert len(receipts) == 2 and all(json.loads(p.read_text())["status"] == "readable" for p in receipts)
    frozen["specialist_explanation_policy"]["bindings"]["hiv"]["scope_value"] = "missing-domain"
    with pytest.raises(knowledge.KnowledgeError, match="preflight failed"):
        asyncio.run(explanation.preflight(frozen, tmp_path / "run"))


def test_research_activation_keeps_execution_receipts_readable(frozen, tmp_path, monkeypatch):
    run = tmp_path / 'execution'
    run.mkdir()
    config = run / 'config.json'
    config.write_text(json.dumps(frozen))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(config))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path / 'research' / 'derived'))
    asyncio.run(explanation.preflight(frozen, run))
    assert list((run / 'explanation_io').glob('preflight-*.json'))
    receipt = explanation.write_record(run / 'explanation_io', 'output', {'result': 'synthetic'})
    assert explanation.read_receipt(receipt) == {'result': 'synthetic'}
    derived = explanation.write_record(tmp_path / 'research' / 'derived' / 'interpretation_io',
                                       'output', {'interpretation': 'synthetic'})
    assert explanation.read_receipt(derived) == {'interpretation': 'synthetic'}


@pytest.mark.parametrize('outside', ['another-run/explanation_io', 'execution/other-artifacts'])
def test_receipt_scope_does_not_expand_to_other_runs(tmp_path, monkeypatch, outside):
    run = tmp_path / 'execution'
    run.mkdir()
    config = run / 'config.json'
    config.write_text('{}')
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(config))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path / 'derived'))
    with pytest.raises(ValueError, match='outside'):
        explanation.write_record(tmp_path / outside, 'output', {})
    assert not (tmp_path / outside).exists()


def test_execution_receipt_symlink_cannot_escape_run(tmp_path, monkeypatch):
    run, outside = tmp_path / 'run', tmp_path / 'outside'
    run.mkdir()
    outside.mkdir()
    config = run / 'config.json'
    config.write_text('{}')
    (run / 'explanation_io').symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(config))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path / 'derived'))
    with pytest.raises(ValueError, match='outside'):
        explanation.write_record(run / 'explanation_io', 'output', {})
    assert list(outside.iterdir()) == []


def test_assembly_rejects_relabelled_expert(frozen, result, tmp_path):
    directory = tmp_path / "run" / "explanation_io"
    asyncio.run(
        explanation.execute(
            frozen,
            1,
            tmp_path / "run",
            ("agent", "prompt"),
            {"registry": None, "tools": [], "stage": "report"},
            AsyncMock(return_value=("Evidence [addiction-fixture:a]", {"status": "completed"})),
            AsyncMock(return_value={"results": [result]}),
        )
    )
    path = directory / "loop-1.json"
    item = json.loads(path.read_text())
    item["summary"]["expert"] = "hiv"
    path.write_text(json.dumps(item))
    frozen["combination_plan"] = {"total_loops": 1}
    with pytest.raises(ValueError, match="provenance integrity"):
        explanation.assemble(frozen, directory)


@pytest.mark.parametrize('second,valid', [('b', True), ('invented', False), ('', False)])
def test_grouped_citations_validate_every_document(frozen, result, tmp_path, second, valid):
    directory = tmp_path / 'run' / 'explanation_io'
    prepared = asyncio.run(explanation.prepare(frozen, [result], 1, directory))
    documents = prepared['payload']['results'][0]['knowledge']['documents']
    documents.append({**documents[0], 'id': 'b'})
    prepared['receipt'] = explanation.write_record(directory, 'input', prepared['payload'])
    text = f'Evidence [addiction-fixture:a; addiction-fixture:{second}]'
    if valid:
        entry = explanation.finish(prepared, text, {'status': 'completed'}, directory)
        assert explanation.read_receipt(entry['specialist_explanation']['output'])['output'] == text
    else:
        entry = explanation.finish(prepared, text, {'status': 'completed'}, directory)
        audit = explanation.read_receipt(entry['specialist_explanation']['output'])['citation_audit']
        assert entry['status'] == 'completed'
        assert audit['status'] == 'warning'
        assert audit['unsupported_citations'] == [f'[addiction-fixture:{second}]']
