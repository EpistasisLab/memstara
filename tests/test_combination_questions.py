"""Regression: a small predictor pool must not terminate a combination schedule."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from memstara.pipeline import combination_questions as policy
from memstara.pipeline.checkpoint import Checkpoint
from memstara.pipeline.exploration import record_round, round_summary


def plan():
    return {'run_tag': 'test', 'config_hash': 'hash', 'y_column': 'FIXED_TARGET',
            'combination_plan': {'total_loops': 4},
            'hypothesis_policy': {'version': 'knowledge_only_v1', 'question_contract': 'fixed_target_v1',
                                  'combination_questions': policy.VERSION}}


def test_skipped_middle_loop_preserves_results_and_advances_checkpoint(tmp_path):
    checkpoint = Checkpoint(tmp_path)
    record_round(tmp_path, 1, 'completed')
    checkpoint.advance(0, dry_streak=0, waves_run=1, seeded_total=1, missing_trials=[])
    assert policy.skip_unavailable(plan(), tmp_path, 1, checkpoint, dry_streak=0,
                                   waves_run=1, seeded_total=1, missing_trials=[])
    assert not (tmp_path / 'pipeline_failure.json').exists()
    recovered = Checkpoint(tmp_path, resume=True)
    assert recovered.state['next_wave'] == 2
    assert recovered.state['seeded_total'] == 1
    record_round(tmp_path, 3, 'completed')
    summary = round_summary(tmp_path)
    assert (summary['completed'], summary['skipped'], summary['blocked']) == (2, 1, 0)
    assert summary['attempted'] == 3


def test_old_frozen_runs_do_not_silently_change_policy(tmp_path):
    legacy = plan()
    del legacy['hypothesis_policy']['combination_questions']
    assert not policy.skip_unavailable(legacy, tmp_path, 1, None, dry_streak=0,
                                       waves_run=1, seeded_total=1, missing_trials=[])
    assert not list(tmp_path.iterdir())


def test_mapping_infrastructure_failure_is_not_a_skipped_loop(tmp_path):
    (tmp_path / 'question_repair_1_writer.json').write_text(json.dumps({
        'run_tag': 'test', 'config_hash': 'hash',
        'response': {'rejected': [{'code': 'mapping_preflight_unavailable'}]}}))
    checkpoint = Checkpoint(tmp_path)
    with pytest.raises(RuntimeError, match='infrastructure'):
        policy.skip_unavailable(plan(), tmp_path, 1, checkpoint, dry_streak=0,
                                waves_run=1, seeded_total=1, missing_trials=[])
    assert checkpoint.state['next_wave'] == 0
    assert not (tmp_path / 'iteration_outcomes.json').exists()


def test_same_question_allowed_across_combinations_but_not_within_loop(monkeypatch):
    from memstara.mcp_servers import blackboard as bb
    p = plan()
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: p)
    monkeypatch.setattr(bb, '_pipeline_run', lambda: 'test')
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    stored = []
    async def fetch(sql, run, wave):
        return [r for r in stored if r['origin_run'] == run and (wave is None or r['origin_wave'] == wave)]
    async def insert(sql, text, key, tags, rationale, run, wave, writer, contract):
        assert not any(r['key'] == key for r in stored)
        stored.append({'question_id': len(stored)+1, 'text': text, 'key': key,
                       'okf_tags': tags, 'origin_run': run, 'origin_wave': wave})
        return len(stored)
    conn.fetch.side_effect = fetch
    conn.fetchval.side_effect = insert
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    item = {'predictor_concepts': ['age', 'history'], 'okf_tags': ['cardiac'],
            'rationale': 'Supported by documented cardiac evidence.'}
    async def submit(wave):
        return json.loads(await bb.propose_questions([item], origin_run='test', origin_wave=wave))
    assert asyncio.run(submit(0))['added']
    assert asyncio.run(submit(1))['added']
    assert asyncio.run(submit(1))['duplicates']
    assert len(stored) == 2
    assert stored[0]['key'] != stored[1]['key']
    # Ordinary iterative discovery still rejects the cross-wave duplicate.
    del p['hypothesis_policy']['combination_questions']
    assert asyncio.run(submit(2))['duplicates']


def test_combination_prompt_does_not_require_novelty_or_prior_ml_feedback(monkeypatch):
    from memstara.pipeline import board
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: plan())
    tools = AsyncMock(return_value={'questions': []})
    agent = AsyncMock()
    monkeypatch.setattr(board, 'call_board_tool', tools)
    monkeypatch.setattr(board, 'call_agent', agent)
    assert asyncio.run(board.questions_for_wave(None, {'hypothesis': 'agent'}, {'question': []},
                                               run_tag='test', wave=3, want=1)) == ([], True)
    prompt = agent.call_args.args[1]
    assert 'earlier Loop is NOT a reason' in prompt
    assert 'Do not repeat an already banked question' not in prompt
    assert all(call.args[1] != 'read_board' for call in tools.call_args_list)


def test_proposal_database_error_is_preserved_as_failure_feedback(tmp_path, monkeypatch):
    from memstara.mcp_servers import blackboard as bb
    p = plan()
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: p)
    monkeypatch.setattr(bb, '_pipeline_run', lambda: 'test')
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(side_effect=ConnectionError('fixture unavailable')))
    response = json.loads(asyncio.run(bb.propose_questions([{
        'predictor_concepts': ['age'], 'okf_tags': ['cardiac'],
        'rationale': 'Supported by documented evidence.'}], origin_run='test', origin_wave=1)))
    assert response['error']
    checkpoint = Checkpoint(tmp_path)
    with pytest.raises(RuntimeError, match='infrastructure'):
        policy.skip_unavailable(p, tmp_path, 1, checkpoint, dry_streak=0,
                                waves_run=0, seeded_total=0, missing_trials=[])
    assert checkpoint.state['next_wave'] == 0
