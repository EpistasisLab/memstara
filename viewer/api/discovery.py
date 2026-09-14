"""Read-only question discovery, linked only through recorded question identifiers."""
import asyncio
from typing import Any

from fastapi import HTTPException
from db import pools
import scene
import queries
import run_artifacts

QUESTION_FIELDS = "question_id, text, okf_tags, rationale, origin_run, origin_wave, times_used, best_auc, status, created_at, writer"


async def question_list(before: int = 0) -> dict[str, Any]:
    async def read(conn):
        rows = await conn.fetch(f"SELECT {QUESTION_FIELDS} FROM memstara_questions "
                                "WHERE ($1::integer = 0 OR question_id < $1) "
                                "ORDER BY question_id DESC LIMIT 121", before)
        items = [{**dict(row), 'okf_tags': scene._jsonb(row['okf_tags'], []),
                  'created_at': scene._iso(row['created_at'])} for row in rows[:120]]
        return {'questions': items, 'next_before': items[-1]['question_id'] if len(rows) > 120 else None}
    result = await pools.guarded('memstara', read, None)
    if result is None:
        raise HTTPException(503, 'Question records are temporarily unavailable.')
    return result


async def question_detail(question_id: int) -> dict[str, Any]:
    async def read(conn):
        question = await conn.fetchrow(f'SELECT {QUESTION_FIELDS} FROM memstara_questions WHERE question_id=$1', question_id)
        if question is None:
            return None
        # No fuzzy joins on wording: a result is linked only by its persisted question_id.
        tasks = await conn.fetch(queries.BOARD.replace("WHERE ($1 = '' OR run_tag = $1)",
                                  'WHERE question_id = $1').replace('ORDER BY task_id', 'ORDER BY task_id DESC LIMIT 100'), question_id)
        results = await conn.fetch(queries.RESULTS.replace("WHERE ($1 = '' OR run_tag = $1)",
                                    'WHERE question_id = $1').replace('ORDER BY result_id', 'ORDER BY result_id DESC') + ' LIMIT 100', question_id)
        return {
            'question': {**dict(question), 'okf_tags': scene._jsonb(question['okf_tags'], [])},
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
                                    'WHERE origin_run = ANY($1::text[]) ORDER BY question_id DESC LIMIT 200', tags)
        tasks = await conn.fetch('SELECT task_id, question_id, run_tag, trial, hypothesis, '
                                 'columns_used, auc, interpretation, task_type, status, updated_at '
                                 'FROM memstara_blackboard WHERE run_tag = ANY($1::text[]) '
                                 'ORDER BY updated_at DESC LIMIT 200', tags)
        results = await conn.fetch(queries.RESULTS.replace('SELECT result_id,', 'SELECT question_id, result_id,')
                                   .replace("WHERE ($1 = '' OR run_tag = $1)", 'WHERE run_tag = ANY($1::text[])')
                                   .replace('ORDER BY result_id', 'ORDER BY result_id DESC LIMIT 200'), tags)
        return questions, tasks, results
    try:
        async with asyncio.timeout(4):
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
