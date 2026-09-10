import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer' / 'api'))
import run_artifacts


def test_artifacts_are_scoped_and_do_not_expose_prompts(tmp_path, monkeypatch):
    monkeypatch.setattr(run_artifacts, 'ROOT', tmp_path)
    for tag in ('first', 'second'):
        directory = tmp_path / tag
        directory.mkdir()
        (directory / 'config.json').write_text(json.dumps({'run_tag': tag, 'hypotheses': 3, 'prompts': 'private'}))
        (directory / 'execution.json').write_text(json.dumps({'calls': [{'run_id': tag}]}))
        (directory / 'report.md').write_text(tag + ' report')
    selected = run_artifacts.lookup('first')
    assert selected['calls'] == [{'run_id': 'first'}]
    assert selected['report']['text'] == 'first report'
    assert 'prompts' not in selected['config']
    assert run_artifacts.lookup('../first') is None


def test_index_does_not_rescan_directories_without_configs(tmp_path, monkeypatch):
    monkeypatch.setattr(run_artifacts, 'ROOT', tmp_path)
    for name in ('archived', 'first', 'second'):
        (tmp_path / name).mkdir()
    (tmp_path / 'first' / 'config.json').write_text(json.dumps({'run_tag': 'first'}))
    original = run_artifacts.read_json
    reads = []
    def counted(path):
        reads.append(path)
        return original(path)
    monkeypatch.setattr(run_artifacts, 'read_json', counted)
    run_artifacts.configs()
    initial = len(reads)
    for _ in range(46):
        run_artifacts.config_for('first')
    assert len(reads) == initial


def test_live_report_updates_and_report_recovery_are_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(run_artifacts, 'ROOT', tmp_path)
    base = tmp_path / 'base'
    recovery = tmp_path / 'recovery'
    for directory, config in ((base, {'run_tag': 'run', 'hypotheses': 2}),
                              (recovery, {'run_tag': 'run', 'mode': 'report_only'})):
        directory.mkdir()
        (directory / 'config.json').write_text(json.dumps(config))
    (recovery / 'execution.json').write_text(json.dumps({'calls': [
        {'stage': 'report', 'started_at': 1, 'status': 'completed'}]}))
    (recovery / 'report.md').write_text('first version')
    assert run_artifacts.lookup('run')['config']['hypotheses'] == 2
    assert run_artifacts.lookup('run')['report']['text'] == 'first version'
    (recovery / 'report.md').write_text('updated version')
    assert run_artifacts.lookup('run')['report']['text'] == 'updated version'
