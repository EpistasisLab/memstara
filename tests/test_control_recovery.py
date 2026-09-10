import json

from memstara.control import recovery


def test_recovery_reattaches_only_to_same_process(tmp_path, monkeypatch):
    directory = tmp_path / 'run'
    directory.mkdir()
    record = {'run_tag': 'test', 'pid': 123, 'run_dir': str(directory), 'process_identity': 'birth and command'}
    recovery.save_record(record)
    monkeypatch.setattr(recovery, 'identity', lambda pid: 'birth and command')
    live, done = recovery.recover(tmp_path)
    assert live['run_tag'] == 'test' and not done
    assert live['popen'].poll() is None
    monkeypatch.setattr(recovery, 'identity', lambda pid: 'different birth and command')
    live, done = recovery.recover(tmp_path)
    assert live is None and done[0]['exit_code'] == 1


def test_completed_run_survives_control_restart(tmp_path):
    directory = tmp_path / 'run'
    directory.mkdir()
    recovery.save_record({'run_tag': 'test', 'pid': 123, 'run_dir': str(directory), 'exit_code': 0})
    live, done = recovery.recover(tmp_path)
    assert live is None and done[0]['exit_code'] == 0
    assert json.loads((directory / 'control_record.json').read_text())['run_tag'] == 'test'
