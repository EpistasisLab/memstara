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
        sql, tag, offset = conn.fetch.call_args.args
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
