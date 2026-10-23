"""Read-only run provenance. Never infer one run's state from another run's calls."""
import json
import os
import time
import threading
try:
    from .explanation_outputs import saved_outputs
except ImportError:
    from explanation_outputs import saved_outputs
from pathlib import Path

ROOT = Path(os.environ.get("MEMSTARA_RUNS_DIR", "/runs"))
_config_index: dict[str, dict] | None = None
_indexed_root: Path | None = None
_index_expires = 0.0
_index_lock = threading.RLock()
_matches: dict[str, list] = {}


def _refresh_index():
    """Refresh configuration metadata at most every two seconds, off the API loop.

    Archive directories without config.json are normal. Their count must not be used
    to invalidate an index keyed by run tags. Reports and execution state stay uncached
    so updates and report recovery are visible on the next snapshot.
    """
    global _config_index, _indexed_root, _index_expires
    if _indexed_root == ROOT and time.monotonic() < _index_expires:
        return
    try:
        directories = tuple(sorted((d for d in ROOT.iterdir() if d.is_dir()), key=str))
    except OSError:
        directories = ()
    index: dict[str, dict] = {}
    _matches.clear()
    for directory in directories:
        config = read_json(directory / "config.json")
        if isinstance(config, dict) and config.get("run_tag"):
            _matches.setdefault(config['run_tag'], []).append((directory, config))
    for tag, matches in _matches.items():
        matches.sort(key=lambda pair: pair[1].get('mode') == 'report_only')
        index[tag] = matches[0][1]
    _config_index = index
    _indexed_root = ROOT
    _index_expires = time.monotonic() + 2.0


def config_for(tag):
    with _index_lock:
        _refresh_index()
        return _config_index.get(tag)


def configs():
    with _index_lock:
        _refresh_index()
        return dict(_config_index)


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def pipeline_state(directory):
    """Read the first recorded cause without rewriting historical run artifacts."""
    state = read_json(directory / "pipeline_status.json")
    failure = read_json(directory / "pipeline_failure.json")
    if (isinstance(failure, dict) and isinstance(failure.get("message"), str)
            and (not isinstance(state, dict) or state.get("status") != "completed")):
        result = {**(state if isinstance(state, dict) else {}), "status": "failed",
                  **{key: failure[key] for key in ("message", "code", "stage", "loop") if key in failure}}
        if failure.get("http_status") == 429 and result.get("code") == "model_request_rejected":
            result.update(code="model_rate_limit", message=(
                "The model service returned HTTP 429. This response does not establish "
                "a request-settings error; inspect the saved provider response. "
                "Saved results are retained; further execution was stopped."))
        # Older records retained the typed provider exception but used a generic
        # code. Explain only that recorded type; do not infer an HTTP status.
        if (result.get("code") == "agent_execution_failed"
                and "InternalServerError" in (failure.get("exception_types") or [])):
            result.update(code="model_server", message="The model service reported an internal server error. "
                          "This execution did not complete; saved results remain available.")
        return result
    return state


def lookup(tag):
    with _index_lock:
        _refresh_index()
        matches = list(_matches.get(tag, []))
    for directory, config in matches:
        if not isinstance(config, dict) or config.get("run_tag") != tag:
            continue
        calls = []
        locations = [directory, *directory.glob("report-recovery*"),
                     *[d for d, c in matches if d != directory and c.get("mode") == "report_only"]]
        report_location = directory
        report_time = 0
        for location in locations:
            manifest = read_json(location / "execution.json")
            records = manifest.get("calls", []) if isinstance(manifest, dict) else read_json(location / "runs.json")
            if isinstance(records, list):
                calls.extend(records)
                for call in records:
                    if call.get("stage") == "report" and (call.get("started_at") or 0) >= report_time:
                        report_location, report_time = location, call.get("started_at") or 0
        report_status = read_json(report_location / "report_status.json")
        report = ""
        try:
            report = (report_location / "report.md").read_text()
        except OSError:
            pass
        report_calls = [call for call in calls if call.get("stage") == "report"]
        latest = max(report_calls, key=lambda call: call.get("started_at") or 0, default={})
        if latest.get("status") in ("started", "running"):
            report_status = {"status": "generating"}
        elif latest.get("status") in ("failed", "cancelled"):
            report_status = {"status": latest["status"], "error": latest.get("error", "Report call failed")}
        explanations = {}
        for location in locations:
            if location.resolve().is_relative_to(ROOT.resolve()):
                for output in saved_outputs(location, tag):
                    explanations[(output['loop'], output['result_id'])] = output
        result = {
            "config": {k: config.get(k) for k in (
                "hypotheses", "interpreters", "interpretation_mode", "books", "evaluation", "comparison_policy",
                "pipeline_id", "pipeline_name", "research_profile", "data_mode", "knowledge_mode",
                "empirical_evaluation", "research_objective",
                "trials", "waves", "continuous", "skill", "question", "y_column", "provider", "model",
            )},
            "calls": calls,
            "report": {"status": (report_status or {}).get(
                           "status", "available" if report.strip() else "not_available"),
                       "text": report, "explanation_outputs": sorted(explanations.values(), key=lambda row: (row["loop"], row["result_id"] or 0)), "error": (report_status or {}).get("error"),
                       "specialist_explanation": (report_status or {}).get("specialist_explanation")},
            "pipeline": pipeline_state(directory),
        }
        return result
    return None


def result_identity(config, tag, trial):
    """Trial indices are zero based: board.py allocates wave * trials + index."""
    trials = config.get("trials")
    iteration = (trial // trials + 1 if config.get("pipeline_id")
                 and isinstance(trials, int) and trials > 0 and trial >= 0 else None)
    return {"run_tag": tag, "pipeline_id": config.get("pipeline_id"),
            "pipeline_name": config.get("pipeline_name"), "iteration": iteration}


def directory_for(tag):
    """Resolve only an indexed run, never a user-supplied filesystem path."""
    with _index_lock:
        _refresh_index()
        matches = _matches.get(tag, [])
        return matches[0][0] if matches else None
