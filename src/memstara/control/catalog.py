"""Local, versioned skill catalog. No executable uploads and no caller-owned paths."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from memstara.paths import DEFAULT_OUTPUT_DIR, PACKAGE_ROOT
from memstara.agent_labels import agent_label
from memstara.pipeline import prompts

ROLES = ('hypothesis', 'data', 'ml', 'interpreter', 'report')

# Exact current filenames only: no recursive discovery and no archive fallback.
ANIL_SKILLS = {
    'shared-anil-shap': ('SHAP-Interpretation.md', 'interpreter', 'SHAP Interpretation'),
    'shared-anil-lime': ('LIME-Interpretation.md', 'interpreter', 'LIME Interpretation'),
    'shared-anil-addiction': ('Addiction-Expert-Explanation.md', 'report', 'Addiction Expert Explanation'),
    'shared-anil-hiv': ('HIV-Expert-Explanation.md', 'report', 'HIV Expert Explanation'),
}


def anil_dir() -> Path:
    configured = os.environ.get('MEMSTARA_SPECIALIST_SKILLS_DIR', '').strip()
    if configured:
        return Path(configured).expanduser()
    return PACKAGE_ROOT / 'resources/contributed/specialists'


def anil_skills() -> list[dict]:
    root = anil_dir().resolve()
    if 'old' in {part.casefold() for part in root.parts}:
        raise ValueError('Archived skill directories are not allowed')
    items = []
    for item_id, (filename, stage, title) in ANIL_SKILLS.items():
        path = root / filename
        if not path.is_file():
            continue
        if path.resolve().parent != root:
            raise ValueError(f'{filename}: shared skills must be current root files, not archive links')
        item = _external_entry(item_id, path, stage)
        if not item['content'].strip():
            raise ValueError(f'{filename}: shared skill has no instructions')
        item.update(title=title, source_file=filename,
                    source_hash=hashlib.sha256(path.read_bytes()).hexdigest())
        items.append(item)
    return items


# Optional external documents are configured by the deployment.
def shared_dir() -> Path | None:
    value = os.environ.get('MEMSTARA_SHARED_SKILLS_DIR', '').strip()
    return Path(value).expanduser() if value else None


def document_path(variable: str, filename: str) -> Path | None:
    value = os.environ.get(variable, '').strip()
    if value:
        return Path(value).expanduser()
    directory = shared_dir()
    if directory is not None:
        return directory / filename
    bundled = {'ml-reference.md': 'ML Knowledge (1).md', 'ml-results.md': 'ML Skill (1).md'}
    name = bundled.get(filename)
    return PACKAGE_ROOT / 'resources/contributed/machine-learning' / name if name else None


def canonical_name(name: str) -> str:
    """Resolve deployment-owned aliases without changing saved run records."""
    path = Path(os.environ.get('MEMSTARA_SKILL_ALIASES_PATH') or
                (Path(os.environ.get('MEMSTARA_OUTPUT_DIR') or DEFAULT_OUTPUT_DIR) / 'skill_aliases.json'))
    if not path.is_file():
        return name
    aliases = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(aliases, dict) or any(
        not isinstance(key, str) or not key.strip() or
        not isinstance(value, str) or not value.strip()
        for key, value in aliases.items()
    ):
        raise ValueError('Skill aliases must map nonempty names to nonempty strings')
    target = aliases.get(name, name)
    if not isinstance(target, str):
        raise ValueError('Skill aliases must map names to strings')
    return target


def user_dir() -> Path:
    return Path(os.environ.get('MEMSTARA_USER_SKILLS_DIR') or
                (Path(os.environ.get('MEMSTARA_OUTPUT_DIR') or DEFAULT_OUTPUT_DIR) / 'skills'))


def catalog(*, include_hidden: bool = False) -> list[dict]:
    items = anil_skills()
    path = document_path('MEMSTARA_RESULTS_SKILL_PATH', 'ml-results.md')
    if include_hidden and path is not None and path.is_file():
        items.append(_external_entry('shared-ml-results', path, 'report'))
    for path in sorted(prompts.PLAYBOOKS_DIR.glob('*.md')):
        if not include_hidden and path.stem in prompts.HIDDEN_PLAYBOOKS:
            continue
        content = prompts._body(path.read_text(encoding='utf-8'))
        stage = ('data' if path.stem.startswith('data_') else 'ml' if path.stem.startswith('ml_') else
                 'interpreter' if path.stem.startswith('interpreter_') else
                 'report' if path.stem.startswith('report_') else 'hypothesis')
        items.append(_entry(path.stem, content, stage, 'Project default'))
    for path in sorted(user_dir().glob('*.json')):
        try:
            item = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(item, dict) or item.get('stage') not in ROLES
                    or any(not isinstance(item.get(key), str)
                           for key in ('id', 'title', 'description', 'content', 'hash', 'source'))
                    or item['id'] != path.stem or not item['content'].strip()):
                raise ValueError('Invalid skill record')
        except (ValueError, UnicodeError):
            raise ValueError('Invalid saved user skill record; restore the original '
                             'record or register a new version') from None
        item['stage_label'] = agent_label(item['stage'])
        items.append(item)
    return items


def reference_knowledge() -> list[dict]:
    """Tool background, separate from selectable behavioral skills."""
    path = document_path('MEMSTARA_ML_REFERENCE_PATH', 'ml-reference.md')
    if path is None or not path.is_file():
        return []
    item = _external_entry('shared-ml-reference', path, 'ml')
    return [{**item, 'kind': 'reference', 'automatic': True}]


def _external_entry(item_id: str, path: Path, stage: str) -> dict:
    """Read a shared skill without changing its source file or Markdown body."""
    raw = path.read_text(encoding='utf-8')
    if raw.startswith('---\n') and '\n---\n' in raw[4:]:
        raw = raw[raw.find('\n---\n', 4) + len('\n---\n'):]
    content = prompts._body(raw)
    return _entry(item_id, content, stage, f'Shared document · original ({path.name})')


def _entry(name: str, content: str, stage: str, source: str) -> dict:
    lines = [line.strip().lstrip('#').strip() for line in content.splitlines() if line.strip()]
    return {'id': name, 'title': lines[0] if lines else name, 'stage': stage,
            'stage_label': agent_label(stage),
            'description': ' '.join(lines[1:4])[:400], 'content': content,
            'hash': hashlib.sha256(content.strip().encode()).hexdigest(), 'source': source}


def resolve(name: str) -> dict:
    name = canonical_name(name)
    item = next((x for x in catalog(include_hidden=True) if x['id'] == name), {})
    if not item and name in prompts.LEGACY_PLAYBOOKS:
        path = prompts.PLAYBOOKS_DIR / prompts.LEGACY_PLAYBOOKS[name]
        item = _entry(name, prompts._body(path.read_text(encoding='utf-8')),
                      'ml' if name.startswith('ml_') else 'data', 'Legacy compatibility only')
    if name in ANIL_SKILLS and not item:
        raise FileNotFoundError(
            f'{ANIL_SKILLS[name][0]} is missing from the current shared folder; no archive fallback')
    return item


def register(body: dict) -> dict:
    stage, name, content = body.get('stage'), body.get('name', ''), body.get('content', '')
    if stage not in ROLES:
        raise ValueError('Choose a Hypothesis, ML, Interpreter or Explanation agent skill')
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
    from memstara.pipeline.checkpoint import atomic_json
    destination = directory / f'{item["id"]}.json'
    try:
        atomic_json(destination, item, overwrite=False)
    except FileExistsError:
        # Concurrent identical submissions are idempotent; a conflicting version
        # must never replace the evidence already referenced by a saved pipeline.
        if json.loads(destination.read_text(encoding='utf-8')) != item:
            raise ValueError('This skill version already exists with different content; '
                             'use a different name and retain the existing record') from None
    return item


def ensure_explanation_enabled(names) -> None:
    for name in names:
        if canonical_name(name) in prompts.DISABLED_EXPLANATION_SKILLS:
            raise ValueError(f'{name}: this Explanation skill is disabled for execution. '
                             'Select General research explanation, or an explicitly compatible specialist.')


def ensure_hypothesis_enabled(names) -> None:
    for name in names:
        if canonical_name(name) in prompts.DISABLED_HYPOTHESIS_SKILLS:
            raise ValueError(f'{name}: this Hypothesis skill is disabled for execution. '
                             'Select General research hypothesis, Random features, '
                             'or an explicitly compatible specialty.')


def validate_selection(body: dict) -> None:
    from memstara.control.request import normalize_agent_configuration, playbook_field
    body = normalize_agent_configuration(body)
    selected = []
    interpreters = []
    if body.get('trials', 3) < body.get('hypothesis_agents', 1):
        raise ValueError('Give every hypothesis at least one trial')
    for stage in ROLES:
        names = body.get(playbook_field(stage), '').split(',')
        if stage == 'report':
            ensure_explanation_enabled(names)
        if stage == 'hypothesis':
            ensure_hypothesis_enabled(names)
        for name in names:
            if not name:
                continue
            item = resolve(name)
            if not item or item['stage'] != stage:
                raise ValueError(f'{name}: select a skill for the {agent_label(stage)} role')
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
