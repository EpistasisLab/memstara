"""Read-only question discovery, linked only through recorded question identifiers."""
import asyncio
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
import hashlib
import json
from db import pools
import scene
import queries
import run_artifacts
import discovery_sources

QUESTION_FIELDS = "question_id, question_contract, text, okf_tags, rationale, origin_run, origin_wave, times_used, best_auc, status, created_at, writer"


async def question_list(before: int = 0, source: str = 'all', query: str = '') -> dict[str, Any]:
    tags = await discovery_sources.scope(source)
    async def read(conn):
        rows = await conn.fetch(f"SELECT {QUESTION_FIELDS} FROM memstara_questions "
                                "WHERE status <> 'cleared' AND ($1::integer = 0 OR question_id < $1) "
                                "AND ($2::text[] IS NULL OR coalesce(origin_run, '') = ANY($2)) "
                                "AND ($3::text = '' OR strpos(lower(text || ' ' || coalesce(rationale, '') || ' ' || coalesce(okf_tags::text, '')), lower($3)) > 0) "
                                "ORDER BY question_id DESC LIMIT 121", before, tags, query)
        items = [{**dict(row), 'okf_tags': scene._jsonb(row['okf_tags'], []),
                  'question_contract': scene._jsonb(row.get('question_contract'), {}),
                  'created_at': scene._iso(row['created_at'])} for row in rows[:120]]
        cleared_through = await conn.fetchval("SELECT coalesce(max(question_id), 0) FROM memstara_questions WHERE status='cleared'")
        total = await conn.fetchval("SELECT count(*) FROM memstara_questions WHERE status <> 'cleared' AND ($1::text[] IS NULL OR coalesce(origin_run, '') = ANY($1)) AND ($2::text = '' OR strpos(lower(text || ' ' || coalesce(rationale, '') || ' ' || coalesce(okf_tags::text, '')), lower($2)) > 0)", tags, query)
        return {'source': source, 'total': total, 'cleared_through': cleared_through, 'questions': items, 'next_before': items[-1]['question_id'] if len(rows) > 120 else None}
    result = await pools.guarded('memstara', read, None)
    if result is None:
        raise HTTPException(503, 'Question records are temporarily unavailable.')
    return result


async def question_detail(question_id: int, source: str = 'all') -> dict[str, Any]:
    tags = await discovery_sources.scope(source)
    async def read(conn):
        question = await conn.fetchrow(f'SELECT {QUESTION_FIELDS} FROM memstara_questions WHERE question_id=$1', question_id)
        if question is None or (tags is not None and (question['origin_run'] or '') not in tags):
            return None
        # No fuzzy joins on wording: a result is linked only by its persisted question_id.
        tasks = await conn.fetch(queries.BOARD.replace("WHERE ($1 = '' OR run_tag = $1)",
                                  'WHERE question_id = $1 AND ($2::text[] IS NULL OR run_tag = ANY($2))').replace('ORDER BY task_id', 'ORDER BY task_id DESC LIMIT 100'), question_id, tags)
        results = await conn.fetch(queries.RESULTS.replace("WHERE ($1 = '' OR run_tag = $1)",
                                    'WHERE question_id = $1 AND ($2::text[] IS NULL OR run_tag = ANY($2))').replace('ORDER BY result_id', 'ORDER BY result_id DESC') + ' LIMIT 100', question_id, tags)
        return {
            'question': {**dict(question), 'question_contract': scene._jsonb(question.get('question_contract'), {}),
                         'okf_tags': scene._jsonb(question['okf_tags'], [])},
            'tasks': [{**dict(t), 'columns': scene._jsonb(t['columns'], []),
                       'columns_used': scene._jsonb(t['columns_used'], []),
                       'columns_missing': scene._jsonb(t['columns_missing'], []),
                       'importance': scene._jsonb(t['feature_importance'], {})} for t in tasks],
            'results': [{**dict(r), 'columns_used': scene._jsonb(r['columns_used'], []),
                         'columns_missing': scene._jsonb(r['columns_missing'], []),
                         'importance': scene._jsonb(r['feature_importance'], {}),
                         'evaluation': scene._jsonb(r['evaluation'], {})} for r in results],
            'record_limit': 100,
        }
    data = await pools.guarded('memstara', read, False)
    if data is False:
        raise HTTPException(503, 'Question evidence is temporarily unavailable.')
    if data is None:
        raise HTTPException(404, 'Question not found.')
    return data


