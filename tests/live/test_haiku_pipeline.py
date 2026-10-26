"""Real Haiku provider, board, tools and persistence across supported input modes."""

import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

import asyncpg
import pytest

MODEL = "claude-haiku-5-5"
STAGES = {"question", "hypothesis", "data", "ml", "interpreter", "report"}
pytestmark = pytest.mark.live


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def role(stage):
    match = re.match(r"^(question|hypothesis|data|ml|interpret(?:er)?|report)(?:[#0-9-].*)?$", stage)
    assert match, f"Unknown saved stage: {stage}"
    return match[1].replace("interpreter", "interpret")


@pytest.fixture(scope="session")
def live_batch(pytestconfig):
    from memstara.env import load_env
    from memstara.paths import output_dir, REPO_ROOT
    from memstara.stage_models import deployment_profiles

    load_env()
    profiles = deployment_profiles()
    assert profiles and all(p["model"] == MODEL for p in profiles.values()), "All stages must use Haiku 5.5"
    identifier = "haiku_live_" + datetime.now(UTC).strftime("%Y%m%dt%H%M%S") + "_" + uuid.uuid4().hex[:8]
    verification = output_dir() / "verification"
    chosen = pytestconfig.getoption("--live-batch")
    root = Path(chosen).resolve() if chosen else verification / identifier
    assert root.parent == verification and re.fullmatch(r"haiku_live_[a-z0-9_]+", root.name)
    identifier = root.name
    root.mkdir(parents=True, exist_ok=bool(chosen))
    installed = pytestconfig.getoption("--live-installed-python")
    worker = [sys.executable]
    identity = None
    if installed:
        # Preserve the venv executable path: resolving its symlink selects base Python.
        worker = [str(Path(installed).absolute()), "-I"]
        code = """import json, sys, memstara
from pathlib import Path
from importlib.metadata import distribution, version
dist = distribution('memstara')
direct = json.loads(dist.read_text('direct_url.json') or '{}')
assert not direct.get('dir_info', {}).get('editable'), 'Editable installation is not a wheel'
assert direct.get('url', '').endswith('.whl'), 'Wheel provenance required'
assert Path(memstara.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
print(json.dumps({'version': version('memstara'), 'module': memstara.__file__,
                  'python': sys.executable, 'distribution': direct}))
"""
        identity = json.loads(subprocess.check_output([*worker, "-c", code], cwd=root, text=True))
        (root / "installed_distribution.json").write_text(json.dumps(identity, indent=2))
    print(f"\nLIVE BATCH {identifier}: {pytestconfig.getoption('--live-loops')} paid Haiku Loops "
          f"per selected case (HeartFailure combinations: four); evidence {root}", flush=True)
    return {"root": root, "repo": REPO_ROOT, "profiles": profiles, "id": identifier,
            "worker": worker, "installed_distribution": identity}


