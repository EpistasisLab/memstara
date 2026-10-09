"""Proposal provenance stays distinct from real Motoro agent-run evidence."""
import json
import uuid

import pytest

from memstara.experiment_registry import proposal_evidence


@pytest.fixture
def proposal(tmp_path):
    config = {'mode': 'proposal', 'empirical_evaluation': {'status': 'not_executed', 'metrics': None}}
    call = {'run_id': str(uuid.uuid4()), 'stage': 'report', 'loop': 1, 'mode': 'proposal',
            'execution_adapter': 'proposal_text', 'core_run_id': None, 'computation_status': 'not_executed',
            'model': 'fixture', 'provider': 'openai', 'status': 'completed'}
    io = tmp_path / 'proposal_io' / 'loop-0001'
    io.mkdir(parents=True)
    (io / 'report.input.json').write_text(json.dumps({'profile': {'model': 'fixture', 'provider': 'openai'}}))
    (io / 'report.output.json').write_text(json.dumps(call))
    (io / 'report.attempt-1.json').write_text(json.dumps({'text': 'Planning output', 'usage': {}}))
    return tmp_path, config, call, io


def test_proposal_records_use_saved_io_and_attempts(proposal):
    root, config, call, _ = proposal
    evidence = proposal_evidence(root, config, call)
    assert evidence['adapter'] == 'proposal_text' and evidence['output']['run_id'] == call['run_id']
    assert len(evidence['attempts']) == 1


@pytest.mark.parametrize('patch', [
    {'mode': 'pipeline'}, {'core_run_id': str(uuid.uuid4())}, {'computation_status': 'executed'},
    {'stage': '../secret'}, {'loop': 0}, {'loop': True}, {'run_id': str(uuid.uuid4())}, {'model': 'different'},
])
def test_mixed_or_mismatched_evidence_rejected(proposal, patch):
    root, config, call, _ = proposal
    with pytest.raises(ValueError):
        proposal_evidence(root, config, {**call, **patch})


def test_missing_completed_output_is_never_successful(proposal):
    root, config, call, io = proposal
    (io / 'report.output.json').unlink()
    with pytest.raises(ValueError, match='output'):
        proposal_evidence(root, config, call)
    evidence = proposal_evidence(root, config, {**call, 'status': 'failed'})
    assert evidence['output'] is None and evidence['attempts']


def test_proposal_adapter_cannot_bypass_empirical_run_evidence(proposal):
    root, config, call, _ = proposal
    with pytest.raises(ValueError, match='non-empirical'):
        proposal_evidence(root, {**config, 'mode': 'pipeline'}, call)


def test_proposal_io_cannot_read_a_symlink_outside_execution(proposal, tmp_path):
    root, config, call, io = proposal
    private = tmp_path.parent / ('outside_' + uuid.uuid4().hex)
    private.write_text('outside evidence')
    try:
        (io / 'report.input.json').unlink()
        (io / 'report.input.json').symlink_to(private)
        with pytest.raises(ValueError, match='escapes'):
            proposal_evidence(root, config, call)
    finally:
        private.unlink()
