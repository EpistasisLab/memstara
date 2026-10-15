"""Registry privacy boundaries and explicit identity; no model APIs or DB needed."""
import json
from pathlib import Path

import pytest

from memstara.experiment_registry import artifacts, identity, register_experiment


def test_artifacts_never_index_outside_output_root(tmp_path):
    output=tmp_path/'outputs'
    run=output/'runs'/'one'
    run.mkdir(parents=True)
    secret=tmp_path/'private.txt'
    secret.write_text('not an artifact')
    (run/'escape').symlink_to(secret)
    (run/'config.json').write_text('{}')
    dataset=output/'subset.csv'
    dataset.write_text('x,y\n1,0\n')
    (output/'subset.evaluation.json').write_text('{}')
    rows=artifacts(run,{'subset_path':str(dataset),'outside':str(secret)},output)
    names={Path(r[0]).name for r in rows}
    assert names=={'config.json','subset.csv','subset.evaluation.json'}
    assert all(len(r[1])==64 for r in rows)


def test_binding_is_explicit_not_inferred_from_folder(tmp_path):
    config={'run_tag':'run-1'}
    assert identity(config,tmp_path)[:2]==('standalone:run-1','C01')
    (tmp_path/'experiment_binding.json').write_text(json.dumps({'experiment_id':'pilot','combination_id':'C32'}))
    assert identity(config,tmp_path)[:2]==('pilot','C32')


@pytest.mark.asyncio
async def test_cannot_redefine_registered_experiment():
    from unittest.mock import AsyncMock
    conn=AsyncMock()
    conn.fetchval.return_value='{"planned_runs":64}'
    with pytest.raises(ValueError,match='definition changed'):
        await register_experiment(conn,'pilot',{'planned_runs':32},{})


@pytest.mark.asyncio
async def test_ready_registry_never_changes_schema_or_permissions():
    from unittest.mock import AsyncMock, Mock
    from memstara.experiment_registry import initialize
    conn = AsyncMock()
    conn.is_in_transaction = Mock(return_value=False)
    conn.fetchval.return_value = True
    await initialize(conn)
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_initialization_rejects_execution_transaction():
    from unittest.mock import AsyncMock, Mock
    from memstara.experiment_registry import initialize
    conn = AsyncMock()
    conn.is_in_transaction = Mock(return_value=True)
    with pytest.raises(RuntimeError, match='precede'):
        await initialize(conn)
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_deadlock_retries_only_the_mirror(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock
    from memstara import experiment_registry as registry
    attempt = AsyncMock(side_effect=[registry.asyncpg.DeadlockDetectedError(), None])
    monkeypatch.setattr(registry, '_sync', attempt)
    monkeypatch.setattr(registry.asyncio, 'sleep', AsyncMock())
    await registry.sync(tmp_path, evidence=False)
    assert attempt.await_count == 2
    attempt.assert_awaited_with(tmp_path, evidence=False)


@pytest.mark.asyncio
async def test_exhausted_conflict_retains_results_and_records_pending(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock
    from memstara import experiment_registry as registry
    evidence = tmp_path / 'execution.json'
    evidence.write_text('{"status":"completed"}')
    attempt = AsyncMock(side_effect=registry.asyncpg.DeadlockDetectedError())
    monkeypatch.setattr(registry, '_sync', attempt)
    monkeypatch.setattr(registry.asyncio, 'sleep', AsyncMock())
    await registry.sync_after_agent(tmp_path)
    assert attempt.await_count == 5
    assert json.loads((tmp_path / 'registry_status.json').read_text())['status'] == 'pending'
    assert evidence.read_text() == '{"status":"completed"}'


@pytest.mark.asyncio
async def test_integrity_errors_are_neither_retried_nor_hidden(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock
    from memstara import experiment_registry as registry
    attempt = AsyncMock(side_effect=ValueError('Frozen execution configuration changed'))
    monkeypatch.setattr(registry, '_sync', attempt)
    with pytest.raises(ValueError, match='Frozen'):
        await registry.sync_after_agent(tmp_path)
    assert attempt.await_count == 1
