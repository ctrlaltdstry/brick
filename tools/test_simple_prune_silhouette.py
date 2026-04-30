"""Regression checks for simple/internal silhouette pruning behavior.

Run from repo root:
    python tools/test_simple_prune_silhouette.py

These tests keep physical pruning from treating source-contiguous facade
pieces as floating debris just because they are not clutch-connected.
"""
from __future__ import annotations

import os
import sys

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brick.connectivity import check_connectivity  # noqa: E402
from brick.fitter import BrickPlacement  # noqa: E402
from brick.library import BrickType  # noqa: E402
from brick.pipeline import _prune_floating_fragments_by_voxel_island  # noqa: E402


def test_prune_keeps_side_attached_source_silhouette_fragment():
    brick = BrickType("brick_1x1", 1, 1, 1, "3005")
    placements = [
        BrickPlacement(brick, 0, y, 0, 0)
        for y in range(6)
    ] + [
        # Same-layer facade ledge: source-contiguous via side contact, but not
        # structurally coupled because LEGO clutch edges are vertical only.
        BrickPlacement(brick, 1, 2, 0, 0),
        BrickPlacement(brick, 2, 2, 0, 0),
    ] + [
        # Diagonal/no-face-contact debris in the same 26-connected voxel island.
        BrickPlacement(brick, 3, 3, 1, 0),
    ]
    labels = np.zeros((4, 6, 2), dtype=np.int32)
    for p in placements:
        labels[p.x:p.x + p.w, p.y:p.y + p.h, p.z:p.z + p.d] = 1

    kept, dropped, summary = _prune_floating_fragments_by_voxel_island(
        placements,
        labels,
        check_connectivity(placements),
        max_drop_ratio_per_island=0.35,
    )

    kept_cells = {(p.x, p.y, p.z) for p in kept}
    dropped_cells = {(p.x, p.y, p.z) for p in dropped}
    assert (1, 2, 0) in kept_cells
    assert (2, 2, 0) in kept_cells
    assert (3, 3, 1) in dropped_cells
    assert summary[0]["kept_source_attached_fragments"] == 2


def main():
    test_prune_keeps_side_attached_source_silhouette_fragment()
    print("simple prune silhouette regressions passed")


if __name__ == "__main__":
    main()
