"""Exercise V1 tools in an isolated PostgreSQL schema, rolled back on every exit.

Run from the repo root with the project interpreter. No cohort rows or LLM calls.
"""

import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import asyncpg
from memstara.blackboard import SCHEMA, dsn
from memstara.mcp_servers import blackboard as tools
from memstara.mcp_servers.ml import train_and_score


async def main():
    conn = await asyncpg.connect(dsn(), timeout=5)
    transaction = conn.transaction()
    await transaction.start()
    original_connect = asyncpg.connect

    class Shared:
        def __getattr__(self, name):
            return getattr(conn, name)

        async def close(self):
            pass

    async def shared(*args, **kwargs):
        return Shared()

    try:
        schema = "test_v1_" + uuid.uuid4().hex
        await conn.execute(f"CREATE SCHEMA {schema}")
        await conn.execute(f"SET LOCAL search_path TO {schema}")
        await conn.execute(SCHEMA)
        asyncpg.connect = shared
        with tempfile.TemporaryDirectory() as directory:
            os.environ["MEMSTARA_OUTPUT_DIR"] = directory
            os.environ.pop("MEMSTARA_RUN_CONFIG", None)
            p = Path(directory) / "subset.csv"
            p.write_text("a,outcome\n" + "".join(f"{i % 10},{int(i % 10 > 4)}\n" for i in range(80)))
            created = json.loads(await tools.create_task("v1", 0, "test", "hypothesis", ["a"], "outcome"))
            assert "error" not in created, created
            tid = created["task_id"]
            claimed = json.loads(await tools.claim_task("data", "v1", "data#1"))
            assert claimed["task_id"] == tid
            result = json.loads(await tools.submit_result(tid, subset_path=str(p), columns_used=["a"], worker="data#1"))
            assert result.get("ok"), result
            await tools.claim_task("ml", "v1", "ml#1")
            measured = json.loads(train_and_score(str(p), "outcome"))
            assert "error" not in measured, measured
            result = json.loads(await tools.submit_result(tid, auc=0.123, model="invented", worker="ml#1"))
            assert result.get("ok"), result
            claim = json.loads(await tools.claim_task("interpret", "v1", "interpret#1"))
            assert claim["auc"] == measured["auc"] and claim["model"] == "xgboost"
            assert claim["evaluation"]["seed"] == 42
            assert claim["evaluation"]["explanation"]["shap"]["method"] == "XGBoost TreeSHAP"
            result = json.loads(
                await tools.submit_result(tid, interpretation="Synthetic evaluation", worker="interpret#1")
            )
            assert result.get("ok"), result
            rows = json.loads(await tools.read_results("v1"))
            assert rows["count"] == 1 and rows["results"][0]["evaluation"]["seed"] == 42
            bad = Path(directory) / "bad.csv"
            bad.write_text("a,outcome\n1,0\n2,0\n3,1\n")
            created = json.loads(await tools.create_task("v1", 1, "bad", "hypothesis", ["a"], "outcome"))
            bad_id = created["task_id"]
            await tools.claim_task("data", "v1", "data#2")
            await tools.submit_result(bad_id, subset_path=str(bad), columns_used=["a"], worker="data#2")
            await tools.claim_task("ml", "v1", "ml#2")
            failure = json.loads(train_and_score(str(bad), "outcome"))
            assert failure["status"] == "failed"
            rejected = json.loads(await tools.submit_result(bad_id, worker="someone-else"))
            assert "error" in rejected
            recorded = json.loads(await tools.submit_result(bad_id, worker="ml#2"))
            assert recorded["status"] == "failed" and recorded["ok"]
            row = await conn.fetchrow("SELECT status,error,claimed_by,auc FROM memstara_blackboard WHERE task_id=$1", bad_id)
            assert row["status"] == "failed" and row["error"] and not row["claimed_by"] and row["auc"] is None
            assert json.loads(await tools.read_results("v1"))["count"] == 1
            created = json.loads(await tools.create_task("v1", 2, "no-artifact", "hypothesis", ["a"], "outcome"))
            missing_id = created["task_id"]
            await tools.claim_task("data", "v1", "data#3")
            await tools.submit_result(missing_id, subset_path=str(Path(directory) / "not-created.csv"),
                                      columns_used=["a"], worker="data#3")
            await tools.claim_task("ml", "v1", "ml#3")
            assert "error" in json.loads(await tools.submit_result(missing_id, worker="ml#3"))
            assert "error" in json.loads(await tools.submit_result(missing_id, error="No measured evaluation"))
            failure = json.loads(await tools.submit_result(missing_id, worker="ml#3", error="No measured evaluation"))
            assert failure["status"] == "failed"
            qid = await conn.fetchval(
                "INSERT INTO memstara_questions (text,text_key,writer) "
                "VALUES ('q','q','hypothesis#2') RETURNING question_id"
            )
            q = json.loads(await tools.claim_question("v1", "h2", question_id=qid))
            assert q["question_id"] == qid, q
        print(
            "PASS: additive schema, task/data/ML/interpret/report contract, "
            "measured artifact overrides LLM numbers, exact question claim"
        )
    finally:
        asyncpg.connect = original_connect
        await transaction.rollback()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
