"""Application-owned experiment registry. Files remain a recoverable ingestion journal.

Run with --run-dir to reconcile an execution without making model calls.
No Motoro tables are modified. Reconciliation is transactional and idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import time
import uuid
import weakref

import asyncpg

from memstara.blackboard import dsn

SCHEMA = """
CREATE TABLE IF NOT EXISTS memstara_experiments (
 id TEXT PRIMARY KEY, definition JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS memstara_experiment_combinations (
 experiment_id TEXT REFERENCES memstara_experiments(id), id TEXT,
 definition JSONB NOT NULL, PRIMARY KEY(experiment_id,id)
);
CREATE TABLE IF NOT EXISTS memstara_executions (
 run_tag TEXT PRIMARY KEY, experiment_id TEXT NOT NULL,
 combination_id TEXT NOT NULL, pipeline_id TEXT, run_directory TEXT NOT NULL,
 status TEXT NOT NULL, configuration JSONB NOT NULL, prompts JSONB NOT NULL,
 report TEXT, outcome JSONB NOT NULL, synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(experiment_id,combination_id) REFERENCES memstara_experiment_combinations(experiment_id,id)
);
CREATE TABLE IF NOT EXISTS memstara_execution_agents (
 run_tag TEXT REFERENCES memstara_executions(run_tag), agent_run_id UUID,
 stage TEXT NOT NULL, started_at DOUBLE PRECISION, duration_seconds DOUBLE PRECISION,
 metadata JSONB NOT NULL, evidence JSONB NOT NULL,
 PRIMARY KEY(run_tag,agent_run_id)
);
CREATE TABLE IF NOT EXISTS memstara_execution_costs (
 run_tag TEXT REFERENCES memstara_executions(run_tag), id TEXT,
 receipt JSONB NOT NULL, PRIMARY KEY(run_tag,id)
);
CREATE TABLE IF NOT EXISTS memstara_execution_artifacts (
 run_tag TEXT REFERENCES memstara_executions(run_tag), path TEXT, sha256 TEXT,
 bytes BIGINT, kind TEXT NOT NULL, PRIMARY KEY(run_tag,path)
);
CREATE INDEX IF NOT EXISTS memstara_execution_experiment_idx ON memstara_executions(experiment_id);
"""


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def encoded(value):
    return json.dumps(value, default=str, allow_nan=False)


def core_record(row):
    """Copy mapped scalar fields without traversing ORM relationships."""
    if row is None:
        return None
    from sqlalchemy import inspect

    return {field.key: getattr(row, field.key) for field in inspect(type(row)).column_attrs}


def identity(config, root):
    """Explicit batch binding wins; standalone runs get a truthful one-run identity."""
    binding = read(root / "experiment_binding.json", {})
    tag = config["run_tag"]
    return (binding.get("experiment_id") or f"standalone:{tag}", binding.get("combination_id") or "C01", binding)


REGISTRY_TABLES = (
    "memstara_experiments",
    "memstara_experiment_combinations",
    "memstara_executions",
    "memstara_execution_agents",
    "memstara_execution_costs",
    "memstara_execution_artifacts",
)


async def schema_ready(conn):
    """Read-only readiness: routine mirroring must never rewrite pg_class ACLs."""
    for name in (*REGISTRY_TABLES, "memstara_execution_experiment_idx"):
        if not await conn.fetchval("SELECT to_regclass($1)", name):
            return False
    if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='memstara_viewer')"):
        for name in REGISTRY_TABLES:
            if not await conn.fetchval("SELECT has_table_privilege('memstara_viewer', $1, 'SELECT')", name):
                return False
    return True


async def initialize(conn):
    """Commit schema/ACL setup before any execution writes; serialize cold starts."""
    if conn.is_in_transaction():
        raise RuntimeError("Registry initialization must precede the data transaction")
    if await schema_ready(conn):
        return
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('memstara.registry.schema', 0))")
        if await schema_ready(conn):
            return
        await conn.execute(SCHEMA)
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='memstara_viewer')"):
            await conn.execute("GRANT SELECT ON " + ", ".join(REGISTRY_TABLES) + " TO memstara_viewer")


async def register_experiment(conn, experiment_id, definition, combinations):
    """A declared design is immutable; retries cannot silently redefine a batch."""
    await conn.execute(
        "INSERT INTO memstara_experiments(id,definition) VALUES($1,$2::jsonb) ON CONFLICT DO NOTHING",
        experiment_id,
        encoded(definition),
    )
    actual = await conn.fetchval("SELECT definition FROM memstara_experiments WHERE id=$1", experiment_id)
    if json.loads(actual) != definition:
        raise ValueError("Experiment definition changed; create a new experiment ID")
    for key, value in combinations.items():
        await conn.execute(
            "INSERT INTO memstara_experiment_combinations VALUES($1,$2,$3::jsonb) ON CONFLICT DO NOTHING",
            experiment_id,
            key,
            encoded(value),
        )
        actual = await conn.fetchval(
            "SELECT definition FROM memstara_experiment_combinations WHERE experiment_id=$1 AND id=$2",
            experiment_id,
            key,
        )
        if json.loads(actual) != value:
            raise ValueError("Combination definition changed")


def artifacts(root, board, output_root, *, candidates=None, fingerprints=None, metrics=None):
    """Index run files and explicit analysis references, never arbitrary external paths."""
    output_root = output_root.resolve()
    paths = set(candidates) if candidates is not None else set(
        p
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
        and p.name not in {"registry_status.json", "registry_metrics.jsonl"} and not p.name.endswith(".tmp")
    )

    def visit(value):
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and len(value) < 4096 and "\n" not in value:
            try:
                path = Path(value).resolve()
                if path.is_relative_to(output_root) and path.is_file():
                    paths.add(path)
                    if path.suffix == ".csv":
                        paths.update(path.parent.glob(path.stem + ".*"))
                elif path.is_relative_to(output_root) and path.is_dir() and path != output_root:
                    paths.update(p for p in path.rglob("*") if p.is_file())
            except (OSError, ValueError):
                pass

    visit(board)
    records = []
    for path in sorted(paths):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(output_root):
            continue
        before = path.stat()
        stamp = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        if fingerprints is not None and fingerprints.get(str(path)) == stamp:
            continue
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            continue  # Still being written; the next reconciliation will index it.
        records.append((str(path.resolve()), digest, after.st_size, path.suffix or "file"))
        if fingerprints is not None:
            fingerprints[str(path)] = stamp
        if metrics is not None:
            metrics["artifact_bytes_hashed"] = metrics.get("artifact_bytes_hashed", 0) + after.st_size
    return records


def record_metrics(root, value):
    """Operational counters contain no prompts, credentials or patient records."""
    try:
        with (Path(root) / "registry_metrics.jsonl").open("a") as stream:
            stream.write(encoded({"at": time.time(), **value}) + "\n")
    except OSError:
        logging.getLogger(__name__).warning("Registry timing evidence could not be saved")


def appended_costs(path, cursor=None):
    """Read complete appended records; replacement/truncation triggers a backfill."""
    if not path.exists():
        return [], None
    before = path.stat()
    identity = (before.st_dev, before.st_ino)
    offset = cursor[2] if cursor and tuple(cursor[:2]) == identity and cursor[2] <= before.st_size else 0
    rows = []
    with path.open("rb") as stream:
        stream.seek(offset)
        end = offset
        while stream.tell() < before.st_size:
            raw = stream.readline()
            if not raw.endswith(b"\n"):
                break  # A writer has not published this complete receipt yet.
            if raw.strip():
                rows.append(json.loads(raw))
            end = stream.tell()
    return rows, (*identity, end)


_mirrors = weakref.WeakKeyDictionary()


def mirror_state(root):
    """Caches are disposable hints: a new process/loop starts with a full backfill."""
    states = _mirrors.setdefault(asyncio.get_running_loop(), {})
    return states.setdefault(str(Path(root).resolve()), {"lock": asyncio.Lock(), "cache": None})


async def sync_incremental(root, call):
    from memstara.artifact_changes import watch

    watch(root)
    state = mirror_state(root)
    async with state["lock"]:
        for attempt in range(5):
            try:
                cache = await _sync(root, delta=[call], cache=state["cache"])
                state["cache"] = cache  # Never advance derived state before commit.
                return
            except RETRYABLE_MIRROR_ERRORS:
                state["cache"] = None  # Backfill any pending calls on recovery.
                if attempt == 4:
                    raise
                await asyncio.sleep(0.1 * (2**attempt))
            except BaseException:
                state["cache"] = None
                raise


def proposal_evidence(root, config, call):
    """Proposal adapter IDs identify local stage records, not Motoro agent runs."""
    from memstara.pipeline.proposal import STAGES

    empirical = config.get("empirical_evaluation", {})
    if (
        config.get("mode") != "proposal"
        or call.get("mode") != "proposal"
        or call.get("execution_adapter") != "proposal_text"
        or call.get("core_run_id") is not None
        or call.get("computation_status") != "not_executed"
        or empirical.get("status") != "not_executed"
        or empirical.get("metrics") is not None
    ):
        raise ValueError("Proposal adapter evidence requires an explicit non-empirical execution")
    stage, loop = call.get("stage"), call.get("loop")
    if stage not in STAGES or type(loop) is not int or loop < 1:
        raise ValueError("Invalid proposal stage identity")
    io = root / "proposal_io" / f"loop-{loop:04d}"
    paths = [io / f"{stage}.input.json", io / f"{stage}.output.json", *sorted(io.glob(f"{stage}.attempt-*.json"))]
    if any(not path.resolve().is_relative_to(root.resolve()) for path in paths):
        raise ValueError("Proposal evidence escapes execution directory")
    request = read(paths[0], None)
    output = read(paths[1], None)
    if not request or any(request.get("profile", {}).get(k) != call.get(k) for k in ("model", "provider")):
        raise ValueError("Proposal input or model identity is missing or inconsistent")
    identity_fields = ("run_id", "stage", "loop", "model", "provider", "status")
    if call.get("status") == "completed" and (not output or any(output.get(k) != call.get(k) for k in identity_fields)):
        raise ValueError("Completed proposal output is missing or inconsistent")
    return {
        "adapter": "proposal_text",
        "input": request,
        "output": output,
        "attempts": [read(path, {}) for path in paths[2:]],
    }


TRANSIENT_MIRROR_ERRORS = (
    asyncpg.DeadlockDetectedError,
    asyncpg.SerializationError,
    asyncpg.PostgresConnectionError,
    asyncpg.CannotConnectNowError,
    TimeoutError,
)
RETRYABLE_MIRROR_ERRORS = (*TRANSIENT_MIRROR_ERRORS, PermissionError)


async def sync(root: Path, *, evidence=True):
    """Retry whole rolled-back transactions, never agents or model requests."""
    for attempt in range(5):
        try:
            return await _sync(root, evidence=evidence)
        except RETRYABLE_MIRROR_ERRORS:
            if attempt == 4:
                raise
            await asyncio.sleep(0.1 * (2**attempt))


async def sync_after_agent(root: Path, *, call=None):
    """A transient mirror conflict is not a failure of an already completed agent.

    Local evidence remains authoritative for reconciliation. Identity/integrity
    errors still propagate; final reconciliation must report any pending mirror.
    """
    try:
        if call is None:
            await sync(root)
        else:
            await sync_incremental(root, call)
    except RETRYABLE_MIRROR_ERRORS as exc:
        # Defer only the mirror, never a failure to persist the primary journal.
        if isinstance(exc, PermissionError):
            from memstara.execution_journal import load_calls

            calls = load_calls(root)
            if not calls or not any(call.get("status") == "completed" for call in calls):
                raise
            for call in calls:
                if call.get("status") == "completed":
                    evidence_path = call.get("step_evidence", {}).get("path")
                    if not evidence_path or not (root / evidence_path).is_file():
                        raise
                    saved = root / evidence_path
                    if not saved.resolve().is_relative_to(root.resolve()):
                        raise ValueError("Agent evidence is outside the execution directory") from exc
                    raw = saved.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != call["step_evidence"].get("sha256"):
                        raise ValueError("Agent evidence changed; registry failure cannot be deferred") from exc
                    json.loads(raw)
        from memstara.pipeline.checkpoint import atomic_json
        from memstara.pipeline.failures import exception_locations

        atomic_json(
            root / "registry_status.json",
            {
                "status": "pending",
                "error_type": type(exc).__name__,
                "reason": "Registry mirror unavailable; local evidence retained for reconciliation",
                "exception_locations": exception_locations(exc),
            },
        )
        print(f"Experiment registry pending: {type(exc).__name__}; agent results retained.")


async def _sync(root: Path, *, evidence=True, delta=None, cache=None):
    root = root.resolve()
    from memstara.artifact_changes import pending, acknowledge
    from memstara.execution_journal import load_calls

    started = time.monotonic()
    incremental = delta is not None and cache is not None
    observed = pending(root)
    metrics = {"operation": "registry_sync", "mode": "incremental" if incremental else "full"}
    config = read(root / "config.json", {})
    if not config:
        return
    tag = config["run_tag"]
    experiment, combination, binding = identity(config, root)
    calls = list(delta) if incremental else load_calls(root)
    if incremental:
        # Console/trace metadata can change after an earlier mirror; consume
        # those explicitly changed per-agent records without scanning history.
        pending_calls = {
            row["run_id"]: row for path in observed
            if path.parent == root / "call_records" and path.is_file()
            for row in [read(path, {})] if row.get("run_id")
        }
        pending_calls.update({call["run_id"]: call for call in delta})
        calls = list(pending_calls.values())
    call_hashes = dict(cache["call_hashes"]) if incremental else {}
    changed_calls = []
    for call in calls:
        digest = hashlib.sha256(encoded(call).encode()).hexdigest()
        if call_hashes.get(call.get("run_id")) != digest:
            changed_calls.append(call)
            call_hashes[call.get("run_id")] = digest
    calls = changed_calls
    outcome = read(root / "pipeline_status.json", {"status": "running"})
    costs, cursor = appended_costs(root / "cost_ledger.jsonl", cache["cost_cursor"] if incremental else None)
    cost_ids = set(cache["cost_ids"]) if incremental else set()
    cost_ids.update(row["id"] for row in costs)
    records = []
    evidence_keys = dict(cache.get("evidence_keys", {})) if incremental else {}
    evidence_reads = 0
    if evidence and calls:
        from motoro.runner import get_run, get_run_steps

        for call in calls:
            if not call.get("run_id"):
                continue
            evidence_key = encoded({key: call.get(key) for key in ("status", "step_evidence", "output")})
            if incremental and evidence_keys.get(call["run_id"]) == evidence_key:
                records.append((call, {}))
                continue
            if call.get("execution_adapter") == "proposal_text":
                records.append((call, proposal_evidence(root, config, call)))
                evidence_keys[call["run_id"]] = evidence_key
                continue
            run_id = uuid.UUID(call["run_id"])
            run = await get_run(run_id)
            if run is None:
                raise ValueError("Agent execution evidence is missing from Motoro")
            steps = await get_run_steps(run_id)
            evidence_reads += 1
            records.append((call, {"run": core_record(run), "steps": [core_record(s) for s in steps]}))
            if call.get("status") in ("completed", "failed", "cancelled"):
                evidence_keys[call["run_id"]] = evidence_key
    else:
        records = [(c, {}) for c in calls if c.get("run_id")]
    metrics.update(calls_loaded=len(calls), motoro_calls=evidence_reads,
                   cost_receipts_read=len(costs), evidence_seconds=time.monotonic() - started)
    db_started = time.monotonic()
    conn = await asyncpg.connect(dsn(), timeout=10, command_timeout=30)
    try:
        await initialize(conn)
        async with conn.transaction():
            # Same-run mirrors must acquire locks in one order, including first INSERT.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", "memstara.registry.run:" + tag)
            # Batch definitions must be explicitly registered before binding a run.
            if binding:
                exists = await conn.fetchval(
                    "SELECT 1 FROM memstara_experiment_combinations WHERE experiment_id=$1 AND id=$2",
                    experiment,
                    combination,
                )
                if not exists:
                    raise ValueError("Experiment binding references an unregistered combination")
            else:
                await register_experiment(
                    conn,
                    experiment,
                    {"kind": "standalone", "planned_runs": 1},
                    {combination: {"configuration": config}},
                )
            existing = await conn.fetchrow(
                "SELECT configuration,experiment_id,combination_id "
                "FROM memstara_executions WHERE run_tag=$1 FOR UPDATE",
                tag,
            )
            if existing and (
                json.loads(existing["configuration"]) != config
                or (existing["experiment_id"], existing["combination_id"]) != (experiment, combination)
            ):
                raise ValueError("Frozen execution configuration or identity changed")
            report = (root / "report.md").read_text() if (root / "report.md").exists() else None
            await conn.execute(
                """INSERT INTO memstara_executions
                (run_tag,experiment_id,combination_id,pipeline_id,run_directory,status,configuration,prompts,report,outcome)
                VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10::jsonb)
                ON CONFLICT(run_tag) DO UPDATE SET status=EXCLUDED.status,prompts=EXCLUDED.prompts,
                report=EXCLUDED.report,outcome=EXCLUDED.outcome,synced_at=now()""",
                tag,
                experiment,
                combination,
                config.get("pipeline_id"),
                str(root),
                outcome["status"],
                encoded(config),
                encoded(read(root / "prompts.json", config.get("prompts", {}))),
                report,
                encoded(outcome),
            )
            for call, detail in records:
                await conn.execute(
                    """INSERT INTO memstara_execution_agents VALUES($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb)
                    ON CONFLICT(run_tag,agent_run_id) DO UPDATE SET started_at=EXCLUDED.started_at,
                    duration_seconds=EXCLUDED.duration_seconds,metadata=EXCLUDED.metadata,
                    evidence=CASE WHEN EXCLUDED.evidence='{}'::jsonb THEN memstara_execution_agents.evidence
                    ELSE EXCLUDED.evidence END""",
                    tag,
                    uuid.UUID(call["run_id"]),
                    call["stage"],
                    call.get("started_at"),
                    call.get("duration_seconds"),
                    encoded(call),
                    encoded(detail),
                )
            if costs:
                await conn.executemany(
                    "INSERT INTO memstara_execution_costs VALUES($1,$2,$3::jsonb) ON CONFLICT DO NOTHING",
                    [(tag, receipt["id"], encoded(receipt)) for receipt in costs],
                )
                saved_rows = await conn.fetch(
                    "SELECT id,receipt FROM memstara_execution_costs WHERE run_tag=$1 AND id=ANY($2::text[])",
                    tag, [receipt["id"] for receipt in costs],
                )
                saved = {row["id"]: json.loads(row["receipt"]) for row in saved_rows}
                if any(saved.get(receipt["id"]) != receipt for receipt in costs):
                    raise ValueError("Recorded cost receipt changed")
            loops = {c.get("loop") for c in (delta or [])}
            if incremental:
                loops.update(cache.get("loops", []))
            loops = sorted(n for n in loops if type(n) is int and n > 0)
            board_query = "SELECT subset_path,evaluation FROM memstara_blackboard WHERE run_tag=$1"
            board_args = [tag]
            if incremental and loops:
                board_query += " AND trial=ANY($2::int[])"
                board_args.append([n - 1 for n in loops])
            board = [
                dict(r)
                for r in await conn.fetch(board_query, *board_args)
            ]
            for row in board:
                if isinstance(row["evaluation"], str):
                    row["evaluation"] = json.loads(row["evaluation"])
            from memstara.paths import DEFAULT_OUTPUT_DIR

            metrics["database_before_artifacts_seconds"] = time.monotonic() - db_started
            artifact_started = time.monotonic()
            fingerprints = dict(cache["artifacts"]) if incremental else {}
            candidates = None
            if incremental:
                # Growing journals are independently persisted and verified by
                # full final/manual reconciliation, not rehashed on every call.
                deferred = {"calls_checkpoint.json", "runs.json", "factors.json", "control.log",
                            "run.jsonl", "registry_metrics.jsonl", "registry_status.json"}
                candidates = {p for p in observed if p.name not in deferred and p.suffix != ".jsonl"}
                candidates.update(root / name for name in (
                    "config.json", "execution.json", "progress.json", "report.md", "pipeline_status.json"))
                for call in delta:
                    if call.get("step_evidence", {}).get("path"):
                        candidates.add(root / call["step_evidence"]["path"])
            indexed = await asyncio.to_thread(
                artifacts, root, board, Path(DEFAULT_OUTPUT_DIR), candidates=candidates,
                fingerprints=fingerprints, metrics=metrics,
            )
            metrics.update(artifact_seconds=time.monotonic() - artifact_started, artifacts_written=len(indexed),
                           board_rows=len(board))
            await conn.executemany(
                "INSERT INTO memstara_execution_artifacts VALUES($1,$2,$3,$4,$5) "
                "ON CONFLICT(run_tag,path) DO UPDATE SET sha256=EXCLUDED.sha256,bytes=EXCLUDED.bytes",
                [(tag, *a) for a in indexed],
            )
    finally:
        await conn.close()
    acknowledge(root, observed)
    metrics["total_seconds"] = time.monotonic() - started
    record_metrics(root, metrics)
    (root / "registry_status.json").write_text(
        encoded(
            {
                "status": "synced",
                "run_tag": tag,
                "experiment_id": experiment,
                "combination_id": combination,
                "calls": len(call_hashes),
                "cost_records": len(cost_ids),
                "sync_mode": metrics["mode"],
                "artifact_scope": "changed_files_and_recent_tasks" if incremental else "full_execution",
            }
        )
    )
    return {"call_hashes": call_hashes, "cost_cursor": cursor, "cost_ids": cost_ids,
            "artifacts": fingerprints, "evidence_keys": evidence_keys,
            "loops": [c.get("loop") for c in (delta or [])]}


async def reconcile(root):
    """A failed mirror is visible and recoverable; never overwrite a scientific result."""
    try:
        await sync(root)
    except Exception as exc:
        (root / "registry_status.json").write_text(encoded({"status": "pending", "error_type": type(exc).__name__}))
        print(f"Experiment registry pending: {type(exc).__name__}; reconcile before the next execution.")
        return False
    return True


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-dir", type=Path)
    group.add_argument("--register", type=Path, help="JSON with id, definition and combinations keyed by C01 etc.")
    args = parser.parse_args()
    from memstara.env import load_env

    load_env()
    from memstara.config import Settings
    from motoro import configure

    configure(Settings())
    if args.register:
        plan = read(args.register, {})
        if not plan.get("id") or not isinstance(plan.get("combinations"), dict) or not plan["combinations"]:
            raise ValueError("Experiment requires an ID and named combinations")
        if plan["definition"].get("planned_runs") != len(plan["combinations"]):
            raise ValueError("planned_runs must equal the number of declared combinations")
        conn = await asyncpg.connect(dsn(), timeout=10, command_timeout=30)
        try:
            await initialize(conn)
            async with conn.transaction():
                await register_experiment(conn, plan["id"], plan["definition"], plan["combinations"])
        finally:
            await conn.close()
        print(encoded({"registered": plan["id"], "combinations": len(plan["combinations"])}))
        return
    if not await reconcile(args.run_dir):
        raise SystemExit(1)
    print((args.run_dir / "registry_status.json").read_text())


if __name__ == "__main__":
    asyncio.run(main())
