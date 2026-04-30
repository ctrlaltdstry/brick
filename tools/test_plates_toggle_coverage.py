"""Regression checks for Use Plates coverage behavior.

Run from repo root:
    python tools/test_plates_toggle_coverage.py
"""
from __future__ import annotations

import os
import sys

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brick.library import BrickLibrary, BrickType  # noqa: E402
from brick.pipeline import brick_mesh  # noqa: E402


def _sample_voxels():
    """A tall column plus a one-plate ledge, matching the failure shape."""
    occupancy = np.zeros((2, 3, 1), dtype=bool)
    occupancy[0, :, 0] = True
    occupancy[1, 0, 0] = True
    colors = np.full(occupancy.shape + (3,), 180, dtype=np.uint8)
    origin = np.zeros(3, dtype=np.float64)
    return occupancy, colors, origin, {"voxel_backend": "test"}


def _run(library, *, prune_connectivity, relaxed_boundary_fit=None):
    if relaxed_boundary_fit is None:
        relaxed_boundary_fit = not prune_connectivity
    occupancy, colors, origin, backend_info = _sample_voxels()
    placements, info = brick_mesh(
        np.zeros((1, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.int32),
        stud_size=8.0,
        plate_size=3.2,
        library=library,
        max_brick_height=3,
        merge_plates=True,
        merge_horizontal=True,
        prune_connectivity=prune_connectivity,
        relaxed_boundary_fit=relaxed_boundary_fit,
        precomputed_voxels=(occupancy, colors, origin, backend_info),
        include_debug_info=False,
    )
    return placements, info


def _no_plates_library():
    return BrickLibrary([
        BrickType("brick_1x1", 1, 1, 3, "3005"),
        BrickType("brick_h2_1x1", 1, 1, 2, "custom_h2_1x1"),
        BrickType("brick_h1_1x1", 1, 1, 1, "custom_h1_1x1"),
    ])


def _covered_names(placements):
    return {p.brick.name for p in placements}


def test_no_plates_library_covers_one_plate_leftovers_in_artist_mode():
    placements, info = _run(_no_plates_library(), prune_connectivity=False)

    assert info["coverage"]["uncovered"] == 0
    assert info["coverage"]["coverage_ratio"] == 1.0
    assert "plate_1x1" not in _covered_names(placements)
    assert any(p.h == 1 for p in placements)


def test_no_plates_library_keeps_grounded_leftovers_in_physical_mode():
    placements, info = _run(_no_plates_library(), prune_connectivity=True)

    assert info["pre_prune_coverage"]["uncovered"] == 0
    assert info["coverage"]["uncovered"] == 0
    assert info["n_dropped"] == 0
    assert "plate_1x1" not in _covered_names(placements)


def test_coverage_metrics_report_uncovered_cells():
    no_height_one = BrickLibrary([
        BrickType("brick_1x1", 1, 1, 3, "3005"),
        BrickType("brick_h2_1x1", 1, 1, 2, "custom_h2_1x1"),
    ])

    _placements, info = _run(
        no_height_one,
        prune_connectivity=False,
        relaxed_boundary_fit=False,
    )

    assert info["coverage"]["uncovered"] == 1
    assert info["n_uncovered"] == 1
    assert info["coverage"]["uncovered_by_y"] == [1, 0, 0]
    assert info["coverage"]["coverage_ratio"] < 1.0


def main():
    test_no_plates_library_covers_one_plate_leftovers_in_artist_mode()
    test_no_plates_library_keeps_grounded_leftovers_in_physical_mode()
    test_coverage_metrics_report_uncovered_cells()
    print("plates toggle coverage regressions passed")


if __name__ == "__main__":
    main()
