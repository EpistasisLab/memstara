"""Local, versioned skill catalog. No executable uploads and no caller-owned paths."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from memstara.paths import DEFAULT_OUTPUT_DIR
from memstara.pipeline import prompts

ROLES = ('hypothesis', 'ml', 'interpreter', 'report')

# reviewer's shared skills are kept outside this checkout. They remain the source of truth;
# the catalog exposes them without copying or rewriting their Markdown.
SHARED_ROOT_SKILLS_DIR = Path(__file__).resolve().parents[4] / 'shared' / 'skills'
shared_SKILLS = {
    'shared-ml-results': 'ml-results.md',
    'shared-ml-reference': 'ml-reference.md',
}


def user_dir() -> Path:
    return Path(os.environ.get('MEMSTARA_OUTPUT_DIR') or DEFAULT_OUTPUT_DIR) / 'skills'


def catalog() -> list[dict]:
    items = []
    for item_id, filename in shared_SKILLS.items():
        path = SHARED_ROOT_SKILLS_DIR / filename
        if path.is_file():
            items.append(_external_entry(item_id, path))
    for path in sorted(prompts.PLAYBOOKS_DIR.glob('*.md')):
        content = prompts._body(path.read_text(encoding='utf-8'))
        stage = ('ml' if path.stem.startswith('ml_') else
                 'interpreter' if path.stem.startswith('interpreter_') else
                 'report' if path.stem.startswith('report_') else 'hypothesis')
        items.append(_entry(path.stem, content, stage, 'Project default'))
    for path in sorted(user_dir().glob('*.json')):
        item = json.loads(path.read_text(encoding='utf-8'))
        items.append(item)
    return items


def _external_entry(item_id: str, path: Path) -> dict:
    """Read a shared skill without changing its source file or Markdown body."""
    raw = path.read_text(encoding='utf-8')
    if raw.startswith('---\n') and '\n---\n' in raw[4:]:
        raw = raw[raw.find('\n---\n', 4) + len('\n---\n'):]
    content = prompts._body(raw)
    return _entry(item_id, content, 'ml', f'Shared document · original ({path.name})')


def _entry(name: str, content: str, stage: str, source: str) -> dict:
    lines = [line.strip().lstrip('#').strip() for line in content.splitlines() if line.strip()]
    return {'id': name, 'title': lines[0] if lines else name, 'stage': stage,
            'description': ' '.join(lines[1:4])[:400], 'content': content,
            'hash': hashlib.sha256(content.strip().encode()).hexdigest(), 'source': source}


def resolve(name: str) -> dict:
    return next((x for x in catalog() if x['id'] == name), {})


def register(body: dict) -> dict:
    stage, name, content = body.get('stage'), body.get('name', ''), body.get('content', '')
    if stage not in ROLES:
        raise ValueError('Choose hypothesis, ml, interpreter or report')
    if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}', name):
        raise ValueError('Use a name of 1–60 letters, numbers, hyphens or underscores')
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > 48_000:
        raise ValueError('A skill must contain 1–48000 bytes of Markdown')
    match = re.search(r'<!--\s*evaluation:\s*(\{.*?\})\s*-->', content, re.S)
    evaluation = json.loads(match.group(1)) if match else None
    if evaluation is not None:
        from memstara.evaluation import validate
        if stage != 'ml' or not isinstance(evaluation, dict):
            raise ValueError('Evaluation settings belong to an ML skill and must be a JSON object')
        validate(evaluation)
    content = prompts._body(content)
    if not content.strip():
        raise ValueError('The skill has no instructions after comments are removed')
    item = _entry(name, content, stage, 'User supplied')
    if evaluation is not None:
        item['evaluation'] = evaluation
        item['hash'] = hashlib.sha256((content.strip() + json.dumps(evaluation, sort_keys=True)).encode()).hexdigest()
    item['id'] = f'user-{stage}-{name}-{item["hash"][:12]}'
    directory = user_dir()
    directory.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', dir=directory, suffix='.tmp', delete=False) as stream:
        json.dump(item, stream, indent=2)
        temporary = Path(stream.name)
    temporary.replace(directory / f'{item["id"]}.json')
    return item


def validate_selection(body: dict) -> None:
    selected = []
    interpreters = []
    if body.get('trials', 3) < body.get('hypothesis_agents', 1):
        raise ValueError('Give every hypothesis at least one trial')
    if body.get('playbook_data'):
        raise ValueError('Data skill editing is not part of the V1 user configuration')
    for stage in ROLES:
        names = body.get(f'playbook_{stage}', '').split(',')
        for name in names:
            if not name:
                continue
            item = resolve(name)
            if not item or item['stage'] != stage:
                raise ValueError(f'{name}: select a skill for the {stage} role')
            if stage == 'hypothesis':
                if item['hash'] in selected:
                    raise ValueError('Each hypothesis must have a different skill (including its contents)')
                selected.append(item['hash'])
            if stage == 'interpreter':
                if item['hash'] in interpreters:
                    raise ValueError('Each interpreter must have a different skill')
                interpreters.append(item['hash'])
    if body.get('hypothesis_agents', 1) > 1 and len(selected) != body['hypothesis_agents']:
        raise ValueError('Select a distinct skill for every hypothesis before starting')
    if body.get('interpret_agents', 1) > 1 and len(interpreters) != body['interpret_agents']:
        raise ValueError('Select a distinct skill for every interpreter before starting')
