"""Telemetry polls must never materialize unrelated run history."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer' / 'api'))
import scene
import queries


def fetch_facts(ids, **kwargs):
    connection = AsyncMock()
    connection.fetch.return_value = []
    async def guarded(store, callback, fallback):
        return await callback(connection)
    with patch.object(scene.pools, 'guarded', guarded):
        asyncio.run(scene._core_facts(ids, **kwargs))
    return connection


def test_selected_run_is_filtered_before_json_materialization():
    conn = fetch_facts(['11111111-1111-1111-1111-111111111111'])
    statements = [call.args[0] for call in conn.execute.call_args_list]
    materialization = next(sql for sql in statements if 'CREATE TEMP TABLE flat AS' in sql)
    assert 'JOIN selected_run_ids selected ON selected.id = s.run_id' in materialization
    assert not any(sql.startswith('DELETE FROM flat') for sql in statements)
    assert 'ANALYZE selected_run_ids' in statements
    assert 'WITH scoped_steps AS MATERIALIZED' in materialization
    scoped_source = materialization.split(')\nSELECT s.run_id')[0]
    assert 'json_typeof' not in scoped_source and 'json_to_record' not in scoped_source


def test_new_run_empty_scope_cannot_fall_back_to_all_history():
    conn = fetch_facts([])
    conn.executemany.assert_not_called()
    assert any(call.args[0] == queries.SCOPED_FLAT_TEMP_TABLE for call in conn.execute.call_args_list)


def test_task_history_keeps_old_calls_but_live_view_expires_them():
    historical = fetch_facts([], task_history=True)
    live = fetch_facts([])
    history_query = historical.fetch.call_args_list[3]
    live_query = live.fetch.call_args_list[3]
    assert 'f.started_at > now()' not in history_query.args[0]
    assert len(history_query.args) == 1
    assert 'f.started_at > now()' in live_query.args[0]
    assert len(live_query.args) == 2


def test_agent_counts_exclude_other_runs_unused_agents():
    conn = fetch_facts([])
    assert 'HAVING count(r.id) > 0' in conn.fetch.call_args_list[0].args[0]
