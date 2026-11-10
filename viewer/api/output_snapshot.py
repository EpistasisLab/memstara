"""Summary/detail reads for output screens, independent of the live agent scene.

All retained result identities and fitted metrics stay in the summary. Agent
documents are fetched for a selected loop. Export endpoints still read full data.
Cold preparation survives the HTTP wait budget, so polling cannot repeatedly
cancel the same large history before it finishes.
"""
import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from db import pools
import continuations
import output_results
import run_artifacts as archive

_cache = OrderedDict()
_pending = {}
TTL = 10
WAIT = 3
PREPARE_TIMEOUT = 60


def narrative(item):
    text = item.get('text') or ''
    return {**item, 'text': '', 'has_text': bool(text.strip()),
            'text_revision': hashlib.sha256(text.encode()).hexdigest()}


def summary_result(row):
    measured = row.get('evaluation') or {}
    branches = measured.get('interpretations') or ([{
        'slot': 1, 'worker': '', 'skill': '', 'status': 'done',
        'text': row['interpretation'], 'error': '',
    }] if row.get('interpretation') else [])
    # Keep every fitted metric, parameter, seed and schedule identifier. Large
    # attribution arrays and narrative context belong to the detail endpoint.
    lean = {k: v for k, v in measured.items() if k not in (
        'knowledge_provenance', 'specialist_xai', 'explanation',
        'question_contract', 'interpretation_limitations', 'interpretations',
    )}
    if isinstance(lean.get('model_results'), dict):
        lean['model_results'] = {model: {k: v for k, v in value.items()
                                       if k not in ('specialist_xai', 'explanation', 'knowledge_provenance')}
                                 for model, value in lean['model_results'].items()}
    lean['interpretations'] = [narrative({k: v for k, v in branch.items()
                                         if k != 'limitations'}) for branch in branches]
    return {**row, 'interpretation': '', 'evaluation': lean, 'detail_deferred': True}


def archive_scope(tag):
    history = continuations.tags(tag)
    item = archive.lookup(tag)
    if not item:
        raise HTTPException(503, 'Execution archive is unavailable; saved results are unchanged.')
    report = continuations.reports(history, item)
    return history, item, report, archive.configs()


async def records(tag):
    history, item, report, configs = await asyncio.to_thread(archive_scope, tag)
    # Send frozen choices once per execution, not prompts once per result tile.
    # A continued execution must not relabel earlier results with its new skills.
    item = {**item, 'skill_configurations': {
        source: {key: config[key] for key in ('combination_plan', 'books') if key in config}
        for source in history if (config := configs.get(source)) is not None
    }}
    groups = []
    # Bound cold DB work instead of opening one connection per retained session.
    for source in history:
        group = await output_results.results(source)
        groups.extend({**row, **archive.result_identity(configs.get(source) or {}, source, row['trial'])}
                      for row in group)
    return history, item, report, groups


def make_summary(tag, history, item, report, rows):
    config = item['config']
    value = {
        'run_tag': tag, 'scene_scope': 'outputs', 'stale': False,
        'run_configuration': config, 'pipeline': item.get('pipeline'),
        'skill_configurations': item.get('skill_configurations', {}),
        'experiment': {'id': history[0], 'head_run_tag': tag, 'run_tags': history,
            'name': config.get('pipeline_name'),
            'scheduled_combinations': (config.get('combination_plan') or {}).get('total_loops'),
            'result_combinations': len({r.get('iteration') or
                r['trial'] // max(1, config.get('trials') or 1) + 1 for r in rows})},
        'report': {**report, 'text': '', 'specialist_explanation': None,
                   'explanation_outputs': [narrative(o) for o in report.get('explanation_outputs', [])]},
        'results': [summary_result(r) for r in rows],
        # These screen-independent shapes are intentionally not queried. In
        # particular, slow Motoro scene/history reads cannot block saved outputs.
        'health': pools.health.as_dict(),
        'runs': [], 'board': {'lanes': {}, 'tasks': []},
        'scene': {'places': [], 'agents': [], 'flashes': []},
        'agents': [], 'feed': [], 'access': {'rows': [], 'windows': []},
    }
    encoded = json.dumps(value, sort_keys=True, default=jsonable_encoder, separators=(',', ':'))
    value['output_revision'] = hashlib.sha256(encoded.encode()).hexdigest()
    value['generated_at'] = datetime.now(UTC).isoformat()
    return value


async def prepare(tag):
    async with asyncio.timeout(PREPARE_TIMEOUT):
        history, item, report, rows = await records(tag)
        value = await asyncio.to_thread(make_summary, tag, history, item, report, rows)
        _cache[tag] = (time.monotonic(), value)
        _cache.move_to_end(tag)
        while len(_cache) > 16:
            _cache.popitem(last=False)
        return value


async def snapshot(tag):
    cached = _cache.get(tag)
    if cached and time.monotonic() - cached[0] < TTL:
        return cached[1]
    task = _pending.get(tag)
    if task is None or task.done():
        task = asyncio.create_task(prepare(tag))
        _pending[tag] = task
        # Retrieve exceptions even if the requesting browser disconnects.
        def finished(done):
            if not done.cancelled():
                done.exception()
            if _pending.get(tag) is done:
                _pending.pop(tag, None)
        task.add_done_callback(finished)
    try:
        return await asyncio.wait_for(asyncio.shield(task), WAIT)
    except TimeoutError:
        if cached:
            return {**cached[1], 'stale': True}
        if not task.done():
            raise HTTPException(202, 'Saved outputs are being prepared.', headers={'Retry-After': '2'}) from None
        raise HTTPException(503, 'Saved output preparation timed out; retained records are unchanged.') from None
    except HTTPException:
        if cached:
            return {**cached[1], 'stale': True}
        raise


async def detail(tag, loop):
    history, item, report, rows = await records(tag)
    trials = max(1, item['config'].get('trials') or 1)
    selected = [r for r in rows if (r.get('iteration') or r['trial'] // trials + 1) == loop]
    outputs = [o for o in report.get('explanation_outputs', []) if o['loop'] == loop]
    if not selected and not outputs:
        raise HTTPException(404, 'No saved output exists for this replicate.')
    return {'run_tag': tag, 'loop': loop, 'run_tags': history,
            'results': selected, 'explanation_outputs': outputs}
