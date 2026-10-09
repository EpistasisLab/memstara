"""Public Motoro step export preserves complete tool I/O with integrity references."""
import asyncio
from datetime import UTC, datetime
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

pytest.importorskip('motoro')
from motoro.models.run import AgentRun, RunStep, StepPhase
from memstara.pipeline import board
from memstara.pipeline.request_evidence import normalize
from memstara.trace.diagnose import inspect


def fixture_records():
    identifier = uuid4()
    run = AgentRun(id=identifier, status='completed')
    step = RunStep(id=uuid4(), run_id=identifier, sequence=1, phase=StepPhase.ACT,
                   input={'instruction': 'Synthetic'}, output={'answer': 'Full output'},
                   tool_call={'calls': [{'tool': 'synthetic_tool', 'arguments': {'column': 'X'},
                                        'result': {'rows': 8}, 'success': True}]},
                   llm_call={'model': 'synthetic'}, started_at=datetime.now(UTC), completed_at=datetime.now(UTC))
    return identifier, run, step


def test_orm_export_preserves_columns_without_loading_relationships():
    identifier, _, step = fixture_records()
    value = normalize(step)
    assert value['run_id'] == str(identifier)
    assert value['phase'] == 'act' and value['input'] == {'instruction': 'Synthetic'}
    assert value['tool_call']['calls'][0]['result'] == {'rows': 8}
    assert 'run' not in value


@pytest.fixture
def setup(tmp_path, monkeypatch):
    identifier, run, step = fixture_records()
    call = {'run_id': str(identifier), 'stage': 'hypothesis0', 'loop': 1, 'seq': 0,
            'prompt': 'Synthetic prompt', 'status': 'completed', 'allowed_tools': ['synthetic_tool']}
    root = tmp_path / 'trace'
    root.mkdir()
    monkeypatch.setattr(board, '_TRACE_DIR', root)
    monkeypatch.setattr(board, '_CALLS', [call])
    monkeypatch.setattr('motoro.runner.get_run', AsyncMock(return_value=run))
    monkeypatch.setattr('motoro.runner.get_run_steps', AsyncMock(return_value=[step]))
    monkeypatch.setattr(board, 'render', AsyncMock())
    return tmp_path, call, step


def test_trace_exports_machine_readable_stage_and_full_tool_results(setup):
    root, call, _ = setup
    asyncio.run(board._trace_one(call))
    assert call['trace_status'] == 'exported'
    saved = json.loads((root / call['step_evidence']['path']).read_text())
    assert saved['steps'][0]['tool_call']['calls'][0]['arguments'] == {'column': 'X'}
    assert saved['steps'][0]['tool_call']['calls'][0]['result'] == {'rows': 8}
    report = inspect(root)
    assert report['stage_evidence_complete']
    assert not report['service_io_evidence_complete']


def test_missing_steps_are_visible_without_blocking_saved_results(setup, monkeypatch):
    root, call, _ = setup
    monkeypatch.setattr('motoro.runner.get_run_steps', AsyncMock(return_value=[]))
    asyncio.run(board._trace_one(call))
    assert call['trace_status'] == 'unavailable'
    assert not call.get('traced') and not inspect(root)['stage_evidence_complete']


def test_edited_export_and_unfinished_step_cannot_certify_complete(setup):
    root, call, step = setup
    step.completed_at = None
    asyncio.run(board._trace_one(call))
    assert not inspect(root)['stage_evidence_complete']
    path = root / call['step_evidence']['path']
    path.write_text('{}')
    assert not inspect(root)['stage_evidence_complete']
