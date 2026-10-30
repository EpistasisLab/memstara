"""Per-execution Explanation narrative length; never edits contributed skills."""

import math
import re

DEFAULT_WORDS = 250
MAX_WORDS = 10000


def assessment(text, words):
    """Count narrative words, excluding fenced records and link destinations."""
    if words is None:
        return None
    words = validate(words)
    narrative = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    narrative = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", narrative)
    count = len(re.findall(r"\b\w+(?:['’\-]\w+)*\b", narrative))
    lower, upper = max(1, math.floor(words * 0.8)), math.ceil(words * 1.2)
    return {
        "target_words": words,
        "actual_words": count,
        "minimum_words": lower,
        "maximum_words": upper,
        "within_range": lower <= count <= upper,
    }


def correction(audit):
    return (
        f"The previous narrative contained {audit['actual_words']} words. Revise it to "
        f"approximately {audit['target_words']} words "
        f"({audit['minimum_words']}–{audit['maximum_words']} words). "
        "Preserve the supplied findings, uncertainty, limitations and evidence references. "
        "Do not invent facts or cut sentences. Return the complete revised output "
        "in the originally required format."
    )


async def refine(text, entry, words, invoke):
    """Bounded read-only revisions; every call remains visible to the normal recorder."""
    audit = assessment(text, words)
    if audit is None:
        return text, entry
    attempts = [dict(audit, run_id=entry.get("run_id"))]
    for _ in range(2):
        if audit["within_range"]:
            break
        revised, revised_entry = await invoke(text, correction(audit))
        if revised_entry.get("status") != "completed" or not revised.strip():
            attempts.append({"status": "revision_unavailable", "run_id": revised_entry.get("run_id")})
            break
        text, entry = revised, revised_entry
        audit = assessment(text, words)
        attempts.append(dict(audit, run_id=entry.get("run_id")))
    return text, {**entry, "explanation_length": {**audit, "attempts": attempts}}


def validate(value):
    if type(value) is not int or not 1 <= value <= MAX_WORDS:
        raise ValueError("Explanation report length must be a whole number from 1 to 10000 words")
    return value


def frozen_words(args, previous=None):
    # Old checkpoints retain their original unrestricted prompt.
    if previous is not None:
        value = previous.get("explanation_words")
        return None if value is None else validate(value)
    return validate(getattr(args, "explanation_words", DEFAULT_WORDS))


def instruction(words):
    if words is None:
        return ""
    words = validate(words)
    return (
        f"\n\nExplanation report length: aim for approximately {words} words in the "
        "final human-readable Explanation narrative for this execution. This is a "
        "writing target, not an exact-count requirement. Prioritize the main findings, "
        "uncertainty and limitations. Preserve required tool calls, structured records "
        "and evidence references; this target does not limit their size. "
        "Do not truncate sentences to meet the target.\n"
    )
