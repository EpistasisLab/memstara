"""Recover a saved question that cannot produce a task, within the same trial."""

import json
from pathlib import Path

from memstara.pipeline.checkpoint import atomic_json
from memstara.pipeline.recovery import ensure_artifact


async def seed(question, *, root, identity, present, answer, regenerate, wait=None, attempts=3):
    path = Path(root) / "question_mapping_recovery" / f"trial-{identity['trial']}.json"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = (
        json.loads(path.read_text())
        if path.exists()
        else {
            "identity": identity,
            "question": question,
            "rejected_ids": [],
            "attempt": 0,
        }
    )
    if state.get("identity") != identity:
        raise ValueError("Question mapping recovery belongs to another execution")
    while True:
        if wait:
            await wait()
        # A restart or timeout after create_task must never generate duplicate work.
        if await present():
            atomic_json(path, {**state, "status": "ready"})
            return state["question"] or state["last_question"]
        if state["attempt"] >= attempts:
            atomic_json(path, {**state, "status": "needs_review"})
            from memstara.pipeline.failures import stop_execution

            stop_execution(
                root,
                "hypothesis",
                identity["wave"] + 1,
                RuntimeError("No executable mapping"),
                code="question_mapping_exhausted",
                message="No task was saved after question mapping and regeneration attempts. "
                "Review question_mapping_recovery before retrying. This trial was not skipped; "
                "Explanation was not started.",
            )
        if state["question"] is None:
            candidate = await regenerate(state["rejected_ids"], state.get("reason", ""))
            if candidate is None:
                state["attempt"] += 1
                atomic_json(path, {**state, "status": "no_replacement"})
                continue
            if candidate.get("question_id") in state["rejected_ids"]:
                raise ValueError("Question regeneration returned a rejected question")
            state["question"] = candidate
        # Persist the attempt and replacement before invoking paid agent work.
        state["attempt"] += 1
        atomic_json(path, {**state, "status": "mapping"})
        response = ""

        async def invoke(attempt):
            nonlocal response
            response = await answer(state["question"], attempt)

        ok, reason = await ensure_artifact(invoke, present)
        if ok:
            atomic_json(path, {**state, "status": "ready"})
            return state["question"]
        state["rejected_ids"].append(state["question"]["question_id"])
        state["reason"] = {"question": state["question"], "failure": reason, "agent_response": str(response)[-6000:]}
        state["last_question"] = state["question"]
        state["question"] = None
        atomic_json(path, {**state, "status": "regenerating"})


def require_analysis(tasks, expected_trials, root, loop):
    """A report is never the recovery path for missing or failed analysis."""
    expected = set(expected_trials)
    relevant = [t for t in tasks if t.get("trial") in expected]
    if (
        expected
        and len(relevant) == len(expected)
        and {t["trial"] for t in relevant} == expected
        and all(t.get("status") == "done" for t in relevant)
    ):
        return
    from memstara.pipeline.failures import stop_execution

    stop_execution(
        root,
        "interpret",
        loop,
        RuntimeError("Incomplete analysis"),
        code="analysis_required_before_report",
        message="This condition has missing or incomplete analysis tasks. "
        "Explanation was not started. Review mapping and analysis records before retrying.",
    )
