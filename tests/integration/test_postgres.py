"""Database schema, claim concurrency and measured-result persistence contracts."""

import asyncio
import json

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
