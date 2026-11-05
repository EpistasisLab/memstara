"""Narrative exports retain original execution identity and never guess joins."""
import asyncio
import copy
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import linked_outputs as linked
import run_artifacts as archive
from explanation_outputs import saved_outputs


def row(tag='old', number=1, task=7, trial=0):
    return {'run_tag': tag, 'result_id': number, 'task_id': task, 'trial': trial,
            'interpretation': '', 'evaluation': {'interpretations': [
                {'slot': 1, 'skill': 'shap', 'worker': 'a', 'status': 'done', 'text': '\n# Exact 한글\n'},
                {'slot': 2, 'skill': 'lime', 'status': 'failed', 'text': '', 'error': 'Not saved'}]}}


def configs(*tags):
    return {tag: {'pipeline_id': 'p', 'trials': 2, 'waves': 2} for tag in tags}


def artifact(*outputs):
    return {'report': {'text': 'Numeric report must never become agent text', 'explanation_outputs': list(outputs)}}


def test_multi_branch_exact_text_pending_and_stable_content_identity():
    source = [row()]
    original = copy.deepcopy(source)
    first = linked.assemble(source, {}, configs('old'))
    assert source == original
    result = first['results'][0]
    assert len(result['interpretation_output_ids']) == 1
    assert result['interpretation_status'] == 'partial'
    assert result['interpretation_pending'][0]['error'] == 'Not saved'
    output = first['interpretations'][0]
    assert output['text'] == '\n# Exact 한글\n'
    assert output['result_uids'] == [result['result_uid']]
    assert 'interpretation' not in result
    assert 'text' not in result['evaluation']['interpretations'][0]
    assert first == linked.assemble(source, {}, configs('old'))
    source[0]['evaluation']['interpretations'][0]['text'] += 'revision'
    changed = linked.assemble(source, {}, configs('old'))
    assert changed['results'][0]['result_uid'] == result['result_uid']
    assert changed['interpretations'][0]['output_id'] != output['output_id']


def test_resume_same_result_number_never_shares_an_output_identity():
    result = linked.assemble([row('old'), row('retry')], {
        t: artifact({'loop': 1, 'text': 'same text', 'status': 'completed'}) for t in ('old', 'retry')},
        configs('old', 'retry'))
    assert len({r['result_uid'] for r in result['results']}) == 2
    assert len({d['output_id'] for d in result['interpretations']}) == 2
    for document in result['explanations']:
        match = next(r for r in result['results'] if r['run_tag'] == document['run_tag'])
        assert document['result_uids'] == [match['result_uid']]
        assert document['output_id'] in match['explanation_output_ids']


def test_explicit_task_ids_allow_many_results_and_ambiguous_legacy_stays_unlinked():
    rows = [row(number=1, task=7), row(number=2, task=8, trial=1)]
    result = linked.assemble(rows, {'old': artifact(
        {'loop': 1, 'task_ids': [7,8], 'text': 'Shared exact output\n', 'status': 'completed'},
        {'loop': 1, 'text': 'Ambiguous but preserved'},
        {'loop': 2, 'result_id': 1, 'text': 'Wrong loop must not link'})}, configs('old'))
    assert len(result['explanations'][0]['result_uids']) == 2
    assert result['explanations'][1]['result_uids'] == []
    assert result['explanations'][2]['result_uids'] == []
    assert len(result['warnings']) == 2
    assert all(len(r['explanation_output_ids']) == 1 for r in result['results'])


def test_missing_legacy_limitations_and_multiple_interpretations_are_retained():
    source = row()
    source['evaluation']['interpretations'][1].update(text='Second exact text', status='done')
    result = linked.assemble([source], {}, configs('old'))
    assert len(result['interpretations']) == 2
    assert result['results'][0]['interpretation_status'] == 'complete'
    source['evaluation'] = {'interpretation_limitations': 'Stopped before output'}
    missing = linked.assemble([source], {}, configs('old'))['results'][0]
    assert missing['interpretation_output_ids'] == []
    assert missing['interpretation_pending'][0]['limitations'] == 'Stopped before output'
    assert missing['explanation_status'] == 'not_recorded'


def test_modern_reader_exposes_only_verified_final_link_metadata(tmp_path):
    root = tmp_path / 'explanation_io'
    root.mkdir()
    output = root / 'output-abcdef.json'
    output.write_text(json.dumps({'run_tag': 'old', 'loop': 1, 'output': 'Saved original\n',
        'provenance': {'task_ids': [7, 8]}, 'execution': {'run_id': 'agent-run', 'status': 'completed'}, 'expert': 'hiv'}))
    (root/'loop-1.json').write_text(json.dumps({'receipt': {'path': str(output),
        'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}}))
    record = saved_outputs(tmp_path, 'old')[0]
    assert record['task_ids'] == [7, 8] and record['agent_run_id'] == 'agent-run'
    assert record['text'] == 'Saved original\n' and record['expert'] == 'hiv'


def test_archive_export_retains_distinct_recovered_versions(tmp_path, monkeypatch):
    run = tmp_path/'run'
    recovery = run/'report-recovery-1'
    recovery.mkdir(parents=True)
    (run/'config.json').write_text(json.dumps({'run_tag': 'old', **configs('old')['old']}))
    monkeypatch.setattr(archive, 'ROOT', tmp_path)
    monkeypatch.setattr(archive, 'saved_outputs', lambda directory, tag: [
        {'loop': 1, 'result_id': 1, 'text': directory.name, 'status': 'done'}])
    assert len(archive.lookup('old')['report']['explanation_outputs']) == 1
    assert len(archive.lookup('old', preserve_output_versions=True)['report']['explanation_outputs']) == 2


def test_bundle_continuation_result_snapshot_and_registry_gap(monkeypatch):
    monkeypatch.setattr(linked, 'expand', lambda selected: ['old', 'retry'])
    monkeypatch.setattr(archive, 'configs', lambda: configs('old', 'retry'))
    monkeypatch.setattr(archive, 'lookup', lambda tag, **kwargs: artifact())
    conn = AsyncMock()
    conn.fetch.return_value = [row('old'), row('retry', number=2)]
    async def read(store, callback, fallback):
        return await callback(conn)
    monkeypatch.setattr(linked.pools, 'guarded', read)
    async def registry(tag):
        if tag == 'old':
            raise HTTPException(404, 'Not registered')
        return {'run_tag': tag, 'results': ['stale'], 'agents': [], 'report': {'text': 'Recorded numeric report'}}
    monkeypatch.setattr(linked, 'registered_execution', registry)
    result = asyncio.run(linked.bundle(['retry'], True))
    assert result['run_tags'] == ['old', 'retry']
    assert len(result['results']) == 2
    assert result['executions'][0]['registry_status'] == 'not_registered'
    assert result['executions'][1]['report']['text'] == 'Recorded numeric report'
    assert result['executions'][1]['results'] == [result['results'][1]]
    conn.fetch.assert_awaited_once()


def test_failed_database_never_exports_an_empty_success(monkeypatch):
    monkeypatch.setattr(linked, 'expand', lambda selected: selected)
    monkeypatch.setattr(archive, 'configs', lambda: configs('old'))
    monkeypatch.setattr(archive, 'lookup', lambda tag, **kwargs: artifact())
    monkeypatch.setattr(linked.pools, 'guarded', AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as error:
        asyncio.run(linked.bundle(['old']))
    assert error.value.status_code == 503
