"""Offline execution diagnosis: no database, credentials or provider calls required.

python -m memstara.trace.diagnose --from outputs/runs/<execution> [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID


def inspect(directory):
    """Read only recorded metadata; missing historical evidence is never fabricated."""
    directory = Path(directory)
    issues = []

    def read(name, journal=False):
        path = directory / name
        if not path.exists():
            return [] if journal else {}
        try:
            raw = path.read_text()
        except (OSError, UnicodeError):
            issues.append(f'{name}: unreadable')
            return [] if journal else {}
        if not journal:
            try:
                value = json.loads(raw)
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
            issues.append(f'{name}: malformed object')
            return {}
        rows = []
        for index, line in enumerate(raw.splitlines(), 1):
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError()
                rows.append(value)
            except ValueError:
                issues.append(f'{name}: malformed line {index}')
        if raw and not raw.endswith('\n'):
            issues.append(f'{name}: unterminated final line')
        return rows

    events = read('request_events.jsonl', True)
    if not events:
        issues.append('Request start/terminal evidence unavailable (historical run or recording failure)')
    groups = {}
    for event in events:
        identity = event.get('request_id')
        if not isinstance(identity, str) or not identity:
            issues.append('Request event without correlation ID')
            continue
        groups.setdefault(identity, []).append(event)
    requests = []
    payload_issues = []
    payloads = []

    def verify_payload(identity, rows, kind, reference):
        try:
            canonical = str(UUID(identity))
            expected = f'model_io/{canonical}.{kind}.json'
            if not isinstance(reference, dict) or reference.get('path') != expected:
                raise ValueError('Missing or invalid reference')
            path = directory / expected
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Outside execution directory')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != reference.get('sha256') or len(raw) != reference.get('bytes'):
                raise ValueError('Integrity mismatch')
            value = json.loads(raw)
            owner = rows[0]
            if not isinstance(value, dict) or any(value.get(k) != owner.get(k)
                    for k in ('request_id', 'run_id', 'stage', 'loop')) or value.get('kind') != kind:
                raise ValueError('Execution context mismatch')
            payloads.append({'request_id': identity, 'kind': kind, 'path': expected, 'verified': True})
        except (OSError, ValueError, TypeError):
            payload_issues.append(f'{identity}: {kind} payload missing, corrupt or mismatched')
    for identity, rows in groups.items():
        starts = [r for r in rows if r.get('state') == 'started']
        ends = [r for r in rows if r.get('state') in ('completed', 'failed', 'cancelled')]
        if len(starts) != 1 or len(ends) != 1:
            issues.append(f'{identity}: expected one start and one terminal event')
        start, end = (starts or [{}])[0], (ends or [{}])[-1]
        if starts and ends and any(start.get(k) != end.get(k) for k in ('run_id', 'stage', 'loop')):
            issues.append(f'{identity}: start/terminal execution context mismatch')
        inputs = [r.get('evidence') for r in rows if r.get('state') == 'input_saved']
        verify_payload(identity, rows, 'input', inputs[0] if len(inputs) == 1 else None)
        if end.get('state') == 'completed':
            verify_payload(identity, rows, 'output', end.get('output_evidence'))
        elif end.get('state') == 'failed':
            verify_payload(identity, rows, 'failure', end.get('failure_evidence'))
        else:
            payload_issues.append(f'{identity}: response unobserved ({end.get("state", "unresolved")})')
        requests.append({
            'request_id': identity, 'run_id': start.get('run_id', end.get('run_id')),
            'stage': start.get('stage', end.get('stage')), 'loop': start.get('loop'),
            'model': start.get('model'), 'attempt': start.get('attempt'),
            'started_at': start.get('at'), 'ended_at': end.get('at'),
            'state': end.get('state', 'unresolved'),
            'duration_seconds': end.get('duration_seconds'),
            'error_types': end.get('error_types', []),
            'http_status': end.get('http_status'),
            'provider_request_id': end.get('provider_request_id'),
        })
    receipts = read('cost_ledger.jsonl', True)
    receipt_ids = {r.get('request_id') for r in receipts if r.get('request_id')}
    for identity in receipt_ids - groups.keys():
        issues.append(f'{identity}: usage receipt has no request events')
    if events and any(not r.get('request_id') for r in receipts):
        issues.append('Usage receipts without request IDs: historical or incomplete request coverage')
    for request in requests:
        if request['state'] in ('completed', 'failed') and request['request_id'] not in receipt_ids:
            issues.append(f"{request['request_id']}: cost/usage receipt unavailable")
        matching = [r for r in receipts if r.get('request_id') == request['request_id']]
        if any(r.get('agent_run_id') != request['run_id'] or r.get('stage') != request['stage']
               for r in matching):
            issues.append(f"{request['request_id']}: receipt execution context mismatch")
    calls = read('execution.json').get('calls', [])
    if not isinstance(calls, list):
        issues.append('execution.json: calls must be a list')
        calls = []
    stages = [{k: c.get(k) for k in ('run_id', 'stage', 'loop', 'status', 'duration_seconds')}
              for c in calls if isinstance(c, dict)]
    stage_issues = []
    for call in calls:
        if not isinstance(call, dict):
            stage_issues.append('Invalid stage record')
            continue
        try:
            if call.get('execution_adapter') == 'proposal_text':
                for kind in ('input', 'output'):
                    # Proposal execution has no Motoro run steps by design.
                    path = directory / 'proposal_io' / f'loop-{int(call["loop"]):04d}' / f'{call["stage"]}.{kind}.json'
                    if not path.resolve().is_relative_to(directory.resolve()):
                        raise ValueError('Invalid proposal path')
                    value = json.loads(path.read_bytes())
                    if not isinstance(value, dict) or (kind == 'output' and value.get('run_id') != call['run_id']):
                        raise ValueError('Invalid proposal evidence')
                continue
            identifier = str(UUID(call['run_id']))
            expected = f'trace/{identifier}.steps.json'
            reference = call.get('step_evidence')
            if not isinstance(reference, dict) or reference.get('path') != expected:
                raise ValueError('Missing stage reference')
            path = directory / expected
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Outside execution directory')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != reference.get('sha256') or len(raw) != reference.get('bytes'):
                raise ValueError('Invalid stage integrity')
            value = json.loads(raw)
            if not isinstance(value, dict) or any(value.get(k) != call.get(k) for k in ('run_id', 'stage', 'loop')):
                raise ValueError('Stage context mismatch')
            if not isinstance(value.get('steps'), list) or not value['steps'] or 'input' not in value:
                raise ValueError('Missing stage payload')
            for step in value['steps']:
                required = ('input', 'output', 'tool_call', 'llm_call')
                if not isinstance(step, dict) or any(k not in step for k in required):
                    raise ValueError('Missing step payload fields')
                if step.get('completed_at') is None:
                    raise ValueError('Unfinished recorded step')
        except (OSError, ValueError, TypeError, KeyError):
            stage_issues.append(f'{call.get("run_id")}: stage input/output evidence unavailable or invalid')
    retries = [{k: r.get(k) for k in ('at', 'run_id', 'stage', 'loop', 'state', 'attempt',
               'delay_seconds', 'error_type', 'http_status', 'provider_request_id', 'request_id')}
               for r in read('model_retries.jsonl', True)]
    evidence_names = ('config.json', 'prompts.json', 'execution.json', 'calls_checkpoint.json',
                      'pipeline_status.json', 'pipeline_failure.json', 'iteration_outcomes.json',
                      'request_events.jsonl', 'provider_diagnostics.jsonl', 'model_retries.jsonl',
                      'model_response_outcomes.jsonl', 'model_completion_repairs.jsonl',
                      'tool_argument_repairs.jsonl', 'cost_ledger.jsonl', 'registry_status.json',
                      'console.log', 'trace', 'model_io', 'proposal_io', 'explanation_io', 'feature_reproduction')
    return {
        'directory': str(directory), 'request_evidence_complete': bool(events) and not issues,
        'issues': issues, 'requests': requests, 'stages': stages, 'retries': retries,
        'service_io_evidence_complete': bool(events) and not issues and not payload_issues,
        'payload_issues': payload_issues, 'payloads': payloads,
        'stage_evidence_complete': bool(stages) and not stage_issues,
        'stage_issues': stage_issues,
        'evidence': {name: 'present' if (directory / name).exists() else 'unavailable'
                     for name in evidence_names},
        'scope': 'Application request attempts only; unresolved does not prove still running. '
                 'Tool payloads and stage I/O remain in traces/DB. Provider internals and '
                 'execution-specific Azure invoice amounts are not established by this journal.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from', dest='directory', required=True, type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error('Execution directory does not exist')
    report = inspect(args.directory)
    if args.json:
        print(json.dumps(report, indent=2, allow_nan=False))
        return
    print(f"Execution: {args.directory}")
    print(f"Request evidence complete: {report['request_evidence_complete']}")
    print(f"Service input/output evidence complete: {report['service_io_evidence_complete']}")
    print(f"Stage evidence complete: {report['stage_evidence_complete']}")
    for issue in report['issues'] + report['payload_issues'] + report['stage_issues']:
        print(f'ATTENTION: {issue}')
    for stage in report['stages']:
        print(f"Stage {stage['stage']} | {stage['status']} | {stage['duration_seconds']} s | {stage['run_id']}")
    for request in report['requests']:
        print(f"Request {request['request_id']} | {request['stage']} | {request['model']} | "
              f"{request['state']} | {request['duration_seconds']} s | {request['error_types']}")
    for retry in report['retries']:
        print(f"Retry {retry['at']} | {retry['stage']} | {retry['state']} | {retry['error_type']}")
    print('Evidence files: ' + ', '.join(k for k, v in report['evidence'].items() if v == 'present'))
    print(report['scope'])


if __name__ == '__main__':
    main()
