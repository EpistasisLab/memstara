"""Real PostgreSQL ordering, legacy exclusion and run-scoped pagination."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'viewer' / 'api'))
import discovery

pytestmark = pytest.mark.integration


async def test_real_ranking_sql(database, monkeypatch):
    await database.execute("CREATE TEMP TABLE memstara_questions "
                           "(question_id int, status text, origin_run text NOT NULL DEFAULT '')")
    await database.execute('CREATE TEMP TABLE memstara_results (task_id int, result_id int, question_id int, '
                           'run_tag text, trial int, hypothesis text, auc float, evaluation jsonb)')
    await database.execute("INSERT INTO memstara_questions(question_id,status) VALUES (1,'done'),(2,'cleared')")
    for i, score in enumerate([None, 0, .5, 1, 'invalid', .5], 1):
        n = dict(policy='predicted_path_fraction_v1', rankable=True, score=score, coverage=1)
        await database.execute('INSERT INTO memstara_results VALUES ($1,$1,1,$2,0,\'Fixture\',.6,$3::jsonb)',
                               i, 'run-a' if i != 6 else 'run-b', json.dumps({'knowledge_provenance': {'novelty':n}}))
    # Latest result for task 4 is unknown; an old high score must not persist.
    await database.execute("INSERT INTO memstara_results VALUES (4,7,1,'run-a',0,'Latest',.7,'{}')")
    await database.execute("INSERT INTO memstara_results VALUES (8,8,2,'run-a',0,'Cleared',.7,'{}')")
    async def guarded(store, callback, fallback):
        return await callback(database)
    monkeypatch.setattr(discovery.pools, 'guarded', guarded)
    result = await discovery.novelty_ranking(0, 'run-a')
    assert [r['result_id'] for r in result['items']] == [3,2,7,5,1]
    assert result['total'] == 5 and result['next_offset'] is None
    all_runs = await discovery.novelty_ranking()
    assert [r['result_id'] for r in all_runs['items']][:2] == [6,3]
    assert [r['result_id'] for r in (await discovery.novelty_ranking(2,'run-a'))['items']] == [7,5,1]
