"""The HTTP surface that starts a run, and the child process it owns.

==============================================================================
 How to read this file
==============================================================================

 What this file does
   Six routes on 127.0.0.1:8072. Five of them answer questions; one starts
   `python -m memstara.pipeline.board` as a child process. That is the whole
   service — everything else here is about making sure the one dangerous route
   can only be reached from this machine, by the viewer, with a body that says
   exactly what a run takes.

 The six routes
   GET  /control/health          the service is up, and which bundle it reads
   GET  /control/playbooks       the behavioural standards on disk, and which stages
                                 can be given one. Two lists: see `playbooks()`.
   GET  /control/skills          the branches this bundle actually has, with a
                                 document count each. Generated, never listed
   POST /control/runs            start one run. Returns its tag immediately
   GET  /control/runs            what is running, and what recently finished
   GET  /control/runs/{tag}/log  that run's console output, from a byte offset.
                                 `{tag}` may be `latest`
   POST /control/runs/{tag}/stop resumable stop at the next agent-call boundary
   POST /control/runs/{tag}/resume continue that same live execution
   POST /control/runs/{tag}/end permanently terminate the execution

 Easy things to miss
   1. **The branch list is read through the okf server's own loader.** `_load`
      and `values_for` are imported from `src/memstara/mcp_servers/okf.py`, so
      the branches offered on screen are by construction the branches the
      agents will be confined to. A second enumeration written here would be a
      list that drifts, and it would drift in the direction of offering a
      branch that selects nothing.
   2. **Stop uses a durable marker for current drivers.** In-flight work finishes;
      the Python continuation waits before any new agent call. Resume removes the
      marker. End and legacy-driver Stop use SIGINT so traces can be saved. This
      does not recover the continuation after a driver crash or machine restart.
   3. **The child is started in its own session** (`start_new_session=True`),
      so stopping this service does not stop a run. A run holds a database
      advisory lock and is doing paid work; it outliving its launcher is the
      behaviour to want.
   4. **One run at a time**, refused with the running tag rather than queued.
      The board already refuses a second driver on one tag (`run_lock`), but
      two runs on two tags would both be real and neither would be what the
      person at the screen asked for.
   5. `.env` is never read here, never echoed, and never returned. The child
      loads it itself through `load_env()`, as it does when started by hand.
==============================================================================
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from memstara.control.workspace import PipelineWorkspace
from memstara.control.request import build_argv, _MAX_HYPOTHESIS_AGENTS
from memstara.agent_labels import AGENT_LABELS
from memstara.control.catalog import catalog, reference_knowledge, register, validate_selection
from memstara.env import load_env
from memstara.logging_setup import new_run_dir
from memstara.mcp_servers.frontmatter import matches, values_for
from memstara.mcp_servers.okf import OKFError, _bundle_root, _load
from memstara.pipeline.board import PLAYBOOK_STAGES
from memstara.pipeline.prompts import accepts_playbook
from memstara.paths import REPO_ROOT, RUNS_DIR
from memstara.control.recovery import identity, recover, save_record

_SKILL_FIELDS = ("terminus_kind", "mechanism_family")

#: Hostnames this service will answer to. A page on the open web can make a browser
#: send a request here — it cannot read the answer, but this service *starts processes*,
#: so the request going through at all is the problem. An attacker's domain pointed at
#: 127.0.0.1 arrives with its own name in `Host`, and that is what this refuses.
#: nginx sends `$host` (no port), the Vite proxy sends `localhost:8072`, curl sends
#: whatever was typed — so the comparison is on the name with the port stripped.
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "host.docker.internal", "[::1]"})

#: Where the viewer is served from, in Docker and in `npm run dev`
#: (`viewer/docker-compose.yml`, `viewer/web/vite.config.ts:23`). A request with no
#: `Origin` at all — curl, or a same-origin fetch through the proxy — is allowed; one
#: that names a different site is not.
_ALLOWED_ORIGINS = frozenset({
    "http://localhost:8070", "http://127.0.0.1:8070",
    "http://localhost:5173", "http://127.0.0.1:5173",
})

#: How many finished runs `GET /control/runs` remembers. This is a convenience for the
#: screen, not a record — the record is `outputs/runs/`.
_KEEP = 10

#: How much console output one log response may carry. A run's log reaches megabytes, and
#: handing all of it to a browser that asked for everything since byte 0 would lock the
#: tab up and tell nobody anything. Past this the answer starts near the end and says how
#: much it stepped over, which is a fact the screen can show rather than a silent gap.
_MAX_LOG = 64_000


class _Runs:
    """The one child this service may have, and the last few that finished.

    Every method takes the lock. Two browser tabs pressing Start at the same moment is
    the ordinary case, not the exotic one, and `ThreadingHTTPServer` really does run
    them at the same time.
    """

    def __init__(self, pipeline_id=None) -> None:
        self.pipeline_id = pipeline_id
        self._lock = threading.Lock()
        self._live, self._done = recover(RUNS_DIR, self.pipeline_id)

    def _reap(self) -> None:
        """Move the child to the finished list if it has exited. Caller holds the lock."""
        if self._live is None:
            recovered, finished = recover(RUNS_DIR, self.pipeline_id)
            known = {(r["run_tag"], r["run_dir"]) for r in self._done}
            self._done.extend(r for r in finished if (r["run_tag"], r["run_dir"]) not in known)
            self._done.sort(key=lambda r: r.get("started", ""), reverse=True)
            del self._done[_KEEP:]
            self._live = recovered
            if self._live is None:
                return
        code = self._live["popen"].poll()
        if code is None:
            return
        finished = {k: v for k, v in self._live.items() if k != "popen"}
        finished["exit_code"] = code
        finished["ended"] = datetime.now().isoformat(timespec="seconds")
        save_record(finished)
        self._done.insert(0, finished)
        del self._done[_KEEP:]
        self._live = None

    def running(self) -> dict[str, Any] | None:
        with self._lock:
            self._reap()
            if self._live is None:
                return None
            record = {k: v for k, v in self._live.items() if k not in ("popen", "process_identity")}
            try:
                config = json.loads((Path(record["run_dir"]) / "config.json").read_text())
                if record.get("report_only"):
                    for candidate in RUNS_DIR.glob("*/config.json"):
                        original = json.loads(candidate.read_text())
                        if original.get("run_tag") == record["run_tag"] and original.get("mode") != "report_only":
                            config = original
                            break
                record["configuration"] = {k: config.get(k) for k in
                                           ("hypotheses", "interpreters", "interpretation_mode",
                                            "books", "evaluation", "comparison_policy", "trials", "waves", "continuous",
                                            "question", "y_column", "provider", "model")}
                from memstara.stage_models import public_profiles
                record["configuration"]["stage_models"] = public_profiles(config.get("stage_models"))
            except (OSError, ValueError):
                pass
            record["waiting_for_questions"] = (Path(record["run_dir"]) / "questions.waiting").exists()
            record["pause_requested"] = (Path(record["run_dir"]) / "pause.request").exists()
            control_path = Path(record["run_dir"]) / "execution_control.json"
            control = {}
            try:
                control = json.loads(control_path.read_text())
            except (OSError, ValueError):
                pass
            record["resumable"] = bool(record.get("resumable") or control.get("resumable"))
            record["execution_state"] = (
                ('stopping' if control.get('active_calls', 1) else 'paused')
                if record['pause_requested'] else 'running'
            )
            record["active_calls"] = control.get('active_calls')
            from memstara.pipeline.run_ownership import infrastructure_status
            record.update(infrastructure_status(record["run_dir"]))
            return record

    def finished(self) -> list[dict[str, Any]]:
        with self._lock:
            self._reap()
            from memstara.pipeline.checkpoint import recovery_status
            from memstara.pipeline.run_ownership import infrastructure_status
            return [{**{k: v for k, v in record.items() if k != "process_identity"},
                     **recovery_status(record["run_dir"]),
                     **infrastructure_status(record["run_dir"])} for record in self._done]

    def history_records(self):
        """All owned executions for cumulative counts, beyond the recent-runs menu."""
        records = []
        for path in RUNS_DIR.glob("**/control_record.json"):
            try:
                record = json.loads(path.read_text())
                if record.get("pipeline_id") == self.pipeline_id:
                    records.append({"run_tag": record.get("run_tag"), "run_dir": str(path.parent)})
            except (OSError, ValueError):
                continue
        return records

    def locate(self, run_tag: str) -> tuple[str, Path] | None:
        """The tag and directory of a run this service started, or None.

        This lookup is the whole of the log route's safety. The tag arrives from a
        browser and is **never joined onto a path**: it either matches a run this process
        launched — in which case the directory is one this process chose itself — or
        there is nothing to read. A tag containing `../` therefore fails by not matching,
        not by being sanitised, which is the failure mode that cannot be got subtly wrong.

        `latest` means the run going now, or the most recent one to finish. It saves the
        screen from having to track a tag of its own just to ask "what is happening", and
        the answer names the tag it actually read.
        """
        with self._lock:
            self._reap()
            if run_tag == "latest":
                found = self._live or (self._done[0] if self._done else None)
                if found:
                    return found["run_tag"], Path(found["run_dir"])
            if self._live is not None and self._live["run_tag"] == run_tag:
                return run_tag, Path(self._live["run_dir"])
            for record in self._done:
                if record["run_tag"] == run_tag:
                    return run_tag, Path(record["run_dir"])
        for directory in sorted(RUNS_DIR.glob("*"), reverse=True):
            try:
                config = json.loads((directory / "config.json").read_text())
                if run_tag == "latest" or config.get("run_tag") == run_tag:
                    return config["run_tag"], directory
            except (OSError, ValueError, KeyError):
                continue
        return None

    def start(self, argv: list[str], run_tag: str, run_dir: Path, skill: str) -> dict[str, Any]:
        """Launch one run, or raise `RuntimeError` naming the one already going.

        The child's own console output is teed into `<run_dir>/console.log` by
        `board.py` itself, but only once it gets that far: an argument it refuses and a
        missing prerequisite are both printed and gone before the tee is in place. So
        everything is captured here as well, into a second file, which is the one to
        read when a run ends in the first two seconds.

        **`-u` is what makes either file readable while the run is going.** The child's
        stdout here is a regular file, not a terminal, so CPython block-buffers it at 8 KB
        — and a pipeline prints a few hundred bytes over its first several minutes, so
        without this both logs sit at exactly zero bytes while the run is plainly working.
        That is not a slow start that resolves itself; it is a log that arrives in 8 KB
        lumps, minutes late, in the wrong order relative to what the screen otherwise
        shows. The extra write syscalls are the entire cost.
        """
        with self._lock:
            self._reap()
            if self._live is not None:
                raise RuntimeError(
                    f"'{self._live['run_tag']}' is already running. "
                    f"One run at a time — stop it first"
                )
            if self.pipeline_id:
                argv = [*argv, "--pipeline-id", self.pipeline_id]
            log = (run_dir / "control.log").open("wb")
            popen = subprocess.Popen(
                [sys.executable, "-u", "-m", "memstara.pipeline.board",
                 "--run-tag", run_tag, "--run-dir", str(run_dir), *argv],
                cwd=REPO_ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,   # see note 3 in the header
            )
            log.close()
            self._live = {
                "run_tag": run_tag,
                "pipeline_id": self.pipeline_id,
                "resumable": True,
                "run_dir": str(run_dir),
                "skill": skill,
                "pid": popen.pid,
                "started": datetime.now().isoformat(timespec="seconds"),
                "popen": popen,
                "process_identity": identity(popen.pid),
            }
            save_record(self._live)
            return {k: v for k, v in self._live.items() if k not in ("popen", "process_identity")}

    def pause(self, run_tag: str, paused: bool) -> dict[str, Any]:
        """Stop at an agent-call boundary; Resume retains the same continuation."""
        with self._lock:
            self._reap()
            if self._live is None and not paused:
                return self._resume_checkpoint(run_tag)
            if self._live is None or self._live["run_tag"] != run_tag:
                raise RuntimeError("this run is not running")
            marker = Path(self._live["run_dir"]) / "pause.request"
            if paused:
                marker.touch()
            else:
                marker.unlink(missing_ok=True)
            return {"pause_requested": paused}

    def _resume_checkpoint(self, run_tag):
        """Caller holds the manager lock; never accept a client-supplied path."""
        from memstara.pipeline.checkpoint import recovery_status
        record = next((r for r in self._done if r["run_tag"] == run_tag), None)
        if record is None:
            raise RuntimeError("No saved execution belongs to this pipeline")
        root = Path(record["run_dir"])
        status = recovery_status(root)
        if not status.get("recoverable"):
            raise RuntimeError(status.get("recovery_blocked", "This execution has no recoverable checkpoint"))
        saved = json.loads((root / "resume_arguments.json").read_text())
        if saved.get("run_tag") != run_tag or (saved.get("pipeline_id") or None) != self.pipeline_id:
            raise RuntimeError("Checkpoint ownership does not match this pipeline")
        (root / "pause.request").touch()
        with (root / "control.log").open("ab") as log:
            popen = subprocess.Popen(
                [sys.executable, "-u", "-m", "memstara.pipeline.board", "--resume",
                 "--run-tag", run_tag, "--run-dir", str(root)], cwd=REPO_ROOT,
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        self._live = {k: v for k, v in record.items()
                      if k not in ("exit_code", "ended", "recoverable", "recovery_blocked")}
        self._live.update(pid=popen.pid, popen=popen, process_identity=identity(popen.pid),
                          resumed_at=datetime.now().isoformat(timespec="seconds"))
        save_record(self._live)
        self._done = [r for r in self._done if r["run_tag"] != run_tag]
        # The restored driver waits on this marker until ownership is recorded.
        (root / "pause.request").unlink(missing_ok=True)
        return {"pause_requested": False, "recovered": True, "run_tag": run_tag}

    def stop(self, run_tag: str) -> dict[str, Any]:
        """Request resumable stop for new drivers; interrupt legacy drivers."""
        with self._lock:
            self._reap()
            if self._live is None or self._live['run_tag'] != run_tag:
                raise RuntimeError("this run is not running")
            directory = Path(self._live['run_dir'])
            if self._live.get('resumable') or (directory / 'execution_control.json').exists():
                (directory / 'pause.request').touch()
                return {'stopping': run_tag, 'resumable': True}
            self._live['popen'].send_signal(signal.SIGINT)
            return {'stopping': run_tag, 'resumable': False}

    def terminate(self, run_tag: str) -> dict[str, Any]:
        """Ask the running child to wind up, or raise `RuntimeError` saying why not."""
        with self._lock:
            self._reap()
            if self._live is None:
                raise RuntimeError("nothing is running")
            if self._live["run_tag"] != run_tag:
                raise RuntimeError(
                    f"'{run_tag}' is not the run that is going; '{self._live['run_tag']}' is"
                )
            self._live["popen"].send_signal(signal.SIGINT)   # see note 2 in the header
            return {"stopping": run_tag, "pid": self._live["pid"]}


RUNS = _Runs()
# Saved configurations can reference deployment-configured external skills.
load_env()
WORKSPACE = PipelineWorkspace(RUNS_DIR / "pipeline_workspace.json", _Runs)


def skills(root=None) -> list[dict[str, Any]]:
    """Every branch of the bundle that holds at least one document.

    A branch with nothing in it is left out rather than shown greyed: offering it would
    be offering a run whose agents can read nothing, and the failure would look like a
    thin literature rather than like an empty filter.
    """
    docs, _ = _load(root or _bundle_root())
    fields = [d.fields for d in docs]
    out: list[dict[str, Any]] = []

    for key in _SKILL_FIELDS:
        for value in values_for(fields, key):
            n = sum(1 for f in fields if matches(f, {key: value}))
            if n:
                out.append({"skill": f"{key}={value}", "label": value,
                            "field": key, "documents": n})

    # The crossings, in the order `--skill` wants them written. Both keys in one
    # expression is how a run gets down to single figures, which is the whole point of
    # choosing a branch at all.
    for mech in values_for(fields, "mechanism_family"):
        for kind in values_for(fields, "terminus_kind"):
            wanted = {"mechanism_family": mech, "terminus_kind": kind}
            n = sum(1 for f in fields if matches(f, wanted))
            if n:
                out.append({"skill": f"mechanism_family={mech},terminus_kind={kind}",
                            "label": f"{mech} × {kind}", "field": "both", "documents": n})
    return out


def playbooks() -> dict[str, Any]:
    """The behavioural standards on disk, and the stages that can be given one.

    **Two lists, not one, and the second is the point.** A playbook only reaches a model
    through a prompt that carries a ``{{playbook}}`` line; `board.py` refuses the pair at
    `ap.error` otherwise. So a menu built from the playbooks alone would offer the report
    stage a standard it cannot receive, and the browser would find that out from a run
    that never started. `stages` is read off the prompt files themselves
    (`prompts.accepts_playbook`), so marking a third stage makes this endpoint — and the
    form that renders it — grow by itself.

    This is deliberately *not* `skills()`'s shape. That one counts documents per branch
    because a branch with nothing in it is a filter that returns nothing; a playbook has
    no such property, it is one file that is either attached or not.
    """
    return {
        "playbooks": [x["id"] for x in catalog()],
        "catalog": catalog(),
        "references": reference_knowledge(),
        "agent_labels": AGENT_LABELS,
        "max_hypotheses": _MAX_HYPOTHESIS_AGENTS,
        "stages": [s for s in PLAYBOOK_STAGES if accepts_playbook(f"board/{s}")],
    }


def read_log(run_dir: Path, offset: int) -> dict[str, Any]:
    """One run's console output from `offset` bytes in, capped at `_MAX_LOG`.

    Which file, and why it matters. `board.py` tees its own output into
    `<run_dir>/console.log`, but only once it has got far enough to set the tee up: an
    argument it refuses and a missing prerequisite are both printed and gone before that.
    `control.log` is this service's capture of the child's stdout and stderr from the
    first byte, so it is the superset and it is what is read here. `console.log` is the
    fallback, for a run directory written by a board somebody started by hand.

    The caller sends back the `offset` it was last given, so a screen watching a live run
    fetches only what has been written since — the log grows, the responses do not.

    Two things the shape of this admits rather than hides. A slice can begin in the middle
    of a multi-byte character, so decoding is `errors="replace"` and one glyph at a seam
    may come through as U+FFFD. And when the log has outrun the cap, the answer jumps to
    the end rather than truncating from the front, because what someone watching a run
    wants is the part still being written; `skipped` says how many bytes went past.
    """
    path = run_dir / "control.log"
    if not path.exists():
        path = run_dir / "console.log"
    if not path.exists():
        # Not an error. Between `Popen` returning and the child's first flush there is a
        # real moment where the run exists and its log does not.
        return {"offset": 0, "size": 0, "skipped": 0, "text": ""}

    size = path.stat().st_size
    # A file that shrank was replaced under us; start again rather than seek past the end.
    start = 0 if offset > size else offset
    skipped = 0
    if size - start > _MAX_LOG:
        skipped = size - _MAX_LOG - start
        start = size - _MAX_LOG

    with path.open("rb") as handle:
        handle.seek(start)
        raw = handle.read(size - start)

    return {"offset": size, "size": size, "skipped": skipped,
            "text": raw.decode("utf-8", errors="replace")}


class Handler(BaseHTTPRequestHandler):
    """Five routes. Anything else is a 404 with the list of what there is."""

    protocol_version = "HTTP/1.1"
    server_version = "memstara-control"
    sys_version = ""

    # ---- the plumbing ---------------------------------------------------- #

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # No CORS headers, deliberately. The browser reaches this through nginx
        # (`viewer/web/nginx.conf`) or the Vite proxy, so every legitimate request is
        # same-origin and needs none. Adding one to a service that starts processes
        # would hand the ability to any page that asked.
        self.end_headers()
        self.wfile.write(body)

    def _refuse_stranger(self) -> bool:
        """True if the request was answered with a refusal and the caller should stop."""
        host = self.headers.get("Host", "").rsplit(":", 1)[0] or "127.0.0.1"
        if host not in _ALLOWED_HOSTS:
            self._send(403, {"error": f"this service does not answer to the name {host!r}"})
            return True
        origin = self.headers.get("Origin")
        if origin is not None and origin not in _ALLOWED_ORIGINS:
            self._send(403, {"error": f"{origin} is not the viewer"})
            return True
        return False

    def _body(self) -> Any:
        """The decoded JSON object, or `ValueError` with something readable in it.

        The `Content-Type` check is not pedantry. A form on any web page can POST to
        this port without asking the browser's permission, but only with a handful of
        content types — `application/json` is not among them, so requiring it is what
        turns a cross-site POST into a preflight this service never answers.
        """
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("send application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Content-Length is not a number") from None
        if length > 64_000:
            raise ValueError("that is not a run request")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            raise ValueError(f"the body is not JSON: {e}") from None
        if not isinstance(body, dict):
            raise ValueError("the body must be a JSON object")
        return body

    # ---- the routes ------------------------------------------------------ #

    def do_GET(self) -> None:      # noqa: N802 - the name http.server dispatches on
        if self._refuse_stranger():
            return
        path = urlsplit(self.path).path.rstrip("/")

        if path == "/control/research-inputs":
            from memstara.research_inputs import list_inputs
            try:
                self._send(200, {"inputs": list_inputs()})
            except (OSError, ValueError):
                self._send(503, {"error": "Registered research inputs could not be read"})
            return

        if path == "/control/question-memory":
            from memstara.control.question_memory import handle
            try:
                self._send(200, handle(WORKSPACE, RUNS))
            except Exception:
                self._send(503, {"error": "Question memory is unavailable. No records were changed."})
            return

        if path == "/control/skill-drafts/models":
            from memstara.control.skill_drafts import models
            try:
                self._send(200, models())
            except ValueError:
                self._send(503, {"error": "Configure the model connection before generating a skill."})
            return
        if path.startswith("/control/skill-drafts/"):
            from memstara.control.skill_drafts import get
            draft = get(path.rsplit("/", 1)[-1])
            self._send(200 if draft else 404, draft or {"error": "Draft expired or server restarted. Generate again."})
            return

        if path == "/control/health":
            try:
                root = str(_bundle_root())
                docs, _ = _load(_bundle_root())
                bundle: dict[str, Any] = {"path": root, "documents": len(docs)}
            except OKFError as e:
                # Reported, not raised. A missing bundle is a thing to show on screen
                # next to a dot, not a reason for this service to be down.
                bundle = {"error": str(e)}
            from memstara.control.request import configured_llm
            try:
                provider, model = configured_llm()
                from memstara.env import configured_api_base
                from memstara.config import Settings
                endpoint = configured_api_base(provider)
                if not endpoint and provider == "azure_foundry":
                    from motoro.services.credentials import foundry_api_base
                    endpoint = foundry_api_base(Settings().anthropic_foundry_resource)
                host = urlsplit(endpoint or "").hostname or ""
                is_azure = host.endswith((".services.ai.azure.com", ".openai.azure.com"))
                llm = {"provider": provider, "model": model, "endpoint": endpoint,
                       "resource": host.split(".")[0] if is_azure else None,
                       "source": "motoro/.env (process environment)", "restart_required_after_edit": True}
            except ValueError as exc:
                llm = {"provider": "", "model": "", "error": str(exc)}
            from memstara.stage_models import deployment_profiles, public_profiles
            try:
                stage_models = public_profiles(deployment_profiles())
                stage_model_error = None
            except ValueError:
                stage_models = {}
                stage_model_error = "Deployment stage model profiles are missing or invalid"
            self._send(200, {"ok": True, "bundle": bundle, "running": RUNS.running(), "llm": llm,
                             "stage_models": stage_models, "stage_model_error": stage_model_error})
            return

        if path.startswith("/control/pipelines/") and path.endswith("/combinations"):
            try:
                key = path.split("/")[3]
                manager = WORKSPACE.manager(key)
                loop = int(parse_qs(urlsplit(self.path).query).get("loop", ["1"])[0])
                running = manager.running()
                latest = running or next(iter(manager.finished()), None)
                if not latest:
                    self._send(200, {"planned": None, "calls": []})
                    return
                root = Path(latest['run_dir'])
                from memstara.combinations import loop_flavors
                if running and not (root / 'config.json').exists():
                    self._send(200, {"run_tag": latest['run_tag'], "preparing": True,
                                     "planned": None, "executed": None, "calls": []})
                    return
                plan = json.loads((root / 'config.json').read_text()).get('combination_plan')
                planned = loop_flavors(plan, loop) if plan else None
                flavor_file = root / f"loop_{loop}_flavors.json"
                executed = json.loads(flavor_file.read_text()) if flavor_file.exists() else None
                execution_path = root / 'execution.json'
                manifest = json.loads(execution_path.read_text()) if execution_path.exists() else {}
                calls = [c for c in manifest.get('calls', []) if c.get('loop') == loop]
                self._send(200, {"run_tag": latest['run_tag'], "planned": planned, "executed": executed,
                                 "total_loops": plan['total_loops'] if plan else 0, "calls": calls})
            except (ValueError, OSError, TypeError, KeyError) as exc:
                self._send(400, {"error": str(exc)})
            return

        if path == "/control/pipelines":
            self._send(200, {"pipelines": WORKSPACE.list()})
            return

        if path == "/control/skills":
            try:
                self._send(200, {"skills": skills()})
            except OKFError as e:
                self._send(503, {"error": str(e)})
            return

        if path == "/control/playbooks":
            # No try/except around it, unlike /control/skills. That one reads the OKF
            # bundle, which is a path out of the environment and can genuinely be absent;
            # this reads a directory inside the installed package, and `playbook_names`
            # already answers `[]` for a checkout that has none.
            self._send(200, playbooks())
            return

        if path == "/control/runs":
            self._send(200, {"running": RUNS.running(), "finished": RUNS.finished()})
            return

        if path.startswith("/control/runs/") and path.endswith("/log"):
            found = RUNS.locate(path[len("/control/runs/"):-len("/log")])
            if found is None:
                # 404 rather than an empty log: "this service did not start that run" and
                # "that run has printed nothing yet" are different answers, and a screen
                # that cannot tell them apart shows a blank box for both.
                self._send(404, {"error": "this service has no such run"})
                return
            run_tag, run_dir = found
            query = parse_qs(urlsplit(self.path).query)
            try:
                offset = max(0, int(query.get("offset", ["0"])[0]))
            except ValueError:
                offset = 0
            self._send(200, {"run_tag": run_tag, **read_log(run_dir, offset)})
            return

        self._send(404, {"error": f"no route {path}", "routes": _ROUTES})

    def do_POST(self) -> None:     # noqa: N802 - the name http.server dispatches on
        if self._refuse_stranger():
            return
        path = urlsplit(self.path).path.rstrip("/")

        try:
            body = self._body()
        except ValueError as e:
            self._send(400, {"error": str(e)})
            return

        if path in ("/control/research-inputs/inspect", "/control/research-inputs/register"):
            from memstara.research_inputs import inspect, register as register_research_inputs
            try:
                result = (register_research_inputs if path.endswith('/register') else inspect)(body)
                self._send(200, result)
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
            except OSError:
                self._send(400, {"error": "Research files are unavailable or cannot be read"})
            return

        if path == "/control/question-memory/clear":
            from memstara.control.question_memory import handle, MemoryConflict
            try:
                self._send(200, handle(WORKSPACE, RUNS, body))
            except MemoryConflict as exc:
                self._send(409, {"error": str(exc)})
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
            except Exception:
                self._send(503, {"error": "Clear outcome is uncertain. Retry this confirmation to check its outcome."})
            return

        if path == "/control/skill-drafts":
            from memstara.control.skill_drafts import start
            try:
                self._send(202, start(body))
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
            return

        if path == "/control/llm/key":
            if body != {"reveal": True}:
                self._send(400, {"error": "Explicit reveal request required"})
                return
            from memstara.control.request import configured_llm
            from memstara.config import Settings
            try:
                provider, _ = configured_llm()
                settings = Settings()
                key = {"openai": settings.openai_api_key,
                       "azure_foundry": settings.anthropic_foundry_api_key,
                       "anthropic": settings.anthropic_api_key}.get(provider, "")
                if not key:
                    self._send(404, {"error": "No API key is configured for this provider"})
                    return
                self._send(200, {"api_key": key})
            except ValueError:
                self._send(400, {"error": "Model connection is not configured"})
            return

        if path == "/control/playbooks":
            try:
                self._send(201, register(body))
            except (ValueError, OSError) as e:
                self._send(400, {"error": str(e)})
            return

        if path == "/control/pipelines":
            try:
                self._send(200, WORKSPACE.mutate(body))
            except (ValueError, OSError) as e:
                self._send(409, {"error": str(e)})
            return

        if path == "/control/stop-all":
            result = WORKSPACE.stop_all()
            legacy = RUNS.running()
            if legacy:
                try:
                    RUNS.stop(legacy['run_tag'])
                    result['stopping'].append(legacy['run_tag'])
                except (RuntimeError, OSError) as exc:
                    result['errors'].append({'pipeline': 'Standalone execution', 'error': str(exc)})
            self._send(200, result)
            return

        if path == "/control/runs":
            self._start(body)
            return

        if path.startswith("/control/runs/") and path.rsplit("/", 1)[-1] in ("pause", "resume"):
            prefix, action = path.rsplit("/", 1)
            tag = prefix[len("/control/runs/"):]
            try:
                self._send(200, (WORKSPACE.locate_manager(tag) or RUNS).pause(tag, action == "pause"))
            except RuntimeError as e:
                self._send(409, {"error": str(e)})
            return

        if path.startswith("/control/runs/") and path.endswith("/end"):
            tag = path[len("/control/runs/"):-len("/end")]
            try:
                self._send(200, (WORKSPACE.locate_manager(tag) or RUNS).terminate(tag))
            except RuntimeError as e:
                self._send(409, {"error": str(e)})
            return

        if path.startswith("/control/runs/") and path.endswith("/stop"):
            tag = path[len("/control/runs/"):-len("/stop")]
            try:
                self._send(200, (WORKSPACE.locate_manager(tag) or RUNS).stop(tag))
            except RuntimeError as e:
                self._send(409, {"error": str(e)})
            return

        self._send(404, {"error": f"no route {path}", "routes": _ROUTES})

    def _start(self, body: dict[str, Any]) -> None:
        pipeline_id = body.pop("pipeline_id", None)
        if pipeline_id is not None:
            try:
                # Freeze the saved definition while validating and launching it.
                limit = body.pop("iteration_limit", None)
                if limit is not None and (type(limit) is not int or not 1 <= limit <= 10):
                    raise ValueError("iteration_limit must be an integer from 1 to 10")
                def launch(manager, item):
                    configuration = dict(item["configuration"])
                    if limit is not None and configuration.get("combination_skills"):
                        raise ValueError("Combination designs use their reviewed complete schedule")
                    if limit is not None:
                        configuration.update(continuous=False, waves=limit)
                    return self._launch(configuration, manager, item["name"])
                mode = body.pop("execution_mode", "initial")
                additional = body.pop("additional_loops", None)
                expected = body.pop("expected_run_tag", None)
                if mode == "additional" and limit is not None:
                    raise ValueError("Use additional_loops alone for additional analysis")
                return WORKSPACE.start(pipeline_id, launch, mode=mode,
                                       additional_loops=additional, expected_run_tag=expected)
            except (ValueError, RuntimeError) as e:
                self._send(409, {"error": str(e)})
                return
        return self._launch(body, RUNS)

    def _launch(self, body, manager, pipeline_name=""):
        # The web control surface always imposes a finite ceiling, including older clients.
        body = dict(body)
        if body.get('continuous') is True:
            body.update(continuous=False, waves=10)
        research = None
        try:
            if body.get('research_input_id'):
                from memstara.research_inputs import prepare
                research = prepare(body['research_input_id'])
                config = research['configuration']
                body.update(knowledge_mode=config['knowledge_mode'], data_mode=config['data_mode'],
                            research_objective=config['target']['description'],
                            y_column=config['target']['column'] or 'outcome')
            available = ([] if body.get('knowledge_mode') == 'llm_only' else
                         skills(Path(research['root']) / 'okf') if research else skills())
            offered = [s["skill"] for s in available]
        except (OKFError, ValueError, OSError) as e:
            self._send(422, {"error": f"Run not started. {e}", "code": "input_validation_failed"})
            return
        # Read here rather than cached at import, so that writing a new playbook while
        # the service is running makes it startable without a restart. It is a directory
        # listing and a handful of small files; the bundle read above is the expensive
        # half of this handler and it was already being done per request.
        menu = playbooks()
        try:
            argv = build_argv(body, offered, menu["playbooks"], menu["stages"])
            validate_selection(body)
        except ValueError as e:
            self._send(400, {"error": str(e)})
            return

        # Reject unusable input before creating a run, log or child process. Return
        # only aggregate diagnostics, never dataset values, headers or file paths.
        from memstara.evaluation import DataQualityError, preflight, validate
        from memstara.control.catalog import resolve
        try:
            if body.get('data_mode', 'dataset') == 'dataset':
                dataset = (str(Path(research['root']) / 'dataset.csv') if research
                           else os.environ.get("MEMSTARA_DATASET_PATH", ""))
                if not dataset:
                    raise DataQualityError('No dataset is configured. Configure a curated CSV before starting.')
                book = body.get("playbook_ml", "")
                policy = resolve(book).get("evaluation", {}) if book else {}
                plan = validate({**policy, **body.get("evaluation", {})})
                preflight(Path(dataset), argv[argv.index("--y-column") + 1], plan, reserve_validation=True)
                if body.get("combination_skills"):
                    from memstara.pipeline.feature_context import freeze_feature_context
                    freeze_feature_context(Path(dataset), argv[argv.index("--y-column") + 1],
                                           require_complete=True)
                from memstara.comparisons import validate_baseline
                validate_baseline(body.get("baseline_columns", []), argv[argv.index("--y-column") + 1], Path(dataset))
        except ValueError as e:
            self._send(422, {"error": f"Run not started. {e}", "code": "input_validation_failed"})
            return

        started = datetime.now()
        # The same two names `board.py:1912-1915` would have chosen for itself. They are
        # passed explicitly so that this service can answer with the tag in the same
        # response, instead of the screen having to guess which new run is the one it
        # just asked for.
        run_tag = started.strftime("board_%Y%m%dT%H%M%S_%f")
        trials = argv[argv.index("--trials") + 1]
        run_dir = new_run_dir(f"board_{trials}trials", started.strftime("%Y-%m-%dT%H%M%S_%f"))
        skill = argv[argv.index("--skill") + 1]
        try:
            self._send(201, manager.start([*argv, "--pipeline-name", pipeline_name], run_tag, run_dir, skill))
        except RuntimeError as e:
            self._send(409, {"error": str(e)})

    def log_message(self, fmt: str, *args: Any) -> None:
        # One line per request on stderr, without the date the default prefixes. This
        # service is meant to be run in a terminal somebody is watching.
        sys.stderr.write("control  %s\n" % (fmt % args))


_ROUTES = [
    "GET  /control/question-memory",
    "POST /control/question-memory/clear",
    "GET /control/health", "GET /control/skills", "GET /control/playbooks",
    "POST /control/playbooks", "POST /control/runs",
    "GET /control/runs", "GET /control/runs/{tag}/log", "POST /control/runs/{tag}/stop",
]


def serve(port: int = 8072) -> None:
    """Bind the loopback interface and answer until interrupted.

    The address is not configurable. This service starts processes on this machine
    with this machine's credentials; which interface it listens on is not a setting to
    be changed in passing, and exposing it is a decision that needs an answer about
    authentication first.
    """
    load_env()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"control service on http://127.0.0.1:{port}")
    for route in _ROUTES:
        print(f"  {route}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        live = RUNS.running()
        if live:
            print(f"\nstopping; '{live['run_tag']}' keeps running (pid {live['pid']})")
        else:
            print("\nstopping")
    finally:
        server.server_close()
