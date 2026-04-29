"""Regression checks for physically accurate buildability semantics.

Run from repo root:
    python tools/test_physical_connectivity.py
"""
from __future__ import annotations

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brick.connectivity import check_buildability  # noqa: E402
from brick.fitter import BrickPlacement  # noqa: E402
from brick.library import BrickType  # noqa: E402
from brick.pipeline import _physical_repair_summary  # noqa: E402


PLATE_1X1 = BrickType("plate_1x1", 1, 1, 1, "3024")
PLATE_2X1 = BrickType("plate_2x1", 2, 1, 1, "3023")
PLATE_3X1 = BrickType("plate_3x1", 3, 1, 1, "3623")


def _p(brick, x, y, z):
    return BrickPlacement(brick, x, y, z, 0)


def test_side_by_side_is_not_physical_connection():
    placements = [
        _p(PLATE_1X1, 0, 0, 0),
        _p(PLATE_1X1, 1, 0, 0),
    ]
    report = check_buildability(placements)

    assert not report["buildable"]
    assert report["n_components"] == 2
    assert report["n_grounded_components"] == 2
    assert report["n_ungrounded"] == 0
    assert len(report["same_layer_islands"]) == 1
    repair = _physical_repair_summary(report)
    assert repair["needed"]
    assert repair["status"] == "needs_bridge"


def test_top_bridge_makes_side_by_side_bases_one_buildable_assembly():
    placements = [
        _p(PLATE_1X1, 0, 0, 0),
        _p(PLATE_1X1, 1, 0, 0),
        _p(PLATE_2X1, 0, 1, 0),
    ]
    report = check_buildability(placements)

    assert report["buildable"]
    assert report["n_components"] == 1
    assert sorted(edge["studs"] for edge in report["clutch_edges"]) == [1, 1]


def test_floating_brick_is_unsupported_and_ungrounded():
    report = check_buildability([_p(PLATE_1X1, 0, 1, 0)])

    assert not report["buildable"]
    assert report["unsupported_indices"] == [0]
    assert report["ungrounded_indices"] == [0]


def test_vertical_stack_is_buildable():
    placements = [
        _p(PLATE_1X1, 0, 0, 0),
        _p(PLATE_1X1, 0, 1, 0),
        _p(PLATE_1X1, 0, 2, 0),
    ]
    report = check_buildability(placements)

    assert report["buildable"]
    assert report["n_components"] == 1
    assert report["n_unsupported"] == 0


def test_shell_like_fragments_need_a_real_bridge():
    disconnected_towers = [
        _p(PLATE_1X1, 0, 0, 0),
        _p(PLATE_1X1, 0, 1, 0),
        _p(PLATE_1X1, 2, 0, 0),
        _p(PLATE_1X1, 2, 1, 0),
    ]
    disconnected = check_buildability(disconnected_towers)
    assert not disconnected["buildable"]
    assert disconnected["n_grounded_components"] == 2

    bridged = check_buildability(disconnected_towers + [_p(PLATE_3X1, 0, 2, 0)])
    assert bridged["buildable"]
    assert bridged["n_components"] == 1


def main():
    test_side_by_side_is_not_physical_connection()
    test_top_bridge_makes_side_by_side_bases_one_buildable_assembly()
    test_floating_brick_is_unsupported_and_ungrounded()
    test_vertical_stack_is_buildable()
    test_shell_like_fragments_need_a_real_bridge()
    print("physical connectivity regressions passed")


if __name__ == "__main__":
    main()
