"""Several LLM calls must not become several configured hypothesis agents."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewer" / "api"))
import scene  # noqa: E402


def test_skill_identity_survives_adding_a_second_agent():
    from memstara.pipeline.core import hypothesis_agent_names

    one = hypothesis_agent_names(["treatment-toxicity"])
    two = hypothesis_agent_names(["treatment-toxicity", "drug-class-effect"])
    assert one[0] == two[0] == "memstara-board-hypothesis-treatment-toxicity"
    assert hypothesis_agent_names([]) == ["memstara-board-hypothesis"]


def test_new_calls_do_not_inherit_previous_pipeline_roster_before_first_tool():
    now = datetime.now(UTC)
    old = [dict(name="memstara-board-hypothesis", run_id=f"old{i}", worker=f"hypothesis#{i}",
                started_at=now - timedelta(minutes=5)) for i in range(3)]
    current = [dict(name=f"memstara-board-hypothesis-{book}", run_id=book, created_at=now)
               for book in ("treatment-toxicity", "drug-class-effect")]
    core = dict(open=current, last_call=[], touches=[], roster=old, recent=[], totals=[])
    hypotheses = [a for a in scene._build_scene(core, True)["agents"] if a["stage"] == "hypothesis"]
    assert len(hypotheses) == 2
    assert all(a["state"] == "working" for a in hypotheses)


def test_repeated_calls_keep_two_skilled_agents_and_correct_flash():
    now = datetime.now(UTC)
    core = {key: [] for key in ("open", "last_call", "touches", "roster", "recent", "totals")}
    for i, book in enumerate(("treatment-toxicity", "drug-class-effect")):
        for phase in range(2):
            row = dict(name=f"memstara-board-hypothesis-{book}", run_id=f"{i}-{phase}",
                       worker=f"hypothesis#{i + phase * 2}", started_at=now + timedelta(seconds=phase))
            core["roster"].append(row)
            core["last_call"].append({**row, "server": "board", "tool": "claim_question"})
            if phase == 1:
                core["open"].append({**row, "created_at": row["started_at"]})
        core["recent"].append({**core["last_call"][-2], "tool": "claim_question"})
    result = scene._build_scene(core, True)
    hypotheses = [a for a in result["agents"] if a["stage"] == "hypothesis"]
    assert len(hypotheses) == 2
    assert all(a["state"] == "working" for a in hypotheses)
    assert {a["playbook"] for a in hypotheses} == {"treatment-toxicity", "drug-class-effect"}
    assert len({f["agent"] for f in result["flashes"]}) == 2


def test_recent_history_does_not_resurrect_workers_outside_latest_roster():
    now = datetime.now(UTC)
    old = dict(name="memstara-board-hypothesis", run_id="old", worker="hypothesis#9",
               started_at=now, task_id=None, tool="claim_question")
    current = dict(name="memstara-board-hypothesis-treatment-toxicity", run_id="current",
                   worker="hypothesis", started_at=now)
    core = dict(open=[], last_call=[], touches=[old], roster=[current], recent=[], totals=[])
    result = scene._build_scene(core, True)
    hypotheses = [a for a in result["agents"] if a["stage"] == "hypothesis"]
    assert len(hypotheses) == 1
    assert hypotheses[0]["playbook"] == "treatment-toxicity"


def test_rejected_ml_submission_keeps_task_in_scene():
    claim = dict(name="memstara-board-ml", run_id="ml-call", task_id=12, tool="claim_task")
    rejected = {**claim, "tool": "submit_result", "succeeded": False}
    assert scene._carrying([claim, rejected]) == {"ml-call": 12}
    assert scene._carrying([claim, {**rejected, "succeeded": True}]) == {}
