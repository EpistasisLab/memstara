"""Database schema, claim concurrency and measured-result persistence contracts."""

import asyncio
import json
import uuid

import pytest

from memstara.blackboard import BoardBusy, SCHEMA, run_lock
from memstara.mcp_servers import blackboard as board
from memstara.mcp_servers.ml import train_and_score

pytestmark = pytest.mark.integration


async def create(run="test-run", trial=0):
    result = json.loads(
        await board.create_task(run, trial, "synthetic", "Signal predicts outcome", ["signal"], "outcome")
    )
    assert "error" not in result, result
    return result["task_id"]


async def test_schema_reapplication_preserves_data(database):
    task = await create()
    await database.execute(SCHEMA)
    assert await database.fetchval("SELECT count(*) FROM memstara_blackboard WHERE task_id=$1", task) == 1


async def test_concurrent_claims_are_unique_and_scoped(database):
    expected = {await create(trial=i) for i in range(5)}
    other = await create("other-run")
    claims = await asyncio.gather(*(board.claim_task("data", "test-run", f"worker-{i}") for i in range(8)))
    claimed = [json.loads(item)["task_id"] for item in claims if json.loads(item).get("task_id")]
    assert len(claimed) == len(set(claimed)) == 5
    assert set(claimed) == expected
    assert json.loads(await board.claim_task("data", "other-run", "other"))["task_id"] == other


async def test_run_lock_is_exclusive_and_released(database):
    async with run_lock("exclusive"):
        with pytest.raises(BoardBusy):
            async with run_lock("exclusive"):
                pytest.fail("Two drivers acquired the same run")
    async with run_lock("exclusive"):
        pass


async def test_pipeline_persists_measured_evidence_and_checks_ownership(database, tmp_path):
    subset = tmp_path / "subset.csv"
    subset.write_text("signal,outcome\n" + "".join(f"{i % 10},{int(i % 10 > 4)}\n" for i in range(80)))
    task = await create()
    assert json.loads(await board.claim_task("data", "test-run", "data-worker"))["task_id"] == task
    rejected = json.loads(
        await board.submit_result(task, subset_path=str(subset), columns_used=["signal"], worker="wrong")
    )
    assert "error" in rejected
    assert json.loads(
        await board.submit_result(task, subset_path=str(subset), columns_used=["signal"], worker="data-worker")
    )["ok"]
    assert json.loads(await board.claim_task("ml", "test-run", "ml-worker"))["task_id"] == task
    measured = json.loads(train_and_score(str(subset), "outcome"))
    assert "error" not in measured, measured
    assert json.loads(await board.submit_result(task, auc=0.123, model="fabricated", worker="ml-worker"))["ok"]
    claimed = json.loads(await board.claim_task("interpret", "test-run", "interpreter"))
    assert claimed["auc"] == measured["auc"]
    assert claimed["model"] == measured["model"]
    assert claimed["evaluation"]["explanation"]["shap"]["method"] == "XGBoost TreeSHAP"
    assert json.loads(await board.submit_result(task, interpretation="Synthetic result", worker="interpreter"))["ok"]
    result = json.loads(await board.read_results("test-run"))
    assert result["count"] == 1
    assert result["results"][0]["evaluation"]["seed"] == 42


async def test_proposal_final_reconciliation_uses_local_stage_evidence(database, tmp_path, monkeypatch):
    from memstara.experiment_registry import reconcile
    from motoro import runner

    async def forbidden(*args, **kwargs):
        raise AssertionError("Proposal adapter IDs are not Motoro agent runs")
    monkeypatch.setattr(runner, 'get_run', forbidden)
    monkeypatch.setattr(runner, 'get_run_steps', forbidden)
    config = {'run_tag': 'proposal-registry', 'mode': 'proposal', 'planning_adapter': 'proposal_v1',
              'empirical_evaluation': {'status': 'not_executed', 'metrics': None}, 'prompts': {}}
    call = {'run_id': str(uuid.uuid4()), 'stage': 'report', 'loop': 1, 'mode': 'proposal',
            'execution_adapter': 'proposal_text', 'core_run_id': None, 'computation_status': 'not_executed',
            'model': 'fixture', 'provider': 'openai', 'status': 'completed'}
    io = tmp_path / 'proposal_io' / 'loop-0001'
    io.mkdir(parents=True)
    (tmp_path / 'config.json').write_text(json.dumps(config))
    (tmp_path / 'calls_checkpoint.json').write_text(json.dumps([call]))
    (tmp_path / 'pipeline_status.json').write_text(json.dumps({'status': 'completed'}))
    (tmp_path / 'report.md').write_text('Research proposal, not measured findings')
    (io / 'report.input.json').write_text(json.dumps({'profile': {'model': 'fixture', 'provider': 'openai'}}))
    (io / 'report.output.json').write_text(json.dumps(call))
    assert await reconcile(tmp_path)
    evidence = json.loads(await database.fetchval(
        "SELECT evidence FROM memstara_execution_agents WHERE run_tag='proposal-registry'"))
    assert evidence['adapter'] == 'proposal_text'
    assert evidence['output']['run_id'] == call['run_id']
    assert await database.fetchval(
        "SELECT status FROM memstara_executions WHERE run_tag='proposal-registry'") == 'completed'


async def test_registry_concurrent_cold_start_and_same_run_mirrors(database, tmp_path):
    from memstara.experiment_registry import sync
    roots = []
    for number in range(4):
        root = tmp_path / f'pipeline-{number}'
        root.mkdir()
        (root / 'config.json').write_text(json.dumps({'run_tag': f'parallel-{number}'}))
        (root / 'pipeline_status.json').write_text('{"status":"running"}')
        (root / 'cost_ledger.jsonl').write_text('{"id":"receipt-1","tokens":123}\n')
        roots.append(root)
    # Cold start, different pipelines, and overlapping mirrors of the same run.
    await asyncio.wait_for(asyncio.gather(*(
        sync(root, evidence=False) for _ in range(3) for root in roots
    )), timeout=20)
    assert await database.fetchval('SELECT count(*) FROM memstara_executions') == 4
    assert await database.fetchval('SELECT count(*) FROM memstara_execution_costs') == 4
    for root in roots:
        assert json.loads((root / 'registry_status.json').read_text())['status'] == 'synced'


async def test_registry_readiness_does_not_block_an_active_writer(database):
    import asyncpg
    from memstara.blackboard import dsn
    from memstara.experiment_registry import initialize
    await initialize(database)
    other = await asyncpg.connect(dsn())
    try:
        async with database.transaction():
            # A GRANT needs to modify pg_class. Routine readiness must only read it.
            await database.execute('LOCK TABLE memstara_executions IN ACCESS EXCLUSIVE MODE')
            await asyncio.wait_for(initialize(other), timeout=2)
    finally:
        await other.close()


async def test_board_read_preserves_final_validation_candidate(database):
    from memstara.final_validation import eligible_tasks
    task = await create('final-validation-handoff')
    evaluation = {'auc': 0.75, 'ml_configuration': {'effective': {'primary_model': 'logistic_regression'}}}
    await database.execute(
        "UPDATE memstara_blackboard SET status='done', subset_path=$2, columns_used=$3::jsonb, "
        "evaluation=$4::jsonb WHERE task_id=$1",
        task, '/synthetic/saved.csv', json.dumps(['signal', 'outcome']), json.dumps(evaluation))
    state = json.loads(await board.read_board('final-validation-handoff'))
    candidates = eligible_tasks(state['tasks'])
    assert [row['task_id'] for row in candidates] == [task]
    assert candidates[0]['subset_path'] == '/synthetic/saved.csv'
