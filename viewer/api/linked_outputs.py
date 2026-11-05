"""Export saved results and final agent documents with explicit foreign keys.

All operations are reads. Raw documents live in separate collections; result rows
carry IDs. Never use a scheduler position alone to join different executions.
"""
import asyncio
import copy
import hashlib
import json
from datetime import UTC, datetime

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from db import pools
import run_artifacts as archive
from continuations import expand
from experiments import execution as registered_execution

VERSION = 'linked_agent_outputs_v1'
JSON_FIELDS = {'evaluation', 'columns_used', 'columns_missing', 'feature_importance',
               'okf_concept_ids', 'match_trace'}


def stable_id(prefix, *parts):
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return prefix + '-' + hashlib.sha256(raw.encode()).hexdigest()


def decoded(row):
    return {k: json.loads(v) if k in JSON_FIELDS and isinstance(v, str) else v for k, v in dict(row).items()}


def availability(documents, missing=False):
    if not documents:
        return 'not_recorded'
    if missing or any(d['status'] not in ('done', 'completed') for d in documents):
        return 'partial'
    return 'complete'


def assemble(raw_results, artifacts, configs):
    results, interpretations, explanations, warnings = [], {}, {}, []
    for raw in raw_results:
        row = copy.deepcopy(raw)
        tag, identifier = row['run_tag'], row['result_id']
        identity = archive.result_identity(configs.get(tag) or {}, tag, row['trial'])
        row.update(identity, result_uid=stable_id('res', tag, identifier))
        row.update(interpretation_output_ids=[], explanation_output_ids=[])
        evaluation = row.get('evaluation') or {}
        skills = evaluation.get('skills') or {}
        branches = evaluation.get('interpretations') or []
        if not isinstance(branches, list):
            raise HTTPException(503, 'Recorded interpretation branches are invalid')
        documents = [dict(b) for b in branches if isinstance(b, dict)]
        legacy = row.pop('interpretation', None)
        if isinstance(legacy, str) and legacy.strip() and not any(b.get('text') == legacy for b in documents):
            selected = skills.get('interpreter') or []
            documents.append({'text': legacy, 'slot': None if branches else 1,
                              'skill': selected[0] if isinstance(selected, list) and len(selected) == 1 else None,
                              'status': 'done', 'kind': 'legacy_combined' if branches else 'legacy'})
        pending, stored = [], []
        for index, branch in enumerate(documents):
            text = branch.get('text')
            metadata = {k: v for k, v in branch.items() if k != 'text'}
            if not isinstance(text, str) or not text.strip():
                pending.append({**metadata, 'availability': 'no_saved_text'})
                continue
            # Identity includes the content revision, but no export timestamp.
            output_id = stable_id('int', tag, identifier, branch.get('slot'), branch.get('worker'),
                                  branch.get('skill'), text, branch.get('limitations'), branch.get('error'))
            output = {**metadata, 'output_id': output_id, 'agent_role': 'interpretation',
                      **identity, 'result_id': identifier, 'result_uids': [row['result_uid']],
                      'text': text, 'status': branch.get('status') or 'unknown',
                      'result_limitations': evaluation.get('interpretation_limitations'),
                      'content_sha256': hashlib.sha256(text.encode()).hexdigest()}
            interpretations[output_id] = output
            stored.append(output)
            row['interpretation_output_ids'].append(output_id)
        row['interpretation_output_ids'] = list(dict.fromkeys(row['interpretation_output_ids']))
        row['interpretation_status'] = availability(stored, bool(pending))
        if not stored and evaluation.get('interpretation_limitations'):
            pending.append({'scope': 'result', 'limitations': evaluation['interpretation_limitations'],
                            'availability': 'no_saved_text'})
        row['interpretation_pending'] = pending
        # Move the same documents out of the result's nested evaluation as well.
        if 'interpretations' in evaluation:
            evaluation['interpretations'] = [{k: v for k, v in doc.items() if k not in ('text', 'limitations', 'error')}
                                            for doc in documents]
        evaluation.pop('interpretation_limitations', None)
        row['evaluation'] = evaluation
        results.append(row)

    for tag, artifact in artifacts.items():
        config = configs.get(tag) or {}
        for output in artifact.get('report', {}).get('explanation_outputs', []):
            text = output.get('text')
            if not isinstance(text, str) or not text.strip():
                continue
            loop = output.get('loop')
            candidates = [r for r in results if r['run_tag'] == tag]
            explicit = output.get('result_id')
            if explicit is not None:
                matched = [r for r in candidates if r['result_id'] == explicit]
                basis = 'recorded_result_id'
            elif output.get('result_ids'):
                matched = [r for r in candidates if r['result_id'] in output['result_ids']]
                basis = 'recorded_result_ids'
            elif output.get('task_ids'):
                matched = [r for r in candidates if r.get('task_id') is not None and r['task_id'] in output['task_ids']]
                basis = 'recorded_task_ids'
            else:
                matched = [r for r in candidates if r.get('iteration') == loop]
                basis = 'unique_result_in_recorded_loop'
                if len(matched) != 1:
                    matched = []
            # Even an explicit result reference must agree with the recorded loop.
            matched = [r for r in matched if loop is None or r.get('iteration') == loop]
            calls = [c for c in artifact.get('calls', []) if c.get('stage') == 'report' and c.get('loop') == loop
                     and (not output.get('agent_run_id') or c.get('run_id') == output['agent_run_id'])]
            recorded_skills = sorted({c['skill']['id'] for c in calls if isinstance(c.get('skill'), dict) and c['skill'].get('id')})
            output_id = stable_id('exp', tag, loop, explicit, sorted(output.get('result_ids') or []),
                                  sorted(output.get('task_ids') or []), output.get('agent_run_id'),
                                  output.get('expert'), text)
            identity = {'run_tag': tag, 'pipeline_id': config.get('pipeline_id'),
                        **archive.identity(config, loop)}
            record = {**copy.deepcopy(output), **identity, 'output_id': output_id,
                      'agent_role': 'explanation', 'agent_run_ids': sorted({c['run_id'] for c in calls if c.get('run_id')}),
                      'skills': recorded_skills, 'result_uids': [r['result_uid'] for r in matched],
                      'result_ids': [r['result_id'] for r in matched], 'association_basis': basis if matched else 'unresolved',
                      'status': output.get('status') or 'unknown', 'content_sha256': hashlib.sha256(text.encode()).hexdigest()}
            explanations[output_id] = record
            for row in matched:
                if output_id not in row['explanation_output_ids']:
                    row['explanation_output_ids'].append(output_id)
            if not matched:
                warnings.append({'code': 'unlinked_explanation', 'output_id': output_id,
                                 'run_tag': tag, 'loop': loop,
                                 'message': 'No unambiguous result link was recorded. Text is retained without guessing.'})
    for row in results:
        row['explanation_status'] = availability([explanations[i] for i in row['explanation_output_ids']])
    return {'results': results, 'interpretations': list(interpretations.values()),
            'explanations': list(explanations.values()), 'warnings': warnings}


