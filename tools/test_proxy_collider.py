"""Regression checks for BrickIt proxy geometry and separation.

Run from repo root:
    python tools/test_proxy_collider.py
"""
from __future__ import annotations

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brick.assembly import build_assembly  # noqa: E402
from brick.brick_geom_hires import make_low_res_collider, make_proxy_collider  # noqa: E402
from brick.fitter import BrickPlacement  # noqa: E402
from brick.library import BrickType  # noqa: E402


def _bounds(mesh):
    return mesh.vertices.min(axis=0), mesh.vertices.max(axis=0)


def test_proxy_collider_has_shell_and_coarse_studs():
    stud_size = 8.0
    plate_size = 3.2
    height_plates = 3

    proxy = make_proxy_collider(
        2,
        4,
        height_plates,
        stud_size=stud_size,
        plate_size=plate_size,
    )
    low_res = make_low_res_collider(
        2,
        4,
        height_plates,
        stud_size=stud_size,
        plate_size=plate_size,
    )

    _, proxy_max = _bounds(proxy)
    _, low_res_max = _bounds(low_res)
    body_height = height_plates * plate_size

    assert proxy_max[0] == 2 * stud_size
    assert proxy_max[1] > body_height
    assert proxy_max[2] == 4 * stud_size
    assert low_res_max[1] > body_height
    assert "body" in proxy.groups
    assert "studs" in proxy.groups
    assert "underside" in proxy.groups
    assert "tubes" not in proxy.groups


def test_proxy_collider_smooth_top_keeps_underside_without_studs():
    proxy = make_proxy_collider(2, 2, 1, with_studs=False)

    assert "body" in proxy.groups
    assert "underside" in proxy.groups
    assert "studs" not in proxy.groups


def test_proxy_collider_inset_shrinks_collision_bounds():
    proxy = make_proxy_collider(2, 2, 3, inset=0.25)
    min_corner, max_corner = _bounds(proxy)

    assert round(float(min_corner[0]), 6) == 0.25
    assert round(float(min_corner[2]), 6) == 0.25
    assert round(float(max_corner[0]), 6) == 16.0 - 0.25
    assert round(float(max_corner[2]), 6) == 16.0 - 0.25


def test_low_res_assembly_uses_proxy_shell_height():
    brick = BrickType("brick_2x2", 2, 2, 3, "3003")
    placements = [
        BrickPlacement(brick, 0, 0, 0, 0),
        BrickPlacement(brick, 0, 3, 0, 0),
    ]
    mesh = build_assembly(placements, low_res=True)
    _, max_corner = _bounds(mesh)

    assert max_corner[1] > 6 * 3.2


def test_brick_separation_expands_assembly_transforms():
    brick = BrickType("brick_1x1", 1, 1, 3, "3005")
    placements = [
        BrickPlacement(brick, 0, 0, 0, 0),
        BrickPlacement(brick, 1, 0, 0, 0),
    ]
    mesh = build_assembly(placements, low_res=True, brick_separation=0.1)
    min_corner, max_corner = _bounds(mesh)

    assert min_corner[0] < 0.0
    assert max_corner[0] > 2 * 8.0
    assert round(float(max_corner[0] - min_corner[0]), 6) == 16.1


if __name__ == "__main__":
    test_proxy_collider_has_shell_and_coarse_studs()
    test_proxy_collider_smooth_top_keeps_underside_without_studs()
    test_proxy_collider_inset_shrinks_collision_bounds()
    test_low_res_assembly_uses_proxy_shell_height()
    test_brick_separation_expands_assembly_transforms()
    print("proxy collider checks passed")
