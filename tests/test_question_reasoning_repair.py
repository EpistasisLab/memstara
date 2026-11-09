"""Regressions for the actual whole-graph empty-proposal feedback loop."""
import json
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline import question_contract as qc, question_regeneration as regen

PLAN = {'run_tag': 'test', 'config_hash': 'h', 'y_column': 'HIV_DETECTABLE',
        'hypothesis_policy': {'version': 'knowledge_only_v1', 'question_contract': qc.VERSION}}
FALSE_REFUSAL = ('The 14 anchors with metapaths are HIV complications or antiretroviral drug classes; '
                 'using them to predict HIV_DETECTABLE would be leakage. '
                 'No direct edge to the target exists, so no question is possible.')


@pytest.mark.asyncio
async def test_refusal_is_audited_but_not_reinjected_after_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(regen, 'retry_delay', AsyncMock())
    waits = 0
    async def stop():
        nonlocal waits
        waits += 1
        if waits == 2:
            raise asyncio.CancelledError
    async def empty():
        regen.remember_writer('hypothesis', FALSE_REFUSAL)
        return [], True
    import asyncio
    args = dict(root=tmp_path, wave=128, run_tag='r', config_hash='h')
    with pytest.raises(asyncio.CancelledError):
        await regen.until_saved(empty, **args, wait=stop)
    files = list((tmp_path / 'question_regeneration/loop-129').glob('*.json'))
    assert any(json.loads(f.read_text()).get('response') == FALSE_REFUSAL for f in files)
    async def resumed():
        prompt = regen.writer_feedback('hypothesis')
        assert FALSE_REFUSAL not in prompt
        assert 'ROUND 2' in prompt and 'unverified model judgment' in prompt
        assert 'previous_response_sha256' in prompt
        return [{'question_id': 5}], False
    assert await regen.until_saved(resumed, **args) == ([{'question_id': 5}], False)


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['question128-1', 'hypothesis128'])
@pytest.mark.parametrize('no_knowledge', [False, True])
async def test_actual_model_boundary_receives_rules_after_long_catalog(monkeypatch, stage, no_knowledge):
    from memstara.pipeline import board
    from memstara.pipeline.no_knowledge import VERSION
    plan = {**PLAN, 'no_knowledge_condition': no_knowledge, 'no_knowledge_isolation': VERSION}
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: plan)
    monkeypatch.setattr(board, 'require_ownership', lambda: None)
    monkeypatch.setattr(board, '_TRACE_DIR', None)
    class Captured(Exception):
        pass
    captured = {}
    async def create(**kwargs):
        captured.update(kwargs)
        raise Captured
    monkeypatch.setattr(board, 'create_run', create)
    catalog = 'AVAILABLE PREDICTORS\n' + 'feature metadata\n' * 10000
    with pytest.raises(Captured):
        await board._call_agent_uncontrolled('agent', catalog, stage=stage, tools=[], registry=None)
    text = captured['user_input']
    if no_knowledge:
        assert 'Grounded hypotheses and predictor leakage' not in text
    else:
        assert text.index('Grounded hypotheses and predictor leakage') > len(catalog) - 1
        assert 'A graph path need not terminate' in text
        assert 'Unknown timing is neither proven leakage nor proof of safe temporal eligibility' in text
        assert 'verified baseline timing is required' in text


def test_system_and_call_rules_share_one_source_and_nk_remains_separate(monkeypatch):
    from memstara.pipeline.prompts import load_prompt
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: {})
    guide = qc.knowledge_reasoning_instructions(PLAN).strip()
    assert guide in load_prompt('board/hypothesis', 'hiv-okf-whole-graph')['system_prompt']
    assert guide not in load_prompt('board/hypothesis', 'hiv-no-knowledge')['system_prompt']
    assert qc.knowledge_reasoning_instructions({**PLAN, 'no_knowledge_condition': True}) == ''
    assert qc.knowledge_reasoning_instructions({**PLAN, '_hybrid_question': True}) == ''


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [[], '[]'])
async def test_empty_submission_has_actionable_feedback_without_database(value, monkeypatch, tmp_path):
    from memstara.mcp_servers import blackboard as bb
    from memstara.pipeline.question_repair import retry_instructions
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(PLAN))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(path))
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: PLAN)
    monkeypatch.setattr(bb, '_pipeline_run', lambda: 'test')
    connect = AsyncMock(side_effect=AssertionError('Empty proposal must not query the DB'))
    monkeypatch.setattr(bb.asyncpg, 'connect', connect)
    result = json.loads(await bb.propose_questions(value, origin_run='test', origin_wave=128, writer='hypothesis'))
    assert result['added'] == [] and result['rejected'][0]['code'] == 'empty_question_batch'
    assert 'no scientific or mapping validation occurred' in result['rejected'][0]['why']
    assert 'empty_question_batch' in retry_instructions(PLAN, 128, 'hypothesis')
    connect.assert_not_awaited()