async def bundle(requested_tags, include_evidence=False):
    selected = list(dict.fromkeys(requested_tags))
    if not selected or len(selected) > 32 or any(not t.strip() or len(t) > 180 for t in selected):
        raise HTTPException(400, 'Choose up to 32 nonempty execution IDs')
    tags = await asyncio.to_thread(expand, selected)
    configs = await asyncio.to_thread(archive.configs)
    artifacts = await asyncio.to_thread(lambda: {tag: archive.lookup(tag, preserve_output_versions=True) for tag in tags})
    if any(item is None for item in artifacts.values()):
        raise HTTPException(503, 'An execution archive is unavailable; no incomplete export was substituted')
    async def read(conn):
        return [decoded(row) for row in await conn.fetch(
            'SELECT * FROM memstara_results WHERE run_tag = ANY($1::text[]) ORDER BY result_id', tags)]
    rows = await pools.guarded('memstara', read, None)
    if rows is None:
        raise HTTPException(503, 'Result export is unavailable; retry without changing the experiment')
    linked = await asyncio.to_thread(assemble, rows, artifacts, configs)
    executions = []
    if include_evidence:
        for tag in tags:
            try:
                record = await registered_execution(tag)
                record['registry_status'] = 'registered'
            except HTTPException as error:
                if error.status_code != 404:
                    raise
                record = {'run_tag': tag, 'configuration': configs.get(tag), 'registry_status': 'not_registered'}
                linked['warnings'].append({'code': 'registry_not_registered', 'run_tag': tag})
            # Use this export's result snapshot and foreign keys consistently.
            record['results'] = [row for row in linked['results'] if row['run_tag'] == tag]
            record['explanation_output_ids'] = [o['output_id'] for o in linked['explanations'] if o['run_tag'] == tag]
            executions.append(record)
    return jsonable_encoder({'schema_version': VERSION, 'generated_at': datetime.now(UTC).isoformat(),
                             'requested_run_tags': selected, 'run_tags': tags, **linked, 'executions': executions})
