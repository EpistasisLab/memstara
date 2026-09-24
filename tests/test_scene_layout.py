"""The floor plan has to hold the figures the scene is allowed to draw.

`stores.SPLITTABLE` names the stations that show one figure per worker. That set and
`stores.HOME` are declared in different places and neither knows about the other, so
adding a station to one or moving a station in the other can produce a floor plan that
cannot hold what the scene will put on it — and it fails by drawing, not by raising.

The geometry is not in Python. Figures are positioned in
`viewer/web/src/panels/ScenePanel.tsx:76`, and the three numbers below are copied from
there by hand. That copy is the weakness of this file and it is the deliberate one: the
alternative is parsing TSX from a Python test, and a test that reads the implementation
to find out what the rule is agrees with the implementation about everything, including
what it has wrong. If ScenePanel's step changes, this file has to be edited, and a
`Verified:` line is what says someone did.

The viewer is not a package, so `viewer/api` goes on the import path the way
`tests/test_trace_groups.py` does it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viewer" / "api"))

import stores  # noqa: E402

FIGURE_WIDTH = 128
SLOT_STEP_X = 0  # Vertical stacks keep every slot in the same column.
CEILING = 4  # slots 0..3; see `_MAX_HYPOTHESIS_AGENTS` in src/memstara/control/request.py


def _span(station: str, slots: int) -> tuple[int, int]:
    """Left and right edge of a stack of `slots` figures resting at `station`."""
    left = stores.HOME[station]["x"] - FIGURE_WIDTH // 2
    return (left, left + (slots - 1) * SLOT_STEP_X + FIGURE_WIDTH)


def test_every_splittable_station_is_a_station():
    """The same thing `viewer/check_definitions.py` checks, kept here too because that
    script is run by hand and this file is run by CI. A name in `SPLITTABLE` that is not
    in `HOME` folds the stage it was meant to split, silently."""
    assert stores.SPLITTABLE <= set(stores.HOME)


def test_a_full_stack_does_not_reach_the_next_station():
    """Verify that a full stack does not reach the next station."""
    ordered = sorted(stores.HOME, key=lambda s: stores.HOME[s]["x"])
    for station, neighbour in zip(ordered, ordered[1:], strict=False):
        if station not in stores.SPLITTABLE:
            continue
        _, right = _span(station, CEILING)
        left, _ = _span(neighbour, 1)
        assert right < left, (
            f"a full {station} stack ends at x={right} and {neighbour} starts at x={left}"
        )


def test_every_station_has_the_same_room_whether_it_uses_it_or_not():
    """Verify that every station has the same room whether it uses it or not."""
    ordered = sorted(stores.HOME, key=lambda s: stores.HOME[s]["x"])
    for station, neighbour in zip(ordered, ordered[1:], strict=False):
        _, right = _span(station, CEILING)
        left, _ = _span(neighbour, 1)
        assert right < left, f"{station} could not hold {CEILING} figures before {neighbour}"


def test_hypothesis_and_interpreter_stations_are_drawn_per_worker():
    """The design's own shape, and the half of it that is easy to lose while implementing"""
    # Extended multi-agent scope: independently configured interpreters are visible,
    # while replicated data/ML workers remain one role on screen.
    assert stores.SPLITTABLE == frozenset({"hypothesis", "interpreter"})


def test_floor_plan_uses_vertical_slots_for_both_parallel_stages():
    source = (Path(__file__).resolve().parents[1] / "viewer/web/src/panels/ScenePanel.tsx").read_text()
    assert "x: 24 + column * 208" in source
    assert "(row + (rows - count) / 2) * 116" in source
    assert "Math.max(form.hypothesis_agents, form.interpret_agents)" in source