async def run_report(run_tag: str) -> dict[str, Any]:
    # Archive reader enforces path-safe run tags and never reads arbitrary user paths.
    artifact = await asyncio.to_thread(run_artifacts.lookup, run_tag)
    if not artifact:
        return {'run_tag': run_tag, 'report': None}
    return {'run_tag': run_tag, 'report': artifact.get('report')}


async def live_outputs(tags: list[str]) -> dict[str, Any]:
    """One bounded read for all active pipeline outputs, without querying core history."""
    import hashlib
    from datetime import datetime, timezone

    def revision(value):
        import json
        return hashlib.sha256(json.dumps(value, default=str, sort_keys=True).encode()).hexdigest()[:16]

    async def read(conn):
        questions = await conn.fetch(f'SELECT {QUESTION_FIELDS} FROM memstara_questions '
                                    "WHERE status <> 'cleared' AND origin_run = ANY($1::text[]) ORDER BY question_id DESC LIMIT 200", tags)
        tasks = await conn.fetch('SELECT task_id, question_id, run_tag, trial, hypothesis, '
                                 'columns_used, auc, interpretation, task_type, status, updated_at '
                                 'FROM memstara_blackboard WHERE run_tag = ANY($1::text[]) '
                                 'ORDER BY updated_at DESC LIMIT 200', tags)
        results = await conn.fetch(queries.RESULTS.replace('SELECT result_id,', 'SELECT question_id, result_id,')
                                   .replace("WHERE ($1 = '' OR run_tag = $1)", 'WHERE run_tag = ANY($1::text[])')
                                   .replace('ORDER BY result_id', 'ORDER BY result_id DESC LIMIT 200'), tags)
        return questions, tasks, results
    try:
        async with asyncio.timeout(30):
            rows = await pools.guarded('memstara', read, None)
            if rows is None:
                raise HTTPException(503, 'Live outputs are temporarily unavailable.')
            artifacts = await asyncio.gather(*(asyncio.to_thread(run_artifacts.lookup, tag) for tag in tags))
    except TimeoutError:
        raise HTTPException(503, 'Live outputs timed out; retain the last available records.') from None
    configs = {tag: (artifact or {}).get('config', {}) for tag, artifact in zip(tags, artifacts)}
    events = []

    def event(key, tag, stage, title, detail, at=None, question_id=None, result_id=None, trial=None, status='recorded'):
        config = configs.get(tag, {})
        identity = run_artifacts.result_identity(config, tag, trial) if trial is not None else {}
        entry = dict(id=key, run_tag=tag, stage=stage, title=title, detail=detail, at=scene._iso(at) if at else None,
                     question_id=question_id, result_id=result_id, trial=trial, status=status,
                     pipeline_name=config.get('pipeline_name') or tag, pipeline_id=config.get('pipeline_id'), iteration=identity.get('iteration'))
        entry['revision'] = revision({k: v for k, v in entry.items() if k != 'at'})
        entry['detail'] = (detail or '')[:500]
        events.append(entry)

    question_rows, task_rows, result_rows = rows
    questions = []
    for q in question_rows:
        questions.append({**dict(q), 'okf_tags': scene._jsonb(q['okf_tags'], []), 'created_at': scene._iso(q['created_at'])})
        event(f"question:{q['question_id']}", q['origin_run'], 'question', 'Question generated', q['text'],
              q['created_at'], q['question_id'])
    for t in task_rows:
        args = dict(at=t['updated_at'], question_id=t['question_id'], trial=t['trial'])
        if t['hypothesis']:
            event(f"hypothesis:{t['task_id']}", t['run_tag'], 'hypothesis', 'Hypothesis recorded', t['hypothesis'], **args)
        columns = scene._jsonb(t['columns_used'], [])
        if columns:
            event(f"data:{t['task_id']}", t['run_tag'], 'data', f'{len(columns)} features extracted', ', '.join(columns), **args)
        if t['auc'] is not None:
            event(f"ml:{t['task_id']}", t['run_tag'], 'ml', f"ML evaluation · AUC {t['auc']:.4f}", t['hypothesis'], **args)
        if t['status'] == 'failed':
            event(f"failure:{t['task_id']}", t['run_tag'], t['task_type'], 'Task needs attention', t['hypothesis'], status='failed', **args)
    results = []
    for r in result_rows:
        evaluation = scene._jsonb(r['evaluation'], {})
        result = {**dict(r), 'columns_used': scene._jsonb(r['columns_used'], []),
                  'columns_missing': scene._jsonb(r['columns_missing'], []), 'importance': scene._jsonb(r['feature_importance'], {}),
                  'okf_concept_ids': scene._jsonb(r['okf_concept_ids'], []), 'evaluation': evaluation,
                  **run_artifacts.result_identity(configs.get(r['run_tag'], {}), r['run_tag'], r['trial'])}
        results.append(result)
        event(f"result:{r['result_id']}", r['run_tag'], 'result', 'Analysis result available', r['hypothesis'],
              r['created_at'], r['question_id'], r['result_id'], r['trial'])
        voices = evaluation.get('interpretations') or []
        for voice in voices:
            if voice.get('text') or voice.get('error'):
                event(f"interpretation:{r['result_id']}:{voice.get('slot')}", r['run_tag'], 'interpretation',
                      voice.get('worker') or 'Interpretation recorded', voice.get('text') or voice.get('error'),
                      question_id=r['question_id'], result_id=r['result_id'], trial=r['trial'], status=voice.get('status') or 'recorded')
        if not voices and r['interpretation']:
            event(f"interpretation:{r['result_id']}", r['run_tag'], 'interpretation', 'Interpretation recorded', r['interpretation'],
                  question_id=r['question_id'], result_id=r['result_id'], trial=r['trial'])
    reports = {}
    for tag, artifact in zip(tags, artifacts):
        report = (artifact or {}).get('report')
        if report:
            reports[tag] = report
            if report.get('text') or report.get('error'):
                event(f'report:{tag}', tag, 'report', 'Report updated', report.get('text') or report.get('error'), status=report.get('status') or 'recorded')
    # The cap is explicit; browsing archives remains available through the question bank.
    return dict(events=events, questions=questions, results=results, reports=reports,
                generated_at=datetime.now(timezone.utc).isoformat(), record_limit=200)


