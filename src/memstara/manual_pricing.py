"""User-entered estimate rates, separate from Azure billing evidence."""
import hashlib
import json
import math
import os
from datetime import UTC, datetime
from urllib.parse import urlsplit
from typing import Any

from memstara.paths import output_dir


def path():
    return output_dir() / 'pricing' / 'manual-rates.json'


def identities():
    from memstara.stage_models import deployment_profiles
    result: dict[str, dict[str, Any]] = {}
    for role, profile in deployment_profiles().items():
        identity = {key: profile.get(key) for key in ('provider', 'model', 'api_base')}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        result.setdefault(key, {**identity, 'roles': []})['roles'].append(role)
    return result


def external():
    return bool(os.environ.get('MEMSTARA_PRICING_JSON', '').strip()
                or os.environ.get('MEMSTARA_PRICING_PATH', '').strip())


def load():
    if not path().exists():
        return {'profiles': []}
    value = json.loads(path().read_text())
    if (not isinstance(value, dict) or not isinstance(value.get('profiles'), list)
            or any(not isinstance(p, dict) for p in value['profiles'])):
        raise ValueError('Saved manual rates are invalid')
    return value


def view():
    catalog = load()
    items = []
    for key, identity in identities().items():
        matches = [p for p in catalog['profiles'] if all(p.get(k) == identity.get(k)
                    for k in ('provider', 'model', 'api_base'))]
        rate = matches[0] if len(matches) == 1 else {}
        items.append({'id': key, 'provider': identity['provider'], 'model': identity['model'],
                      'roles': identity['roles'], 'enabled': bool(rate),
                      'rates': rate.get('usd_per_million_tokens', {}),
                      'source': rate.get('source', ''), 'valid_until': rate.get('valid_until', ''),
                      'retrieved_at': rate.get('retrieved_at', '')})
    return {'models': items, 'read_only': external(), 'basis': 'manual_estimate',
            'note': 'Manual token rates estimate usage only. They are not Azure actual charges.'}


def save(body):
    if external():
        raise ValueError('Legacy pricing override is active in .env; remove it and restart before using this editor')
    available = identities()
    if not isinstance(body, dict) or set(body) != {'models'} or not isinstance(body['models'], list):
        raise ValueError('Supply model rate entries')
    entries = body['models']
    if len(entries) != len(available) or {e.get('id') for e in entries if isinstance(e, dict)} != set(available):
        raise ValueError('Model configuration changed; reload the editor')
    now = datetime.now(UTC)
    catalog = load()
    # Preserve rates for other deployments; edits only affect currently configured models.
    profiles = [p for p in catalog['profiles'] if not any(all(p.get(k) == i.get(k)
                for k in ('provider', 'model', 'api_base')) for i in available.values())]
    for entry in entries:
        if type(entry.get('enabled')) is not bool:
            raise ValueError('Enable or disable each manual rate explicitly')
        if not entry['enabled']:
            continue
        rates = entry.get('rates')
        if not isinstance(rates, dict) or set(rates) - {'input', 'output', 'cache_read'}:
            raise ValueError('Use input, output and optional cache-read token rates')
        for kind in ('input', 'output', 'cache_read'):
            rate = rates.get(kind)
            if kind == 'cache_read' and rate is None:
                continue
            if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate < 0:
                raise ValueError('Rates must be finite non-negative USD amounts per million tokens')
        source = entry.get('source', '')
        if (not isinstance(source, str) or len(source) > 2000
                or urlsplit(source).scheme != 'https' or not urlsplit(source).hostname):
            raise ValueError('Provide the HTTPS source of the rates you verified')
        until = datetime.fromisoformat(entry.get('valid_until', ''))
        if until.tzinfo is None or until <= now:
            raise ValueError('Choose a future expiry date with a timezone')
        identity = available[entry['id']]
        profiles.append({**{k: identity[k] for k in ('provider', 'model', 'api_base')},
                         'billing': 'tokens', 'currency': 'USD', 'source': source,
                         'retrieved_at': now.isoformat(), 'valid_from': now.isoformat(),
                         'valid_until': until.isoformat(),
                         'usd_per_million_tokens': {k: v for k, v in rates.items() if v is not None}})
    from memstara.pipeline.checkpoint import atomic_json
    path().parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path(), {'profiles': profiles})
    return view()
