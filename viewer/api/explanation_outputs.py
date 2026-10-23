"""Read saved Explanation narratives, never substitute a deterministic final report."""
import hashlib
import json
import re
from pathlib import Path


def read(path, root):
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def saved_outputs(directory, tag):
    outputs = []
    root = directory / 'report_io'
    for path in root.glob('loop-*-result-*-output.json'):
        match = re.fullmatch(r'loop-(\d+)-result-(\d+)-output.json', path.name)
        if not match:
            continue
        loop, result_id = map(int, match.groups())
        record = read(path, directory)
        source = read(path.with_name(path.name.replace('-output.json', '-input.json')), directory)
        if not isinstance(record, dict) or not isinstance(source, dict):
            continue
        if (source.get('run_tag') != tag or source.get('loop') != loop
                or source.get('result_id') != result_id
                or not source.get('sha256') or record.get('input_sha256') != source['sha256']):
            continue
        text = record.get('output')
        if isinstance(text, str) and text.strip():
            outputs.append({'loop': loop, 'result_id': result_id, 'text': text,
                            'status': (record.get('execution') or {}).get('status', 'unknown')})
    root = directory / 'explanation_io'
    for path in root.glob('loop-*.json'):
        match = re.fullmatch(r'loop-(\d+).json', path.name)
        manifest = read(path, directory)
        if not match or not isinstance(manifest, dict):
            continue
        receipt = manifest.get('receipt') or {}
        # Resolve by basename within this execution, including archives moved from another host.
        name = Path(str(receipt.get('path', ''))).name
        if not re.fullmatch(r'output-[a-f0-9]+\.json', name):
            continue
        output_path = root / name
        record = read(output_path, directory)
        if not isinstance(record, dict):
            continue
        try:
            valid_hash = hashlib.sha256(output_path.read_bytes()).hexdigest() == receipt.get('sha256')
        except OSError:
            continue
        loop = int(match[1])
        if not valid_hash or record.get('run_tag') != tag or record.get('loop') != loop:
            continue
        text = record.get('output')
        if isinstance(text, str) and text.strip():
            outputs.append({'loop': loop, 'result_id': None, 'text': text,
                            'status': (record.get('execution') or {}).get('status', 'unknown')})
    return sorted(outputs, key=lambda row: (row['loop'], row['result_id'] or 0))