_live_reads: dict[tuple[str, ...], asyncio.Task] = {}
_live_ready: dict[tuple[str, ...], float] = {}
LIVE_WAIT_SECONDS = 0.75


async def _prepare_live_response(tags):
    data = await live_outputs(tags)
    # Encode the snapshot once off the event loop, rather than recursively copying
    # large evaluation trees through FastAPI for every waiting client.
    return await asyncio.to_thread(json.dumps, data, default=jsonable_encoder,
                                   ensure_ascii=False, allow_nan=False, separators=(',', ':'))


async def live_outputs_response(tags: list[str]):
    """Coalesce expensive archive reads; polling never restarts unfinished work."""
    key = tuple(sorted(set(tags)))
    task = _live_reads.get(key)
    if task is not None and task.done() and asyncio.get_running_loop().time() - _live_ready.get(key, 0) > 2:
        if not task.cancelled():
            task.exception()
        _live_reads.pop(key, None)
        _live_ready.pop(key, None)
        task = None
    if task is not None and task.cancelled():
        _live_reads.pop(key, None)
        task = None
    if task is None:
        for old_key, old_task in list(_live_reads.items()):
            if len(_live_reads) >= 8 and old_task.done():
                if not old_task.cancelled():
                    old_task.exception()
                del _live_reads[old_key]
                _live_ready.pop(old_key, None)
        if len(_live_reads) >= 8:
            return JSONResponse(status_code=202, content={'status': 'loading', 'retry_after_ms': 1000})
        task = asyncio.create_task(_prepare_live_response(list(key)))
        _live_reads[key] = task
        task.add_done_callback(lambda completed: _live_ready.__setitem__(key, asyncio.get_running_loop().time()) if _live_reads.get(key) is completed else None)
    done, _ = await asyncio.wait({task}, timeout=LIVE_WAIT_SECONDS)
    if not done:
        return JSONResponse(status_code=202, content={'status': 'loading', 'retry_after_ms': 1000})
    try:
        payload = task.result()
    except BaseException:
        if _live_reads.get(key) is task:
            _live_reads.pop(key, None)
            _live_ready.pop(key, None)
        raise
    return Response(content=payload, media_type='application/json')


