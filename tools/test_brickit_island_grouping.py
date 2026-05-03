"""Regression checks for BrickIt source-child / polygon-island grouping."""
from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "BrickGen"))


if "c4d" not in sys.modules:
    sys.modules["c4d"] = types.ModuleType("c4d")


from source_geometry import (  # noqa: E402
    placement_group_key,
    placement_grouping_for_islands,
    source_polygon_islands,
)


@dataclass
class _Point:
    x: float
    y: float
    z: float


@dataclass
class _Poly:
    a: int
    b: int
    c: int
    d: int


class _IdentityMatrix:
    def __mul__(self, point):
        return point


class _PolyObject:
    def __init__(self, points, polys):
        self._points = points
        self._polys = polys

    def GetPointCount(self):
        return len(self._points)

    def GetPolygonCount(self):
        return len(self._polys)

    def GetAllPoints(self):
        return self._points

    def GetAllPolygons(self):
        return self._polys

    def GetMg(self):
        return _IdentityMatrix()


@dataclass
class _Brick:
    name: str
    width: int
    depth: int
    height: int


@dataclass
class _Placement:
    brick: _Brick
    x: int
    y: int
    z: int
    rotation_y: int = 0

    @property
    def w(self):
        return self.brick.width

    @property
    def h(self):
        return self.brick.height

    @property
    def d(self):
        return self.brick.depth


def _square(x0):
    base = [
        _Point(x0, 0, 0),
        _Point(x0 + 1, 0, 0),
        _Point(x0 + 1, 1, 0),
        _Point(x0, 1, 0),
    ]
    return base, _Poly(0, 1, 2, 3)


def test_source_child_polygon_islands_are_preserved():
    all_points = []
    all_polys = []
    for offset in (0, 5, 20):
        points, poly = _square(offset)
        point_offset = len(all_points)
        all_points.extend(points)
        all_polys.append(
            _Poly(
                poly.a + point_offset,
                poly.b + point_offset,
                poly.c + point_offset,
                poly.d + point_offset,
            )
        )

    source = _PolyObject(all_points, all_polys)
    metadata = {
        "groups": [
            {"name": "Hull", "poly_start": 0, "poly_end": 2},
            {"name": "Tower", "poly_start": 2, "poly_end": 3},
        ]
    }
    islands = source_polygon_islands(source, metadata)

    assert len(islands["islands"]) == 3
    assert [row["source_name"] for row in islands["islands"]] == ["Hull", "Hull", "Tower"]

    brick = _Brick("brick_1x1", 1, 1, 1)
    placements = [
        _Placement(brick, 0, 0, 0),
        _Placement(brick, 5, 0, 0),
        _Placement(brick, 20, 0, 0),
    ]
    grouping = placement_grouping_for_islands(
        placements,
        islands,
        origin=(0, 0, 0),
        stud_size=1.0,
        plate_size=1.0,
    )

    assigned = [
        grouping["placement_groups"][placement_group_key(placement)]
        for placement in placements
    ]
    assert len(set(assigned)) == 3
    group_names = {
        row["key"]: (row["source_name"], row["island_name"])
        for row in grouping["groups"]
    }
    assert group_names[assigned[0]][0] == "Hull"
    assert group_names[assigned[1]][0] == "Hull"
    assert group_names[assigned[2]][0] == "Tower"

    generated_cap = _Placement(brick, 6, 1, 0)
    grouping["placement_groups"].pop(placement_group_key(generated_cap), None)

    from BrickGen.brickit.brickit_groups import resolve_group_key  # noqa: E402

    assert resolve_group_key({"source_island_groups": grouping}, generated_cap) == assigned[1]


def main():
    test_source_child_polygon_islands_are_preserved()
    print("brickit island grouping regressions passed")


if __name__ == "__main__":
    main()
