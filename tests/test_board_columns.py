# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. afc-forge has no board,
#   so there is no counterpart upstream.
"""The board's write path takes LISTS — the same comma guard as `slice_columns`.

`tests/test_slice_columns.py` guards the 02 path. The 03 path writes column names
through `create_task` and reads them back through `claim_task`, and until the
matcher was wired into the board pipeline no exact name ever reached it — the
hypothesis agent read names off `describe_dataset` by eye. Now the matcher hands
over `LAB__HDL CHOLESTEROL, DIRECT` verbatim, so `create_task` is on the path of
the same 158 columns.

Only the refusal is tested here. The list normalisation and the round trip happen
against Postgres, which these tests deliberately do not need — that half is
covered by `scripts/check_blackboard.py`, run by hand against a live board.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from memstara.mcp_servers import blackboard as tools_blackboard

pytestmark = pytest.mark.unit

#: `@mcp.tool()` wraps the function; `.fn` is the undecorated callable.
create_task = getattr(tools_blackboard.create_task, "fn", tools_blackboard.create_task)
submit_result = getattr(tools_blackboard.submit_result, "fn", tools_blackboard.submit_result)

COMMA = "LAB__HDL CHOLESTEROL, DIRECT"


def test_create_task_refuses_a_joined_string() -> None:
    """A comma-joined string must fail loudly, before any database call.

    Iterated as a string it would store a JSON array of single letters, and the
    data stage would then report 28 missing columns — a failure that reads like a
    naming problem and is not one.
    """
    result = json.loads(
        asyncio.run(create_task("t", 0, "p", "h", f"BMI, {COMMA}", "HIV_DETECTABLE"))
    )

    assert "error" in result
    assert "list" in result["error"]
    assert "task_id" not in result


def test_create_task_refuses_a_joined_concept_id_string() -> None:
    """The same guard covers okf_concept_ids, so one call cannot take two shapes."""
    result = json.loads(
        asyncio.run(create_task("t", 0, "p", "h", ["BMI"], "HIV_DETECTABLE", "a,b"))
    )

    assert "error" in result
    assert "task_id" not in result


def test_submit_result_refuses_joined_column_strings() -> None:
    """The data stage copies slice_columns' own arrays through; a string is a retype."""
    for kwargs in ({"columns_used": f"BMI,{COMMA}"}, {"columns_missing": f"BMI,{COMMA}"}):
        result = json.loads(asyncio.run(submit_result(1, **kwargs)))
        assert "error" in result, kwargs
        assert "list" in result["error"], kwargs
