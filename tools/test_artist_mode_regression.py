"""Regression checks for BrickIt artist-vs-physical fitting behavior.

Run from repo root:
    python tools/test_artist_mode_regression.py

These tests lock in the UX contract:
- Make Physically Accurate OFF is artist-friendly and preserves occupied
  boundary cells without overhanging large selected bricks.
- Make Physically Accurate ON may prune, but must not amputate substantial
  disconnected visual chunks as if they were debris.
"""
from __future__ import annotations

import os
import sys

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brick.fitter import BrickFitter, BrickPlacement  # noqa: E402
from brick.library import BrickLibrary, BrickType  # noqa: E402
from brick.pipeline import _prune_floating_fragments_by_voxel_island  # noqa: E402


def _covered_cells(placements):
    covered = set()
    for p in placements:
        for x in range(p.x, p.x + p.w):
            for y in range(p.y, p.y + p.h):
                for z in range(p.z, p.z + p.d):
                    covered.add((x, y, z))
    return covered


def test_artist_mode_fills_boundaries_without_large_overhangs():
    brick_2x4 = BrickType("brick_2x4", 2, 4, 3, "3001")
    lib = BrickLibrary([brick_2x4])
    occ = np.ones((3, 3, 4), dtype=bool)
    colors = np.full((3, 3, 4, 3), 180, dtype=np.uint8)

    strict = BrickFitter(lib, max_brick_height=3).fit(
        occ,
        colors,
        relaxed_boundary_fit=False,
    )
    strict_covered = _covered_cells(strict)
    assert (2, 0, 0) not in strict_covered

    artist = BrickFitter(lib, max_brick_height=3).fit(
        occ,
        colors,
        relaxed_boundary_fit=True,
    )
    artist_covered = _covered_cells(artist)
    occupied = {
        (int(x), int(y), int(z))
        for x, y, z in zip(*np.where(occ))
    }
    assert occupied <= artist_covered
    assert any(p.brick.name.startswith("artist_fill_1x1") for p in artist)
    for p in artist:
        assert 0 <= p.x and 0 <= p.z
        assert p.x + p.w <= occ.shape[0]
        assert p.z + p.d <= occ.shape[2]


def test_prune_keeps_significant_visual_fragments():
    brick = BrickType("brick_1x1", 1, 1, 1, "3005")
    placements = [
        BrickPlacement(brick, 0, 0, i, 0)
        for i in range(30)
    ] + [
        BrickPlacement(brick, 2, 0, i, 0)
        for i in range(24)
    ] + [
        BrickPlacement(brick, 4, 1, i, 0)
        for i in range(3)
    ]
    labels = np.ones((5, 3, 30), dtype=np.int32)
    graph = {}
    for start, count in ((0, 30), (30, 24), (54, 3)):
        for i in range(start, start + count):
            graph[i] = set()
            if i > start:
                graph[i].add(i - 1)
            if i < start + count - 1:
                graph[i].add(i + 1)

    kept, dropped, _summary = _prune_floating_fragments_by_voxel_island(
        placements,
        labels,
        {"graph": graph},
        max_drop_ratio_per_island=0.35,
    )
    assert len(kept) == 54
    assert len(dropped) == 3
    assert any(p.x == 2 for p in kept)
    assert all(p.x != 4 for p in kept)


def test_prune_keeps_small_source_top_fragments():
    brick = BrickType("brick_1x1", 1, 1, 1, "3005")
    placements = [
        BrickPlacement(brick, 0, 0, i, 0)
        for i in range(30)
    ] + [
        BrickPlacement(brick, 2, 4, i, 0)
        for i in range(4)
    ] + [
        BrickPlacement(brick, 4, 1, i, 0)
        for i in range(3)
    ]
    labels = np.ones((5, 5, 30), dtype=np.int32)
    graph = {}
    for start, count in ((0, 30), (30, 4), (34, 3)):
        for i in range(start, start + count):
            graph[i] = set()
            if i > start:
                graph[i].add(i - 1)
            if i < start + count - 1:
                graph[i].add(i + 1)

    kept, dropped, _summary = _prune_floating_fragments_by_voxel_island(
        placements,
        labels,
        {"graph": graph},
        max_drop_ratio_per_island=0.35,
    )
    assert len(kept) == 34
    assert len(dropped) == 3
    assert any(p.x == 2 for p in kept)
    assert all(p.x != 4 for p in kept)


def main():
    test_artist_mode_fills_boundaries_without_large_overhangs()
    test_prune_keeps_significant_visual_fragments()
    test_prune_keeps_small_source_top_fragments()
    print("artist mode regressions passed")


if __name__ == "__main__":
    main()
