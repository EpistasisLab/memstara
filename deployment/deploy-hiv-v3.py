"""Deploy V3 and continue the existing V2 experiment through an audited new attempt.

Run on the Docker-enabled host with --apply. This deliberately uses Retry, not
checkpoint Resume across changed code. Completed loops and old evidence remain
in place; the interrupted loop may repeat work and incur additional model cost.
No checkpoint flags/hashes, experiment settings or database rows are rewritten
by this helper. Existing application endpoints own pause, termination and retry.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = "bf766f42e7e64501a700f2d4bdabd9ab"
SOURCE = "board_20261109T161949_726327"
V3 = "hiv-okf-whole-graph-v3"
ORIGIN = "http://10.226.8.205:8070"


class Client:
    def __init__(self):
        auth = json.loads((ROOT / ".memstara/web-auth/client.json").read_text())
        token = base64.b64encode(f"{auth['username']}:{auth['password']}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "Origin": ORIGIN,
                        "Content-Type": "application/json"}

    def request(self, path, body=None):
        request = urllib.request.Request(
            "http://127.0.0.1:8070" + path, headers=self.headers,
            data=json.dumps(body).encode() if body is not None else None,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:2000]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from None

    def pipeline(self):
        rows = self.request("/control/pipelines")["pipelines"]
        others = [row["name"] for row in rows if row["id"] != PIPELINE and row.get("running")]
        if others:
            raise RuntimeError("Other experiments are live; deployment was not authorized to stop them: "
                               + ", ".join(others))
        row = next(row for row in rows if row["id"] == PIPELINE)
        record = row.get("running") or row.get("latest") or {}
        if record.get("run_tag") != SOURCE:
            raise RuntimeError("The latest execution changed. Refusing to retry an obsolete source.")
        return row


def wait_for(operation, predicate, label, timeout=180):
    deadline = time.monotonic() + timeout
    print(label, flush=True)
    while True:
        result = operation()
        if predicate(result):
            return result
        if time.monotonic() >= deadline:
            raise RuntimeError(label + " timed out. No forced recovery was attempted.")
        time.sleep(2)


def run(command, **kwargs):
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def retry_preflight(record, configuration):
    """Use the deployed server's read-only retry validation before restarting it."""
    code = """
import json, sys
from memstara.control.retry import configuration_for_retry
value = json.load(sys.stdin)
result = configuration_for_retry(value['record'], value['configuration'], value['pipeline_id'])
print(json.dumps({'first_loop': result['_retry_from_loop'], 'last_loop': result['waves'],
                 'skills': result.get('combination_skills'),
                 'seed_schedule': result.get('_retry_seed_schedule'),
                 'plan': result.get('_retry_combination_plan')}))
"""
    result = run(["docker", "compose", "exec", "-T", "control", "python", "-c", code],
                 input=json.dumps({"record": record, "configuration": configuration,
                                   "pipeline_id": PIPELINE}), text=True, capture_output=True)
    return json.loads(result.stdout)


def preserved_files(record):
    relative = Path(record["run_dir"]).relative_to("/app/outputs/runs")
    root = ROOT / "outputs/runs" / relative
    names = ("config.json", "iteration_outcomes.json", "cost_ledger.jsonl")
    return root, {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def verify_catalog(menu, frozen):
    entries = {item["id"]: item for item in menu["catalog"]}
    allowed = menu["corpus_skill_bindings"]["profiles"]["hiv"]["hypothesis"]
    expected = (ROOT / "src/memstara/playbooks" / (V3 + ".md")).read_text().strip()
    if V3 not in allowed or entries.get(V3, {}).get("content", "").strip() != expected:
        raise RuntimeError("The deployed HIV menu does not contain the exact V3 instructions.")
    for stage, skills in frozen["plan"]["skills"].items():
        for skill in skills:
            if entries.get(skill["id"], {}).get("hash") != skill["hash"]:
                raise RuntimeError(f"Original {stage} skill changed: {skill['id']}. Retry was not started.")


def main(apply):
    client = Client()
    item = client.pipeline()
    print("Experiment:", item["name"], "Source:", SOURCE, flush=True)
    if not apply:
        print("Inspection only. Use --apply to pause, deploy V3, and retry the unfinished loop onward.")
        return
    # Fail before pausing if this terminal cannot operate the Docker daemon.
    run(["docker", "info", "--format", "{{.ServerVersion}}"])
    run(["docker", "compose", "version"])
    if item.get("running"):
        client.request(f"/control/runs/{SOURCE}/pause", {})
        wait_for(client.pipeline,
                 lambda row: not row.get("running") or
                 row["running"].get("execution_state") == "paused", "Waiting for acknowledged Pause...")
        if client.pipeline().get("running"):
            # With pause.request retained, the driver records an interrupted
            # attempt rather than resetting or completing its unfinished loop.
            client.request(f"/control/runs/{SOURCE}/end", {})
        item = wait_for(client.pipeline, lambda row: not row.get("running"),
                        "Waiting for the original process to finish saving its interruption...")
    else:
        item = client.pipeline()
    source = item["latest"]
    configuration = item["configuration"]
    frozen = retry_preflight(source, configuration)
    print(f"Validated Retry: loops {frozen['first_loop']}–{frozen['last_loop']}; original skills and seeds.",
          flush=True)
    root, before = preserved_files(source)
    private = ROOT / ".private-tmp"
    private.mkdir(mode=0o700, exist_ok=True)
    # Normal startup only: no history reset, volume deletion or checkpoint edits.
    run(["./start.sh"], env={**os.environ, "TMPDIR": str(private)})
    menu = client.request("/control/playbooks")
    verify_catalog(menu, frozen)
    item = client.pipeline()
    if item["configuration"] != configuration:
        raise RuntimeError("Experiment settings changed during deployment; retry was not started.")
    _, after = preserved_files(source)
    if after != before:
        raise RuntimeError("Original configuration, loop history or cost ledger changed during deployment.")
    if retry_preflight(item["latest"], configuration) != frozen:
        raise RuntimeError("Retry settings differ after deployment; retry was not started.")
    print("V3 deployed and selectable. Original source records verified unchanged.", flush=True)
    # Only the server creates the new attempt and its continuation lineage.
    # Do not automatically repeat this POST after an ambiguous timeout.
    result = client.request("/control/runs", {
        "pipeline_id": PIPELINE, "execution_mode": "retry", "expected_run_tag": SOURCE,
    })
    print("Retry accepted:", result.get("run_tag", "Check the experiment in the UI"), flush=True)
    print("Existing experiment retains V2; V3 is available for new designs.", flush=True)
    print("Verify Running status in the UI. The interrupted loop may repeat work and cost.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    try:
        main(parser.parse_args().apply)
    except (RuntimeError, OSError, ValueError, StopIteration, KeyError, subprocess.CalledProcessError) as exc:
        print("Deployment workflow stopped:", exc, flush=True)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr[-3000:], flush=True)
        print("No reset or checkpoint bypass was requested. Inspect the current UI state before continuing.",
              flush=True)
        raise SystemExit(1) from None
