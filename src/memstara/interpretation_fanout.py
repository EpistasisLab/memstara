"""One routed interpretation task per skill; one aggregate result per ML outcome.

Uses existing JSONB metadata, avoiding runtime schema changes. Callers must hold
an advisory transaction lock on the source task before changing a child result.
"""
import json


def metadata(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def pending_slots(tasks):
    """None means legacy shared work; a set pins fan-out work to its own skills."""
    ready = [t for t in tasks if t['task_type'] == 'interpret' and t['status'] == 'ready']
    if any(not metadata(t.get('evaluation')).get('interpretation_branch') for t in ready):
        return None
    return {int(metadata(t.get('evaluation'))['interpretation_branch']['slot']) for t in ready}


async def expand(conn, task_id, config, trial=None):
    if config.get('interpretation_mode') != 'all_per_hypothesis':
        return
    count = config.get('interpreters', 1)
    books = config.get('books', {}).get('interpreter') or ['']
    if config.get('combination_plan'):
        from memstara.combinations import task_books
        if trial is None:
            trial = await conn.fetchval('SELECT trial FROM memstara_blackboard WHERE task_id=$1', task_id)
        books = task_books(config, trial).get('interpreter') or ['']
        count = 1
    for slot in range(1, count + 1):
        branch = {'source_task_id': task_id, 'slot': slot, 'total': count,
                  'worker': f'interpret#{slot}', 'skill': books[slot - 1] if slot <= len(books) else books[0]}
        if slot == 1:
            await conn.execute("UPDATE memstara_blackboard SET evaluation=evaluation || $2::jsonb "
                               "WHERE task_id=$1", task_id, json.dumps({'interpretation_branch': branch}))
        else:
            await conn.execute('''
                INSERT INTO memstara_blackboard
                    (run_tag, trial, perspective, status, task_type, hypothesis, columns,
                     okf_concept_ids, match_trace, question_id, y_column, subset_path,
                     columns_used, columns_missing, auc, feature_importance, model,
                     evaluation, hypothesis_id, attempts)
                SELECT run_tag, trial, perspective, 'ready', 'interpret', hypothesis, columns,
                       okf_concept_ids, match_trace, question_id, y_column, subset_path,
                       columns_used, columns_missing, auc, feature_importance, model,
                       evaluation || $2::jsonb, hypothesis_id, 2
                FROM memstara_blackboard WHERE task_id=$1
            ''', task_id, json.dumps({'interpretation_branch': branch}))


async def aggregate(conn, source_id):
    rows = await conn.fetch('''
        SELECT task_id, status, error, interpretation, evaluation FROM memstara_blackboard
        WHERE evaluation->'interpretation_branch'->>'source_task_id'=$1
        ORDER BY (evaluation->'interpretation_branch'->>'slot')::int
    ''', str(source_id))
    if not rows:
        return
    items = []
    for row in rows:
        branch = metadata(row['evaluation'])['interpretation_branch']
        items.append({**branch, 'task_id': row['task_id'], 'status': row['status'],
                      'text': row['interpretation'], 'error': row['error'],
                      'limitations': metadata(row['evaluation']).get('interpretation_limitations', ''),
                      'specialist': metadata(row['evaluation']).get('specialist_interpretation')})
    # Metadata and availability belong outside the agent-authored narrative.
    # Keep every branch separately in `interpretations`; this legacy text field
    # concatenates completed originals without inserting titles or placeholders.
    combined = '\n\n'.join(item['text'] for item in items if item['status'] == 'done')
    summary = {'interpreter': None, 'interpretations': items, 'interpretation_mode': 'all_per_hypothesis',
               'interpretations_complete': all(i['status'] == 'done' for i in items)}
    # The source-task lock serializes concurrent completions. Update in place so
    # result links stay stable while the remaining interpretations arrive.
    existing = await conn.fetchval('SELECT result_id FROM memstara_results WHERE task_id=$1', source_id)
    if existing is not None:
        await conn.execute('UPDATE memstara_results SET interpretation=$2, '
                           'evaluation=evaluation || $3::jsonb WHERE result_id=$1',
                           existing, combined, json.dumps(summary))
    else:
        await conn.execute('''
            INSERT INTO memstara_results
                (task_id, run_tag, trial, perspective, hypothesis, columns, columns_used,
                 columns_missing, okf_concept_ids, match_trace, question_id, y_column,
                 auc, feature_importance, model, interpretation, evaluation, hypothesis_id)
            SELECT task_id, run_tag, trial, perspective, hypothesis, columns, columns_used,
                   columns_missing, okf_concept_ids, match_trace, question_id, y_column,
                   auc, feature_importance, model, $2, evaluation || $3::jsonb, hypothesis_id
            FROM memstara_blackboard WHERE task_id=$1
        ''', source_id, combined, json.dumps(summary))