@pytest.mark.parametrize("study,knowledge,data", [
    ("synthetic", "okf", "dataset"), ("synthetic", "llm_only", "dataset"),
    ("synthetic", "okf", "proposal"), ("synthetic", "llm_only", "proposal"),
    ("heart_combinations", "okf", "dataset"), ("heart_random", "okf", "dataset"),
    ("heart_guided", "okf", "dataset"), ("synthetic_paths", "okf", "dataset"),
    ("synthetic_pipeline_first", "okf", "dataset"),
])
def test_real_haiku_pipeline(live_batch, monkeypatch, pytestconfig, study, knowledge, data):
    from memstara import blackboard
    from memstara.research_inputs import register, digest

    case = f"{knowledge}_{data}" if study == "synthetic" else study
    loops = 4 if study in ("heart_combinations", "synthetic_pipeline_first") else pytestconfig.getoption('--live-loops')
    case_area = live_batch["root"] / case
    area = case_area
    completed = [p for p in area.glob("attempt_*")
                 if read(p / "run" / "pipeline_status.json", {}).get("status") == "completed"
                 and read(p / "acceptance.json", {}).get("exit_code") == 0]
    if completed:
        area = max(completed, key=lambda p: p.stat().st_mtime)
    old_status = read(area / "run" / "pipeline_status.json", {})
    failed_exit = read(area / "acceptance.json", {}).get("exit_code") not in (None, 0)
    # An audit assertion can fail after a successful paid run. Re-audit its
    # preserved evidence instead of silently buying another pipeline execution.
    if failed_exit or ((area / "run").exists() and old_status.get("status") != "completed"):
        assert old_status.get("status") != "running", "Do not duplicate an active live execution"
        assert pytestconfig.getoption("--live-retry-failed"), "Investigate failure before explicitly retrying"
        area = case_area / ("attempt_" + uuid.uuid4().hex[:8])
    area.mkdir(exist_ok=True)
    monkeypatch.setenv("MEMSTARA_RESEARCH_INPUTS_DIR", str(area / "research_inputs"))
    if study == "private_hiv":
        configured = read(Path(pytestconfig.getoption('--live-private-research')).resolve())
        config = configured.get('configuration', configured)
        assert config['target']['column'] == 'HIV_DETECTABLE'
    elif study.startswith("heart"):
        from scripts.prepare_heart_failure_demo import prepare
        demo = live_batch["root"] / "heart_inputs"
        if not demo.exists():
            prepare(live_batch["repo"] / "examples/heart-failure/dataset.csv",
                    live_batch["repo"] / "examples/heart-failure/okf", demo)
        config = read(demo / "research.json")
    else:
        config = read(live_batch["repo"] / "examples/research-inputs/research.json")
    config.update(knowledge_mode=knowledge, data_mode=data)
    for key in ("dataset_path", "knowledge_path"):
        config[key] = str(live_batch["repo"] / config[key])
    if study == "synthetic_paths":
        import shutil
        corpus = area / "path_corpus"
        if not corpus.exists():
            shutil.copytree(config["knowledge_path"], corpus)
            doc = corpus / "observations" / "simulated-risk.md"
            original = doc.read_text()
            records = "metapath_instances:\n"
            for i, name in enumerate(("systolic_pressure", "resting_pulse", "activity_score", "synthetic_marker"), 1):
                evidence = "predicted" if i % 2 else "observed"
                records += (f"  - id: p{i}\n    label: '{name} to simulated event'\n"
                            f"    edges: [{{evidence: {evidence}}}]\n")
            doc.write_text(original.replace("---\n", "---\n" + records, 1))
        config["knowledge_path"] = str(corpus)
    combination = None
    books = {"hypothesis": ["hypothesis_general"], "data": ["data_training_heavy"],
             "ml": ["ml_logistic_regression"], "interpreter": ["shared-anil-shap"],
             "report": ["report_general"]}
    if study == "synthetic_pipeline_first":
        from memstara.combinations import build_plan
        books['data'] = ['data_training_heavy', 'data_balanced_stratified']
        combination = build_plan(books, 2, execution_order='pipeline_replicates_first')
        assert combination['total_loops'] == loops
    if study.startswith("heart"):
        books.update(hypothesis=["heart-failure-cardiovascular"], data=["data_balanced_stratified"],
                     report=["report_heart_failure_cardiovascular"])
        if study == "heart_combinations":
            from memstara.combinations import build_plan
            books["interpreter"] = ["shared-anil-shap", "shared-anil-lime"]
            books["report"] += ["report_heart_failure_cardiorenal"]
            combination = build_plan(books)
            assert combination["total_loops"] == loops
        elif study == "heart_random":
            books.update(hypothesis=["random_features"], ml=["ml_xgboost"], interpreter=["shared-anil-lime"])
            from memstara.combinations import build_plan
            combination = build_plan(books, max_loops=loops)
    if study == "private_hiv":
        books.update(hypothesis=["addiction-psychiatric"], report=["shared-anil-hiv"])
    source = Path(config["dataset_path"])
    source_sha = digest(source)
    run = area / "run"
    schema = live_batch["id"] + "_" + case
    parts = urlsplit(blackboard.dsn())
    query = dict(parse_qsl(parts.query))
    query["search_path"] = schema
    database = urlunsplit(parts._replace(query=urlencode(query)))
    if run.exists():
        assert not pytestconfig.getoption("--live-pause-resume"), "Pause acceptance requires a fresh run"
        assert read(run / "pipeline_status.json", {}).get("status") == "completed", (
            "Failed live cases require investigation")
        frozen = read(run / "config.json")
        assert frozen["stage_models"] == live_batch["profiles"], "Saved model assignment changed"
        assert frozen.get("combination_plan") == combination, "Saved combination design changed"
        if not combination:
            assert frozen["books"] == books, "Saved skill assignment changed"
        saved = frozen["research_profile"]
        assert saved["source_dataset_sha256"] == source_sha if data == "dataset" else True
        assert saved["configuration"]["knowledge_mode"] == knowledge and saved["configuration"]["data_mode"] == data
        from memstara.research_inputs import verify_materialized
        verify_materialized(saved)
        original = read(area / "acceptance.json")
        assert original.get("installed_distribution") == live_batch["installed_distribution"], (
            "Saved execution used a different distribution; select a fresh batch")
        assert original.get('loops', 1) == loops, 'Recorded live Loop count differs'
        elapsed, exit_code = original["elapsed_seconds"], original["exit_code"]
        schema = original["database_schema"]
        query["search_path"] = schema
        database = urlunsplit(parts._replace(query=urlencode(query)))
        print(f"AUDIT {case}: reuse completed real Haiku execution; no duplicate inference", flush=True)
    else:
        record = register(config)
        assert record["input_checks_passed"], record["issues"]
        schema = live_batch["id"] + "_" + case + "_" + uuid.uuid4().hex[:4]

        async def initialize():
            connection = await asyncpg.connect(blackboard.dsn(), timeout=10)
            try:
                await connection.execute(f'CREATE SCHEMA "{schema}"')
                await connection.execute(f'SET search_path TO "{schema}"')
                await connection.execute(blackboard.SCHEMA)
            finally:
                await connection.close()

        asyncio.run(initialize())
        parts = urlsplit(blackboard.dsn())
        query = dict(parse_qsl(parts.query))
        query["search_path"] = schema
        database = urlunsplit(parts._replace(query=urlencode(query)))
        env = {**os.environ, "MEMSTARA_CONFIG_MODE": "environment",
               "MEMSTARA_DATABASE_URL": database, "MEMSTARA_OUTPUT_DIR": str(area),
               "MEMSTARA_ML_ENGINE": "xgboost", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
               "MKL_NUM_THREADS": "1"}
        from memstara.stage_models import expanded_profiles
        for agent, profile in expanded_profiles(live_batch["profiles"]).items():
            for field, value in profile.items():
                env[f"MEMSTARA_{agent.upper()}_{field.upper()}"] = str(value)
        for key in ("MEMSTARA_RUN_CONFIG", "MEMSTARA_COMPARISON_POLICY_PATH", "MEMSTARA_LEAKAGE_RULES_PATH"):
            env.pop(key, None)
        argv = [*live_batch["worker"], "-m", "memstara.pipeline.board", "--trials", "1", "--waves", str(loops),
                "--hypothesis-agents", "1", "--interpret-agents", "1", "--max-attempts", "5",
                "--run-dir", str(run), "--run-tag", schema, "--pipeline-id", schema,
                "--pipeline-name", f"Haiku automated acceptance: {case}", "--research-input-id", record["id"],
                "--stage-models", json.dumps(live_batch["profiles"]), "--baseline-columns", "[]",
                "--evaluation", json.dumps({"engine": "xgboost", "seed": 42, "test_size": .25,
                                             "folds": 0, "replicates": 1, "search_trials": 1}),
                "--playbook-hypothesis", books["hypothesis"][0], "--playbook-data", books["data"][0],
                "--playbook-ml", books["ml"][0], "--playbook-interpreter", books["interpreter"][0],
                "--playbook-explanation", books["report"][0]]
        if combination and study != "heart_random":
            argv.extend(["--combination-plan", json.dumps(combination)])
        started = time.monotonic()
        previous = None
        pause_evidence = {}
        print(f"\nSTART {case}: all model calls use {MODEL}; original files preserved", flush=True)
        with (area / "driver.log").open("w") as log:
            process = subprocess.Popen(argv, env=env, cwd=live_batch["repo"], stdout=log, stderr=log)
            try:
                while process.poll() is None:
                    progress = read(run / "progress.json", {})
                    current = progress.get("stage")
                    if current != previous:
                        print(f"{case}: stage={current}; elapsed={time.monotonic()-started:.1f}s", flush=True)
                        previous = current
                    if pytestconfig.getoption('--live-pause-resume'):
                        calls_now = read(run / 'execution.json', {}).get('calls', [])
                        if not pause_evidence and any(c.get('status') == 'completed' for c in calls_now):
                            (run / 'pause.request').touch()
                            pause_evidence = {'requested_at_seconds': time.monotonic() - started}
                            print(f'{case}: pause requested after a real completed agent call', flush=True)
                        control = read(run / 'execution_control.json', {})
                        if pause_evidence and 'resumed_at_seconds' not in pause_evidence:
                            waiting = control.get('active_calls') == control.get('paused_model_calls', 0)
                            if control.get('state') == 'paused' and waiting:
                                ledger_path = run / 'cost_ledger.jsonl'
                                before = ledger_path.read_bytes() if ledger_path.exists() else b''
                                time.sleep(3)
                                assert process.poll() is None, 'Worker exited while paused'
                                assert read(run / 'execution_control.json', {}).get('state') == 'paused'
                                assert (ledger_path.read_bytes() if ledger_path.exists() else b'') == before
                                pause_evidence.update(paused_without_new_receipts=True,
                                                      worker_pid=process.pid, observed_seconds=3)
                                (run / 'pause.request').unlink()
                                pause_evidence['resumed_at_seconds'] = time.monotonic() - started
                                (area / 'pause_resume.json').write_text(json.dumps(pause_evidence, indent=2))
                                print(f'{case}: resumed same worker after verified pause', flush=True)
                    if time.monotonic() - started > 2400:
                        pytest.fail(f"{case} exceeded 40 minutes; inspect {area / 'driver.log'}")
                    time.sleep(1)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
        elapsed = time.monotonic() - started
        exit_code = process.returncode
        if pytestconfig.getoption('--live-pause-resume'):
            assert pause_evidence.get('paused_without_new_receipts'), 'No verified pause/resume occurred'
    status = read(run / "pipeline_status.json", {})
    calls = read(run / "execution.json", {}).get("calls", [])
    ledger = [json.loads(line) for line in (run / "cost_ledger.jsonl").read_text().splitlines()] \
        if (run / "cost_ledger.jsonl").exists() else []
    summary = {"case": case, "loops": loops, "model": MODEL, "exit_code": exit_code,
               "validation_status": "not_passed",
               "installed_distribution": live_batch["installed_distribution"],
               "elapsed_seconds": elapsed, "database_schema": schema, "run_directory": str(run),
               "status": status, "stages": [{k: c.get(k) for k in ("stage", "status", "duration_seconds")}
                                             for c in calls], "model_requests": len(ledger),
               "input_tokens": sum(r.get("prompt_tokens") or 0 for r in ledger),
               "output_tokens": sum(r.get("completion_tokens") or 0 for r in ledger),
               "known_estimate_subtotal_usd": sum(r["usd"] for r in ledger if r.get("usd") is not None),
               "unpriced_requests": sum(r.get("usd") is None for r in ledger),
               "azure_actual_billed_cost": None, "billing_status": "Not queried; estimates are not actual charges"}
    (area / "acceptance.json").write_text(json.dumps(summary, indent=2))
    print(f"FINISH {case}: exit={exit_code}, status={status.get('status')}, {elapsed:.2f}s", flush=True)
    assert digest(source) == source_sha, "Original CSV changed"
    assert exit_code == 0, f"Inspect {area / 'driver.log'} and saved traces"
    assert status.get("status") == "completed" and status.get("report_completed") is True, status
    outcomes = read(run / "iteration_outcomes.json", {})
    if data == "dataset":
        assert len(outcomes) == loops and all(r.get("outcome") == "completed" for r in outcomes.values()), outcomes
    assert (run / "report.md").stat().st_size > 100
    assert read(run / "registry_status.json", {}).get("status") == "synced"
    roles = {role(c["stage"]) for c in calls if c["status"] == "completed"}
    assert {r.replace("interpreter", "interpret") for r in STAGES} <= roles
    assert ledger and all(row["model"] == MODEL for row in ledger)
    for stage in STAGES:
        name = role(stage)
        receipts = [r for r in ledger if role(r["stage"]) == name]
        assert any((r.get("response_model") or "").split("/")[-1] == MODEL for r in receipts), name
    frozen = read(run / "config.json")
    assert frozen["data_mode"] == data and frozen["knowledge_mode"] == knowledge
    assert frozen["stage_models"] == live_batch["profiles"]
    assert frozen.get('combination_plan') == combination
    if frozen.get('partition_policy') == 'two_way_stratified_v1':
        assert frozen['validation_partition'] is None
        assert status.get('final_validation') is None
        assert not (run / 'validation_partition.json').exists()
        assert not (run / 'final_validation.json').exists()
    if combination:
        from memstara.combinations import loop_flavors
        schedule_audit = []
        for position in range(1, loops + 1):
            expected = loop_flavors(combination, position)
            actual = read(run / f'loop_{position}_flavors.json')
            assert actual['combination'] == expected['combination']
            assert actual['repetition'] == expected['repetition']
            assert [a['id'] for a in actual['agents']] == [a['id'] for a in expected['agents']]
            schedule_audit.append({'position': position, 'pipeline': actual['combination'],
                                   'replicate': actual['repetition']})
        (area / 'schedule_audit.json').write_text(json.dumps(schedule_audit, indent=2))
        from memstara.feature_reproduction import replay
        reproduction = replay(run / 'feature_reproduction')
        (area / 'feature_reproduction_audit.json').write_text(json.dumps(reproduction, indent=2))
        assert reproduction['status'] == 'verified'
        assert reproduction['accepted_extractions_validated'] == loops
        assert reproduction['random_loops_replayed'] == (loops if study == 'heart_random' else 0)
    assert summary["input_tokens"] > 0 and summary["output_tokens"] > 0
    if pytestconfig.getoption('--live-audit-io'):
        from memstara.trace.diagnose import inspect
        audit = inspect(run)
        (area / 'input_output_audit.json').write_text(json.dumps(audit, indent=2))
        assert audit['request_evidence_complete'], audit['issues']
        if pytestconfig.getoption('--live-pause-resume'):
            events = [json.loads(line) for line in (run / 'request_events.jsonl').read_text().splitlines()]
            expected_unobserved = {f"{e['request_id']}: response unobserved (cancelled)"
                                   for e in events if e.get('reason') == 'user_pause'}
            assert not (set(audit['payload_issues']) - expected_unobserved), audit['payload_issues']
            # Cancellation has no observed provider output; retain that fact in
            # the audit rather than labelling response evidence complete.
        else:
            assert audit['service_io_evidence_complete'], audit['payload_issues']
        assert audit['stage_evidence_complete'], audit['stage_issues']
        assert {r['loop'] for r in audit['requests'] if r['loop'] is not None} >= set(range(1, loops + 1))

    async def persisted():
        connection = await asyncpg.connect(database, timeout=10)
        try:
            tag = frozen["run_tag"]
            row = await connection.fetchrow("SELECT status, report FROM memstara_executions WHERE run_tag=$1", tag)
            assert row and row["status"] == "completed" and row["report"]
            count = await connection.fetchval("SELECT count(*) FROM memstara_execution_costs WHERE run_tag=$1", tag)
            assert count == len(ledger)
            if study == "synthetic_paths":
                results = await connection.fetch("SELECT evaluation FROM memstara_results WHERE run_tag=$1", tag)
                scores = []
                for result in results:
                    ev = result["evaluation"]
                    ev = json.loads(ev) if isinstance(ev, str) else ev
                    novelty = ev["knowledge_provenance"]["novelty"]
                    assert novelty["rankable"] and novelty["coverage"] == 1, novelty
                    assert novelty["paths"] and all(p.get("rationale") for p in novelty["paths"])
                    scores.append(novelty)
                assert scores
                (area / "novelty_audit.json").write_text(json.dumps(scores, indent=2))
        finally:
            await connection.close()
    asyncio.run(persisted())
    if data == "proposal":
        assert status["empirical_evaluation"]["metrics"] is None
        assert all(c["computation_status"] == "not_executed" for c in calls)
        for stage in STAGES:
            output = read(run / "proposal_io" / "loop-0001" / f"{stage}.output.json")
            assert output["status"] == "completed" and output["model"] == MODEL
            if knowledge == "llm_only":
                assert output["output"]["source_ids"] == []
    else:
        tools = [tool for call in read(run / "runs.json", []) for tool in call.get("actual_tools", [])]
        assert "train_and_score" in tools
        if knowledge == "llm_only":
            assert not any(tool.startswith("okf_") for tool in tools), "No-corpus mode invoked retrieval"
        elif study != "heart_random":
            assert "okf_read" in tools, "The supplied corpus was not actually read"
        if study == "heart_random":
            hypothesis_tools = [tool for call in read(run / "runs.json", [])
                                if call.get("stage", "").startswith(("question", "hypothesis"))
                                for tool in call.get("actual_tools", [])]
            assert not any(tool.startswith("okf_") or tool in ("match_concept", "match_concepts")
                           for tool in hypothesis_tools), "Random selection accessed knowledge/matching"
        async def measured():
            connection = await asyncpg.connect(database, timeout=10)
            try:
                tag = read(run / "config.json")["run_tag"]
                rows = await connection.fetch(
                    "SELECT trial, auc, interpretation, evaluation FROM memstara_results WHERE run_tag=$1", tag)
                persisted = await connection.fetchval(
                    "SELECT count(*) FROM memstara_execution_costs WHERE run_tag=$1", tag)
                assert rows and all(r["auc"] is not None and r["interpretation"] for r in rows)
                assert {r["trial"] for r in rows} == set(range(loops)), "Missing per-Loop measured result"
                assert persisted == len(ledger)
                seed_audit = []
                for row in rows:
                    evaluation = row['evaluation']
                    evaluation = json.loads(evaluation) if isinstance(evaluation, str) else evaluation
                    evaluation = evaluation['evaluation']
                    if frozen.get('partition_policy') == 'two_way_stratified_v1':
                        assert evaluation['score_scope'] == 'two_way_test'
                        assert len(evaluation['replicates']) == 1
                        assert evaluation['validation_reserve'] == {}
                    assert evaluation['classifier_seed_policy'] == 'split_seed_v1'
                    for replicate in evaluation['replicates']:
                        seed = replicate['seed']
                        assert seed == replicate['effective_random_state'] == replicate['parameters']['random_state']
                        seed_audit.append({'trial': row['trial'], 'split_seed': seed,
                                           'classifier_random_state': replicate['effective_random_state']})
                assert seed_audit, 'No persisted classifier seed evidence'
                (area / 'classifier_seed_audit.json').write_text(json.dumps(seed_audit, indent=2))
            finally:
                await connection.close()
        asyncio.run(measured())
    # Keep the unique schema and all artifacts as auditable live execution evidence.
    summary['validation_status'] = 'passed'
    (area / "acceptance.json").write_text(json.dumps(summary, indent=2))


def test_private_hiv_pipeline(live_batch, monkeypatch, pytestconfig):
    if not pytestconfig.getoption('--live-private-research'):
        pytest.skip('Private HIV acceptance requires an explicit local research contract')
    test_real_haiku_pipeline(live_batch, monkeypatch, pytestconfig, 'private_hiv', 'okf', 'dataset')
