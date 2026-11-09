"""Rebuild a completed logical experiment's report without models or training."""

import argparse
import asyncio
from datetime import UTC, datetime
import fcntl
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from memstara.control.history_gate import execution_guard
from memstara.logical_experiment import lineage, read, report_index
from memstara.paths import RUNS_DIR
from memstara.pipeline.checkpoint import atomic_json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def report_failure(root):
    """Recognize old generic report errors without relabeling analysis failures."""
    root = Path(root)
    try:
        failure = read(root / "pipeline_failure.json")
        report = read(root / "report_status.json")
    except (OSError, ValueError):
        return False
    if not isinstance(failure, dict) or not isinstance(report, dict):
        return False
    original_report = {}
    try:
        original_report = read(root / "report-before-rebuild.json").get("report_status", {})
    except (OSError, ValueError, AttributeError):
        pass
    return (
        failure.get("loop") is None
        and failure.get("stage") in ("report", "report_assembly")
        and (
            failure.get("code") == "final_report_assembly_failed"
            or report.get("error") == "Missing per-condition Explanation reports"
            or original_report.get("error") == "Missing per-condition Explanation reports"
        )
    )


@lru_cache(maxsize=2048)
def version_digest(path, modified, size, inode):
    return sha(path)


def recovered(root):
    """Validate an explicit recovery receipt; never rewrite the process exit code."""
    root = Path(root)
    try:
        current = read(root / "pipeline_status.json")
        if current.get("status") != "completed" or not current.get("report_recovered"):
            return False
        receipt = read(root / "report_rebuild.json")
        if receipt.get("status") != "completed" or receipt.get("model_calls") != 0:
            return False
        for value in receipt["files"]:
            path = Path(value["path"])
            stat = path.stat()
            if (
                path.is_symlink()
                or version_digest(str(path), stat.st_mtime_ns, stat.st_size, stat.st_ino) != value["sha256"]
            ):
                return False
        index = read(root / "experiment_index.json")
        return (
            index.get("status") == "completed"
            and not index.get("missing_loops")
            and len(index["reports"]) == index["expected_combinations"]
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def rebuild(root):
    root = Path(root).resolve()
    from memstara.control.recovery import records, RecoveredProcess

    with execution_guard(), (root / ".report-rebuild.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = read(root / "config.json")
        for _, record in records(root.parent):
            if record.get("run_tag") == config["run_tag"] and record.get("exit_code") is None:
                if RecoveredProcess(record).poll() is None:
                    raise ValueError("End the active execution before rebuilding its report")
        if not report_failure(root) and not recovered(root):
            raise ValueError("This is not an isolated final-report failure; no analysis will be rerun")
        if not config.get("combination_plan") or not config.get("specialist_explanation_policy"):
            raise ValueError("Report-only recovery requires saved per-combination Explanation receipts")
        try:
            index, reports = report_index(config, root)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("Saved report metadata is incomplete or invalid; no analysis was rerun") from error
        if index["missing_loops"]:
            raise ValueError(
                "Completed Explanation receipts are missing for original combinations: "
                + ", ".join(map(str, index["missing_loops"]))
            )
        # No partial report is published on missing/tampered ancestry or receipts.
        before = read(root / "pipeline_status.json")
        archive = root / "report-before-rebuild.json"
        if not archive.exists():
            atomic_json(
                archive,
                {
                    "pipeline_status": before,
                    "report_status": read(root / "report_status.json"),
                    "report": (root / "report.md").read_text() if (root / "report.md").exists() else None,
                },
                overwrite=False,
            )
        text = "\n\n".join(reports[loop]["output"] for loop in sorted(reports))
        status = {
            "status": "completed",
            "agent_run_id": None,
            "error": None,
            "model_calls": 0,
            "specialist_explanation": {
                "status": "completed",
                "logical_experiment_id": index["id"],
                "reports": [reports[loop]["summary"] for loop in sorted(reports)],
                "missing_loops": [],
                "aggregation": "verbatim verified reports across explicit continuation attempts; no new LLM call",
            },
        }
        atomic_json(root / "experiment_index.json", index)
        temporary = root / "report.md.rebuilding"
        temporary.write_text(text)
        temporary.replace(root / "report.md")
        atomic_json(root / "report_status.json", status)
        paths = [
            root / "config.json",
            root / "pipeline_failure.json",
            root / "experiment_index.json",
            root / "report.md",
            root / "report_status.json",
        ]
        paths += [Path(row["receipt"]["path"]) for row in index["reports"]]
        paths += [
            directory / "config.json" for _, directory in lineage(config, root) if (directory / "config.json").exists()
        ]
        receipt = {
            "status": "completed",
            "run_tag": config["run_tag"],
            "logical_experiment_id": index["id"],
            "at": datetime.now(UTC).isoformat(),
            "model_calls": 0,
            "analyses_recomputed": 0,
            "combinations": len(reports),
            "files": [{"path": str(path), "sha256": sha(path)} for path in dict.fromkeys(paths)],
        }
        atomic_json(root / "report_rebuild.json", receipt)
        atomic_json(
            root / "pipeline_status.json",
            {
                "status": "completed",
                "report_completed": True,
                "report_recovered": True,
                "original_failure_retained": True,
                "recovery_receipt": "report_rebuild.json",
                "logical_experiment_id": index["id"],
                "code": "report_rebuilt",
                "message": "All scheduled analyses and the final report are complete. "
                "Original attempt diagnostics are retained.",
            },
        )
        return {key: value for key, value in receipt.items() if key != "files"}


async def publish(root):
    """Update only the registry mirror; leave frozen configurations and costs intact."""
    import asyncpg
    from memstara.experiment_registry import dsn

    root = Path(root)
    config = read(root / "config.json")
    connection = await asyncpg.connect(dsn(), timeout=10, command_timeout=10)
    try:
        async with connection.transaction():
            tag = await connection.fetchval(
                """UPDATE memstara_executions SET status='completed',
                report=$2,outcome=$3::jsonb,synced_at=now()
                WHERE run_tag=$1 AND configuration=$4::jsonb RETURNING run_tag""",
                config["run_tag"],
                (root / "report.md").read_text(),
                json.dumps(read(root / "pipeline_status.json")),
                json.dumps(config),
            )
            if tag != config["run_tag"]:
                raise ValueError("Registry source configuration does not match the saved execution")
            for name in (
                "experiment_index.json",
                "report_rebuild.json",
                "report-before-rebuild.json",
                "report_status.json",
                "report.md",
            ):
                path = root / name
                await connection.execute(
                    """INSERT INTO memstara_execution_artifacts VALUES($1,$2,$3,$4,$5)
                    ON CONFLICT(run_tag,path) DO UPDATE SET sha256=EXCLUDED.sha256,bytes=EXCLUDED.bytes""",
                    tag,
                    str(path),
                    sha(path),
                    path.stat().st_size,
                    path.suffix,
                )
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    args = parser.parse_args()
    candidates = [
        directory
        for directory in RUNS_DIR.iterdir()
        if directory.is_dir()
        and (directory / "config.json").is_file()
        and read(directory / "config.json").get("run_tag") == args.run_tag
        and read(directory / "config.json").get("mode") != "report_only"
    ]
    if len(candidates) != 1:
        raise ValueError("Execution is missing or ambiguous")
    result = rebuild(candidates[0])
    asyncio.run(publish(candidates[0]))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
