"""Read agent-authored answers from the selected invocation history."""
import asyncio
import json
import uuid
import time
from fastapi import HTTPException
from db import pools
import run_artifacts
from loop_history import call_loops
from queries import telemetry_jsonb
import stores

TEXT_FIELDS = (("final_answer", "Agent answer"), ("thought", "Agent note"),
               ("message", "Agent message"))


def text_outputs(value):
    """Only explicitly recorded agent text, never tool results or synthetic status."""
    if not isinstance(value, dict):
        return []
    seen, messages = set(), []
    for field, label in TEXT_FIELDS:
        text = value.get(field)
        if isinstance(text, str) and text.strip() and text not in seen:
            seen.add(text)
            messages.append((field, label, text))
    return messages



async def _conversation(tag, loop):
    try:
        async with asyncio.timeout(6):
            artifact = await asyncio.to_thread(run_artifacts.lookup, tag)
            if not artifact:
                raise HTTPException(404, 'This execution archive is unavailable.')
            calls = [c for c in call_loops(artifact['calls'])
                     if c.get('run_id') and (loop is None or c['loop'] == loop)]
            by_id = {c['run_id']: c for c in calls}
            async def read(conn):
                # Extract only the three displayed fields before JSONB conversion. The
                # old inlined expression reparsed entire output documents for each
                # predicate, leaving CPU-heavy queries alive after HTTP cancellation.
                payload = telemetry_jsonb("json_build_object('final_answer', text_fields.final_answer, 'thought', text_fields.thought, 'message', text_fields.message)")
                predicates = ' OR '.join(
                    f"(jsonb_typeof(payload->'{field}') = 'string' "
                    f"AND length(btrim(payload->>'{field}')) > 0)" for field, _ in TEXT_FIELDS)
                return await conn.fetch(f"""WITH scoped_steps AS MATERIALIZED (
                    SELECT id, run_id, started_at, completed_at, output_data
                    FROM run_steps WHERE run_id = ANY($1::uuid[])
                    ORDER BY coalesce(completed_at, started_at) DESC NULLS LAST, id DESC
                    LIMIT 500
                ), messages AS MATERIALIZED (
                    SELECT s.id, s.run_id, coalesce(s.completed_at, s.started_at) AS recorded_at,
                           a.name, {payload} AS payload
                    FROM scoped_steps s JOIN agent_runs r ON r.id=s.run_id
                    JOIN agents a ON a.id=r.agent_id
                    CROSS JOIN LATERAL json_to_record(
                        CASE WHEN json_typeof(s.output_data::json) = 'object'
                             THEN s.output_data::json ELSE '{{}}'::json END
                    ) AS text_fields(final_answer json, thought json, message json))
                    SELECT id, run_id, recorded_at AS started_at, name, payload::text AS output
                    FROM messages WHERE {predicates}
                    ORDER BY recorded_at DESC NULLS LAST, id DESC LIMIT 201""",
                    [uuid.UUID(i) for i in by_id])
            rows = await pools.guarded('core', read, None) if by_id else []
            if rows is None:
                raise HTTPException(503, 'Agent conversation is temporarily unavailable.')
            messages = []
            for r in reversed(rows[:200]):
                value = json.loads(r['output'] or '{}')
                call = by_id[str(r['run_id'])]
                name = stores.reported_as(r.get('name') or call['stage'])
                for field, label, text in text_outputs(value):
                    messages.append({'id': f"{r['id']}:{field}", 'run_id': str(r['run_id']),
                                     'stage': call['stage'], 'name': name, 'label': stores.label_of(name),
                                     'kind': field, 'kind_label': label, 'loop': call['loop'],
                                     'at': r['started_at'].isoformat() if r['started_at'] else None,
                                     'text': text[:50000], 'truncated': len(text) > 50000})
            return {'run_tag': tag, 'loop': loop, 'messages': messages, 'limited': True, 'note': 'Showing up to 200 message-bearing records from the latest 500 steps in this scope. Select a loop to inspect older history.'}
    except TimeoutError:
        raise HTTPException(503, 'Conversation lookup timed out.') from None


_conversations = {}
_pending = {}


async def conversation(tag, loop):
    key = (tag, loop)
    hit = _conversations.get(key)
    if hit and time.monotonic() - hit[0] < 4:
        return hit[1]
    task = _pending.get(key)
    if task is None:
        if len(_pending) >= 32:
            raise HTTPException(503, 'Conversation history is busy; retrying is safe.')
        task = asyncio.create_task(_conversation(tag, loop))
        _pending[key] = task
        def finished(done):
            _pending.pop(key, None)
            if not done.cancelled() and done.exception() is None:
                if len(_conversations) >= 32:
                    _conversations.pop(min(_conversations, key=lambda k:_conversations[k][0]))
                _conversations[key] = (time.monotonic(), done.result())
        task.add_done_callback(finished)
    return await asyncio.shield(task)
