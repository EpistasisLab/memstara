"""Source declarations are never promoted into verified scientific novelty."""
import json

import pytest

from memstara.knowledge_provenance import document_provenance


@pytest.mark.parametrize('fields,body,status,diagnostic', [
    ({'evidence': 'observed'}, '', 'observed', None),
    ({'evidence': 'predicted'}, '', 'predicted', None),
    ({'evidence': 'mixed', 'predicted_hop_count': 1}, '', 'mixed', None),
    ({'evidence': 'mixed'}, '# Evidence — OBSERVED\n', 'unknown', 'conflicting_evidence_declarations'),
    ({'evidence': 'observed', 'predicted_hop_count': 1}, '', 'unknown', 'predicted_hop_count_conflicts_with_evidence'),
    ({'evidence': 'predicted', 'predicted_hop_count': 0}, '', 'unknown', 'predicted_hop_count_conflicts_with_evidence'),
    ({'evidence': 'mixed', 'predicted_hop_count': True}, '', 'unknown', 'invalid_predicted_hop_count'),
    ({'evidence': {'unexpected': 'value'}}, '', 'unknown', 'unsupported_evidence_annotation'),
    ({'type': 'Literature Evidence'}, 'predicted mortality', 'not_applicable', None),
    ({}, 'A link-predicted path might exist.', 'unknown', None),
    ({'type': 'New user format'}, '', 'unknown', None),
    ({'type': ['malformed']}, '', 'unknown', None),
])
def test_conservative_annotations(fields, body, status, diagnostic):
    result = document_provenance(fields, body)
    assert result['status'] == status
    assert result['novelty_score'] is None
    assert result['hypothesis_attribution'] == 'not_assessed'
    if diagnostic:
        assert diagnostic in result['diagnostics']
    else:
        assert result['diagnostics'] == []


def test_hash_changes_with_content_not_mapping_order():
    first = document_provenance({'evidence': 'mixed', 'type': 'Metapath Schema'}, 'text')
    same = document_provenance({'type': 'Metapath Schema', 'evidence': 'mixed'}, 'text')
    changed = document_provenance({'evidence': 'mixed', 'type': 'Metapath Schema'}, 'changed')
    assert first['parsed_source_sha256'] == same['parsed_source_sha256']
    assert first['parsed_source_sha256'] != changed['parsed_source_sha256']


def test_reader_audits_conflict_even_when_only_instances_are_returned(tmp_path, monkeypatch):
    from memstara.mcp_servers import okf
    root = tmp_path / 'corpus'
    root.mkdir()
    (root / 'path.md').write_text('---\ntitle: Synthetic path\ntype: Metapath Schema\nevidence: mixed\n'
                                 'predicted_hop_count: 1\n---\n# Evidence — OBSERVED\n'
                                 'No predicted edge is used.\n# Instances\nSynthetic example.')
    monkeypatch.setattr(okf, '_bundle_root', lambda: root)
    monkeypatch.delenv('MEMSTARA_OKF_FIELDS', raising=False)
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(tmp_path / 'config.json'))
    row = json.loads(okf.okf_read('path', section='auto', max_chars=5))['documents'][0]
    assert row['truncated']
    assert row['knowledge_provenance']['status'] == 'unknown'
    assert 'conflicting_evidence_declarations' in row['knowledge_provenance']['diagnostics']
    audit = json.loads((tmp_path / 'knowledge_reads.jsonl').read_text())
    assert audit['results'][0]['knowledge_provenance'] == row['knowledge_provenance']
    assert 'Synthetic example' not in json.dumps(audit)
    assert audit['results'][0]['status'] == 'read'


def test_unusual_user_metadata_does_not_break_read():
    result = document_provenance({'custom': {1: 'a', 'two': 'b'}}, 'text')
    assert result['status'] == 'unknown'
    assert result['parsed_source_sha256'] is None
    assert 'source_fingerprint_unavailable' in result['diagnostics']


def audit_file(tmp_path, rows):
    (tmp_path / 'knowledge_reads.jsonl').write_text(json.dumps({'results': rows}) + '\n')
    return str(tmp_path / 'config.json')


def resolve(refs, config):
    from memstara.knowledge_provenance import hypothesis_provenance
    return hypothesis_provenance(refs, config, run_tag='isolated-run', trial=2, question_id=8)


