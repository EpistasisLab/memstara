"""Continuous scheduling must remain pausable and cancellable without an LLM."""
import asyncio

import pytest

from memstara.control.request import build_argv
from memstara.pipeline.exploration import rounds


def test_continuous_request_is_explicit_and_validated(monkeypatch):
    for role in ('QUESTION', 'HYPOTHESIS', 'DATA', 'ML', 'INTERPRETATION', 'EXPLANATION'):
        monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER', "openai")
        monkeypatch.setenv(f'MEMSTARA_{role}_MODEL', "test-deployment")
    assert "--continuous" not in build_argv({}, [])
    assert "--continuous" in build_argv({"continuous": True}, [])
    for invalid in ("false", "true", 1, None):
        with pytest.raises(ValueError, match="continuous"):
            build_argv({"continuous": invalid}, [])


def test_finite_rounds_and_continuous_rounds(tmp_path):
    async def scenario():
        assert [n async for n in rounds(2, False, tmp_path)] == [0, 1]
        iterator = rounds(1, True, tmp_path)
        assert [await anext(iterator) for _ in range(4)] == [0, 1, 2, 3]
        await iterator.aclose()
    asyncio.run(scenario())


def test_pause_resume_and_stop_while_paused(tmp_path):
    async def scenario():
        iterator = rounds(1, True, tmp_path)
        assert await anext(iterator) == 0
        marker = tmp_path / "pause.request"
        marker.touch()
        pending = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0.02)
        assert not pending.done()
        marker.unlink()
        assert await asyncio.wait_for(pending, 2) == 1
        marker.touch()
        pending = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0.02)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await iterator.aclose()
    asyncio.run(scenario())


def test_empty_exploration_waits_and_clears_state_on_cancellation(tmp_path, monkeypatch):
    from memstara.pipeline import exploration
    async def scenario():
        observed = []
        async def sleep(delay):
            observed.append(delay)
            assert (tmp_path / "questions.waiting").exists()
            raise asyncio.CancelledError()
        monkeypatch.setattr(exploration.asyncio, "sleep", sleep)
        for streak in (1, 2, 100):
            with pytest.raises(asyncio.CancelledError):
                await exploration.wait_for_new_questions(tmp_path, streak)
            assert not (tmp_path / "questions.waiting").exists()
        assert observed == [60, 120, 900]
    asyncio.run(scenario())


def test_stage_progress_resets_and_only_explicit_completion_reaches_100(tmp_path):
    import json
    from memstara.pipeline.exploration import write_progress
    write_progress(tmp_path, 4, "report")
    assert json.loads((tmp_path / "progress.json").read_text())["stage_percent"] == 80
    write_progress(tmp_path, 4, "report", completed=True)
    assert json.loads((tmp_path / "progress.json").read_text())["stage_percent"] == 100
    write_progress(tmp_path, 5, "hypothesis")
    current = json.loads((tmp_path / "progress.json").read_text())
    assert current["stage_percent"] == 0
    assert current["iteration"] == 5


def test_loop_timing_preserves_start_and_records_report_completion(tmp_path, monkeypatch):
    import json
    import time
    from memstara.pipeline.exploration import record_round
    monkeypatch.setattr(time, 'time', lambda: 10)
    record_round(tmp_path, 1, 'running')
    monkeypatch.setattr(time, 'time', lambda: 20)
    record_round(tmp_path, 1, 'analysis_complete')
    value=json.loads((tmp_path/'iteration_outcomes.json').read_text())['1']
    assert value['started_at']==10 and 'ended_at' not in value
    monkeypatch.setattr(time, 'time', lambda: 25)
    record_round(tmp_path, 1, 'completed')
    value=json.loads((tmp_path/'iteration_outcomes.json').read_text())['1']
    assert value['started_at']==10 and value['ended_at']==25


def test_sparse_retry_close_keeps_original_combination_number(tmp_path):
    import json
    from memstara.pipeline.exploration import record_round, write_progress, close_active_round
    for loop in range(29,50):
        record_round(tmp_path,loop,'completed')
    record_round(tmp_path,50,'running')
    write_progress(tmp_path,50,'hypothesis')
    close_active_round(tmp_path,'blocked','Transport failure')
    journal=json.loads((tmp_path/'iteration_outcomes.json').read_text())
    assert journal['50']['outcome']=='blocked'
    assert '22' not in journal and len(journal)==22
    assert json.loads((tmp_path/'progress.json').read_text())['iteration']==50


def test_old_misnumbered_retry_progress_is_derived_without_rewriting_history(tmp_path):
    import json
    from memstara.control.workspace import execution_progress
    progress={'iteration':22,'stage':'report'}
    (tmp_path/'progress.json').write_text(json.dumps(progress))
    (tmp_path/'config.json').write_text(json.dumps({'retry_selection':{'loops':list(range(29,65))}}))
    (tmp_path/'execution.json').write_text(json.dumps({'calls':[{'loop':50,'stage':'question49-1','started_at':10}]}))
    current=execution_progress({'run_dir':str(tmp_path)})
    assert current['iteration']==50 and current['recorded_iteration']==22
    assert current['stage']=='hypothesis' and current['identity_source']=='execution_manifest'
    assert json.loads((tmp_path/'progress.json').read_text())==progress


