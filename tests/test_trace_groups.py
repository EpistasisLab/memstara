"""`scene._trace_groups` — the matcher record, flattened for one result.

This is the whole of `/api/result/{id}`'s interpretation, and it is pure: a stored
`match_trace` and two column lists in, one list of concept groups out. So it is tested
here rather than against a database, and the fixtures below are the shapes the two
matcher tools actually return (`src/memstara/mcp_servers/matcher.py:145-152` and
`:172-176`) as they are filed by `src/memstara/pipeline/board.py:893-897`.

The viewer is not a package and is not on the import path, so `viewer/api` is put there
the same way `viewer/api/main.py:52` does it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewer" / "api"))

import scene  # noqa: E402


def call(tool: str, result: object) -> dict:
    """One entry of a stored trace. `arguments` is kept because the real rows carry it."""
    return {"tool": tool, "arguments": {"concepts": ["x"]}, "result": result}


def group(concept: str, *candidates: tuple[str, str, float], note: str = "") -> dict:
    g = {
        "concept": concept,
        "candidates": [
            {"feature_name": n, "feature_type": t, "similarity_score": s}
            for n, t, s in candidates
        ],
    }
    if note:
        g["note"] = note
    return g


def test_both_matcher_shapes_flatten_to_the_same_thing():
    """`match_concepts` wraps its groups in `{"results": [...]}` and `match_concept` does
    not. A screen must not have to know which tool the agent happened to use."""
    trace = [
        call("match_concepts", {"results": [group("a1c", ("HBA1C", "lab", 0.91))]}),
        call("match_concept", group("smoking", ("TOBACCO_USE", "diagnosis", 0.88))),
    ]
    out = scene._trace_groups(trace, [], [])
    assert [g["concept"] for g in out] == ["a1c", "smoking"]
    assert [g["candidates"][0]["column"] for g in out] == ["HBA1C", "TOBACCO_USE"]


def test_chosen_is_judged_against_what_was_asked_for_not_what_arrived():
    """The distinction the whole endpoint turns on. A column the agent picked and the
    cohort did not have is still a column the agent picked; marking it unchosen would
    report the data stage's gap as the hypothesis agent's mistake."""
    trace = [call("match_concepts", {"results": [group(
        "a1c",
        ("HBA1C", "lab", 0.91),        # asked for and present
        ("GLUCOSE_FASTING", "lab", 0.80),  # asked for, missing from the cohort
        ("GLUCOSE", "lab", 0.72),      # offered and not taken
    )]})]
    out = scene._trace_groups(trace, ["HBA1C", "GLUCOSE_FASTING"], ["HBA1C"])
    by_col = {c["column"]: c for c in out[0]["candidates"]}
    assert (by_col["HBA1C"]["chosen"], by_col["HBA1C"]["present"]) == (True, True)
    assert (by_col["GLUCOSE_FASTING"]["chosen"], by_col["GLUCOSE_FASTING"]["present"]) == (True, False)
    assert (by_col["GLUCOSE"]["chosen"], by_col["GLUCOSE"]["present"]) == (False, False)


def test_a_group_with_no_chosen_candidate_is_kept():
    """`harvest_match_trace` files the turn's whole matcher record on every task that
    turn created (`src/memstara/pipeline/board.py:913-921`), so one result's trace
    carries concepts that were matched for a sibling task. Dropping those would silently
    rewrite the record into something tidier than what happened."""
    trace = [call("match_concepts", {"results": [
        group("a1c", ("HBA1C", "lab", 0.91)),
        group("blood pressure", ("SYSTOLIC_BP", "lab", 0.93)),
    ]})]
    out = scene._trace_groups(trace, ["HBA1C"], ["HBA1C"])
    assert len(out) == 2
    assert not any(c["chosen"] for c in out[1]["candidates"])


def test_the_empty_group_keeps_its_note():
    """"nothing was close enough" and "a code this cohort does not carry" are different
    findings and only one of them is worth rewording for. Without the note an empty group
    is indistinguishable from a call that failed."""
    trace = [call("match_concepts", {"results": [
        group("phlogiston level", note="nothing was close enough"),
    ]})]
    out = scene._trace_groups(trace, [], [])
    assert out[0]["candidates"] == []
    assert out[0]["note"] == "nothing was close enough"


def test_two_calls_for_one_concept_are_two_answers():
    """Not deduplicated. The same concept asked twice with a different `top_k` gives two
    different candidate lists, and keeping one of them would be a claim about which."""
    trace = [
        call("match_concept", group("a1c", ("HBA1C", "lab", 0.91))),
        call("match_concept", group("a1c", ("HBA1C", "lab", 0.91), ("GLUCOSE", "lab", 0.72))),
    ]
    out = scene._trace_groups(trace, [], [])
    assert [len(g["candidates"]) for g in out] == [1, 2]


@pytest.mark.parametrize("trace", [
    None, "", [], "not json at all",
    ["a bare string where a call belongs"],
    [{"tool": "match_concepts", "result": "unparsed json string"}],
    [{"tool": "match_concepts", "result": {"results": [{"no": "concept key"}]}}],
])
def test_malformed_input_yields_no_groups_and_does_not_raise(trace):
    """One unreadable row must not take the endpoint down with it — the same rule
    `_jsonb` follows for every other JSON column (`viewer/api/scene.py:120-133`)."""
    assert scene._trace_groups(trace, [], []) == []


def test_a_broken_candidate_list_still_reports_the_concept():
    """The one malformed shape that is *not* dropped, and deliberately. The concept was
    asked about — that much of the row is readable — so the group is kept with nothing
    offered. Dropping it would say the matcher was never asked, which is the one thing
    the record does establish."""
    trace = [{"tool": "match_concepts",
              "result": {"results": [{"concept": "a1c", "candidates": "not a list"}]}}]
    out = scene._trace_groups(trace, [], [])
    assert [(g["concept"], g["candidates"]) for g in out] == [("a1c", [])]