def test_only_declared_read_sources_count_and_aliases_deduplicate(tmp_path):
    evidence = document_provenance({'evidence': 'mixed'}, 'text')
    config = audit_file(tmp_path, [
        {'status': 'read', 'id': 'a/path', 'ref': 'path', 'knowledge_provenance': evidence},
        {'status': 'read', 'id': 'b/unused', 'knowledge_provenance': evidence},
    ])
    result = resolve(['path', 'a/path', 'missing'], config)
    assert result['counts']['mixed'] == 1
    assert result['counts']['unknown'] == 1
    assert result['unique_source_count'] == 2
    assert result['novelty_score'] is None
    assert result['path_instance_attribution'] == 'not_assessed'
    assert result['trial'] == 2 and result['question_id'] == 8


def test_changed_or_ambiguous_sources_do_not_get_predicted_credit(tmp_path):
    rows = [{'status': 'read', 'id': 'path', 'ref': 'alias',
             'knowledge_provenance': document_provenance({'evidence': 'predicted'}, text)}
            for text in ['first', 'changed']]
    config = audit_file(tmp_path, rows)
    assert resolve(['path'], config)['counts']['unknown'] == 1
    rows.append({'status': 'read', 'id': 'other', 'ref': 'alias'})
    config = audit_file(tmp_path, rows)
    assert resolve(['alias'], config)['sources'][0]['diagnostic'] == 'ambiguous_reference'


def test_missing_malformed_legacy_and_failed_audits_are_nonfatal(tmp_path):
    assert resolve(['path'], '')['status'] == 'partial_or_unknown'
    config = audit_file(tmp_path, [{'status': 'failed', 'id': 'path'},
                                   {'status': 'read', 'id': 'legacy'}])
    with (tmp_path / 'knowledge_reads.jsonl').open('a') as stream:
        stream.write('{broken\n')
    result = resolve(['path', 'legacy'], config)
    assert result['counts']['unknown'] == 2
    assert 'malformed_read_event' in result['diagnostics']
    assert resolve([], config)['status'] == 'no_declared_sources'
    other = tmp_path / 'other'
    other.mkdir()
    assert resolve(['legacy'], str(other / 'config.json'))['diagnostics'] == ['read_audit_unavailable']


def test_path_inventory_is_not_hypothesis_or_edge_attribution():
    body = '# Instances\n\n| # | origin | terminus |\n|---|---|---|\n| 1 | A | B |\n'
    result = document_provenance({'evidence': 'predicted'}, body)
    inventory = result['path_inventory']
    assert inventory['status'] == 'recorded'
    assert inventory['row_count'] == 1
    assert inventory['rows'][0]['evidence_status'] == 'unknown'
    assert inventory['hypothesis_use'] == 'not_assessed'
    assert inventory['edge_provenance'] == 'not_assessed'
    assert inventory == document_provenance({}, body)['path_inventory']
    assert inventory['rows'][0]['row_sha256'] != document_provenance(
        {}, body.replace('| A | B |', '| A | C |'))['path_inventory']['rows'][0]['row_sha256']


def test_path_inventory_unknown_formats_fences_duplicates_and_bounds():
    from memstara.path_inventory import path_inventory
    table = '# Instances\n| # | path |\n|---|---|\n| 1 | A → B |\n'
    assert path_inventory('```markdown\n' + table + '```')['row_count'] == 0
    assert path_inventory('# Literature evidence\n' + table.split('\n', 1)[1])['row_count'] == 0
    assert path_inventory('A free-form user corpus')['status'] == 'unavailable'
    repeated = path_inventory(table + '| 1 | C → D |\n| 2 | invalid | extra |')
    assert repeated['status'] == 'partial'
    assert set(repeated['diagnostics']) == {'duplicate_instance_identifier', 'malformed_instance_row'}
    bounded = path_inventory(table + ''.join(f'| {i} | A → C |\n' for i in range(2, 40)))
    assert bounded['row_count'] == 39 and len(bounded['rows']) == 25 and bounded['truncated']


def test_path_inventory_survives_citation_persistence(tmp_path):
    body = '# Instances\n| # | path |\n|---|---|\n| 1 | A → B |\n'
    metadata = document_provenance({'evidence': 'mixed'}, body)
    config = audit_file(tmp_path, [{'status': 'read', 'id': 'path', 'knowledge_provenance': metadata}])
    result = resolve(['path'], config)
    assert result['sources'][0]['provenance']['path_inventory']['row_count'] == 1
    assert result['path_instance_attribution'] == 'not_assessed'
