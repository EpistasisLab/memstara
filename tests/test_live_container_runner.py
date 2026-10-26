"""Acceptance uses container settings and never starts/replaces operating services."""
import asyncio
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('live_acceptance', ROOT / 'deployment/live_acceptance.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_checks_generated_database_addresses(monkeypatch):
    connections = []
    class Connection:
        async def execute(self, query):
            assert query == 'SELECT 1'
        async def close(self):
            connections.append('closed')
    async def connect(value, timeout):
        connections.append(value)
        assert timeout == 10
        return Connection()
    monkeypatch.setattr(runner.asyncpg, 'connect', connect)
    monkeypatch.setenv('MEMSTARA_DATABASE_URL', 'postgresql://board/db')
    monkeypatch.setenv('MOTORO_DATABASE_URL', 'postgresql+asyncpg://runtime/db')
    asyncio.run(runner.check_databases())
    assert connections == ['postgresql://board/db', 'closed', 'postgresql://runtime/db', 'closed']


def test_connection_failure_never_starts_paid_call_or_leaks_secret(monkeypatch, capsys):
    async def connect(*args, **kwargs):
        raise OSError('private-password')
    monkeypatch.setenv('MEMSTARA_DATABASE_URL', 'postgresql://private-password@board/db')
    monkeypatch.setattr(runner.asyncpg, 'connect', connect)
    monkeypatch.setattr(runner.subprocess, 'call', lambda *a: pytest.fail('must not start inference'))
    assert runner.main() == 1
    error = capsys.readouterr().err
    assert 'MEMSTARA_DATABASE_URL' in error and 'private-password' not in error


def test_runs_exactly_one_real_case(monkeypatch):
    async def checked():
        return None
    monkeypatch.setattr(runner, 'check_databases', checked)
    commands = []
    monkeypatch.setattr(runner.subprocess, 'call', lambda argv: commands.append(argv) or 0)
    assert runner.main() == 0
    assert len(commands) == 1
    assert '--run-live' in commands[0] and '--live-loops=1' in commands[0]
    assert 'synthetic-okf-dataset' in commands[0] and '--live-audit-io' in commands[0]
    shell = (ROOT / 'test-live.sh').read_text()
    assert 'run --rm --no-deps acceptance' in shell
    assert 'compose up' not in shell and 'compose down' not in shell
