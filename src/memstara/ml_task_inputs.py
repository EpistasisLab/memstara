"""Bind ML tools to a claimed board task; never infer a filename from similar paths."""

import json
from pathlib import Path


INSTRUCTIONS = (
    "ML task input binding: call get_ml_configuration and train_and_score with the task_id "
    "from claim_task and your assigned worker name. Omit path and y_column; the server "
    "retrieves them from that task. Omit subset_path in submit_result. This supersedes "
    "older instructions to copy a filename. If ml_task_id_required is returned, add the "
    "claimed task_id and worker; do not repeat a path-only call or report it as a training failure."
)


class MLInputError(ValueError):
    def __init__(self, code, message, hint):
        super().__init__(message)
        self.code = code
        self.hint = hint

    def response(self):
        return {"error": str(self), "code": self.code, "hint": self.hint}


async def read_task(task_id, run_tag):
    import asyncpg
    from memstara.blackboard import dsn

    connection = await asyncpg.connect(dsn(), timeout=10, command_timeout=10)
    try:
        # Both predicates are required: an ID from another run must not disclose
        # that run's private paths, target or evaluation metadata.
        row = await connection.fetchrow(
            "SELECT task_id, run_tag, trial, task_type, status, claimed_by, "
            "subset_path, y_column, evaluation FROM memstara_blackboard "
            "WHERE task_id=$1 AND run_tag=$2", task_id, run_tag,
        )
        return dict(row) if row else None
    finally:
        await connection.close()


async def resolve(path, y_column, task_id, worker, snapshot, root):
    """Keep standalone path callers, but require task identity in UI pipelines.

    A task-bound request ignores legacy path/target strings: the database owns
    both. This also lets an older frozen prompt recover by adding task_id and
    worker without retyping a long filename correctly.
    """
    scoped = bool((snapshot or {}).get("pipeline_id"))
    if task_id is None:
        if scoped:
            raise MLInputError(
                "ml_task_id_required", "ML pipeline tools require the claimed task_id and worker.",
                "Use task_id from claim_task and the same worker. Omit path and y_column; "
                "the server reads them from the task. No training was started.",
            )
        if not path or not y_column:
            raise MLInputError("ml_input_required", "Standalone ML requires path and y_column.",
                               "Supply both fields, or use a claimed task_id in a scoped run.")
        return str(path), y_column
    tag = (snapshot or {}).get("run_tag")
    if type(task_id) is not int or task_id <= 0 or not tag or not worker:
        raise MLInputError("ml_task_identity_invalid", "A run, positive task_id and worker are required.",
                           "Use the exact identity of the ML task you claimed; do not guess an ID.")
    task = await read_task(task_id, tag)
    if task is None:
        raise MLInputError("ml_task_not_found", "Task was not found in this pipeline run.",
                           "Use task_id from this run's claim_task receipt.")
    if (task["task_type"] != "ml" or task["status"] != "in_progress"
            or task["claimed_by"] != worker):
        raise MLInputError("ml_task_not_owned", "The worker does not hold this active ML task.",
                           "Only the worker holding an in_progress ML task may evaluate it.")
    metadata = task.get("evaluation") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    if (task["y_column"] != snapshot.get("y_column")
            or metadata.get("config_hash") != snapshot.get("config_hash")):
        raise MLInputError("ml_task_contract_mismatch", "Task target or configuration differs from this run.",
                           "Restore the matching run configuration; do not change the target or split.")
    if not task.get("subset_path"):
        raise MLInputError("ml_task_handoff_missing", "The claimed task has no saved data subset.",
                           "The Data stage must publish its verified handoff before ML can run.")
    subset = Path(task["subset_path"]).resolve()
    try:
        subset.relative_to(Path(root).resolve())
    except ValueError:
        raise MLInputError("ml_task_path_outside_root", "Recorded subset is outside the allowed directory.",
                           "Restore the run's output mount; do not substitute another dataset.") from None
    if not subset.is_file():
        raise MLInputError("ml_subset_missing", "The task's recorded CSV file is missing.",
                           "Restore the original artifact; changing the filename or seed is not recovery.")
    if snapshot.get("data_allocation_policy"):
        sidecar = subset.with_suffix(".comparison.json")
        if not sidecar.is_file():
            raise MLInputError("ml_handoff_missing", "The CSV exists but its Data allocation receipt is missing.",
                               "Restore the original verified handoff; do not invent a split.")
        handoff = json.loads(sidecar.read_text())
        allocation = handoff.get("data_allocation") or {}
        if (handoff.get("trial") != task["trial"]
                or allocation.get("task_id") != task_id
                or allocation.get("run_tag") != tag
                or allocation.get("trial") != task["trial"]
                or allocation != metadata.get("data_allocation")):
            raise MLInputError("ml_handoff_identity_mismatch", "Data receipt does not match the claimed task.",
                               "Restore the matching receipt; another task's data must not be used.")
    # load_effective still verifies hashes and reconstructs the accepted split.
    return str(subset), task["y_column"]