def test_retry_counts_exclude_phantom_ordinals_and_terminal_failure_is_visible(tmp_path):
    import json
    from memstara.control.workspace import execution_progress,loop_totals
    (tmp_path/'progress.json').write_text(json.dumps({'iteration':23,'exploration':{'attempted':24,'completed':21,'blocked':2}}))
    (tmp_path/'config.json').write_text(json.dumps({'retry_selection':{'loops':list(range(29,65))}}))
    journal={str(i):{'outcome':'completed'} for i in range(29,50)}
    journal.update({'22':{'outcome':'blocked'},'23':{'outcome':'blocked'},'50':{'outcome':'running'}})
    (tmp_path/'iteration_outcomes.json').write_text(json.dumps(journal))
    (tmp_path/'execution.json').write_text(json.dumps({'calls':[{'loop':50,'stage':'question49-1'}]}))
    (tmp_path/'pipeline_status.json').write_text(json.dumps({'status':'failed','message':'Transport failure'}))
    record={'run_dir':str(tmp_path),'run_tag':'retry'}
    current=execution_progress(record)
    assert current['iteration']==50
    assert current['exploration']['completed']==21 and current['exploration']['attempted']==22
    assert current['exploration']['blocked']==1 and current['exploration']['outcome']=='blocked'
    assert loop_totals([record])['attempted']==22
    assert json.loads((tmp_path/'iteration_outcomes.json').read_text())==journal


def test_stop_keeps_exact_continuation_and_never_replays_completed_calls(tmp_path):
    from memstara.pipeline.exploration import ExecutionGate
    import json

    async def scenario():
        gate = ExecutionGate(tmp_path)
        entered, finish = asyncio.Event(), asyncio.Event()
        calls = []
        async def first():
            calls.append('ml')
            entered.set()
            await finish.wait()
            return 'saved-model'
        async def second(model):
            calls.append(('interpret', model))
        async def pipeline():
            model = await gate.call(first)
            await gate.call(second, model)
        task = asyncio.create_task(pipeline())
        await entered.wait()
        marker = tmp_path / 'pause.request'
        marker.touch()
        finish.set()
        await asyncio.sleep(.03)
        assert calls == ['ml'] and not task.done()
        assert json.loads((tmp_path / 'execution_control.json').read_text())['state'] == 'paused'
        marker.unlink()
        await asyncio.wait_for(task, 2)
        assert calls == ['ml', ('interpret', 'saved-model')]
    asyncio.run(scenario())


def test_master_stop_gate_blocks_queued_calls_while_other_calls_finish(tmp_path):
    from memstara.pipeline.exploration import ExecutionGate
    import json

    async def scenario():
        gate = ExecutionGate(tmp_path)
        started, finish = asyncio.Event(), asyncio.Event()
        calls = []
        async def work(name):
            calls.append(name)
            started.set()
            await finish.wait()
        first = asyncio.create_task(gate.call(work, 'first'))
        await started.wait()
        marker = tmp_path / 'pause.request'
        marker.touch()
        second = asyncio.create_task(gate.call(work, 'second'))
        await asyncio.sleep(.03)
        assert json.loads((tmp_path / 'execution_control.json').read_text())['state'] == 'stopping'
        finish.set()
        await asyncio.sleep(.03)
        assert calls == ['first']
        assert json.loads((tmp_path / 'execution_control.json').read_text())['active_calls'] == 0
        marker.unlink()
        await asyncio.wait_for(asyncio.gather(first, second), 2)
        assert calls == ['first', 'second']
    asyncio.run(scenario())


def test_resume_does_not_reset_total_loop_limit(tmp_path):
    from memstara.pipeline.exploration import ExecutionGate

    async def scenario():
        gate = ExecutionGate(tmp_path)
        calls = []
        paused = asyncio.Event()
        async def work(loop):
            calls.append(loop)
            if loop == 1:
                (tmp_path / 'pause.request').touch()
                paused.set()
        async def pipeline():
            async for loop in rounds(3, False, tmp_path):
                await gate.call(work, loop)
        task = asyncio.create_task(pipeline())
        await paused.wait()
        await asyncio.sleep(.03)
        assert calls == [0, 1]
        (tmp_path / 'pause.request').unlink()
        await asyncio.wait_for(task, 2)
        assert calls == [0, 1, 2]
    asyncio.run(scenario())


def test_gate_cleans_active_count_on_failure_and_cancellation(tmp_path):
    from memstara.pipeline.exploration import ExecutionGate
    async def scenario():
        gate = ExecutionGate(tmp_path)
        async def fail():
            raise ValueError('provider failed')
        with pytest.raises(ValueError):
            await gate.call(fail)
        assert gate.active_calls == 0
        async def hang():
            await asyncio.Event().wait()
        task = asyncio.create_task(gate.call(hang))
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert gate.active_calls == 0
    asyncio.run(scenario())
