"""Run offline checks and fresh paid pipeline acceptance; never accept skipped live tests."""

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from xml.etree import ElementTree


LIVE_CASES = {
    "synthetic-okf-dataset", "synthetic-llm_only-dataset",
    "synthetic-okf-proposal", "synthetic-llm_only-proposal",
    "heart_combinations-okf-dataset", "heart_random-okf-dataset",
    "heart_guided-okf-dataset", "synthetic_paths-okf-dataset",
}


def require_live_success(report: Path) -> None:
    """Require every public case, including setup/teardown success, exactly once."""
    cases = list(ElementTree.parse(report).getroot().iter("testcase"))
    expected = {f"test_real_haiku_pipeline[{case}]" for case in LIVE_CASES}
    if len(cases) != len(expected) or {case.get("name") for case in cases} != expected:
        raise ValueError("Live acceptance incomplete: all eight public cases must run exactly once")
    if any(case.find(tag) is not None for case in cases for tag in ("skipped", "failure", "error")):
        raise ValueError("Live acceptance failed: skipped, failed or errored cases are not accepted")


def require_docker_success(report: Path) -> None:
    cases = list(ElementTree.parse(report).getroot().iter('testcase'))
    required = {'test_container_kill_restart_reuses_durable_phase_without_repeating_effect',
                'test_paired_dump_and_isolated_restore'}
    if (len(cases) != len(required) or {c.get('name') for c in cases} != required
            or any(c.find(tag) is not None for c in cases for tag in ('skipped', 'failure', 'error'))):
        raise ValueError('Both isolated Docker recovery tests must run and pass')


def main() -> int:
    if len(sys.argv) != 1:
        print("Usage: python -m scripts.verify_pipeline (no bypass or reuse options)", file=sys.stderr)
        return 2
    repo = Path(__file__).resolve().parents[1]
    root = repo / "outputs" / "verification" / (
        "pipeline_check_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    )
    root.mkdir(parents=True)
    summary = {"status": "running", "live_status": "not_started", "phase": "offline",
               "evidence": str(root)}
    summary_path = root / "verification.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    env = dict(os.environ)
    # Shell-level selection flags must not silently remove mandatory test cases.
    env.pop("PYTEST_ADDOPTS", None)
    common = [sys.executable, "-m", "pytest", "-o", "addopts=", "-q"]
    print("Full verification includes eight fresh paid Haiku 5.5 cases (11 Loops). "
          "Configured model credentials and reachable initialized databases are required. "
          "Missing prerequisites fail verification; previous runs cannot replace new calls.", flush=True)
    try:
        subprocess.run([*common, "tests", "--ignore=tests/live", "--ignore=tests/integration",
                        f"--junitxml={root / 'offline.xml'}"], cwd=repo, env=env, check=True)
        summary['phase'] = 'docker_restart'
        summary_path.write_text(json.dumps(summary, indent=2))
        subprocess.run([*common, 'tests/docker', '--run-docker',
                        f"--junitxml={root / 'docker.xml'}"], cwd=repo, env=env, check=True)
        require_docker_success(root / 'docker.xml')
        summary['phase'] = 'browser_recovery'
        summary_path.write_text(json.dumps(summary, indent=2))
        web = repo / 'viewer' / 'web'
        subprocess.run(['npm', 'run', 'build'], cwd=web, env=env, check=True)
        subprocess.run(['npm', 'run', 'test:browser', '--', '--grep',
                        'recovery-states|clinical-log|combination-skips'], cwd=web, env=env, check=True)
        summary['phase'] = 'live'
        summary["live_status"] = "running"
        summary_path.write_text(json.dumps(summary, indent=2))
        report = root / "live.xml"
        subprocess.run([
            *common, "tests/live/test_haiku_pipeline.py::test_real_haiku_pipeline",
            "--run-live", "--live-audit-io", "--live-loops=1", "-x", "-s",
            f"--junitxml={report}",
        ], cwd=repo, env=env, check=True)
        require_live_success(report)
        summary.update(status="passed", live_status="passed", phase="completed")
        return 0
    except (subprocess.CalledProcessError, OSError, ValueError, ElementTree.ParseError, KeyboardInterrupt):
        summary["status"] = "failed"
        if summary["live_status"] == "running":
            summary["live_status"] = "failed"
        print("Verification failed. See test output and evidence; live success was not confirmed.",
              file=sys.stderr)
        return 1
    finally:
        summary_path.write_text(json.dumps(summary, indent=2))
        print(f"Verification summary: {summary_path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
