"""Public agent names, independent of durable stage IDs and artifact filenames.

The report ID remains compatible with saved runs and Motoro agent identities.
Its public name is Explanation Agent; Interpreter remains a separate role.
"""

AGENT_LABELS = {
    "hypothesis": "Hypothesis Agent",
    "data": "Data Agent",
    "ml": "ML Agent",
    "interpreter": "Interpreter Agent",
    "report": "Explanation Agent",
}


def agent_label(stage: str) -> str:
    return AGENT_LABELS.get(stage, "Explanation Agent" if stage == "explanation" else stage)
