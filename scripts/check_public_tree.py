#!/usr/bin/env python3
"""Reject ignored files and machine-specific home paths in the published tree."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME_PATH = re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/')
LOCAL_CONFIG = re.compile(r'^config/[^/]+\.local[^/]*\.json$', re.IGNORECASE)


def main() -> int:
    names = subprocess.check_output(
        ['git', 'ls-files', '-z'], cwd=ROOT, text=True,
    ).strip('\0').split('\0')
    ignored = subprocess.run(
        ['git', 'check-ignore', '--no-index', '--stdin', '-z'],
        cwd=ROOT, input='\0'.join(names) + '\0', text=True, capture_output=True,
    )
    if ignored.returncode not in (0, 1):
        raise RuntimeError(ignored.stderr)
    errors = [f'{name}: ignored file is tracked' for name in ignored.stdout.split('\0') if name]
    for name in names:
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
    for error in errors:
        print(error)
    print(f'{len(names)} tracked files checked; {len(errors)} publication errors.')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
