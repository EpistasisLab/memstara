"""A partial or skipped live suite must never count as successful verification."""

from xml.etree import ElementTree as ET
import json
import subprocess

import pytest

from scripts.verify_pipeline import LIVE_CASES, require_live_success
from scripts import verify_pipeline


def report(tmp_path, *, omit=False, duplicate=False, result=None):
    suite = ET.Element("testsuite")
    names = sorted(LIVE_CASES)
    if omit:
        names.pop()
    if duplicate:
        names[-1] = names[0]
    for name in names:
        case = ET.SubElement(suite, "testcase", name=f"test_real_haiku_pipeline[{name}]")
        if result:
            ET.SubElement(case, result)
    path = tmp_path / "live.xml"
    ET.ElementTree(suite).write(path)
    return path


def test_complete_live_suite(tmp_path):
    require_live_success(report(tmp_path))


@pytest.mark.parametrize("result", ["skipped", "failure", "error"])
def test_live_non_success_rejected(tmp_path, result):
    with pytest.raises(ValueError):
        require_live_success(report(tmp_path, result=result))


@pytest.mark.parametrize("change", [{"omit": True}, {"duplicate": True}])
def test_missing_or_duplicate_live_case_rejected(tmp_path, change):
    with pytest.raises(ValueError):
        require_live_success(report(tmp_path, **change))


def test_missing_evidence_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        require_live_success(tmp_path / "missing.xml")


@pytest.mark.parametrize("fail_at", [None, 1, 2, 3, 4, 5])
def test_command_requires_fresh_audited_live_calls(tmp_path, monkeypatch, fail_at):
    monkeypatch.setattr(verify_pipeline, "__file__", str(tmp_path / "scripts" / "verify_pipeline.py"))
    monkeypatch.setattr(verify_pipeline.sys, "argv", ["verify_pipeline"])
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k nonexistent")
    calls = []

    def run(args, *, cwd, env, check):
        calls.append(args)
        assert "PYTEST_ADDOPTS" not in env and check
        if len(calls) == fail_at:
            raise subprocess.CalledProcessError(1, args)
        if len(calls) == 2:
            suite = ET.Element('testsuite')
            ET.SubElement(suite, 'testcase',
                          name='test_container_kill_restart_reuses_durable_phase_without_repeating_effect')
            ET.SubElement(suite, 'testcase', name='test_paired_dump_and_isolated_restore')
            path = next(arg.split('=', 1)[1] for arg in args if arg.startswith('--junitxml='))
            ET.ElementTree(suite).write(path)
        if len(calls) == 5:
            path = next(arg.split("=", 1)[1] for arg in args if arg.startswith("--junitxml="))
            verify_pipeline.Path(path).write_bytes(report(tmp_path).read_bytes())

    monkeypatch.setattr(verify_pipeline.subprocess, "run", run)
    assert verify_pipeline.main() == (1 if fail_at else 0)
    summary = json.loads(next(tmp_path.glob("outputs/verification/*/verification.json")).read_text())
    assert summary["status"] == ("failed" if fail_at else "passed")
    if fail_at and fail_at < 5:
        assert len(calls) == fail_at and summary["live_status"] == "not_started"
    else:
        assert len(calls) == 5
        assert "--run-live" in calls[4] and "--live-audit-io" in calls[4]
        assert not any(arg.startswith("--live-batch") for arg in calls[4])
        assert '--run-docker' in calls[1]


@pytest.mark.parametrize('result', ['skipped', 'failure', 'error'])
def test_docker_skip_or_failure_is_not_a_full_pass(tmp_path, result):
    suite = ET.Element('testsuite')
    case = ET.SubElement(suite, 'testcase',
                        name='test_container_kill_restart_reuses_durable_phase_without_repeating_effect')
    ET.SubElement(case, result)
    path = tmp_path / 'docker.xml'
    ET.ElementTree(suite).write(path)
    with pytest.raises(ValueError):
        verify_pipeline.require_docker_success(path)
