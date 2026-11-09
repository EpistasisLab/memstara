"""Real PostgreSQL transactions with synthetic Motoro evidence; no model requests."""

import asyncio
import json
from pathlib import Path
import uuid

import pytest

from memstara import experiment_registry as registry
from memstara.execution_journal import save_call
from memstara.pipeline.checkpoint import atomic_json

pytestmark = pytest.mark.integration


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    from motoro import runner
    from memstara import paths

    root = tmp_path / 'run'
    root.mkdir()
    (root / 'config.json').write_text('{"run_tag":"incremental-test"}')
    counter = {'runs': 0, 'steps': 0}

    async def get_run(identifier):
        counter['runs'] += 1
        return {'id': str(identifier), 'status': 'completed'}

    async def get_steps(identifier):
        counter['steps'] += 1
        return [{'run_id': str(identifier), 'output': 'saved synthetic evidence'}]

    monkeypatch.setattr(runner, 'get_run', get_run)
    monkeypatch.setattr(runner, 'get_run_steps', get_steps)
    monkeypatch.setattr(registry, 'core_record', lambda row: row)
    monkeypatch.setattr(paths, 'DEFAULT_OUTPUT_DIR', tmp_path)

    def add(number, *, receipt_id=None, tokens=10):
        call = {'run_id': str(uuid.uuid4()), 'stage': 'hypothesis', 'status': 'completed',
                'loop': number, 'started_at': number, 'prompt': 'synthetic prompt'}
        save_call(root, call)
        with (root / 'cost_ledger.jsonl').open('a') as stream:
            stream.write(json.dumps({'id': receipt_id or str(number), 'tokens': tokens}) + '\n')
        return call

    return root, counter, add


@pytest.mark.asyncio
@pytest.mark.parametrize('history', [5, 100, 1000])
async def test_new_and_resumed_runs_only_fetch_new_evidence(database, synthetic, monkeypatch, history):
    root, counter, add = synthetic
    calls = [add(n) for n in range(1, history + 1)]
    old_artifact = root / 'old-evidence.json'
    old_artifact.write_text('{"saved":true}')
    await registry.sync_after_agent(root, call=calls[-1])
    assert counter == {'runs': history, 'steps': history}
    counter.update(runs=0, steps=0)
    new = add(history + 1)
    original_open, original_rglob = Path.open, Path.rglob

    def guarded_open(path, *args, **kwargs):
        assert path != old_artifact, 'Routine mirror reread historical artifact bytes'
        return original_open(path, *args, **kwargs)

    def guarded_rglob(path, *args, **kwargs):
        assert path != root, 'Routine mirror recursively scanned the whole execution'
        return original_rglob(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', guarded_open)
        patch.setattr(Path, 'rglob', guarded_rglob)
        await registry.sync_after_agent(root, call=new)
    assert counter == {'runs': 1, 'steps': 1}
    metric = json.loads((root / 'registry_metrics.jsonl').read_text().splitlines()[-1])
    assert metric['mode'] == 'incremental'
    assert metric['calls_loaded'] == 1 and metric['cost_receipts_read'] == 1
    assert await database.fetchval('SELECT count(*) FROM memstara_execution_agents') == history + 1
    assert await database.fetchval('SELECT count(*) FROM memstara_execution_costs') == history + 1

    # Process restart invalidates disposable state and backfills once. The next
    # completion must immediately return to constant per-call evidence reads.
    registry.mirror_state(root)['cache'] = None
    await registry.sync_after_agent(root, call=new)
    counter.update(runs=0, steps=0)
    await registry.sync_after_agent(root, call=add(history + 2))
    assert counter == {'runs': 1, 'steps': 1}


@pytest.mark.asyncio
async def test_rollback_preserves_unmirrored_calls_and_cost_conflicts(database, synthetic):
    root, _, add = synthetic
    first = add(1)
    await registry.sync_after_agent(root, call=first)
    valid_ledger = (root / 'cost_ledger.jsonl').read_bytes()
    second = add(2, receipt_id='1', tokens=999)
    with pytest.raises(ValueError, match='cost receipt changed'):
        await registry.sync_after_agent(root, call=second)
    assert await database.fetchval('SELECT count(*) FROM memstara_execution_agents') == 1
    assert registry.mirror_state(root)['cache'] is None
    (root / 'cost_ledger.jsonl').write_bytes(valid_ledger + b'{"id":"2","tokens":10}\n')
    await registry.sync_after_agent(root, call=add(3))
    assert await database.fetchval('SELECT count(*) FROM memstara_execution_agents') == 3
    assert await database.fetchval('SELECT count(*) FROM memstara_execution_costs') == 3


@pytest.mark.asyncio
async def test_concurrent_completions_and_changed_artifacts_are_retained(database, synthetic):
    root, counter, add = synthetic
    first = add(1)
    await registry.sync_after_agent(root, call=first)
    evidence = root / 'new-evidence.json'
    atomic_json(evidence, {'value': 1})
    second, third = add(2), add(3)
    await asyncio.gather(registry.sync_after_agent(root, call=second), registry.sync_after_agent(root, call=third))
    assert await database.fetchval('SELECT count(*) FROM memstara_execution_agents') == 3
    assert await database.fetchval('SELECT count(*) FROM memstara_execution_costs') == 3
    original_hash = await database.fetchval('SELECT sha256 FROM memstara_execution_artifacts WHERE path=$1', str(evidence))
    atomic_json(evidence, {'value': 2})
    await registry.sync_after_agent(root, call=add(4))
    assert await database.fetchval('SELECT sha256 FROM memstara_execution_artifacts WHERE path=$1', str(evidence)) != original_hash
    # Final full reconciliation still verifies historical receipts, even though
    # they were not re-read during every ordinary completion.
    ledger = root / 'cost_ledger.jsonl'
    ledger.write_text(ledger.read_text().replace('"tokens": 10', '"tokens": 11', 1))
    with pytest.raises(ValueError, match='cost receipt changed'):
        await registry.sync(root)
