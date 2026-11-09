import json
import uuid

import pytest

from memstara.artifact_changes import acknowledge, changed, pending, watch
from memstara.execution_journal import load_calls, save_call
from memstara.experiment_registry import appended_costs


def test_per_agent_journal_recovers_over_legacy_without_rewriting_history(tmp_path):
    first = {'run_id': str(uuid.uuid4()), 'started_at': 1, 'status': 'running'}
    second = {'run_id': str(uuid.uuid4()), 'started_at': 2, 'status': 'completed'}
    old = json.dumps([first])
    (tmp_path / 'calls_checkpoint.json').write_text(old)
    save_call(tmp_path, {**first, 'status': 'completed', 'prompt': 'original instructions'})
    save_call(tmp_path, second)
    assert load_calls(tmp_path) == [{**first, 'status': 'completed', 'prompt': 'original instructions'}, second]
    assert (tmp_path / 'calls_checkpoint.json').read_text() == old


def test_journal_identity_tampering_fails_closed(tmp_path):
    call = {'run_id': str(uuid.uuid4())}
    save_call(tmp_path, call)
    path = tmp_path / 'call_records' / (call['run_id'] + '.json')
    path.write_text(json.dumps({'run_id': str(uuid.uuid4())}))
    with pytest.raises(ValueError, match='identity changed'):
        load_calls(tmp_path)


def test_cost_cursor_keeps_partial_receipt_and_backfills_replaced_file(tmp_path):
    path = tmp_path / 'cost_ledger.jsonl'
    path.write_bytes(b'{"id":"one"}\n{"id":')
    rows, cursor = appended_costs(path)
    assert rows == [{'id': 'one'}]
    with path.open('ab') as stream:
        stream.write(b'"two"}\n')
    rows, cursor = appended_costs(path, cursor)
    assert rows == [{'id': 'two'}]
    assert appended_costs(path, cursor)[0] == []
    replacement = tmp_path / 'new-ledger'
    replacement.write_text('{"id":"three"}\n')
    replacement.replace(path)
    assert appended_costs(path, cursor)[0] == [{'id': 'three'}]


def test_acknowledgement_does_not_drop_changes_during_transaction(tmp_path):
    watch(tmp_path)
    path = tmp_path / 'evidence.json'
    changed(path)
    observed = pending(tmp_path)
    changed(path)
    acknowledge(tmp_path, observed)
    assert path in pending(tmp_path)
    acknowledge(tmp_path, pending(tmp_path))
    assert pending(tmp_path) == {}


def test_explanation_model_lookup_does_not_read_other_agents(tmp_path, monkeypatch):
    import hashlib
    from pathlib import Path
    from memstara.specialist_explanation import model_records

    directory = tmp_path / 'models' / hashlib.sha256(b'current').hexdigest()
    directory.mkdir(parents=True)
    (directory / 'model-one.json').write_text('{"run_id":"current","model":"fixture"}')
    other = tmp_path / 'model-old.json'
    other.write_text('{"run_id":"old"}')
    original = Path.read_text

    def guarded(path, *args, **kwargs):
        assert path != other, 'An indexed current agent must not scan legacy history'
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', guarded)
    assert model_records(tmp_path, 'current') == [{'run_id': 'current', 'model': 'fixture'}]


@pytest.mark.asyncio
async def test_checkpoint_control_writes_do_not_copy_historical_phase_payloads(tmp_path):
    from memstara.pipeline.checkpoint import Checkpoint, RecoveryBlocked

    checkpoint = Checkpoint(tmp_path)
    payload = 'synthetic evidence ' * 100000

    async def work():
        return payload

    await checkpoint.phase('finished', work)
    checkpoint.call_started('next')
    assert checkpoint.path.stat().st_size < 4096
    checkpoint.call_finished('next')
    restored = Checkpoint(tmp_path, resume=True)

    async def forbidden():
        raise AssertionError('A completed phase must not run again')

    assert await restored.phase('finished', forbidden) == payload
    reference = restored.state['phases']['finished']['result_ref']
    (tmp_path / reference['path']).write_text('{}')
    with pytest.raises(RecoveryBlocked, match='integrity'):
        Checkpoint(tmp_path, resume=True)
