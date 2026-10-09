"""Independent pipeline definitions, recovery scopes, and launch isolation."""

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from memstara.control.workspace import PipelineWorkspace
from memstara.control import recovery
from memstara.pipeline.exploration import write_progress


class Manager:
    def __init__(self, key):
        self.key = key
        self.live = None

    def running(self):
        return self.live

    def finished(self):
        return []


def test_workspace_preserves_more_than_three_concurrent_adds(tmp_path):
    workspace = PipelineWorkspace(tmp_path / "workspace.json", Manager)
    assert workspace.list() == []

    def add(_):
        try:
            return workspace.mutate({"action": "add"})["id"]
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        added = [p for p in pool.map(add, range(8)) if p]
    assert len(added) == len(set(added)) == 8
    restored = PipelineWorkspace(tmp_path / "workspace.json", Manager)
    assert len(restored.list()) == 8
    assert {p["number"] for p in restored.list()} == set(range(1, 9))
    removed = restored.items[3]
    restored.mutate({"action": "remove", "id": removed['id']})
    replacement = restored.mutate({"action": "add"})
    assert replacement['number'] == removed['number']
    assert replacement['id'] != removed['id']


def test_independent_edit_launch_lock_and_removal(tmp_path):
    w = PipelineWorkspace(tmp_path / "workspace.json", Manager)
    a = w.mutate({"action": "add"})
    b = w.mutate({"action": "add"})
    w.start(a["id"], lambda manager, item: setattr(manager, "live", {"run_tag": "run-a", "run_dir": str(tmp_path)}))
    with pytest.raises(ValueError, match="Stop"):
        w.mutate({"action": "remove", "id": a["id"]})
    w.mutate({"action": "update", "id": b["id"], "name": "Other research"})
    assert w.locate_manager("run-a").key == a["id"]
    assert w.manager(b["id"]).running() is None
    w.mutate({"action": "remove", "id": b["id"]})
    assert len(w.list()) == 1
    assert w.list()[0]["name"] == a["name"]


def test_one_hypothesis_and_interpreter_per_pipeline():
    config = PipelineWorkspace.configuration({"hypothesis_agents": 3, "interpret_agents": 4, "trials": 20})
    assert config["hypothesis_agents"] == config["interpret_agents"] == config["trials"] == 1
    with pytest.raises(ValueError):
        PipelineWorkspace.configuration({"playbook_hypothesis": "a,b"})


def test_recovery_separates_pipeline_processes(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "identity", lambda pid: f"identity-{pid}")
    for pid, key in [(101, "a"), (102, "b"), (103, None)]:
        directory = tmp_path / str(pid)
        directory.mkdir()
        recovery.save_record(
            {
                "pid": pid,
                "pipeline_id": key,
                "run_tag": str(pid),
                "process_identity": f"identity-{pid}",
                "run_dir": str(directory),
            }
        )
    for key, expected in [("a", 101), ("b", 102), (None, 103)]:
        live, _ = recovery.recover(tmp_path, key)
        assert live["pid"] == expected


def test_progress_has_iteration_not_invented_percentage(tmp_path):
    write_progress(tmp_path, 6, "ml", [{"status": "in_progress"}])
    data = json.loads((tmp_path / "progress.json").read_text())
    assert data["iteration"] == 6 and data["stage"] == "ml"
    assert data["counts"]["in_progress"] == 1 and "percentage" not in data
    assert not Path(tmp_path / "progress.tmp").exists()


