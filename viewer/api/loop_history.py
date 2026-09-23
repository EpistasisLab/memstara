"""Loop attribution from durable call IDs, with explicit legacy provenance."""
import re
from collections import deque

QUESTION = re.compile(r'^question(\d+)-\d+$')
ROUND = re.compile(r'^\s*(?:round|loop)\s+(\d+)\s*/', re.I)


def call_loops(calls):
    # Legacy workers have names like ml#1 in every loop. Only recorded question
    # boundaries can disambiguate them; never use the agent name or latest task.
    boundaries = {}
    for call in calls:
        match = QUESTION.match(call.get('stage', ''))
        if match and isinstance(call.get('started_at'), (int, float)):
            number = int(match[1]) + 1
            boundaries[number] = min(boundaries.get(number, float('inf')), call['started_at'])
    ordered = sorted((start, number) for number, start in boundaries.items())
    assigned = []
    for call in calls:
        if 'loop' in call:
            number = call['loop']
            number = number if type(number) is int and number > 0 else None
            source = 'recorded'
        else:
            timestamp = call.get('started_at')
            candidates = [(at, n) for at, n in ordered if isinstance(timestamp, (int, float)) and at <= timestamp]
            number = candidates[-1][1] if candidates else None
            source = 'recorded_boundary' if number else 'unassigned'
        assigned.append({**call, 'loop': number, 'loop_source': source})
    return assigned


def record_loop(record, config):
    size = config.get('trials')
    index = record.get('trial')
    if type(size) is int and size > 0 and type(index) is int and index >= 0:
        return index // size + 1
    return None


def read_log(directory, loop):
    """Read only the requested round's console region; never fabricate attribution."""
    if directory is None:
        return {'lines': [], 'note': 'No archived console log is available.', 'truncated': False}
    lines = deque(maxlen=2000)
    matched = loop is None
    current = None
    total = 0
    truncated = False
    try:
        with (directory / 'console.log').open('rb') as handle:
            for raw in handle:
                total += len(raw)
                if total > 16 * 1024 * 1024:
                    truncated = True
                    break
                text = raw.decode('utf-8', errors='replace').rstrip('\r\n')
                marker = ROUND.match(text)
                if marker:
                    current = int(marker[1])
                    if loop is not None and matched and current != loop:
                        break
                # Final execution-wide synthesis is not part of the last loop.
                if loop is not None and '(6)' in text and 'wrap up at the end' in text:
                    break
                if loop is None or current == loop:
                    matched = True
                    truncated = truncated or len(lines) == lines.maxlen
                    lines.append(text)
    except OSError:
        return {'lines': [], 'note': 'The archived console log could not be read.', 'truncated': False}
    note = '' if matched else 'This archive has no reliable log boundary for the selected loop.'
    if truncated:
        note = 'Log display is limited to 2,000 lines and a 16 MB scan; some content is not shown.'
    return {'lines': list(lines), 'note': note, 'truncated': truncated}
