"""Read-only source scopes from frozen run metadata, never question wording or tags."""
import asyncio
import hashlib
import json
import re

from fastapi import HTTPException
from db import pools
import run_artifacts


def source_identity(config):
    config = config if isinstance(config, dict) else {}
    profile = config.get('research_profile') or {}
    profile = profile if isinstance(profile, dict) else {}
    settings = profile.get('configuration') or {}
    settings = settings if isinstance(settings, dict) else {}
    policy = config.get('knowledge_policy')
    policy = policy if isinstance(policy, dict) else {}
    mode = config.get('knowledge_mode') or settings.get('knowledge_mode')
    if mode == 'llm_only' or policy.get('mode') == 'no_okf':
        return 'none', 'No knowledge source'
    hashes = config.get('knowledge_hashes') or {}
    hashes = hashes if isinstance(hashes, dict) else {}
    if not hashes:
        artifacts = profile.get('artifact_hashes')
        artifacts = artifacts if isinstance(artifacts, dict) else {}
        hashes = {k[4:]: v for k, v in artifacts.items() if isinstance(k, str) and k.startswith('okf/')}
    documents = {k: v for k, v in hashes.items() if isinstance(k, str) and k.lower().endswith('.md') and isinstance(v, str)}
    if not documents:
        return 'unknown', 'Source unknown'
    digest = hashlib.sha256(json.dumps(documents, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    name = settings.get('knowledge_name') or settings.get('name')
    return 'okf_' + digest, str(name)[:160] if name else ''


async def catalog():
    configs = await asyncio.to_thread(run_artifacts.configs)
    async def read(conn):
        return await conn.fetch("SELECT coalesce(origin_run, '') AS run_tag, count(*) AS count "
                                "FROM memstara_questions WHERE status <> 'cleared' GROUP BY coalesce(origin_run, '')")
    rows = await pools.guarded('memstara', read, None)
    if rows is None:
        raise HTTPException(503, 'Knowledge source records are temporarily unavailable.')
    identities = {tag: source_identity(config) for tag, config in configs.items()}
    names = {}
    for key, label in identities.values():
        if label:
            names.setdefault(key, set()).add(label)
    groups = {}
    for row in rows:
        key, _ = identities.get(row['run_tag'], ('unknown', 'Source unknown'))
        group = groups.setdefault(key, {'id': key, 'count': 0, 'runs': []})
        group['count'] += row['count']
        group['runs'].append(row['run_tag'])
    for key, group in groups.items():
        group['label'] = sorted(names.get(key, []))[0] if names.get(key) else (
            'Source unknown' if key == 'unknown' else 'No knowledge source' if key == 'none' else 'Recorded OKF')
        # Distinguish revisions and independently registered sources with the same label.
        if key.startswith('okf_'):
            group['label'] += ' · ' + key[4:12]
    for tag, (key, _) in identities.items():
        if key in groups and tag not in groups[key]['runs']:
            groups[key]['runs'].append(tag)
    return groups


async def sources():
    groups = await catalog()
    return {'sources': [{'id': 'all', 'label': 'All sources', 'count': sum(g['count'] for g in groups.values())},
                        *[{k: g[k] for k in ('id', 'label', 'count')} for g in sorted(groups.values(), key=lambda g: g['label'])]]}


async def scope(source):
    if source == 'all':
        return None
    if source not in ('none', 'unknown') and not re.fullmatch(r'okf_[a-f0-9]{64}', source):
        raise HTTPException(422, 'Invalid knowledge source.')
    return (await catalog()).get(source, {}).get('runs', [])
