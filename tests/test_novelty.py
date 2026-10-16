"""Scoring is deterministic and unknown evidence is never a zero score."""
import json
from pathlib import Path

import pytest

from memstara.knowledge_provenance import document_provenance, hypothesis_provenance
from memstara.novelty import score_paths, source_paths


def source(status='predicted', body=None):
    body = body or '# Instances\n| # | path |\n|---|---|\n| 1 | A → B |\n'
    return {'id': 'a', 'declared_ref': 'alias', 'status': status,
            'provenance': document_provenance({'evidence': status}, body)}


def use(ref='a', pid='1'):
    return {'source_id': ref, 'path_id': pid, 'rationale': 'This path links the predictor to the outcome.'}


@pytest.mark.parametrize('status,score', [('observed', 0.0), ('predicted', 1.0)])
def test_full_coverage_scoring_and_dedup(status, score):
    result = score_paths([source(status)], [use(), use('alias')])
    assert result['score'] == score and result['coverage'] == 1 and result['rankable']
    assert len(result['paths']) == 1
    assert score_paths([source(status)], [use()]) == result
    assert result['scientific_validation'] == 'not_validated'


def test_mixed_document_is_not_uniform_path_annotation():
    result = score_paths([source('mixed')], [use()])
    assert result['score'] is None and not result['rankable']
    assert result['counts']['unknown'] == 1


def test_explicit_edges_and_fraction():
    fields = {'metapath_instances': [
        {'id': '1', 'edges': [{'evidence': 'observed'}, {'evidence': 'predicted'}]},
        {'id': '2', 'edges': [{'evidence': 'observed'}]}]}
    metadata = document_provenance(fields, '')
    s = {'id': 'a', 'status': 'unknown', 'provenance': metadata}
    result = score_paths([s], [use(), use(pid='2')])
    assert result['score'] == .5 and result['counts']['mixed'] == 1
    assert metadata['paths'][0]['predicted_edges'] == 1


@pytest.mark.parametrize('claims', [None, [], [None], [use('invented')], [use(pid='absent')],
                                    [{'source_id': 'a', 'path_id': '1'}]])
def test_missing_and_invalid_claims_are_unranked(claims):
    result = score_paths([source()], claims)
    assert result['score'] is None and not result['rankable']


def test_conflicts_and_unattributed_citations_prevent_ranking():
    s = source(body='# Evidence — OBSERVED\n# Instances\n| # | path |\n|---|---|\n| 1 | A → B |')
    assert score_paths([s], [use()])['score'] is None
    other = {**source(), 'id': 'other', 'declared_ref': 'other'}
    result = score_paths([source(), other], [use()])
    assert result['score'] is None and 'cited_source_without_path_attribution' in result['diagnostics']


def test_predicted_edge_adapter_and_unknown_formats():
    text = '# Predicted edges — R\n| overall rank | source | target |\n|---|---|---|\n| 8 | A | B |'
    metadata = document_provenance({'type': 'Predicted Edges', 'evidence': 'predicted'}, text)
    assert metadata['paths'][0]['path_id'] == '8'
    assert metadata['paths'][0]['status'] == 'predicted'
    assert source_paths({}, 'free form custom corpus', 'unknown') == []
    assert source_paths({}, '```\n'+text+'\n```', 'predicted') == []
    duplicate = '# Instances\n| # | path |\n|---|---|\n| 1 | A |\n| 1 | B |'
    assert all(p['status'] == 'unknown' for p in source_paths({}, duplicate, 'predicted'))


def test_run_read_attribution_persists_and_does_not_cross_runs(tmp_path):
    metadata = source()['provenance']
    (tmp_path/'knowledge_reads.jsonl').write_text(json.dumps({'results': [
        {'status': 'read', 'id': 'a', 'knowledge_provenance': metadata}]}))
    kwargs = dict(run_tag='run', trial=0, question_id=9, path_uses=[use()])
    result = hypothesis_provenance(['a'], str(tmp_path/'config.json'), **kwargs)
    assert result['novelty']['score'] == 1
    assert result['novelty']['paths'][0]['parsed_source_sha256'] == metadata['parsed_source_sha256']
    assert hypothesis_provenance(['a'], str(tmp_path/'other'/'config.json'), **kwargs)['novelty']['score'] is None
    assert hypothesis_provenance([], '', **kwargs)['novelty']['score'] is None


def test_real_corpus_annotations_are_conservative():
    from memstara.mcp_servers.okf import _parse_concept_file
    root = Path('resources/knowledge/hiv')
    if not root.exists():
        pytest.skip('Local corpus is not distributed')
    fields, body = _parse_concept_file(root/'predictions/edges/drugtreatsdisease-p1.md')
    metadata = document_provenance(fields, body)
    assert any(p['path_id'] == '8' and p['status'] == 'predicted' for p in metadata['paths'])
    fields, body = _parse_concept_file(root/'predictions/metapaths/shared-pharmacology/pmp015-shared-pharmacology-sud.md')
    metadata = document_provenance(fields, body)
    result = score_paths([{'id':'a', 'status':metadata['status'], 'provenance':metadata}], [use()])
    assert result['score'] is None


def test_row_and_explicit_edge_conflicts_with_uniform_document_are_unknown():
    text = '# Instances\n| # | path | evidence |\n|---|---|---|\n| 1 | A → B | predicted |'
    paths = source_paths({}, text, 'observed')
    assert paths[0]['status'] == 'unknown'
    assert paths[0]['diagnostic'] == 'path_document_evidence_conflict'
    fields = {'metapath_instances':[{'id':'1','edges':[{'evidence':'observed'}]}]}
    assert source_paths(fields, '', 'predicted')[0]['status'] == 'unknown'
