"""Resolve an experiment's history by saved identity, never by display name.

The durable plan survives a partial cross-database clear. Shared definitions,
question memory, agent calls and generated artifacts remain owned by survivors.
"""

import json
import os
from pathlib import Path
from uuid import UUID

from memstara.control.recovery import records


def validate_paths(root, paths):
    root = Path(root).resolve()
    for path in paths:
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise RuntimeError("Experiment cleanup path escapes the output directory")
        relative = path.relative_to(root)
        parts = relative.parts
        allowed = (
            len(parts) >= 2 and parts[0] == "runs" and parts[1] not in ("pipeline_workspace.json", "history_epoch.json")
        )
        allowed |= (
            len(parts) >= 5
            and parts[:2] == ("research_inputs", "prepared")
            and parts[3] == "derived"
            and path.is_file()
            and path.name not in ("matcher_catalog.json", ".paired-ml.lock")
        )
        if not allowed:
            raise RuntimeError("Unrecognized experiment cleanup path; nothing deleted")
        for parent in path.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise RuntimeError("Experiment cleanup path traverses a symlink")


def local_scope(root, pipeline_id):
    tags, paths, calls = set(), set(), set()
    for record_path, record in records(Path(root) / "runs"):
        if record.get("pipeline_id") != pipeline_id:
            continue
        tag = record.get("run_tag")
        if not isinstance(tag, str) or not tag:
            raise ValueError("Selected experiment has an invalid execution identity")
        tags.add(tag)
        directory = record_path.parent
        paths.add(str(directory))
        manifest = directory / "execution.json"
        if manifest.exists():
            for call in json.loads(manifest.read_text()).get("calls", []):
                if call.get("run_id"):
                    calls.add(str(UUID(call["run_id"])))
    validate_paths(root, map(Path, paths))
    return tags, paths, calls


async def plan(root, pipeline_id):
    import asyncpg

    root = Path(root).resolve()
    tags, paths, calls = local_scope(root, pipeline_id)
    other_calls: set[str] = set()
    other_directories = []
    for record_path, record in records(root / "runs"):
        if record.get("pipeline_id") == pipeline_id:
            continue
        other_directories.append(record_path.parent)
        manifest = record_path.parent / "execution.json"
        if manifest.exists():
            other_calls.update(
                str(UUID(c["run_id"])) for c in json.loads(manifest.read_text()).get("calls", []) if c.get("run_id")
            )
    connection = await asyncpg.connect(
        os.environ["MEMSTARA_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1), timeout=15
    )
    try:
        executions = await connection.fetch(
            "SELECT run_tag, experiment_id, run_directory FROM memstara_executions WHERE pipeline_id=$1", pipeline_id
        )
        for row in executions:
            tags.add(row["run_tag"])
            directory = Path(row["run_directory"])
            if directory.exists():
                paths.add(str(directory))
        tags = sorted(tags)
        # An inconsistent owner must never authorize deletion of another experiment.
        if await connection.fetchval(
            "SELECT count(*) FROM memstara_executions WHERE run_tag=ANY($1::text[]) "
            "AND pipeline_id IS DISTINCT FROM $2",
            tags,
            pipeline_id,
        ):
            raise RuntimeError("Execution ownership disagrees between files and the registry")
        calls.update(
            str(row["agent_run_id"])
            for row in await connection.fetch(
                "SELECT agent_run_id FROM memstara_execution_agents WHERE run_tag=ANY($1::text[]) "
                "AND agent_run_id IS NOT NULL",
                tags,
            )
        )
        # Only explicitly indexed, exclusively owned generated files can be removed.
        artifacts = await connection.fetch(
            """SELECT DISTINCT path FROM memstara_execution_artifacts a
            WHERE run_tag=ANY($1::text[]) AND NOT EXISTS (
              SELECT 1 FROM memstara_execution_artifacts other WHERE other.path=a.path
              AND NOT (other.run_tag=ANY($1::text[])))""",
            tags,
        )
        directories = [Path(p) for p in paths]
        for row in artifacts:
            path = Path(row["path"])
            if not path.exists() or any(path.is_relative_to(p) for p in directories):
                continue
            # Input/settings and shared preparation caches are never export-history targets.
            if not path.is_relative_to(root / "research_inputs" / "prepared"):
                continue
            if "derived" not in path.relative_to(root).parts or path.name in (
                "matcher_catalog.json",
                ".paired-ml.lock",
            ):
                continue
            validate_paths(root, [path])
            paths.add(str(path))
        validate_paths(root, map(Path, paths))
        if any(
            other.is_relative_to(Path(p)) or Path(p).is_relative_to(other) for p in paths for other in other_directories
        ):
            raise RuntimeError("Execution directories overlap another experiment; nothing deleted")
        return {
            "pipeline_id": pipeline_id,
            "run_tags": tags,
            "paths": sorted(paths),
            "runtime_run_ids": sorted(calls - other_calls),
            "shared_runtime_run_ids": sorted(other_calls),
            "experiment_ids": sorted({row["experiment_id"] for row in executions}),
        }
    finally:
        await connection.close()


def board_predicates(scope):
    tags = scope["run_tags"]
    result = {
        table: ("run_tag=ANY($1::text[])", [tags])
        for table in (
            "memstara_execution_artifacts",
            "memstara_execution_costs",
            "memstara_execution_agents",
            "memstara_executions",
            "memstara_results",
            "memstara_blackboard",
        )
    }
    result["memstara_questions"] = (
        """origin_run=ANY($1::text[])
        AND (claimed_run='' OR claimed_run=ANY($1::text[]))
        AND NOT EXISTS (SELECT 1 FROM memstara_blackboard b WHERE b.question_id=memstara_questions.question_id
                        AND NOT (b.run_tag=ANY($1::text[])))
        AND NOT EXISTS (SELECT 1 FROM memstara_results r WHERE r.question_id=memstara_questions.question_id
                        AND NOT (r.run_tag=ANY($1::text[])))""",
        [tags],
    )
    result["memstara_experiment_combinations"] = (
        """experiment_id=ANY($1::text[])
        AND NOT EXISTS (SELECT 1 FROM memstara_executions e
          WHERE e.experiment_id=memstara_experiment_combinations.experiment_id
          AND e.combination_id=memstara_experiment_combinations.id)""",
        [scope["experiment_ids"]],
    )
    result["memstara_experiments"] = (
        """id=ANY($1::text[]) AND NOT EXISTS (
        SELECT 1 FROM memstara_experiment_combinations c WHERE c.experiment_id=memstara_experiments.id)""",
        [scope["experiment_ids"]],
    )
    return result
