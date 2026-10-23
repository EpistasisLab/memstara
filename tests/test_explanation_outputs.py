import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer' / 'api'))
from explanation_outputs import saved_outputs


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_ordinary_output_is_exact_and_scoped(tmp_path):
    text = '\n## Trial 1\n\nOriginal **Explanation**.\n'
    source = tmp_path / 'report_io/loop-1-result-2-input.json'
    write(source, {'run_tag': 'a', 'loop': 1, 'result_id': 2, 'sha256': 'hash'})
    write(source.with_name('loop-1-result-2-output.json'), {
        'input_sha256': 'hash', 'output': text, 'execution': {'status': 'completed'}})
    (tmp_path / 'report.md').write_text('Deterministic comparison')
    assert saved_outputs(tmp_path, 'a') == [{'loop': 1, 'result_id': 2, 'text': text, 'status': 'completed'}]
    assert saved_outputs(tmp_path, 'b') == []
    write(source, {'run_tag': 'a', 'loop': 1, 'result_id': 2, 'sha256': 'different'})
    assert saved_outputs(tmp_path, 'a') == []


def test_specialist_receipt_integrity_and_moved_archive(tmp_path):
    output = tmp_path / 'explanation_io/output-abcdef.json'
    text = 'Exact saved specialist output'
    write(output, {'run_tag': 'a', 'loop': 2, 'output': text, 'execution': {'status': 'completed'}})
    write(tmp_path / 'explanation_io/loop-2.json', {'receipt': {
        'path': '/old/host/explanation_io/output-abcdef.json',
        'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}})
    assert saved_outputs(tmp_path, 'a')[0]['text'] == text
    assert saved_outputs(tmp_path, 'b') == []
    output.write_text('{}')
    assert saved_outputs(tmp_path, 'a') == []


def test_never_substitute_comparison_or_unbound_loop_text(tmp_path):
    (tmp_path / 'report.md').write_text('Numeric comparison')
    write(tmp_path / 'report_io/loop-1.json', {'text': 'Unbound text'})
    assert saved_outputs(tmp_path, 'a') == []


def test_symlink_outside_execution_is_not_read(tmp_path):
    outside = tmp_path / 'outside'
    write(outside / 'loop-1-result-2-input.json', {'run_tag': 'a', 'loop': 1, 'result_id': 2, 'sha256': 'h'})
    write(outside / 'loop-1-result-2-output.json', {'input_sha256': 'h', 'output': 'private'})
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'report_io').symlink_to(outside, target_is_directory=True)
    assert saved_outputs(run, 'a') == []


def test_legacy_trace_final_output_is_exact_without_exposing_prompt(tmp_path):
    text = '# Original narrative\nTrial 1 stays Trial 1.\n'
    trace = tmp_path / 'trace/report.steps.json'
    write(trace, {'run_id': 'r', 'stage': 'report', 'loop': 1,
                  'input': 'private prompt', 'run': {'id': 'r', 'output': json.dumps({
                      'kind': 'motoro.output.envelope/v1', 'result': text})}})
    write(tmp_path / 'execution.json', {'calls': [{'stage': 'report', 'run_id': 'r',
        'loop': 1, 'status': 'completed', 'step_evidence': {'path': 'trace/report.steps.json',
        'sha256': hashlib.sha256(trace.read_bytes()).hexdigest()}}]})
    assert saved_outputs(tmp_path, 'a') == [{'loop': 1, 'result_id': None, 'text': text, 'status': 'completed'}]
    trace.write_text('{}')
    assert saved_outputs(tmp_path, 'a') == []
