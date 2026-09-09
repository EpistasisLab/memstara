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

#  Copied from viewer/web/src/panels/ScenePanel.tsx:76 and the `w-32` on the agent node
#  (viewer/web/src/components/nodes.tsx:53). A figure is drawn from `home.x - 64`, which
#  is half its width, so it stands centred on its station.
FIGURE_WIDTH = 128
SLOT_STEP_X = 22
CEILING = 3  # slots 0..2; see `_MAX_HYPOTHESIS_AGENTS` in src/memstara/control/request.py


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


    Three figures span 172 and the stations sit 175 apart, so a full stack clears the
    next station's column by 3px. The stack grows up and to the right, so the neighbour
    that matters is the right-hand one, and only a splittable station can have a stack.
    """
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
    """Why A-33's deferred *layout* decision turned out not to be one.

    The item expected a second stacking station to need a new floor plan. It would not
    have: the row is evenly spaced, so the clearance is the same 3px at every station.
    A-33 was then settled the other way for a reason that has nothing to do with pixels
    — the design puts one interpreter on screen — but that is exactly why this test is
    kept. It is what says the next such question is a design question too, and what
    would stop being true if someone moved a station and made it a layout one again.
    """
    ordered = sorted(stores.HOME, key=lambda s: stores.HOME[s]["x"])
    for station, neighbour in zip(ordered, ordered[1:], strict=False):
        _, right = _span(station, CEILING)
        left, _ = _span(neighbour, 1)
        assert right < left, f"{station} could not hold {CEILING} figures before {neighbour}"


def test_only_the_hypothesis_station_is_drawn_per_worker():
    """The design's own shape, and the half of it that is easy to lose while implementing
    the other half.

    V1 is *hypothesis 1–2, and data · ML · interpreter · report one role each*; reading
    one hypothesis with several interpreters was considered and rejected for the volume of

    non-hypothesis roles still run N workers internally, and not showing that as a
    duplicated role is the decision, not an omission — so `--data-agents 2` must stay one
    character with a 2 on it.

    `interpreter` was in `SPLITTABLE` for part of 2026-09-08 on a misreading of that
    design. This test is written as an equality rather than as four `not in`s so that
    adding a station fails here and has to be argued for.
    """
    assert stores.SPLITTABLE == frozenset({"hypothesis"})
