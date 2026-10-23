"""Read saved Explanation narratives, never substitute a deterministic final report."""
import hashlib
import json
import re
from functools import lru_cache
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
    manifest = read(directory / 'execution.json', directory)
    calls = manifest.get('calls', []) if isinstance(manifest, dict) else []
    recorded_loops = {item['loop'] for item in outputs}
    for call in calls:
        loop = call.get('loop')
        if call.get('stage') != 'report' or not isinstance(loop, int) or loop in recorded_loops:
            continue
        evidence = call.get('step_evidence') or {}
        path = directory / str(evidence.get('path', ''))
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            continue
        try:
            stat = path.stat()
            text = trace_output(str(path), stat.st_mtime_ns, stat.st_size,
                                evidence.get('sha256'), call.get('run_id'), loop)
        except OSError:
            continue
        if text:
            outputs.append({'loop': loop, 'result_id': None, 'text': text,
                            'status': call.get('status', 'unknown')})
    return sorted(outputs, key=lambda row: (row['loop'], row['result_id'] or 0))


@lru_cache(maxsize=128)
def trace_output(path, modified, size, expected_hash, run_id, loop):
    """Cache only final text, never retain or expose prompts and tool histories."""
    raw = Path(path).read_bytes()
    if not expected_hash or hashlib.sha256(raw).hexdigest() != expected_hash:
        return None
    try:
        trace = json.loads(raw)
        if trace.get('run_id') != run_id or trace.get('stage') != 'report' or trace.get('loop') != loop:
            return None
        run = trace.get('run') or {}
        if run.get('id') != run_id:
            return None
        output = run.get('output')
        if isinstance(output, str):
            try:
                envelope = json.loads(output)
            except ValueError:
                return output if output.strip() else None
        else:
            envelope = output
        if isinstance(envelope, dict) and envelope.get('kind') == 'motoro.output.envelope/v1':
            text = envelope.get('result')
            return text if isinstance(text, str) and text.strip() else None
    except (ValueError, AttributeError):
        return None
    return None
