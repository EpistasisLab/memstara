"""Exercise real MCP SQL in an isolated synthetic schema; no LLM or cohort access."""
import asyncio
import json
import os
import uuid
from pathlib import Path
import tempfile

from memstara.env import load_env
from memstara.blackboard import SCHEMA
from memstara.mcp_servers import blackboard as bb


async def main():
    load_env()
    import asyncpg
    connect = asyncpg.connect
    schema = 'test_fanout_' + uuid.uuid4().hex
    admin = await connect(bb._dsn())
    await admin.execute(f'CREATE SCHEMA {schema}')
    async def isolated(*args, **kwargs):
        return await connect(bb._dsn(), server_settings={'search_path': schema, 'lock_timeout': '3000'})
    old_config = os.environ.get('MEMSTARA_RUN_CONFIG')
    old_output = os.environ.get('MEMSTARA_OUTPUT_DIR')
    try:
        c = await isolated()
        await c.execute(SCHEMA)
        bb.asyncpg.connect = isolated
        # Concurrent rewords must see the other writer's committed decision (#53).
        proposals = await asyncio.gather(*(bb.propose_questions(json.dumps([{
            'text': text, 'okf_tags': ['synthetic-branch'], 'rationale': 'synthetic test',
        }]), origin_run='synthetic', writer=f'writer-{i}') for i, text in enumerate([
            'Investigate whether treatment exposure predicts the synthetic outcome',
            'Investigate whether treatment exposure predicts a synthetic outcome',
        ])))
        proposals = [json.loads(value) for value in proposals]
        assert not any('error' in value for value in proposals), proposals
        assert sum(len(value['added']) for value in proposals) == 1, proposals
        assert sum(len(value['skipped']) for value in proposals) == 1, proposals
        assert await c.fetchval('SELECT count(*) FROM memstara_questions') == 1
        print('PASS: concurrent reword proposals bank one question and return duplicate_of for the other.')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.json'
            policy = {'version': 'knowledge_only_v1', 'kind': 'primary_knowledge_driven',
                      'prior_ml_feedback': False, 'validation_status': 'exploratory_not_independently_validated'}
            config.write_text(json.dumps({'run_tag': 'synthetic', 'hypothesis_policy': policy,
                              'interpretation_mode': 'all_per_hypothesis', 'interpreters': 3,
                              'books': {'interpreter': ['clinical', 'robustness', 'actionability']},
                              'y_column': 'outcome', 'evaluation': {'engine': 'logistic_regression',
                              'seed': 7, 'test_size': 0.4, 'folds': 2, 'replicates': 1, 'search_trials': 2}}))
            os.environ['MEMSTARA_RUN_CONFIG'] = str(config)
            os.environ['MEMSTARA_OUTPUT_DIR'] = str(root)
            # Outcome metadata exists, but primary agents must never receive it.
            await c.execute("UPDATE memstara_questions SET best_auc=.99, rationale='Prior ML features' ")
            catalog = json.loads(await bb.read_question_catalog())
            assert catalog['questions']
            assert all(set(q) == {'question_id', 'text', 'okf_tags'} for q in catalog['questions'])
            claim = json.loads(await bb.claim_question('synthetic', 'hypothesis'))
            assert claim['question_id']
            assert not {'best_auc', 'rationale', 'times_used'} & set(claim)
            assert 'error' in json.loads(await bb.propose_questions('[]', origin_run='other'))
            print('PASS: primary catalog and claims exclude score feedback; cross-run proposals rejected.')
            for index in range(2):
                subset = root / f'subset{index}.csv'
                subset.write_text('x,outcome\n' + ''.join(f'{i % 7},{i % 2}\n' for i in range(100)))
                from memstara.mcp_servers.ml import train_and_score
                measured = json.loads(train_and_score(str(subset), 'outcome', seed=999))
                assert 'error' not in measured, measured
                assert measured['seed'] == 7 and measured['test_size'] == 0.4
                # Exercise actual task creation and the data -> ML transition.
                created = json.loads(await bb.create_task('synthetic', index, 'Synthetic question',
                                      'Synthetic hypothesis', ['x'], 'outcome', ['synthetic-source']))
                assert 'error' not in created, created
                tid = created['task_id']
                claimed = json.loads(await bb.claim_task('data', 'synthetic', 'data#1'))
                assert claimed['task_id'] == tid
                assert claimed['evaluation']['hypothesis_policy'] == policy
                moved = json.loads(await bb.submit_result(tid, subset_path=str(subset),
                                   columns_used=['x'], columns_missing=[], worker='data#1'))
                assert moved.get('ok'), moved
                claimed_ml = json.loads(await bb.claim_task('ml', 'synthetic', 'ml#1'))
                assert claimed_ml['task_id'] == tid
                out = json.loads(await bb.submit_result(tid, worker='ml#1'))
                assert out.get('ok'), out
            assert await c.fetchval('SELECT count(*) FROM memstara_blackboard') == 6
            assert json.loads(await bb.claim_task('interpret','synthetic','interpret#4'))['task_id'] is None
            for iteration in range(2):
                claims = await asyncio.gather(*(bb.claim_task('interpret','synthetic',f'interpret#{i}') for i in (1,2,3)))
                tasks = [json.loads(x) for x in claims]
                assert len({t['task_id'] for t in tasks}) == 3
                for i,t in enumerate(tasks,1):
                    ev = t['evaluation']
                    if isinstance(ev,str): ev=json.loads(ev)
                    assert ev['interpretation_branch']['slot'] == i
                rejected = json.loads(await bb.submit_result(tasks[0]['task_id'],interpretation='wrong',worker='interpret#2'))
                assert 'error' in rejected
                results = await asyncio.gather(*(bb.submit_result(t['task_id'],interpretation=f'Perspective {i}',worker=f'interpret#{i}') for i,t in enumerate(tasks,1)))
                assert all(json.loads(x).get('ok') for x in results), results
                replay = json.loads(await bb.submit_result(tasks[0]['task_id'],interpretation='duplicate',worker='interpret#1'))
                assert 'error' in replay
            rows = await c.fetch('SELECT evaluation, interpretation FROM memstara_results')
            assert len(rows) == 2
            for row in rows:
                ev=json.loads(row['evaluation'])
                assert ev['hypothesis_policy'] == policy
                assert ev['seed'] == 7 and ev['test_size'] == 0.4
                assert ev['evaluation']['plan']['folds'] == 2
                assert ev['evaluation']['replicates'][0]['cv_auc'] is not None
                assert ev['interpretations_complete'] and len(ev['interpretations'])==3
                assert all(f'Perspective {i}' in row['interpretation'] for i in (1,2,3))
            print('PASS: measured ML seed=7, test_size=0.4 and CV policy survive into final database results.')
            # Exercise terminal retry exhaustion on a synthetic pending branch.
            last_id = await c.fetchval('SELECT max(task_id) FROM memstara_blackboard')
            await c.execute("UPDATE memstara_blackboard SET status='ready' WHERE task_id=$1", last_id)
            from memstara.pipeline.board import give_up_on
            await give_up_on([last_id])
            partial = await c.fetchval("SELECT evaluation FROM memstara_results WHERE trial=1")
            partial = json.loads(partial)
            assert not partial['interpretations_complete']
            assert [i['status'] for i in partial['interpretations']] == ['done', 'done', 'failed']
            print('PASS: 2 ML outcomes -> 6 pinned interpretation tasks -> 2 complete aggregate results; concurrent completion, wrong-worker, replay and terminal-failure aggregation checks passed.')
        await c.close()
    finally:
        bb.asyncpg.connect = connect
        for key,value in [('MEMSTARA_RUN_CONFIG',old_config),('MEMSTARA_OUTPUT_DIR',old_output)]:
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value
        await admin.execute(f'DROP SCHEMA {schema} CASCADE')
        await admin.close()


if __name__ == '__main__':
    asyncio.run(main())
