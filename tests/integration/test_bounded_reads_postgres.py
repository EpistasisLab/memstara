"""Exercise SQL filtering against real PostgreSQL with accumulated synthetic history."""

import json

import pytest

from memstara.mcp_servers import blackboard as board
from memstara.pipeline.iteration_learning import summarize

pytestmark = pytest.mark.integration


async def test_loop_reads_do_not_grow_with_prior_history_and_archive_retains_every_row(database):
    await database.execute(
        "INSERT INTO memstara_results (run_tag, trial, match_trace) VALUES ('bounded', 32, $1::jsonb)",
        json.dumps([{'evidence': 'large trace' * 10000}]),
    )
    before = await board.read_results('bounded', trial_start=32, trial_end=33)
    await database.executemany(
        "INSERT INTO memstara_results (run_tag, trial, evaluation) VALUES ('bounded', $1, $2::jsonb)",
        [(trial, json.dumps({'historic': 'x' * 100000})) for trial in range(32)],
    )
    after = await board.read_results('bounded', trial_start=32, trial_end=33)
    assert before == after
    current = json.loads(after)
    assert current['count'] == 1 and current['results'][0]['trial'] == 32
    assert current['results'][0]['match_trace_calls'] == 1
    assert 'match_trace' not in current['results'][0]
    assert len(after) < 2000
    trace = json.loads(await board.read_results('bounded', True, 32, 33))
    assert len(trace['results'][0]['match_trace']) == 1
    archive = json.loads(await board.read_results('bounded'))
    assert archive['count'] == 33


async def test_scheduler_and_feedback_queries_preserve_their_exact_contracts(database):
    await database.executemany(
        "INSERT INTO memstara_blackboard (run_tag, trial, status, task_type, hypothesis) "
        "VALUES ('bounded', $1, $2, 'interpret', 'Synthetic evidence')",
        [(trial, 'done' if trial < 32 else 'ready') for trial in range(34)],
    )
    current = json.loads(await board.read_board('bounded', state_only=True, trial_start=32, trial_end=33))
    assert [row['trial'] for row in current['tasks']] == [32]
    entire = json.loads(await board.read_board('bounded'))
    recent = json.loads(await board.read_board('bounded', feedback_before_trial=32))
    assert recent['count'] == 12
    assert all('match_trace' not in row for row in recent['tasks'])
    plan = {'run_tag': 'bounded', 'trials': 1, 'config_hash': 'synthetic'}
    assert summarize(recent['tasks'], plan, 32) == summarize(entire['tasks'], plan, 32)
    claimed = json.loads(await board.claim_task('interpret', 'bounded', 'interpret#1'))
    assert claimed['trial'] == 32 and 'tasks' not in claimed
    assert json.loads(await board.read_board('bounded'))['count'] == 34


async def test_current_question_is_not_hidden_by_newer_questions_from_other_waves(database):
    await database.executemany(
        "INSERT INTO memstara_questions (text, text_key, origin_run, origin_wave) VALUES ($1, $1, 'bounded', $2)",
        [(f'question-{wave}', wave) for wave in range(250)],
    )
    selected = json.loads(await board.read_questions(origin_run='bounded', origin_wave=32))
    assert selected['count'] == 1
    assert selected['questions'][0]['origin_wave'] == 32
