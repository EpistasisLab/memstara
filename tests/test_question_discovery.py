"""Read-only discovery preserves identity, pagination and outage semantics."""
import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer' / 'api'))
import discovery
from fastapi import HTTPException


def question(i):
    return dict(question_id=i, text=f'Question {i}', okf_tags='["tag"]', rationale='Reason',
                origin_run='run-a', origin_wave=1, times_used=0, best_auc=None,
                status='open', created_at=datetime.now(timezone.utc), writer='agent')


class DiscoveryTests(unittest.TestCase):
    def test_page_boundary_does_not_drop_the_next_question(self):
        conn = AsyncMock()
        conn.fetch.return_value = [question(i) for i in range(200, 79, -1)]
        async def guarded(store, callback, fallback): return await callback(conn)
        with patch.object(discovery.pools, 'guarded', guarded):
            value = asyncio.run(discovery.question_list())
        self.assertEqual(len(value['questions']), 120)
        self.assertEqual(value['next_before'], 81)
        self.assertEqual(value['questions'][0]['okf_tags'], ['tag'])

    def test_absence_is_not_an_outage(self):
        for fallback, status in [(None, 404), (False, 503)]:
            with self.subTest(status=status), patch.object(discovery.pools, 'guarded', AsyncMock(return_value=fallback)):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(discovery.question_detail(123))
                self.assertEqual(caught.exception.status_code, status)

    def test_evidence_uses_question_identity_not_similar_wording(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = question(123)
        conn.fetch.return_value = []
        async def guarded(store, callback, fallback): return await callback(conn)
        with patch.object(discovery.pools, 'guarded', guarded):
            result = asyncio.run(discovery.question_detail(123))
        self.assertEqual(result['tasks'], [])
        self.assertEqual(result['results'], [])
        for call in conn.fetch.call_args_list:
            self.assertIn('WHERE question_id = $1', call.args[0])
            self.assertIn('LIMIT 100', call.args[0])
            self.assertEqual(call.args[1], 123)


    def test_result_provenance_survives_the_question_api(self):
        import json
        policy = {'version': 'knowledge_only_v1', 'kind': 'primary_knowledge_driven'}
        conn = AsyncMock()
        conn.fetchrow.return_value = question(123)
        result = dict(result_id=1, question_id=123, columns_used='[]',
                      columns_missing='[]', feature_importance='{}',
                      evaluation=json.dumps({'hypothesis_policy': policy}))
        conn.fetch.side_effect = [[], [result]]
        async def guarded(store, callback, fallback): return await callback(conn)
        with patch.object(discovery.pools, 'guarded', guarded):
            data = asyncio.run(discovery.question_detail(123))
        self.assertEqual(data['results'][0]['evaluation']['hypothesis_policy'], policy)


class LiveOutputsTests(unittest.TestCase):
    def test_live_result_query_reads_migrated_columns_without_serializing_trace(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        async def guarded(store, callback, fallback): return await callback(conn)
        with patch.object(discovery.pools, 'guarded', guarded), patch.object(discovery.run_artifacts, 'lookup', return_value={}):
            result = asyncio.run(discovery.live_outputs(['run-a', 'run-b']))
        sql, tags = conn.fetch.call_args_list[2].args
        self.assertEqual(tags, ['run-a', 'run-b'])
        self.assertIn('WHERE run_tag = ANY($1::text[])', sql)
        self.assertIn('ORDER BY result_id DESC LIMIT 200', sql)
        self.assertIn("COALESCE(evaluation, '{}'::jsonb)", sql)
        self.assertIn("COALESCE(hypothesis_id, '')", sql)
        self.assertNotIn('to_jsonb(memstara_results)', sql)
        self.assertNotIn('match_trace', sql)
        self.assertEqual(result['record_limit'], 200)
        self.assertEqual(result['results'], [])

    def test_task_timestamp_changes_do_not_invent_new_agent_outputs(self):
        from datetime import timedelta
        conn = AsyncMock()
        q = question(12)
        task = dict(task_id=90, question_id=12, run_tag='run-a', trial=0,
                    hypothesis='Recorded relationship', columns_used='["feature"]', auc=.71,
                    interpretation='', task_type='ml', status='in_progress', updated_at=q['created_at'])
        artifact = {'config': {'pipeline_id': 'p-a', 'pipeline_name': 'Research A', 'trials': 1},
                    'report': {'status': 'generating', 'text': ''}}
        async def guarded(store, callback, fallback): return await callback(conn)
        with patch.object(discovery.pools, 'guarded', guarded), patch.object(discovery.run_artifacts, 'lookup', return_value=artifact):
            conn.fetch.side_effect = [[q], [task], []]
            first = asyncio.run(discovery.live_outputs(['run-a']))
            conn.fetch.side_effect = [[q], [{**task, 'updated_at': task['updated_at'] + timedelta(seconds=10)}], []]
            second = asyncio.run(discovery.live_outputs(['run-a']))
        self.assertEqual({e['id']: e['revision'] for e in first['events']}, {e['id']: e['revision'] for e in second['events']})
        self.assertEqual({e['stage'] for e in first['events']}, {'question', 'hypothesis', 'data', 'ml'})
        self.assertTrue(all('ANY($1::text[])' in c.args[0] for c in conn.fetch.call_args_list))

    def test_changed_report_body_is_detected_beyond_preview_length(self):
        conn = AsyncMock()
        conn.fetch.return_value = []
        artifact = {'config': {}, 'report': {'status': 'completed', 'text': 'a' * 600}}
        async def guarded(store, callback, fallback): return await callback(conn)
        with patch.object(discovery.pools, 'guarded', guarded), patch.object(discovery.run_artifacts, 'lookup', return_value=artifact):
            first = asyncio.run(discovery.live_outputs(['run-a']))
            artifact['report']['text'] += 'new section'
            second = asyncio.run(discovery.live_outputs(['run-a']))
        self.assertEqual(first['events'][0]['detail'], second['events'][0]['detail'])
        self.assertNotEqual(first['events'][0]['revision'], second['events'][0]['revision'])


class NoveltyRankingTests(unittest.TestCase):
    def test_ranking_is_paginated_and_scoped_without_n_plus_one_reads(self):
        import json
        conn = AsyncMock()
        conn.fetch.return_value = [dict(task_id=i, result_id=i, question_id=i, total=51,
            score=.5, novelty=json.dumps({'policy':'predicted_path_fraction_v1','score':.5})) for i in range(51)]
        async def guarded(store, callback, fallback): return await callback(conn)
        with patch.object(discovery.pools, 'guarded', guarded):
            result = asyncio.run(discovery.novelty_ranking(0, 'run-a'))
        self.assertEqual(len(result['items']), 50)
        self.assertEqual(result['next_offset'], 50)
        self.assertEqual(result['items'][0]['novelty']['score'], .5)
        self.assertEqual(conn.fetch.await_count, 1)
        sql, tag, offset, sources = conn.fetch.call_args.args
        self.assertIsNone(sources)
        self.assertEqual(tag, 'run-a')
        self.assertEqual(offset, 0)
        self.assertIn('DISTINCT ON (r.task_id)', sql)
        self.assertIn("q.status <> 'cleared'", sql)
        self.assertIn('DESC NULLS LAST', sql)

    def test_ranking_outage_is_not_empty_success(self):
        with patch.object(discovery.pools, 'guarded', AsyncMock(return_value=None)):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(discovery.novelty_ranking())
            self.assertEqual(caught.exception.status_code, 503)


class SemanticQuestionsTests(unittest.TestCase):
    def test_semantic_service_failure_is_explicit_and_list_stays_available(self):
        conn = AsyncMock()
        conn.fetch.return_value = [question(1)]
        conn.fetchval.return_value = 1
        async def guarded(store, callback, fallback): return await callback(conn)
        with patch.object(discovery.pools, 'guarded', guarded), patch('universe_semantics.index', side_effect=RuntimeError('model absent')):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(discovery.semantic_questions())
            self.assertEqual(caught.exception.status_code, 503)
            self.assertEqual(len(asyncio.run(discovery.question_list())['questions']), 1)

    def test_semantic_index_receives_active_text_and_reports_coverage(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{'question_id': 3, 'text': 'A research question'}]
        conn.fetchval.return_value = 1
        async def guarded(store, callback, fallback): return await callback(conn)
        with patch.object(discovery.pools, 'guarded', guarded), patch('universe_semantics.index', return_value={'points': [], 'neighbors': [], 'indexed_count': 1}) as index:
            result = asyncio.run(discovery.semantic_questions('cardiac', 3))
        self.assertEqual(result['coverage'], 'complete')
        self.assertEqual(result['total_questions'], 1)
        index.assert_called_once_with(conn.fetch.return_value, 'cardiac', 3)
        self.assertIn("status <> 'cleared'", conn.fetch.call_args.args[0])


    def test_slow_index_returns_progress_without_cancelling_work(self):
        import time
        calls = []
        def slow_index(*args):
            calls.append(args)
            time.sleep(.05)
            return {'points': [], 'neighbors': [], 'indexed_count': 1}
        async def scenario():
            with patch.object(discovery.pools, 'guarded', AsyncMock(return_value=([{'question_id': 1, 'text': 'x'}], 1))), patch('universe_semantics.index', slow_index), patch.object(discovery, 'SEMANTIC_WAIT_SECONDS', .001):
                first = await discovery.semantic_questions('slow')
                self.assertEqual(first.status_code, 202)
                await asyncio.sleep(.1)
                second = await discovery.semantic_questions('slow')
                self.assertEqual(second['indexed_count'], 1)
                self.assertEqual(len(calls), 1)
        asyncio.run(scenario())


class WorkspaceRunCountTests(unittest.TestCase):
    def test_five_live_executions_are_accepted(self):
        import main
        with patch.object(discovery, 'live_outputs', AsyncMock(return_value={'events': []})) as live:
            import json
            self.assertEqual(json.loads(asyncio.run(main.discovery_live('a,b,c,d,e')).body), {'events': []})
            live.assert_awaited_once_with(['a', 'b', 'c', 'd', 'e'])

    def test_five_result_executions_are_accepted_without_losing_scope(self):
        import main
        from types import SimpleNamespace
        with patch.object(main.scene, '_results', AsyncMock(return_value=[])) as results, patch.object(
            main.scene, '_board', AsyncMock(return_value=[])
        ), patch.object(main.run_artifacts, 'configs', return_value={}), patch.object(
            main.pools, 'health', SimpleNamespace(as_dict=lambda: {'memstara': {'up': True}})
        ):
            self.assertEqual(asyncio.run(main.pipeline_results('a,b,c,d,e')), {'results': [], 'failures': []})
            self.assertEqual([call.args[0] for call in results.call_args_list], ['a', 'b', 'c', 'd', 'e'])


class LiveOutputProgressTests(unittest.TestCase):
    def test_slow_archive_read_is_shared_and_returns_preparation_then_complete(self):
        async def scenario():
            discovery._live_reads.clear()
            release = asyncio.Event()
            calls = []
            async def read(tags):
                calls.append(tags)
                await release.wait()
                return {'results': [{'result_id': 42}]}
            with patch.object(discovery, 'live_outputs', read), patch.object(discovery, 'LIVE_WAIT_SECONDS', .001):
                first = await discovery.live_outputs_response(['b', 'a'])
                second = await discovery.live_outputs_response(['a', 'b'])
                self.assertEqual(first.status_code, 202)
                self.assertEqual(second.status_code, 202)
                self.assertEqual(calls, [['a', 'b']])
                release.set()
                result = await discovery.live_outputs_response(['a', 'b'])
                import json
                self.assertEqual(json.loads(result.body), {'results': [{'result_id': 42}]})
                again = await discovery.live_outputs_response(['a', 'b'])
                self.assertEqual(json.loads(again.body), {'results': [{'result_id': 42}]})
                self.assertEqual(len(calls), 1)
                discovery._live_reads.clear()
        asyncio.run(scenario())

    def test_background_failure_remains_an_error_not_an_empty_success(self):
        async def scenario():
            discovery._live_reads.clear()
            async def fail(tags):
                raise HTTPException(503, 'Source unavailable')
            with patch.object(discovery, 'live_outputs', fail):
                with self.assertRaises(HTTPException):
                    await discovery.live_outputs_response(['a'])
                self.assertEqual(discovery._live_reads, {})
        asyncio.run(scenario())
