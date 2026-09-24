#!/usr/bin/env python3
"""Check repository-local Markdown links against tracked files, not local-only data.

Run from any directory. Fenced examples and HTML comments are not link targets.
This checks file availability, not the truth of prose or external-site availability.
"""
from __future__ import annotations

import posixpath
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    tracked = set(subprocess.check_output(
        ['git', '-C', str(ROOT), 'ls-files', '-z'], text=True,
    ).strip('\0').split('\0'))
    errors = []
    count = 0
    for name in sorted(tracked):
        if not name.endswith('.md'):
            continue
        path = ROOT / name
        if not path.is_file():
            errors.append(f'{name}: tracked file missing')
            continue
        count += 1
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
        fence = None
        for line_number, line in enumerate(text.splitlines(), 1):
            marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
            if marker:
                token = marker.group(1)
                if fence is None:
                    fence = token
                elif token[0] == fence[0] and len(token) >= len(fence):
                    fence = None
                continue
            if fence:
                continue
            targets = re.findall(r'!?\[[^\]]*\]\(<?([^\s)>]+)>?(?:\s+"[^"]*")?\)', line)
            definition = re.match(r'^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?', line)
            if definition:
                targets.append(definition.group(1))
            for target in targets:
                parts = urlsplit(target)
                if parts.scheme or parts.netloc or not parts.path:
                    continue
                resolved = posixpath.normpath(posixpath.join(
                    posixpath.dirname(name), unquote(parts.path),
                ))
                if resolved in tracked or any(p.startswith(resolved.rstrip('/') + '/') for p in tracked):
                    continue
                errors.append(f'{name}:{line_number}: target is not tracked: {target}')
        if fence:
            errors.append(f'{name}: unclosed code fence')
    for error in errors:
        print(error)
    print(f'{count} Markdown files checked; {len(errors)} errors.')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
