"""Pure-Python smoke test for brickit_sources Phase 1.

Not run inside C4D — uses light stubs for c4d, c4d_symbols, and
logo_helpers so the source-list enumeration and Mode lookup logic can
be exercised on a workstation without launching Cinema 4D.

Run from the BrickGen/ directory:
    python brickit/_test_brickit_sources_smoke.py
"""
import os
import sys
import types


def _install_stubs():
    here = os.path.abspath(os.path.dirname(__file__))
    brickgen = os.path.abspath(os.path.join(here, ".."))
    if brickgen not in sys.path:
        sys.path.insert(0, brickgen)

    c4d_stub = types.ModuleType("c4d")
    c4d_stub.DIRTYFLAGS_DATA = 1
    c4d_stub.DIRTYFLAGS_CACHE = 2
    c4d_stub.DIRTYFLAGS_MATRIX = 4
    sys.modules["c4d"] = c4d_stub

    logo_helpers_stub = types.ModuleType("logo_helpers")

    def _baked(source_obj, doc):
        if source_obj is None:
            return None, {"groups": []}
        if getattr(source_obj, "_polygon_count", 0) == 0:
            return None, {"groups": []}
        baked = _FakePolygon(
            point_count=source_obj._point_count,
            polygon_count=source_obj._polygon_count,
            name=source_obj._name,
        )
        return baked, {
            "groups": [
                {
                    "name": source_obj._name,
                    "point_start": 0,
                    "point_end": source_obj._point_count,
                    "poly_start": 0,
                    "poly_end": source_obj._polygon_count,
                }
            ]
        }

    logo_helpers_stub.baked_polygon_object_with_metadata = _baked
    sys.modules["logo_helpers"] = logo_helpers_stub


class _FakePolygon(object):
    def __init__(self, point_count=8, polygon_count=12, name="poly"):
        self._point_count = point_count
        self._polygon_count = polygon_count
        self._name = name

    def GetPointCount(self):
        return self._point_count