def test_three_controllers_launch_independently_and_stop_only_the_target(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.control import service

    monkeypatch.setattr(service, "RUNS_DIR", tmp_path)
    processes = []

    class Child:
        def __init__(self, argv, **kwargs):
            self.pid = 9000 + len(processes)
            self.argv = argv
            self.code = None
            self.signals = []
            processes.append(self)

        def poll(self):
            return self.code

        def send_signal(self, sig):
            self.signals.append(sig)

    monkeypatch.setattr(service.subprocess, "Popen", Child)
    monkeypatch.setattr(service, "identity", lambda pid: f"identity-{pid}")
    monkeypatch.setattr(recovery, "identity", lambda pid: f"identity-{pid}")
    managers = [service._Runs(key) for key in ("a", "b", "c")]
    for i, manager in enumerate(managers):
        directory = tmp_path / str(i)
        directory.mkdir()
        manager.start([], f"run-{i}", directory, "")
    assert len(processes) == 3
    assert all("--pipeline-id" in p.argv for p in processes)
    with pytest.raises(RuntimeError):
        managers[0].start([], "duplicate", tmp_path, "")
    managers[1].stop("run-1")
    assert [len(p.signals) for p in processes] == [0, 0, 0]
    assert [(tmp_path / str(i) / 'pause.request').exists() for i in range(3)] == [False, True, False]
    restored = service._Runs('b')
    assert restored.running()['pause_requested'] is True
    restored.pause('run-1', False)
    assert not (tmp_path / '1' / 'pause.request').exists()
    managers[1].terminate('run-1')
    assert [len(p.signals) for p in processes] == [0, 1, 0]
    assert [service._Runs(key).running()["run_tag"] for key in ("a", "b", "c")] == ["run-0", "run-1", "run-2"]


def test_agent_names_are_separate_across_independent_runs():
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.pipeline.core import board_workers

    first = board_workers({"hypothesis": ["same"]}, "run-a")
    second = board_workers({"hypothesis": ["same"]}, "run-b")
    assert not ({name for name, _ in first.values()} & {name for name, _ in second.values()})


def test_tools_reject_other_pipeline_before_connecting(monkeypatch):
    import asyncio
    from memstara.mcp_servers import blackboard as bb

    monkeypatch.setattr(bb, "_pipeline_run", lambda: "mine")

    async def check():
        assert "error" in json.loads(await bb.read_results("other"))
        assert "error" in json.loads(await bb.claim_task("data", "other"))
        assert "error" in json.loads(await bb.propose_questions("[]", origin_run="other"))

    asyncio.run(check())


def test_running_pipeline_can_be_renamed_without_changing_its_execution(tmp_path):
    workspace = PipelineWorkspace(tmp_path / 'workspace.json', Manager)
    pipeline = workspace.mutate({'action': 'add'})
    live = {'run_tag': 'keep-running', 'run_dir': str(tmp_path)}
    workspace.manager(pipeline['id']).live = live
    renamed = workspace.mutate({'action': 'update', 'id': pipeline['id'], 'name': '  My research  '})
    assert renamed['name'] == 'My research'
    assert renamed['configuration'] == pipeline['configuration']
    assert workspace.manager(pipeline['id']).live is live
    assert PipelineWorkspace(workspace.path, Manager).items[0]['name'] == 'My research'
    with pytest.raises(ValueError, match='Stop'):
        workspace.mutate({'action': 'update', 'id': pipeline['id'], 'name': 'Other', 'configuration': {}})
    with pytest.raises(ValueError, match='1–80'):
        workspace.mutate({'action': 'update', 'id': pipeline['id'], 'name': '   '})


def test_creation_saves_name_and_configuration_together(tmp_path):
    path = tmp_path / 'workspace.json'
    workspace = PipelineWorkspace(path, Manager)
    item = workspace.mutate({'action': 'add', 'name': '  Treatment effects  ',
        'configuration': {'playbook_hypothesis': 'treatment-toxicity',
                          'playbook_ml': 'ml_governance',
                          'question': 'Do not reuse this'}})
    assert PipelineWorkspace(path, Manager).items[0] == item
    assert item['name'] == 'Treatment effects'
    assert item['configuration']['playbook_ml'] == 'ml_governance'
    assert item['configuration']['question'] == ''
    assert workspace.manager(item['id']).running() is None


@pytest.mark.parametrize('name', ['', '   ', 'a' * 81, None, 42])
def test_invalid_creation_does_not_leave_a_pipeline(tmp_path, name):
    path = tmp_path / 'workspace.json'
    workspace = PipelineWorkspace(path, Manager)
    with pytest.raises(ValueError, match='1–80'):
        workspace.mutate({'action': 'add', 'name': name})
    assert workspace.items == []
    assert not path.exists()


def test_loop_limit_is_persisted_and_validated():
    config = PipelineWorkspace.configuration({'waves': 7, 'continuous': False})
    assert config['waves'] == 7 and config['continuous'] is False
    for invalid in (0, 11, True, 2.5):
        with pytest.raises(ValueError, match='Maximum loops'):
            PipelineWorkspace.configuration({'waves': invalid})
    assert PipelineWorkspace.configuration({})['continuous'] is False
    assert PipelineWorkspace.configuration({})['waves'] == 10
    assert PipelineWorkspace.configuration({'continuous': True, 'waves': 1})['waves'] == 10


def test_stop_all_attempts_every_pipeline_even_if_one_fails(tmp_path):
    class Manager:
        def __init__(self, key): self.key = key; self.called = False
        def running(self): return {'run_tag': self.key}
        def stop(self, tag):
            self.called = True
            if tag == 'a': raise RuntimeError('test failure')
    workspace = PipelineWorkspace(tmp_path/'workspace.json', Manager)
    workspace.items = [{'id':'a','name':'A'}, {'id':'b','name':'B'}]
    result = workspace.stop_all()
    assert result['stopping'] == ['b'] and len(result['errors']) == 1
    assert all(m.called for m in workspace.managers.values())


def test_legacy_unlimited_workspace_is_durably_migrated_before_launch(tmp_path):
    path = tmp_path / 'workspace.json'
    path.write_text(json.dumps([{'id': 'legacy', 'name': 'Legacy', 'number': 1,
                                 'configuration': {'continuous': True, 'waves': 1}}]))
    workspace = PipelineWorkspace(path, Manager)
    config = workspace.list()[0]['configuration']
    assert config['waves'] == 10 and config['continuous'] is False
    assert json.loads(path.read_text())[0]['configuration'] == config
    received = workspace.start('legacy', lambda manager, item: item['configuration'])
    assert received == config
    restored = PipelineWorkspace(path, Manager)
    assert restored.items[0]['configuration'] == config


def test_finished_loop_limit_uses_frozen_execution_not_next_settings(tmp_path):
    class FinishedManager(Manager):
        def finished(self):
            return [{'run_tag': 'saved', 'run_dir': str(tmp_path), 'exit_code': 0}]
    (tmp_path/'config.json').write_text(json.dumps({'waves': 10, 'continuous': False}))
    (tmp_path/'progress.json').write_text(json.dumps({'iteration': 7}))
    workspace = PipelineWorkspace(tmp_path/'workspace.json', FinishedManager)
    item = workspace.mutate({'action':'add'})
    workspace.mutate({'action':'update', 'id':item['id'], 'configuration':{'waves':3}})
    result = workspace.list()[0]
    assert result['configuration']['waves'] == 3
    assert result['latest']['configuration']['waves'] == 10
    assert result['progress']['iteration'] == 7


def test_failure_details_follow_execution_and_do_not_mark_recovered_success_failed(tmp_path):
    old = tmp_path / 'failed'
    old.mkdir()
    (old / 'execution.json').write_text(json.dumps({'calls': [
        {'status': 'failed', 'error': 'System message must be at the beginning.', 'stage': 'question0-1'}]}))
    record = {'run_tag': 'old', 'run_dir': str(old), 'exit_code': 1}
    class HistoryManager(Manager):
        def finished(self):
            return [record]
    workspace = PipelineWorkspace(tmp_path / 'workspace.json', HistoryManager)
    item = workspace.mutate({'action': 'add'})
    assert workspace.list()[0]['failure']['code'] == 'model_message_format'
    record['exit_code'] = 0
    assert workspace.list()[0]['failure'] is None
    record['exit_code'] = 1
    workspace.manager(item['id']).live = {'run_tag': 'new', 'run_dir': str(tmp_path / 'new')}
    assert workspace.list()[0]['failure'] is None
