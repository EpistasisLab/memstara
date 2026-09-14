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


def test_workspace_starts_empty_and_caps_concurrent_adds(tmp_path):
    workspace = PipelineWorkspace(tmp_path / "workspace.json", Manager)
    assert workspace.list() == []

    def add(_):
        try:
            return workspace.mutate({"action": "add"})["id"]
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        added = [p for p in pool.map(add, range(8)) if p]
    assert len(added) == len(set(added)) == 3
    restored = PipelineWorkspace(tmp_path / "workspace.json", Manager)
    assert len(restored.list()) == 3
    assert {p["number"] for p in restored.list()} == {1, 2, 3}


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
    assert [len(p.signals) for p in processes] == [0, 1, 0]
    assert [service._Runs(key).running()["run_tag"] for key in ("a", "b", "c")] == ["run-0", "run-1", "run-2"]


def test_agent_names_are_separate_across_independent_runs():
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
