#!/usr/bin/env python3
"""Reject ignored files and machine-specific home paths in the published tree."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME_PATH = re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/')
LOCAL_CONFIG = re.compile(r'^config/[^/]+\.local[^/]*\.json$', re.IGNORECASE)
SECRET_PATTERNS = {
    'private key header': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,})\b'),
    'AWS access key identifier': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
}


def protected_path(name: str) -> bool:
    """Never depend on .gitignore alone to protect force-added local records."""
    path = Path(name)
    base = path.name.lower()
    if base.startswith('.env') and base != '.env.example':
        return True
    if path.suffix.lower() in {'.pem', '.key'}:
        return True
    if base in {'backlog.md', 'backlog_kr.md', 'claude.md', 'claude_kr.md',
                'checklist.md', 'checklist_kr.md'}:
        return True
    return bool({part.lower() for part in path.parts} & {'daily_log', 'anil_shared', 'phil_shared'})


def main() -> int:
    names = [name for name in subprocess.check_output(
        ['git', 'ls-files', '-z'], cwd=ROOT, text=True,
    ).split('\0') if name]
    if not names:
        print('No tracked files found; publication contents cannot be verified.')
        return 1
    ignored = subprocess.run(
        ['git', 'check-ignore', '--no-index', '--stdin', '-z'],
        cwd=ROOT, input='\0'.join(names) + '\0', text=True, capture_output=True,
    )
    if ignored.returncode not in (0, 1):
        raise RuntimeError(ignored.stderr)
    errors = [f'{name}: ignored file is tracked' for name in ignored.stdout.split('\0') if name]
    for name in names:
        if protected_path(name):
            errors.append(f'{name}: protected local material must not be published')
            # Credential files must not be opened merely to report their path.
            continue
        if LOCAL_CONFIG.fullmatch(name):
            errors.append(f'{name}: deployment-local configuration must not be published')
        path = ROOT / name
        if not path.is_file():
            errors.append(f'{name}: tracked file missing')
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if HOME_PATH.search(line):
                errors.append(f'{name}:{number}: machine-specific home path')
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    errors.append(f'{name}:{number}: possible {label}; value redacted')
    for error in errors:
        print(error)
    print(f'{len(names)} tracked files checked; {len(errors)} publication errors.')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
