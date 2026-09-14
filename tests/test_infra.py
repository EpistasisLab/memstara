"""Protect live-data volume identity without touching Docker or running services."""
import pytest

from memstara import infra


def mount(name):
    return {"Destination": infra.DATA_PATH, "Type": "volume", "Name": name}


@pytest.mark.parametrize("mounts", [[], [mount("motoro_postgres_data")],
                                   [{"Destination": infra.DATA_PATH, "Type": "bind"}],
                                   [mount("agentic_core_postgres_data")] * 2])
def test_wrong_or_ambiguous_mount_is_rejected(mounts):
    with pytest.raises(RuntimeError, match="Refusing"):
        infra.validate_mount("motoro-postgres", mounts)


def test_all_mounts_are_checked_before_any_start(monkeypatch):
    import json
    calls = []

    def fake(*args):
        calls.append(args)
        if args[0] != "inspect":
            pytest.fail("No mutation is allowed when another container has the wrong volume")
        volume = "agentic_core_postgres_data" if args[-1] == "motoro-postgres" else "wrong"
        return json.dumps({"state": "exited", "mounts": [mount(volume)]})

    monkeypatch.setattr(infra, "docker", fake)
    with pytest.raises(RuntimeError, match="Refusing memstara-postgres"):
        infra.check(start=True)
    assert len(calls) == 2


def test_running_services_are_not_restarted(monkeypatch):
    import json
    calls = []

    def fake(*args):
        calls.append(args)
        if args[0] == "inspect":
            volume = infra.EXPECTED_VOLUMES[args[-1]]
            return json.dumps({"state": "running", "mounts": [mount(volume)] if volume else []})
        assert args[0] == "exec"
        return "PONG" if args[1] == "motoro-redis" else "accepting connections"

    monkeypatch.setattr(infra, "docker", fake)
    infra.check(start=True)
    assert not any(args[0] == "start" for args in calls)
