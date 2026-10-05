"""Developer inspection must preserve run boundaries and distinguish missing evidence."""

import asyncio
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewer" / "api"))
import developer

RUN = "11111111-1111-1111-1111-111111111111"
ARCHIVE = {
    "calls": [{"run_id": RUN, "stage": "ml#1", "loop": 2, "seq": 1, "prompt": "Recorded input", "status": "completed"}]
}


def test_cross_execution_invocation_is_rejected_before_database_access():
    with (
        patch.object(developer.run_artifacts, "lookup", return_value=ARCHIVE),
        patch.object(developer.pools, "guarded", new_callable=AsyncMock) as guarded,
    ):
        with pytest.raises(HTTPException) as error:
            asyncio.run(developer.steps("chosen", uuid.uuid4()))
        assert error.value.status_code == 404
        guarded.assert_not_called()


def test_loop_filter_does_not_include_other_calls():
    with patch.object(developer.run_artifacts, "lookup", return_value=ARCHIVE):
        assert asyncio.run(developer.execution("chosen", 1))["calls"] == []
        call = asyncio.run(developer.execution("chosen", 2))["calls"][0]
        assert call["loop_source"] == "recorded"


def test_metadata_pagination_and_on_demand_full_payload():
    conn = AsyncMock()

    async def guarded(store, callback, fallback):
        assert store == "core"
        return await callback(conn)

    with (
        patch.object(developer.run_artifacts, "lookup", return_value=ARCHIVE),
        patch.object(developer.pools, "guarded", guarded),
    ):
        conn.fetch.return_value = [{"id": i} for i in range(51)]
        page = asyncio.run(developer.steps("chosen", RUN, 50))
        assert len(page["steps"]) == 50 and page["next_offset"] == 100
        query, identity, offset = conn.fetch.call_args.args
        assert "WHERE run_id=$1" in query and "row_to_json" not in query
        assert identity == uuid.UUID(RUN) and offset == 50
        payload = {
            "tool_call": {"calls": [{"tool": "train_and_score", "arguments": {"x": 1}, "result": {"auc": 0.7}}]},
            "input_data": "input",
            "output_data": "output",
        }
        conn.fetch.return_value = [{"record": json.dumps(payload)}]
        detail = asyncio.run(developer.steps("chosen", RUN, 3, True))
        assert detail["steps"] == [payload]
        assert "LIMIT 1" in conn.fetch.call_args.args[0]


def test_unavailable_database_is_not_empty_history():
    with (
        patch.object(developer.run_artifacts, "lookup", return_value=ARCHIVE),
        patch.object(developer.pools, "guarded", new_callable=AsyncMock, return_value=None),
    ):
        with pytest.raises(HTTPException) as error:
            asyncio.run(developer.steps("chosen", RUN))
        assert error.value.status_code == 503
