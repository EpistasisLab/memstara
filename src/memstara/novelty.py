"""Versioned, source-relative predicted-path proxy; not literature novelty."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

POLICY = 'predicted_path_fraction_v1'


def source_paths(fields: dict[str, Any], body: str, document_status: str) -> list[dict[str, Any]]:
    """Adapt explicit path records and known numbered tables without editing sources.

    User corpora may supply metapath_instances: [{id, edges: [{evidence}]}].
    Existing numbered Instances tables inherit only unambiguous all-observed or
    all-predicted declarations, never a document-wide mixed declaration. Predicted
    Edges tables are one-hop paths; their consensus is not a novelty score.
    """
    paths: list[dict[str, Any]] = []
    structured = fields.get('metapath_instances')
    if isinstance(structured, list):
        for row in structured[:200]:
            if not isinstance(row, dict) or not isinstance(row.get('id'), (str, int)):
                continue
            edges = row.get('edges')
            values = ([e.get('evidence') if isinstance(e, dict) else None for e in edges]
                      if isinstance(edges, list) else [])
            status = 'unknown'
            if values and all(v in ('observed', 'predicted') for v in values):
                status = 'mixed' if len(set(values)) > 1 else str(values[0])
            canonical = json.dumps(row, sort_keys=True, default=str)
            paths.append({'path_id': str(row['id']), 'status': status,
                          'annotation_scope': 'explicit_edges', 'edge_count': len(values),
                          'predicted_edges': values.count('predicted'),
                          'row_sha256': hashlib.sha256(canonical.encode()).hexdigest(),
                          'source_location': 'frontmatter.metapath_instances',
                          'label': str(row.get('label', row['id']))[:300]})
    # Markdown adapters are deliberately narrow and domain-independent.
    active = False
    fenced = False
    header: list[str] | None = None
    ready = False
    for number, line in enumerate(body.splitlines(), 1):
        if re.match(r'^\s*(```|~~~)', line):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = re.match(r'^#{1,6}\s+(.+)', line)
        if heading:
            title = heading.group(1).casefold().strip()
            active = title == 'instances' or (title.startswith('predicted edges')
                                               and fields.get('type') == 'Predicted Edges')
            header, ready = None, False
            continue
        if not active or not line.strip().startswith('|'):
            if active:
                header, ready = None, False
            continue
        cells = [v.strip() for v in re.split(r'(?<!\\)\|', line.strip().strip('|'))]
        if header is None:
            if cells[0].casefold() in ('#', 'id', 'overall rank'):
                header = cells
            continue
        if not ready:
            ready = len(cells) == len(header) and all(re.fullmatch(r':?-{3,}:?', v) for v in cells)
            if not ready:
                header = None
            continue
        if len(cells) != len(header) or not cells[0].isdigit():
            continue
        status = document_status if document_status in ('observed', 'predicted') else 'unknown'
        explicit = next((cells[i].casefold() for i, h in enumerate(header) if h.casefold() == 'evidence'), None)
        if explicit in ('observed', 'predicted', 'mixed'):
            status = explicit
        paths.append({'path_id': cells[0], 'status': status,
                      'annotation_scope': 'row' if explicit else 'document_uniform',
                      'row_sha256': hashlib.sha256(line.strip().encode()).hexdigest(),
                      'source_location': f'body:{number}', 'label': ' → '.join(cells[1:4])[:300]})
    for path in paths:
        if document_status in ('observed', 'predicted') and path['status'] not in ('unknown', document_status):
            path['status'] = 'unknown'
            path['diagnostic'] = 'path_document_evidence_conflict'
    ids = [p['path_id'] for p in paths]
    for path in paths:
        if ids.count(path['path_id']) > 1:
            path['status'] = 'unknown'
            path['diagnostic'] = 'duplicate_path_id'
    return paths[:200]


def score_paths(sources: list[dict[str, Any]], claims: Any) -> dict[str, Any]:
    """Validate declared use against immutable run reads, then compute the proxy.

    Rank only full coverage. Missing claims for any cited metapath document,
    invalid IDs, unread sources, conflicts and unknown paths prevent ranking.
    Literature is not assigned an observed zero. LLMs cannot submit a score.
    """
    result: dict[str, Any] = {'policy': POLICY, 'status': 'unavailable', 'score': None,
        'coverage': 0.0, 'rankable': False, 'paths': [], 'diagnostics': [],
        'counts': dict.fromkeys(('observed', 'predicted', 'mixed', 'unknown'), 0),
        'attribution': 'agent_declared_use_validated_against_recorded_source',
        'scientific_validation': 'not_validated',
        'formula': '(predicted + mixed) / (observed + predicted + mixed)',
        'scope': 'Recorded KG paths only; not novelty across the literature.'}
    if not isinstance(claims, list) or not claims:
        result['diagnostics'].append('no_path_use_declared')
        return result
    if len(claims) > 100:
        result['diagnostics'].append('path_claim_limit_exceeded')
    covered: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for claim in claims[:100]:
        item: dict[str, Any] = {'status': 'unknown'}
        if not isinstance(claim, dict):
            item['diagnostic'] = 'invalid_path_claim'
        else:
            ref, pid, reason = claim.get('source_id'), claim.get('path_id'), claim.get('rationale')
            item.update(source_id=ref if isinstance(ref, str) else '', path_id=pid if isinstance(pid, str) else '',
                        rationale=reason[:2000] if isinstance(reason, str) else '')
            hits = [s for s in sources if ref and ref in (s.get('id'), s.get('declared_ref'))]
            if len(hits) != 1:
                item['diagnostic'] = 'source_not_uniquely_cited_and_read'
            else:
                source = hits[0]
                canonical = source.get('id', '')
                key = (canonical, str(pid))
                if key in seen:
                    continue
                seen.add(key)
                covered.add(canonical)
                metadata = source.get('provenance', {})
                paths = [p for p in metadata.get('paths', []) if p.get('path_id') == pid]
                if not isinstance(reason, str) or not reason.strip():
                    item['diagnostic'] = 'missing_use_rationale'
                elif metadata.get('diagnostics') or not metadata.get('parsed_source_sha256'):
                    item['diagnostic'] = 'conflicting_or_unverified_source'
                elif len(paths) != 1:
                    item['diagnostic'] = 'path_not_in_recorded_source'
                else:
                    item.update(paths[0], source_id=canonical,
                                parsed_source_sha256=metadata['parsed_source_sha256'])
        status = item.get('status')
        if status not in result['counts']:
            item['status'] = 'unknown'
        result['paths'].append(item)
        result['counts'][item['status']] += 1
    for source in sources:
        metadata = source.get('provenance', {})
        if source.get('id') not in covered and source.get('status') != 'not_applicable':
            result['diagnostics'].append('cited_source_without_path_attribution')
    counts = result['counts']
    known = counts['observed'] + counts['predicted'] + counts['mixed']
    total = known + counts['unknown']
    result['coverage'] = known / total if total else 0.0
    result['known_path_fraction'] = (counts['predicted'] + counts['mixed']) / known if known else None
    if known and known == total and not result['diagnostics']:
        result.update(score=result['known_path_fraction'], rankable=True, status='scored')
    elif total:
        result['status'] = 'partial'
    result['diagnostics'] = sorted(set(result['diagnostics']))
    return result
