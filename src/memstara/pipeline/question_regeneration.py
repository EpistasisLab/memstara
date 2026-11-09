"""Regenerate questions in the same Loop until a verified question is saved."""

import asyncio
import hashlib
import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from memstara.pipeline.checkpoint import atomic_json

VERSION = "regenerate_until_saved_v1"
FEEDBACK_VERSION = "verified_repair_only_v2"
_context: ContextVar[dict | None] = ContextVar("question_regeneration", default=None)

# Rotate the diagnostic task, not the target, data or scientific validation rules.
REPAIR_FOCUS = (
    "Reassess actual predictor definitions and recorded timing; a clinical topic alone does not establish leakage.",
    "Try a materially different candidate using the permitted knowledge and available measurements, "
    "not a reworded refusal.",
    "Separate the permitted evidence, the proposed inference and the exact measurement; "
    "explain rather than invent their connection.",
    "Check concrete validator feedback and the complete allowed predictor catalog "
    "before concluding that no candidate is feasible.",
)


def writer_feedback(writer):
    context = _context.get()
    if context is None:
        return ""
    path = context["folder"] / (hashlib.sha256(writer.encode()).hexdigest() + ".json")
    previous = {}
    if path.exists():
        previous = json.loads(path.read_text())
        if previous.get("identity") != context["identity"]:
            raise ValueError("Question generation feedback belongs to another execution")
    response = previous.get("response", "")
    # Preserve the response in its audit file, but never recycle a model's own
    # unvalidated refusal as the next request's evidence. Actual tool rejections
    # remain available through question_repair.retry_instructions.
    receipt = {
        "policy": FEEDBACK_VERSION,
        "previous_attempt": previous.get("attempt"),
        "previous_response_sha256": hashlib.sha256(response.encode()).hexdigest() if response else None,
    }
    return (
        f"\nQUESTION REGENERATION ROUND {context['attempt']} in this SAME Loop. "
        "Do not advance to another Loop or report an empty proposal as success. "
        "Use the current rejection feedback and try a different supported hypothesis or search strategy "
        "within this skill and the fixed study contract. Preserve the target and source restrictions. "
        "Do not invent measurements, evidence or citations, or use prior model performance. "
        "A previous writer's refusal is an unverified model judgment, not a validator decision or "
        "a corpus fact. Its narrative is deliberately not repeated. Use actual tool rejection codes "
        "and newly checked permitted evidence. Diagnostic focus for this round: "
        + REPAIR_FOCUS[(context["attempt"] - 1) % len(REPAIR_FOCUS)]
        + " If no candidate is defensible, record the specific obstacle honestly; never invent one "
        "just to finish. Audit receipt (not scientific evidence): " + json.dumps(receipt)
    )


def remember_writer(writer, response):
    context = _context.get()
    if context is None:
        return
    if not isinstance(response, str):
        raise ValueError("Question writer response must be text")
    path = context["folder"] / (hashlib.sha256(writer.encode()).hexdigest() + ".json")
    atomic_json(
        path,
        {
            "identity": context["identity"],
            "attempt": context["attempt"],
            "feedback_policy": FEEDBACK_VERSION,
            "response": response[-6000:],
        },
    )


def verify_feedback(root, identity):
    """An unavailable DB/matcher is not evidence that another question is needed."""
    for path in root.glob(f"question_repair_{identity['wave']}_*.json"):
        value = json.loads(path.read_text())
        if any(value.get(k) != identity[k] for k in ("run_tag", "config_hash")):
            raise ValueError("Question feedback belongs to another execution")
        response = value.get("response", {})
        if response.get("error") or any(
            item.get("code") == "mapping_preflight_unavailable" for item in response.get("rejected", [])
        ):
            raise RuntimeError("Question generation infrastructure is unavailable; this Loop was not skipped")


async def retry_delay(attempt):
    await asyncio.sleep(min(attempt, 5))


async def until_saved(operation, *, root, wave, run_tag, config_hash, wait=None):
    """Keep the question checkpoint active; never advance the schedule on an empty bank."""
    from memstara.pipeline.exploration import record_round, write_progress

    root = Path(root)
    folder = root / "question_regeneration" / f"loop-{wave + 1}"
    folder.mkdir(parents=True, exist_ok=True)
    identity = {"version": VERSION, "run_tag": run_tag, "config_hash": config_hash, "wave": wave}
    state_path = folder / "state.json"
    state: dict[str, Any] = (
        json.loads(state_path.read_text()) if state_path.exists() else {"identity": identity, "attempt": 1}
    )
    if state.get("identity") != identity or type(state.get("attempt")) is not int or state["attempt"] < 1:
        raise ValueError("Question regeneration state does not match this execution")
    while True:
        if wait is not None:
            await wait()
        attempt = state["attempt"]
        atomic_json(state_path, {**state, "status": "generating"})
        record_round(root, wave + 1, "running", f"Generating a verified question; regeneration round {attempt}.")
        write_progress(root, wave + 1, "hypothesis")
        token = _context.set({"folder": folder, "identity": identity, "attempt": attempt})
        try:
            questions, _ = await operation()
        finally:
            _context.reset(token)
        if questions:
            atomic_json(state_path, {**state, "status": "ready"})
            return questions, False
        verify_feedback(root, identity)
        # Durable distinct attempt identity prevents reusing a completed empty
        # writer response from the pause/recovery cache as a new model request.
        atomic_json(folder / f"attempt-{attempt}.json", {**state, "status": "empty"})
        state = {"identity": identity, "attempt": attempt + 1}
        atomic_json(state_path, {**state, "status": "waiting"})
        record_round(
            root, wave + 1, "running", f"No valid question saved; regenerating in this Loop (round {attempt + 1})."
        )
        write_progress(root, wave + 1, "hypothesis")
        await retry_delay(attempt)
