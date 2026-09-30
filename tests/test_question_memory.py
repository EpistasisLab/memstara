"""Confirmation and control-plane blockers require no data or model calls."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from memstara.control import question_memory as memory


def test_unconfirmed_request_never_opens_database(monkeypatch):
    connect = Mock()
    monkeypatch.setattr(memory.asyncpg, "connect", connect)
    import asyncio

    with pytest.raises(ValueError, match="confirmation"):
        asyncio.run(memory.clear({}))
    connect.assert_not_called()


@pytest.mark.parametrize("execution", [{"execution_state": "running"}, {"execution_state": "paused"}])
def test_running_and_paused_control_processes_block_clear(execution):
    workspace = SimpleNamespace(lock=threading.RLock(), list=lambda: [{"running": execution}])
    runs = SimpleNamespace(running=lambda: None)
    with pytest.raises(memory.MemoryConflict, match="End all"):
        memory.handle(
            workspace,
            runs,
            {
                "confirm": "CLEAR QUESTION MEMORY",
                "request_id": "00000000-0000-0000-0000-000000000001",
                "token": "a" * 64,
            },
        )