class _V(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = x
        self.y = y
        self.z = z


class _FakeMatrix(object):
    """Translation-only matrix stub supporting ~ (invert) and * (compose).

    Enough to exercise brickit_sources._matrix_key's relative-matrix
    path (~brickit_op.GetMg() * child.GetMg()) without numpy or c4d.
    Rotation is fixed to identity; only the offset moves, which is all
    the relative-pose cache key needs to distinguish.
    """

    def __init__(self, ox=0.0, oy=0.0, oz=0.0):
        self.off = _V(ox, oy, oz)
        self.v1 = _V(1.0, 0.0, 0.0)
        self.v2 = _V(0.0, 1.0, 0.0)
        self.v3 = _V(0.0, 0.0, 1.0)

    def __invert__(self):
        return _FakeMatrix(-self.off.x, -self.off.y, -self.off.z)

    def __mul__(self, other):
        return _FakeMatrix(
            self.off.x + other.off.x,
            self.off.y + other.off.y,
            self.off.z + other.off.z,
        )


class _FakeChild(object):
    _next_guid = 1000

    def __init__(self, name, point_count=8, polygon_count=12, mg=None):
        self._name = name
        self._point_count = point_count
        self._polygon_count = polygon_count
        self._guid = _FakeChild._next_guid
        _FakeChild._next_guid += 1
        self._next = None
        self._mg = mg if mg is not None else _FakeMatrix()

    def GetGUID(self):
        return self._guid

    def GetName(self):
        return self._name

    def GetNext(self):
        return self._next

    def GetDirty(self, _flags):
        return 0

    def GetMg(self):
        return self._mg


class _FakeInExclude(object):
    def __init__(self):
        self._entries = []  # list of (child, flags)

    def AppendObject(self, child, flags):
        self._entries.append((child, int(flags)))

    def GetObjectCount(self):
        return len(self._entries)

    def ObjectFromIndex(self, _doc, i):
        return self._entries[i][0]

    def GetFlags(self, i):
        return self._entries[i][1]


class _FakeBrickitOp(object):
    def __init__(self, sources_data, mg=None):
        self._sources_data = sources_data
        self._first_child = None
        self._mg = mg if mg is not None else _FakeMatrix()

    def GetMg(self):
        return self._mg

    def __getitem__(self, key):
        from c4d_symbols import BRICKIFYASSEMBLY_SOURCES
        if key == BRICKIFYASSEMBLY_SOURCES:
            return self._sources_data
        raise KeyError(key)

    def GetDocument(self):
        return None

    def GetDown(self):
        return self._first_child

    def add_children(self, *children):
        for i, c in enumerate(children):
            if i + 1 < len(children):
                c._next = children[i + 1]
        self._first_child = children[0] if children else None


def main():
    _install_stubs()
    from brickit_sources import (
        BRICKIFYASSEMBLY_SOURCE_MODE_UNION,
        BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT,
        BRICKIFYASSEMBLY_SOURCE_MODE_INTERSECT,
        bake_brickit_sources,
        enumerate_brickit_sources,
        mode_for_child,
        sources_state_key,
    )

    sphere = _FakeChild("Sphere")
    cube = _FakeChild("Cube")

    incl = _FakeInExclude()
    incl.AppendObject(sphere, BRICKIFYASSEMBLY_SOURCE_MODE_UNION)
    incl.AppendObject(cube, BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT)

    op = _FakeBrickitOp(incl)
    op.add_children(sphere, cube)

    # enumerate_brickit_sources
    pairs = enumerate_brickit_sources(op)
    assert len(pairs) == 2, "expected 2 sources, got {0}".format(len(pairs))
    assert pairs[0][0] is sphere and pairs[0][1] == BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    assert pairs[1][0] is cube and pairs[1][1] == BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT

    # mode_for_child default-Union for unlisted child
    new_child = _FakeChild("Recently Dragged")
    assert mode_for_child(op, new_child) == BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    assert mode_for_child(op, sphere) == BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    assert mode_for_child(op, cube) == BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT

    # bake groups by mode and emit a flat groups metadata list
    per_mode, all_groups = bake_brickit_sources(op, doc=None)
    assert len(per_mode[BRICKIFYASSEMBLY_SOURCE_MODE_UNION]) == 1
    assert len(per_mode[BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT]) == 1
    assert len(per_mode[BRICKIFYASSEMBLY_SOURCE_MODE_INTERSECT]) == 0
    assert len(all_groups) == 2
    assert all_groups[0]["name"] == "Sphere"
    assert all_groups[0]["mode"] == BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    assert all_groups[1]["name"] == "Cube"
    assert all_groups[1]["mode"] == BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT

    # Empty children should bake to nothing without raising
    empty_child = _FakeChild("Empty Null", point_count=0, polygon_count=0)
    op2 = _FakeBrickitOp(_FakeInExclude())
    op2.add_children(empty_child)
    per_mode2, all_groups2 = bake_brickit_sources(op2, doc=None)
    assert sum(len(v) for v in per_mode2.values()) == 0
    assert all_groups2 == []

    # sources_state_key should be deterministic and Mode-sensitive
    k1 = sources_state_key(op)
    k2 = sources_state_key(op)
    assert k1 == k2, "state key must be deterministic for unchanged inputs"
    incl_alt = _FakeInExclude()
    incl_alt.AppendObject(sphere, BRICKIFYASSEMBLY_SOURCE_MODE_UNION)
    incl_alt.AppendObject(cube, BRICKIFYASSEMBLY_SOURCE_MODE_INTERSECT)  # changed
    op_alt = _FakeBrickitOp(incl_alt)
    op_alt.add_children(sphere, cube)
    k3 = sources_state_key(op_alt)
    assert k1 != k3, "state key must change when a child's Mode changes"

    # Relative-matrix cache key (the viewport-drag perf fix):
    # moving the whole rig (BrickIt + its children) as a unit must NOT
    # change the key — the bricks are layout-invariant to world position
    # — so the GVO cache stays warm during a drag.
    rig_sphere = _FakeChild("Sphere", mg=_FakeMatrix(10.0, 0.0, 0.0))
    rig_cube = _FakeChild("Cube", mg=_FakeMatrix(20.0, 0.0, 0.0))
    rig_incl = _FakeInExclude()
    rig_incl.AppendObject(rig_sphere, BRICKIFYASSEMBLY_SOURCE_MODE_UNION)
    rig_incl.AppendObject(rig_cube, BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT)
    rig_op = _FakeBrickitOp(rig_incl, mg=_FakeMatrix(0.0, 0.0, 0.0))
    rig_op.add_children(rig_sphere, rig_cube)
    key_before_move = sources_state_key(rig_op)

    # Translate BrickIt and both children by +100 X (a rigid rig move).
    rig_op._mg = _FakeMatrix(100.0, 0.0, 0.0)
    rig_sphere._mg = _FakeMatrix(110.0, 0.0, 0.0)
    rig_cube._mg = _FakeMatrix(120.0, 0.0, 0.0)
    key_after_move = sources_state_key(rig_op)
    assert key_before_move == key_after_move, (
        "moving the whole rig must NOT bust the cache key "
        "(relative pose unchanged): {0} != {1}".format(
            key_before_move, key_after_move
        )
    )

    # But moving a source INDEPENDENTLY of BrickIt (child moves, op
    # stays put) changes its relative pose and MUST invalidate.
    rig_sphere._mg = _FakeMatrix(115.0, 0.0, 0.0)  # child only
    key_after_independent = sources_state_key(rig_op)
    assert key_after_move != key_after_independent, (
        "moving a source relative to BrickIt must bust the cache key"
    )

    print("OK: brickit_sources Phase 1 smoke test passed")
    _phase2_compose_smoke()
    print("OK: brickit_sources Phase 2 compose smoke test passed")


def _phase2_compose_smoke():
    """Exercise compose_voxel_grids on lattice-aligned synthetic grids.

    Numpy is required (it's a hard dep of the brick package), but no
    Cinema 4D bindings are needed.
    """
    import numpy as np

    from brickit_sources import (
        BRICKIFYASSEMBLY_SOURCE_MODE_UNION,
        BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT,
        BRICKIFYASSEMBLY_SOURCE_MODE_INTERSECT,
        compose_voxel_grids,
    )

    voxel_mm = np.array([8.0, 3.2, 8.0], dtype=np.float64)

    # Union bucket: a 4x4x4 sphere-ish blob anchored at origin (0,0,0).
    occ_u = np.zeros((4, 4, 4), dtype=bool)
    occ_u[1:4, 0:4, 1:4] = True
    col_u = np.zeros((4, 4, 4, 3), dtype=np.uint8)
    col_u[..., 0] = 200  # red-ish
    origin_u = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    info_u = {
        "voxel_backend": "internal",
        "voxel_backend_fallback": False,
        "voxel_backend_raw_occupied": int(occ_u.sum()),
        "voxel_backend_volume_seconds": 0.01,
        "voxel_backend_sample_seconds": 0.005,
        "voxel_backend_sample_count": int(occ_u.size),
        "voxel_backend_note": "union test",
    }

    # Subtract bucket: a 2x2x2 chunk that overlaps the right side of Union,
    # offset by (2, 0, 2) voxels = (16, 0, 16) world units.
    occ_s = np.ones((2, 2, 2), dtype=bool)
    col_s = np.zeros((2, 2, 2, 3), dtype=np.uint8)
    origin_s = np.array([2.0 * voxel_mm[0], 0.0, 2.0 * voxel_mm[2]], dtype=np.float64)
    info_s = {
        "voxel_backend": "internal",
        "voxel_backend_fallback": False,
        "voxel_backend_raw_occupied": int(occ_s.sum()),
        "voxel_backend_note": "subtract test",
    }

    per_bucket = {
        BRICKIFYASSEMBLY_SOURCE_MODE_UNION: (occ_u, col_u, origin_u, info_u),
        BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT: (occ_s, col_s, origin_s, info_s),
    }

    composed = compose_voxel_grids(per_bucket, voxel_mm, default_color=(180, 180, 180))
    assert composed is not None, "Union ∖ Subtract should leave geometry"
    occ, colors, origin, info = composed
    # Composed origin matches the union AABB (which here equals union bucket's
    # origin since subtract is fully inside the union AABB).
    assert np.allclose(origin, origin_u), "composed origin should equal union AABB min"
    assert occ.shape == (4, 4, 4), "composed dims should equal union AABB dims"
    # Cells where Union was True AND Subtract was False stay True.
    expected = occ_u.copy()
    expected[2:4, 0:2, 2:4] &= ~np.ones((2, 2, 2), dtype=bool)  # carve subtract region
    assert np.array_equal(occ, expected), "subtract should carve exactly the overlap"
    # Composed color tracks the Union-painted cells.
    assert colors.dtype == np.uint8 and colors.shape == (4, 4, 4, 3)
    assert (colors[1, 0, 1] == np.array([200, 0, 0], dtype=np.uint8)).all()

    # Intersect bucket: same shape as union, shifted by (-1,0,0). The
    # intersect should crop the composed result to just the overlap region.
    occ_i = np.ones((4, 4, 4), dtype=bool)
    col_i = np.zeros((4, 4, 4, 3), dtype=np.uint8)
    origin_i = np.array([-1.0 * voxel_mm[0], 0.0, 0.0], dtype=np.float64)
    info_i = {"voxel_backend": "internal", "voxel_backend_fallback": False}
    per_bucket_i = {
        BRICKIFYASSEMBLY_SOURCE_MODE_UNION: (occ_u, col_u, origin_u, info_u),
        BRICKIFYASSEMBLY_SOURCE_MODE_INTERSECT: (occ_i, col_i, origin_i, info_i),
    }
    composed_i = compose_voxel_grids(per_bucket_i, voxel_mm, default_color=(180, 180, 180))
    assert composed_i is not None
    occ_ci, _, origin_ci, _ = composed_i
    # Union AABB now starts at x=-1 voxel.
    assert np.allclose(origin_ci, origin_i)
    # Composed dims expand to fit both grids: x extent = max(0+4, -1+4) - (-1) = 5.
    assert occ_ci.shape == (5, 4, 4)
    # In the composed frame, union sits at offset x=+1 and intersect at x=0.
    # Intersect covers x∈[0..3], union covers x∈[1..4] → overlap is x∈[1..3].
    # Within union, only x=1..3 (i.e. raw-union x=0..2) survive intersect.
    assert occ_ci[0, 0, 0] == False  # outside union
    assert occ_ci[1, 0, 1] == False  # union-x=0 is empty in occ_u
    assert occ_ci[2, 0, 1] == True   # union-x=1, occupied + within intersect
    assert occ_ci[4, 0, 1] == False  # union-x=3, but outside intersect grid

    # Empty composition: only a subtract bucket → no Union, returns None.
    per_bucket_empty = {BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT: (occ_s, col_s, origin_s, info_s)}
    assert compose_voxel_grids(per_bucket_empty, voxel_mm, (180, 180, 180)) is None

    # Full cancellation: union fully subtracted leaves nothing.
    big_sub = np.ones((4, 4, 4), dtype=bool)
    per_bucket_full_sub = {
        BRICKIFYASSEMBLY_SOURCE_MODE_UNION: (occ_u, col_u, origin_u, info_u),
        BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT: (
            big_sub,
            np.zeros((4, 4, 4, 3), dtype=np.uint8),
            origin_u,
            info_s,
        ),
    }
    assert compose_voxel_grids(per_bucket_full_sub, voxel_mm, (180, 180, 180)) is None


if __name__ == "__main__":
    main()
