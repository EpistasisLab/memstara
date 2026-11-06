"""Large evidence uses bounded cursor transfers without changing live-screen limits."""
import asyncio
import json
import sys
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import export_records as records


def connection(monkeypatch):
    conn = MagicMock()
    conn.transaction.return_value = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'run_tag': 'saved', 'configuration': '{}'})
    conn.cursor = AsyncMock()

    async def guarded(which, callback, fallback):
        assert which == 'memstara'
        return await callback(conn)

    monkeypatch.setattr(records.pools, 'guarded', guarded)
    return conn


def test_results_are_batched_ordered_lossless_and_decoded_off_loop(monkeypatch):
    conn = connection(monkeypatch)
    source = [{'result_id': i, 'evaluation': json.dumps({'text': 'x' * 10000, 'index': i})} for i in range(19)]
    cursor = AsyncMock()
    cursor.fetch.side_effect = [source[:8], source[8:16], source[16:], []]
    conn.cursor.return_value = cursor
    owner = threading.get_ident()
    threads = []

    def decode(row):
        threads.append(threading.get_ident())
        return {**row, 'evaluation': json.loads(row['evaluation'])}

    result = asyncio.run(records.results(['saved'], decode))
    assert [row['result_id'] for row in result] == list(range(19))
    assert result[-1]['evaluation'] == {'text': 'x' * 10000, 'index': 18}
    assert all(thread != owner for thread in threads)
    conn.transaction.assert_called_once_with(isolation='repeatable_read', readonly=True)
    conn.execute.assert_awaited_once_with("SET LOCAL statement_timeout = '30000'", timeout=30)
    assert all(call.args == (8,) and call.kwargs == {'timeout': 30} for call in cursor.fetch.await_args_list)
    conn.transaction.return_value.__aexit__.assert_awaited_once()


def test_registry_uses_snapshot_results_without_reading_them_again(monkeypatch):
    conn = connection(monkeypatch)
    cursors = []
    for source in [[{'agent_run_id': 'a', 'evidence': '{"kept":true}'}],
                   [{'id': 'c', 'receipt': '{"usd":0.01}'}], [{'path': '/saved'}]]:
        cursor = AsyncMock()
        cursor.fetch.side_effect = [source, []]
        cursors.append(cursor)
    conn.cursor.side_effect = cursors
    value = asyncio.run(records.execution('saved'))
    assert value['agents'][0]['evidence'] == {'kept': True}
    assert value['costs'][0]['receipt'] == {'usd': 0.01}
    assert value['artifacts'] == [{'path': '/saved'}]
    assert 'results' not in value
    assert all('memstara_results' not in call.args[0] for call in conn.cursor.await_args_list)


def test_missing_registry_remains_explicit_404(monkeypatch):
    conn = connection(monkeypatch)
    conn.fetchrow.return_value = None
    with pytest.raises(HTTPException) as error:
        asyncio.run(records.execution('missing'))
    assert error.value.status_code == 404


def test_partial_cursor_failure_never_returns_partial_success(monkeypatch):
    conn = connection(monkeypatch)
    cursor = AsyncMock()
    cursor.fetch.side_effect = [[{'result_id': 1}], TimeoutError()]
    conn.cursor.return_value = cursor

    async def guarded(which, callback, fallback):
        try:
            return await callback(conn)
        except TimeoutError:
            return fallback

    monkeypatch.setattr(records.pools, 'guarded', guarded)
    with pytest.raises(HTTPException) as error:
        asyncio.run(records.results(['saved'], dict))
    assert error.value.status_code == 503
    assert 'saved results' in error.value.detail
    assert 'No partial file' in error.value.detail
    assert conn.transaction.return_value.__aexit__.await_args.args[0] is TimeoutError