async def novelty_ranking(offset: int = 0, run_tag: str = '', source: str = 'all') -> dict[str, Any]:
    """Rank latest recorded result per hypothesis, never infer historical scores."""
    tags = await discovery_sources.scope(source)
    async def read(conn):
        rows = await conn.fetch("""
            WITH latest AS (
                SELECT DISTINCT ON (r.task_id) r.task_id, r.result_id, r.question_id,
                       r.run_tag, r.trial, r.hypothesis, r.auc,
                       r.evaluation->'knowledge_provenance'->'novelty' AS novelty
                FROM memstara_results r JOIN memstara_questions q USING (question_id)
                WHERE q.status <> 'cleared' AND ($1::text = '' OR r.run_tag = $1)
                  AND ($3::text[] IS NULL OR (coalesce(q.origin_run, '') = ANY($3) AND r.run_tag = ANY($3)))
                ORDER BY r.task_id, r.result_id DESC
            ), scored AS (
                SELECT *, CASE WHEN novelty->>'policy' = 'predicted_path_fraction_v1'
                    AND novelty->>'rankable' = 'true'
                    AND novelty->>'coverage' IN ('1', '1.0')
                    AND jsonb_typeof(novelty->'score') = 'number'
                    THEN (novelty->>'score')::numeric ELSE NULL END AS score
                FROM latest
            )
            SELECT *, count(*) OVER () AS total FROM scored
            ORDER BY CASE WHEN score BETWEEN 0 AND 1 THEN score ELSE NULL END DESC NULLS LAST,
                     result_id DESC LIMIT 51 OFFSET $2
        """, run_tag, offset, tags)
        items = [{k: v for k, v in dict(row).items() if k not in ('score', 'total')}
                 for row in rows[:50]]
        for item in items:
            item['novelty'] = scene._jsonb(item.get('novelty'), {})
        return {'items': items, 'total': rows[0]['total'] if rows else 0,
                'next_offset': offset + 50 if len(rows) > 50 else None,
                'policy': 'predicted_path_fraction_v1', 'run_tag': run_tag}
    result = await pools.guarded('memstara', read, None)
    if result is None:
        raise HTTPException(503, 'Novelty records are temporarily unavailable.')
    return result


_semantic_jobs: dict[str, asyncio.Task] = {}
SEMANTIC_WAIT_SECONDS = 1.0


async def semantic_questions(query: str = '', question_id: int | None = None, source: str = 'all'):
    """Read active question text only; heavy indexing runs off the request event loop."""
    from universe_semantics import index
    tags = await discovery_sources.scope(source)
    source_id = source
    async def read(conn):
        rows = await conn.fetch("SELECT question_id,text FROM memstara_questions "
                                "WHERE status <> 'cleared' AND ($1::text[] IS NULL OR coalesce(origin_run, '') = ANY($1)) ORDER BY question_id DESC", tags)
        total = len(rows)
        return [{'question_id': row['question_id'], 'text': row['text']} for row in rows], total
    source = await pools.guarded('memstara', read, None)
    if source is None:
        raise HTTPException(503, 'Question records are temporarily unavailable.')
    key = hashlib.sha256(json.dumps([source_id, source[0], query, question_id], sort_keys=True).encode()).hexdigest()
    task = _semantic_jobs.get(key)
    if task is None:
        for old_key, old_task in list(_semantic_jobs.items()):
            if old_task.done():
                if not old_task.cancelled():
                    old_task.exception()  # Retrieve exceptions from abandoned requests.
                del _semantic_jobs[old_key]
        if len(_semantic_jobs) >= 4:
            return JSONResponse({'status': 'indexing', 'retry_after': 2}, status_code=202)
        if source_id == 'all':
            task = asyncio.create_task(asyncio.to_thread(index, source[0], query, question_id))
        else:
            task = asyncio.create_task(asyncio.to_thread(index, source[0], query, question_id, scope=source_id))
        _semantic_jobs[key] = task
    try:
        result = await asyncio.wait_for(asyncio.shield(task), timeout=SEMANTIC_WAIT_SECONDS)
    except TimeoutError:
        return JSONResponse({'status': 'indexing', 'retry_after': 2}, status_code=202)
    except Exception:
        _semantic_jobs.pop(key, None)
        # Optional local model/cache failures must not break the regular question browser.
        raise HTTPException(503, 'Semantic view unavailable. Install viewer semantic dependencies and cache the pinned model; '
                            'the question list remains available.') from None
    _semantic_jobs.pop(key, None)
    result['total_questions'] = source[1]
    result['coverage'] = ('complete' if result.get('indexed_count', 0) + result.get('excluded_empty', 0)
                          == source[1] else 'changed_during_indexing')
    return result
