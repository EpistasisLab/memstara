import asyncio
from unittest.mock import AsyncMock

import pytest
pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")

from memstara.pipeline.scheduler import StageWorkers
from memstara.pipeline import board
from memstara.pipeline.core import board_workers
from memstara.control.request import build_argv


def test_fast_path_advances_while_other_path_is_running():
    async def scenario():
        workers = StageWorkers()
        blocked = asyncio.Event()
        fast = asyncio.Event()
        try:
            workers.launch('data', 1, blocked.wait())
            workers.launch('data', 2, fast.wait())
            assert workers.available('data', 2, 5) == []
            fast.set()
            await workers.wait(.1)
            assert [key for key, _ in await workers.completed()] == [('data', 2)]
            assert ('data', 1) in workers.active
            assert workers.available('data', 2, 1) == [2]
            workers.launch('ml', 1, asyncio.sleep(0, result='trained'))
            await workers.wait(.1)
            assert await workers.completed() == [(('ml', 1), 'trained')]
            assert not blocked.is_set()
        finally:
            await workers.close()
        assert not workers.active
    asyncio.run(scenario())


def test_failure_and_shutdown_do_not_orphan_other_workers():
    async def scenario():
        workers = StageWorkers()
        started, stopped = asyncio.Event(), asyncio.Event()
        async def slow():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        async def fail():
            raise ValueError('isolated failure')
        workers.launch('ml', 1, slow())
        await started.wait()
        workers.launch('data', 1, fail())
        await workers.wait(.1)
        outcomes = await workers.completed()
        assert isinstance(outcomes[0][1], ValueError)
        assert not stopped.is_set()
        await workers.close()
        assert stopped.is_set()
    asyncio.run(scenario())


def test_reconciliation_never_fails_a_still_running_worker(monkeypatch):
    monkeypatch.setattr(board, 'board_state', AsyncMock(return_value={'tasks': [
        {'task_id': 1, 'task_type': 'data', 'status': 'in_progress', 'claimed_by': 'data#1'},
        {'task_id': 2, 'task_type': 'interpret', 'status': 'in_progress', 'claimed_by': 'interpret#2'},
    ]}))
    submit = AsyncMock(return_value={'ok': True, 'status': 'failed'})
    monkeypatch.setattr(board, 'call_board_tool', submit)
    asyncio.run(board.settle_finished_workers(None, 'test', {'interpret#2'}))
    assert submit.await_count == 1
    assert submit.await_args.args[2]['task_id'] == 2


def test_interpreter_skills_are_provisioned_and_forwarded_individually(monkeypatch):
    monkeypatch.setenv("MEMSTARA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MEMSTARA_LLM_MODEL", "test-deployment")
    skills = ['interpreter_clinical', 'interpreter_attribution', 'interpreter_robustness', 'interpreter_actionability']
    argv = build_argv({'interpret_agents': 4, 'playbook_interpreter': ','.join(skills)},
                      [], skills, ['interpreter'])
    assert argv[argv.index('--interpret-agents') + 1] == '4'
    assert argv[argv.index('--playbook-interpreter') + 1] == ','.join(skills)
    workers = board_workers({'interpreter': skills})
    selected = [value for key, value in workers.items() if key.startswith('interpreter')]
    assert [book for _, book in selected] == skills
    assert len({name for name, _ in selected}) == 4


def test_four_hypotheses_and_repeated_waves_are_accepted(monkeypatch):
    monkeypatch.setenv("MEMSTARA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MEMSTARA_LLM_MODEL", "test-deployment")
    argv = build_argv({'hypothesis_agents': 4, 'trials': 4, 'waves': 3}, [])
    assert argv[argv.index('--hypothesis-agents') + 1] == '4'
    assert argv[argv.index('--waves') + 1] == '3'


def test_sparse_work_rotates_across_all_interpreter_skills():
    async def scenario():
        workers = StageWorkers()
        observed = []
        try:
            for _ in range(8):
                slot, = workers.available('interpreter', 4, 1)
                observed.append(slot)
                workers.launch('interpreter', slot, asyncio.sleep(0))
                await workers.wait(.1)
                await workers.completed()
            assert observed == [1, 2, 3, 4, 1, 2, 3, 4]
        finally:
            await workers.close()
    asyncio.run(scenario())
