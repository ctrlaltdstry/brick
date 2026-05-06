"""Watertight OBJ-based proxy bricks.

Loads hand-authored brick references (welded, single-island geometry) and
synthesizes meshes for any (W, D, H, smooth) request BrickIt makes for
proxy quality. Falls back to the procedural `make_proxy_collider` only when
synthesis can't cover a request.

Two reference OBJs ship today:
    - brick_2x4_h2p.obj — 2 studs wide, 4 studs deep, 2 plates tall, studded.
    - brick_3x4_h2p.obj — 3 studs wide, 4 studs deep, 2 plates tall, studded.

Each reference is positioned with its body centered on Y=0 in OBJ units;
this module re-frames each loaded mesh so its bottom-front-left corner sits
at (0, 0, 0), matching what `_center_template_mesh` in
brickit_mograph_generator expects from procedural meshes. Each OBJ is
scale-calibrated independently (the modeler may have authored at different
scales).

Synthesis covers four axes:
    - Footprint trim along X (e.g. 2x4 → 1x4) and Z (e.g. 2x4 → 2x2).
    - Footprint extend along Z (e.g. 2x4 → 2x6) by duplicating an interior
      cell column.
    - Vertical stretch along Y (any height in plates).
    - Smooth-cap variant — strip studs and cap the holes for the surface-
      cap path.

Trim is implemented via Sutherland-Hodgman clipping against an axis-aligned
plane, plus a boundary-loop capping pass to keep the mesh watertight.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from brick.mesh import Mesh

try:
    from plugin_bootstrap import brick_log as _brick_log
except Exception:  # pragma: no cover — outside plugin (unit tests).
    def _brick_log(msg):
        print(msg)


# BrickIt's canonical sizes.
_STUD_SIZE = 8.0
_PLATE_SIZE = 3.2
_STUD_HEIGHT_RATIO = 0.55  # of plate_size; matches procedural builder.
_STUD_HEIGHT = _PLATE_SIZE * _STUD_HEIGHT_RATIO  # ~1.76


@dataclass
class _Reference:
    """A hand-authored reference brick OBJ + its metadata.

    `_loaded` holds the post-frame, post-scale Mesh; populated lazily.
    """
    name: str
    obj_path_rel: str
    width_studs: int
    depth_studs: int
    height_plates: int
    has_studs: bool = True
    _loaded: Optional[Mesh] = field(default=None, repr=False)


_REFERENCES: List[_Reference] = [
    _Reference("2x4_h2p", "library/brick_2x4_h2p.obj", 2, 4, 2),
    _Reference("3x4_h2p", "library/brick_3x4_h2p.obj", 3, 4, 2),
]

# Cell-tile reference: a hand-authored 1x1 closed brick. Tiled W×D times,
# welded, with adjacent outer-wall pairs removed. Cavity stays per-cell
# internally (invisible from outside).
_CELL_REF = _Reference("1x1_h2p", "library/brick_1x1_h2p.obj", 1, 1, 2)

# Variant-based synthesis: 4 top-piece variants + walls extracted from ref 1.
# Each variant is a 1x1 top piece (top + stud + cavity ceiling) where the
# cavity ceiling is INSET on certain sides indicating wall positions.
_VARIANTS_OBJ_REL = "library/brick_1x1_tops_h2p.obj"
_FULL_REF_OBJ_REL = "library/brick_1x1_h2p.obj"
# V4: complete top+walls variants in one OBJ.
# V5: clean per-cell complete pieces — preferred path.
_PIECES_OBJ_REL = "library/brick_1x1_Proxy_Pieces.obj"  # Edge, Corner, Tunnel, Endcap
_TOPS_WALLS_OBJ_REL = "library/brick_1x1_Proxy_tops_walls.obj"
_V4_VARIANTS_CACHE: Optional[Dict[str, Mesh]] = None

# V5 — 3-piece scheme. The user's manual C4D testing established that any
# brick (W,D >= 2) needs only three pieces: Corner (rotated 4 ways for the
# 4 outer corners), Edge (rotated 4 ways for cells along the outer edges),
# and Top (a center-fill piece with no walls/rim, used for interior cells).
# No cavity walls — the cavity is a single open volume bounded only by the
# brick's outer perimeter walls and the cavity ceiling that every piece
# carries on its top.
_THREE_PIECES_OBJ_REL = "library/brick_1x1_Proxy_Pieces_new.obj"  # Corner, Edge, Top
_THREE_PIECES_CACHE: Optional[Dict[str, Mesh]] = None

# V5 — 5-piece scheme (Corner, Edge, Tunnel, Endcap, Center_Fill). Covers
# every cell case for W,D >= 1 without trimming. 1x1 is special-cased to the
# full-walls reference brick.
_FIVE_PIECES_OBJ_REL = "library/brick_1x1_Proxy_Pieces_V3.obj"
_FIVE_PIECES_CACHE: Optional[Dict[str, Mesh]] = None

# Geometric constants in BrickIt units (after scale).
_BODY_TOP_Y = 2 * _PLATE_SIZE  # = 6.4 (for h2p reference)
_CAVITY_TOP_Y_FRAC = 2.754 / (2.754 - (-3.954))  # 2.754 / 6.708 = ~0.41
_BODY_BOTTOM_Y = 0.0  # after corner-at-origin reframe
# Cavity top in BrickIt units (after reframe): the OBJ Y=2.754 maps to
# Y_in_BrickIt = (2.754 - obj_min_y) * scale. For ref 1 with obj_min_y=-3.954
# and scale=8/9.884, Y_cavity = (2.754 + 3.954) * 0.8095 = 5.43.
_CAVITY_TOP_Y = 5.43  # approx; computed precisely at load time

# Cached at module load.
_VARIANTS_CACHE: Optional[Dict[str, Mesh]] = None
_WALLS_PER_SIDE_CACHE: Optional[Dict[str, Mesh]] = None


# ---------------------------------------------------------------------------
# OBJ parser
# ---------------------------------------------------------------------------


def _plugin_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _parse_obj(path: str) -> Mesh:
    """Single-pass OBJ parser. Reads `v` and `f` lines; ignores everything
    else. Supports `v/vt/vn` triplet face indices and arbitrary face arity.
    """
    verts = []
    faces = []
    with open(path, "r") as f:
        for line in f:
            head = line[:2]
            if head == "v ":
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif head == "f ":
                indices = []
                for tok in line.split()[1:]:
                    indices.append(int(tok.split("/", 1)[0]) - 1)
                faces.append(tuple(indices))
    if not verts or not faces:
        raise RuntimeError("Empty OBJ: {0}".format(path))
    mesh = Mesh()
    mesh.vertices = np.asarray(verts, dtype=np.float64)
    mesh.add_group_faces("body", faces)
    return mesh


def _reframe_for_brickit(mesh: Mesh, ref: _Reference) -> Mesh:
    """Calibrate scale per-OBJ (so stud spacing maps to BrickIt's stud_size),
    translate so bottom-front-left corner is at origin. Mutates and returns
    `mesh`."""
    mesh.flush()
    v = mesh.vertices
    # Use the longer axis (Z = depth_studs) for scale calibration — more
    # sample distance for a more accurate measurement.
    z_extent = float(v[:, 2].max() - v[:, 2].min())
    stud_spacing_obj = z_extent / float(ref.depth_studs)
    scale = _STUD_SIZE / stud_spacing_obj
    v = v * scale
    v = v - v.min(axis=0)
    mesh.vertices = v
    return mesh


def _load_reference(ref: _Reference) -> Mesh:
    """Lazy-load + reframe a reference. Returns a deep copy so callers can
    mutate without polluting the cache."""
    if ref._loaded is None:
        path = os.path.join(_plugin_root(), ref.obj_path_rel)
        raw = _parse_obj(path)
        ref._loaded = _reframe_for_brickit(raw, ref)
        _orient_faces_consistently(ref._loaded)
        _brick_log(
            "[brick] OBJ proxy: loaded reference '{0}' ({1} verts, {2} faces)".format(
                ref.name, len(ref._loaded.vertices), len(ref._loaded.faces)
            )
        )
    return _clone_mesh(ref._loaded)


def _clone_mesh(src: Mesh) -> Mesh:
    src.flush()
    return Mesh(
        vertices=src.vertices.copy(),
        faces=[tuple(f) for f in src.faces],
        groups={g: list(idxs) for g, idxs in src.groups.items()},
    )


# ---------------------------------------------------------------------------
# Polygon clipping (Sutherland-Hodgman against axis-aligned plane)
# ---------------------------------------------------------------------------


def _clip_polygon_against_plane(
    poly_verts: np.ndarray,
    axis: int,
    cut: float,
    keep_below: bool,
    eps: float = 1e-7,
) -> np.ndarray:
    """Clip a convex polygon against an axis-aligned plane (`coord[axis] = cut`).
    `keep_below=True` retains the part where coord[axis] <= cut.

    Returns an (M, 3) ndarray of clipped polygon verts; may be empty.
    Edges crossing the plane produce new verts at the intersection.
    """
    n = len(poly_verts)
    if n == 0:
        return poly_verts
    out = []

    def inside(p):
        return (p[axis] <= cut + eps) if keep_below else (p[axis] >= cut - eps)

    for i in range(n):
        a = poly_verts[i]
        b = poly_verts[(i + 1) % n]
        a_in = inside(a)
        b_in = inside(b)
        if a_in:
            out.append(a)
            if not b_in:
                # Crossing out — add intersection.
                t = (cut - a[axis]) / (b[axis] - a[axis])
                out.append(a + (b - a) * t)
        elif b_in:
            # Crossing in — add intersection (before b on next iter).
            t = (cut - a[axis]) / (b[axis] - a[axis])
            out.append(a + (b - a) * t)
    if not out:
        return np.zeros((0, 3), dtype=np.float64)
    return np.asarray(out, dtype=np.float64)


def _slice_along_axis(
    mesh: Mesh,
    axis: int,
    cut: float,
    keep_below: bool,
    weld_tol: float = 1e-3,
    cap: bool = True,
) -> Mesh:
    """Clip mesh against an axis-aligned plane. If `cap=True`, fill the
    open boundary so the result is watertight; if False, leave it open
    so the slice can be welded to another slice at the same plane.

    Used as a building block for both single-sided trim and middle-slab
    extraction.
    """
    mesh.flush()
    src_v = mesh.vertices
    new_verts = []
    new_faces = []

    def emit_vert(p) -> int:
        new_verts.append(tuple(p))
        return len(new_verts) - 1

    eps = max(1e-6, weld_tol * 0.1)

    for face in mesh.faces:
        poly = src_v[list(face)]
        clipped = _clip_polygon_against_plane(poly, axis, cut, keep_below, eps=eps)
        if len(clipped) < 3:
            continue
        face_indices = [emit_vert(p) for p in clipped]
        new_faces.append(tuple(face_indices))

    out = Mesh()
    if not new_faces:
        out.vertices = np.zeros((0, 3), dtype=np.float64)
        return out
    out.vertices = np.asarray(new_verts, dtype=np.float64)
    out.add_group_faces("body", new_faces)
    out.weld_vertices(tol=weld_tol)
    if cap:
        _cap_boundary_at_plane(out, axis, cut, keep_below=keep_below, weld_tol=weld_tol)
        out.weld_vertices(tol=weld_tol)
    return out


def _trim_along_axis(
    mesh: Mesh,
    axis: int,
    cut: float,
    keep_below: bool,
    weld_tol: float = 1e-3,
) -> Mesh:
    """Trim mesh by clipping faces against a plane and capping the resulting
    boundary loop with ear-clipping triangulation. Outer loop only — cavity
    holes left open (invisible from outside the brick)."""
    return _slice_along_axis(mesh, axis, cut, keep_below, weld_tol, cap=True)


def _signed_area_2d(pts2d: np.ndarray) -> float:
    """Signed polygon area; positive = CCW in projected plane."""
    n = len(pts2d)
    s = 0.0
    for i in range(n):
        x1, y1 = pts2d[i]
        x2, y2 = pts2d[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return 0.5 * s


def _point_in_triangle_2d(p, a, b, c, eps: float = 1e-9) -> bool:
    """Standard sign-of-cross-products test. Treats on-edge as inside."""
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)
    has_neg = (d1 < -eps) or (d2 < -eps) or (d3 < -eps)
    has_pos = (d1 > eps) or (d2 > eps) or (d3 > eps)
    return not (has_neg and has_pos)


def _ear_clip_2d(pts2d: np.ndarray) -> List[Tuple[int, int, int]]:
    """Ear-clip a simple (non-self-intersecting) CCW polygon. Returns
    triangle indices into the input array. Handles non-convex polygons."""
    n = len(pts2d)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]

    indices = list(range(n))
    triangles: List[Tuple[int, int, int]] = []
    safety = n * n  # bail-out for pathological cases

    while len(indices) > 3 and safety > 0:
        safety -= 1
        ear_found = False
        for i in range(len(indices)):
            prev_i = indices[(i - 1) % len(indices)]
            curr_i = indices[i]
            next_i = indices[(i + 1) % len(indices)]
            p, c, q = pts2d[prev_i], pts2d[curr_i], pts2d[next_i]
            # Convex corner test: cross product positive for CCW polygon.
            cross = (c[0] - p[0]) * (q[1] - p[1]) - (c[1] - p[1]) * (q[0] - p[0])
            if cross <= 1e-12:
                continue
            # No other polygon vertex inside this candidate triangle.
            in_tri = False
            for j in indices:
                if j == prev_i or j == curr_i or j == next_i:
                    continue
                if _point_in_triangle_2d(pts2d[j], p, c, q):
                    in_tri = True
                    break
            if in_tri:
                continue
            triangles.append((prev_i, curr_i, next_i))
            indices.pop(i)
            ear_found = True
            break
        if not ear_found:
            # Degenerate or self-intersecting polygon — give up.
            break

    if len(indices) == 3:
        triangles.append((indices[0], indices[1], indices[2]))
    return triangles


def _cap_boundary_at_plane(
    mesh: Mesh,
    axis: int,
    cut: float,
    keep_below: bool = True,
    weld_tol: float = 1e-3,
) -> None:
    """Cap the brick at the cut plane with proper wall thickness.

    Three steps:
      1. Detect cavity-related verts at Z=cut (interior to the outer
         rectangle in (u, w), regardless of perimeter status).
      2. Translate those verts inward by `wall_thickness` (derived from
         the cavity's inset distance from the outer perimeter). This
         physically pulls the cavity walls back, ending them before the
         cut plane.
      3. Emit two center-fan caps:
            - Outer cap at Z=cut (covers the brick's outer rectangle).
            - Inner cap at Z=cut-wall_thickness (covers cavity rectangle,
              normal facing into cavity).
       The thin back rim and the gap between caps appear naturally
       because the cavity verts are at the inner Z and the outer-perim
       verts stay at the cut Z.
    """
    mesh.flush()
    v = mesh.vertices
    eps = max(1e-6, weld_tol * 0.5)
    proj_axes = [a for a in (0, 1, 2) if a != axis]

    on_plane_idx = [i for i in range(len(v)) if abs(v[i, axis] - cut) < eps]
    if len(on_plane_idx) < 4:
        return

    pts = v[on_plane_idx][:, proj_axes]
    u_min, w_min = float(pts[:, 0].min()), float(pts[:, 1].min())
    u_max, w_max = float(pts[:, 0].max()), float(pts[:, 1].max())
    perim_eps = max(1e-5, weld_tol)

    # Identify interior cavity verts: NOT on outer perim.
    interior_verts = []
    for idx, (u, w) in zip(on_plane_idx, pts):
        on_left   = abs(u - u_min) < perim_eps
        on_right  = abs(u - u_max) < perim_eps
        on_bottom = abs(w - w_min) < perim_eps
        on_top    = abs(w - w_max) < perim_eps
        if not (on_left or on_right or on_bottom or on_top):
            interior_verts.append((idx, float(u), float(w)))

    want_positive = (axis != 1)
    outer_sign = (1.0 if want_positive else -1.0) * (1.0 if keep_below else -1.0)

    # If no interior verts, no cavity. Just cap the outer rectangle.
    if not interior_verts:
        outer_verts = [
            (idx, float(u), float(w))
            for idx, (u, w) in zip(on_plane_idx, pts)
        ]
        _emit_center_fan_cap(
            mesh, v, outer_verts, axis, cut, proj_axes,
            u_bounds=(u_min, u_max), w_bounds=(w_min, w_max),
            target_sign=outer_sign, perim_eps=perim_eps, group="cap_outer",
        )
        return

    # Cavity bounds.
    iu_min = min(u for (_, u, _) in interior_verts)
    iu_max = max(u for (_, u, _) in interior_verts)
    iw_min = min(w for (_, _, w) in interior_verts)
    iw_max = max(w for (_, _, w) in interior_verts)

    # Outer cap: the full footprint rectangle. All perimeter verts stay
    # at Z=cut and form the outer cap together with the centroid.
    outer_verts = []
    for idx, (u, w) in zip(on_plane_idx, pts):
        on_left   = abs(u - u_min) < perim_eps
        on_right  = abs(u - u_max) < perim_eps
        on_bottom = abs(w - w_min) < perim_eps
        on_top    = abs(w - w_max) < perim_eps
        if on_left or on_right or on_bottom or on_top:
            outer_verts.append((idx, float(u), float(w)))

    _emit_center_fan_cap(
        mesh, v, outer_verts, axis, cut, proj_axes,
        u_bounds=(u_min, u_max), w_bounds=(w_min, w_max),
        target_sign=outer_sign, perim_eps=perim_eps, group="cap_outer",
    )

    # Inner cavity cap: at Z=cut, normal facing into cavity. Coplanar with
    # outer cap, so literal wall thickness is zero — but visually the inner
    # cap hides the back-side of the outer cap when viewed from inside the
    # cavity. Real wall thickness needs slab-stacking from authored cells
    # (not implemented here).
    _emit_center_fan_cap(
        mesh, v, interior_verts, axis, cut, proj_axes,
        u_bounds=(iu_min, iu_max), w_bounds=(iw_min, iw_max),
        target_sign=-outer_sign, perim_eps=perim_eps, group="cap_inner",
    )


def _emit_center_fan_cap(
    mesh: Mesh,
    v: np.ndarray,
    rect_verts: List[Tuple[int, float, float]],
    axis: int,
    cut: float,
    proj_axes: List[int],
    u_bounds: Tuple[float, float],
    w_bounds: Tuple[float, float],
    target_sign: float,
    perim_eps: float,
    group: str,
) -> None:
    """Add a center-fan cap face group filling the rectangle defined by
    `rect_verts`. A new vertex is appended at the centroid; cap faces are
    triangles from the centroid to consecutive rect_vert pairs sorted CCW
    around the rectangle perimeter.
    """
    if len(rect_verts) < 3:
        return

    u_min, u_max = u_bounds
    w_min, w_max = w_bounds
    width = max(u_max - u_min, 1e-9)
    height = max(w_max - w_min, 1e-9)

    def perim_param(u, w):
        on_bottom = abs(w - w_min) < perim_eps
        on_right  = abs(u - u_max) < perim_eps
        on_top    = abs(w - w_max) < perim_eps
        on_left   = abs(u - u_min) < perim_eps
        if on_bottom:
            return (u - u_min) / width
        if on_right:
            return 1.0 + (w - w_min) / height
        if on_top:
            return 2.0 + (u_max - u) / width
        if on_left:
            return 3.0 + (w_max - w) / height
        return -1.0

    parts = []
    for (idx, u, w) in rect_verts:
        t = perim_param(u, w)
        if t >= 0:
            parts.append((t, idx))
    parts.sort()

    # Deduplicate consecutive same-index entries (corner verts).
    ordered: List[int] = []
    for t, idx in parts:
        if ordered and ordered[-1] == idx:
            continue
        ordered.append(idx)
    if len(ordered) < 3:
        return

    # Insert a centroid vertex.
    cu = 0.5 * (u_min + u_max)
    cw = 0.5 * (w_min + w_max)
    centroid_pos = [0.0, 0.0, 0.0]
    centroid_pos[axis] = cut
    centroid_pos[proj_axes[0]] = cu
    centroid_pos[proj_axes[1]] = cw
    new_idx = mesh.append_verts(np.array([centroid_pos], dtype=np.float64))

    # Build cap tris from centroid to each consecutive pair on the boundary,
    # plus the closing pair (last -> first).
    cap_faces = []
    n = len(ordered)
    for i in range(n):
        a = ordered[i]
        b = ordered[(i + 1) % n]
        cap_faces.append((new_idx, a, b))

    # Determine actual winding of one tri to decide if we need to flip.
    p0 = v[ordered[0]][proj_axes].astype(np.float64)
    p1 = v[ordered[1]][proj_axes].astype(np.float64)
    pc = np.array([cu, cw], dtype=np.float64)
    cross = (p0[0] - pc[0]) * (p1[1] - pc[1]) - (p0[1] - pc[1]) * (p1[0] - pc[0])
    if cross * target_sign < 0:
        cap_faces = [(c, b, a) for (a, b, c) in cap_faces]

    mesh.add_group_faces(group, cap_faces)


# ---------------------------------------------------------------------------
# Mesh assembly helpers
# ---------------------------------------------------------------------------


def _translate_mesh(mesh: Mesh, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> Mesh:
    """Translate every vertex in-place. Returns the same mesh for chaining."""
    mesh.flush()
    v = mesh.vertices
    v[:, 0] += dx
    v[:, 1] += dy
    v[:, 2] += dz
    return mesh


def _merge_meshes(*meshes: Mesh, weld_tol: float = 1e-3) -> Mesh:
    """Merge several meshes into one, welding coincident verts so shared
    boundaries fuse. Vertices preserved with face-index offsets."""
    out = Mesh()
    out.vertices = np.zeros((0, 3), dtype=np.float64)
    for m in meshes:
        m.flush()
        if len(m.vertices) == 0:
            continue
        out.merge(m)
    out.flush()
    out.weld_vertices(tol=weld_tol)
    return out


def _extend_along_axis(
    mesh: Mesh,
    ref_cells: int,
    target_cells: int,
    axis: int,
) -> Mesh:
    """Extend a brick mesh along an axis by tiling a single interior cell.

    Slices the source into:
      - front-corner = 1 cell at the start (cell 0).
      - interior     = 1 cell from the middle (cell 1).
      - back-corner  = 1 cell at the end (cell ref_cells - 1).
    Then assembles: front + (target - 2) copies of interior + back, with
    every slice translated to its target position. Welds at every seam.

    For uniform bricks, all cell-boundary cross-sections are identical by
    construction, so the seams weld cleanly with no open edges.

    Requires `ref_cells >= 3` so an interior cell exists.
    """
    if target_cells <= ref_cells:
        return mesh
    if ref_cells < 3:
        raise NotImplementedError(
            "Reference must have >=3 cells along axis {0} to extend".format(axis)
        )

    stud = _STUD_SIZE
    # Cell boundaries along the axis.
    front_boundary = stud           # end of cell 0
    interior_back_boundary = 2 * stud  # end of cell 1 (interior cell)
    back_front_boundary = (ref_cells - 1) * stud  # start of last cell

    front_piece = _slice_along_axis(
        _clone_mesh(mesh), axis=axis, cut=front_boundary,
        keep_below=True, cap=False,
    )
    interior = _slice_along_axis(
        _clone_mesh(mesh), axis=axis, cut=front_boundary,
        keep_below=False, cap=False,
    )
    interior = _slice_along_axis(
        interior, axis=axis, cut=interior_back_boundary,
        keep_below=True, cap=False,
    )
    back_piece = _slice_along_axis(
        _clone_mesh(mesh), axis=axis, cut=back_front_boundary,
        keep_below=False, cap=False,
    )

    interior_copies = target_cells - 2
    pieces = [front_piece]
    for i in range(interior_copies):
        m = _clone_mesh(interior)
        # Each interior copy starts at Z = stud + i*stud (cell i+1 of result).
        _translate_along_axis(m, axis=axis, delta=i * stud)
        pieces.append(m)

    # Back-corner piece originally starts at back_front_boundary; needs to
    # land at (target_cells - 1) * stud.
    target_back_start = (target_cells - 1) * stud
    _translate_along_axis(back_piece, axis=axis, delta=(target_back_start - back_front_boundary))
    pieces.append(back_piece)

    return _merge_meshes(*pieces, weld_tol=1e-3)


def _translate_along_axis(mesh: Mesh, axis: int, delta: float) -> Mesh:
    if axis == 0:
        return _translate_mesh(mesh, dx=delta)
    if axis == 1:
        return _translate_mesh(mesh, dy=delta)
    return _translate_mesh(mesh, dz=delta)


# ---------------------------------------------------------------------------
# High-level synthesis
# ---------------------------------------------------------------------------


def _scale_to_height(mesh: Mesh, target_h_plates: int, ref_h_plates: int) -> Mesh:
    """Stretch body verts in Y; shift studs to sit on the new body top.
    Body verts are those with Y <= ref_h_plates * plate_size.
    """
    if target_h_plates == ref_h_plates:
        return mesh
    mesh.flush()
    body_h_ref = ref_h_plates * _PLATE_SIZE
    body_h_target = target_h_plates * _PLATE_SIZE
    delta = body_h_target - body_h_ref
    scale = body_h_target / body_h_ref
    v = mesh.vertices
    is_body = v[:, 1] <= body_h_ref + 1e-6
    new_v = v.copy()
    new_v[is_body, 1] = v[is_body, 1] * scale
    new_v[~is_body, 1] = v[~is_body, 1] + delta
    mesh.vertices = new_v
    return mesh


def _remove_coincident_face_pairs(mesh: Mesh) -> int:
    """Find pairs of faces that share the same vertex set (regardless of
    winding order) and delete both. After welding identical-position verts
    together, adjacent cells' shared outer walls become such coincident
    pairs — deleting them removes the doubled walls between cells.
    Returns count of faces removed."""
    mesh.flush()
    by_key: Dict[Tuple[int, ...], List[int]] = {}
    for fi, face in enumerate(mesh.faces):
        key = tuple(sorted(face))
        by_key.setdefault(key, []).append(fi)
    to_drop: set = set()
    for indices in by_key.values():
        if len(indices) >= 2:
            # Two or more faces share the same vertex set → coincident.
            # Drop all of them (for normal brick tiling this will only ever
            # be exactly 2; >2 would indicate something odd, drop all).
            to_drop.update(indices)
    if not to_drop:
        return 0
    new_faces = []
    old_to_new: Dict[int, int] = {}
    for old_i, face in enumerate(mesh.faces):
        if old_i in to_drop:
            continue
        old_to_new[old_i] = len(new_faces)
        new_faces.append(face)
    new_groups: Dict[str, List[int]] = {}
    for g, idxs in mesh.groups.items():
        new_groups[g] = [old_to_new[i] for i in idxs if i in old_to_new]
    mesh.faces = new_faces
    mesh.groups = new_groups
    return len(to_drop)


def _synthesize_by_cell_tile(W: int, D: int, H: int) -> Mesh:
    """Tile the 1x1 cell reference W×D times, weld, remove coincident
    outer-wall pairs at cell boundaries AND the inter-cell solid material
    (cavity walls + rim sections within wall-thickness of cell boundaries)
    so the cavity is continuous through the assembled brick.
    Y-stretch the body for height. Returns a watertight assembled brick.
    """
    cell = _load_reference(_CELL_REF)
    cell.flush()
    out = Mesh()
    out.vertices = np.zeros((0, 3), dtype=np.float64)
    for i in range(W):
        for j in range(D):
            piece = _clone_mesh(cell)
            _translate_mesh(piece, dx=i * _STUD_SIZE, dz=j * _STUD_SIZE)
            out.merge(piece)
    out.flush()
    out.weld_vertices(tol=1e-3)

    # Delete internal cell-boundary material so the cavity is continuous.
    dropped = _delete_internal_partitions(out, W, D)
    # Fill the cavity ceiling gaps that opened up when we deleted the body
    # slab sides between cells.
    bridges = _add_cavity_ceiling_bridges(out, W, D)
    out.flush()
    out.weld_vertices(tol=1e-3)
    _brick_log(
        "[brick] OBJ proxy: cell-tile W={0} D={1} H={2} dropped {3}, bridged {4} ceiling gaps".format(
            W, D, H, dropped, bridges
        )
    )
    if H != _CELL_REF.height_plates:
        out = _scale_to_height(out, H, _CELL_REF.height_plates)
    return out


def _add_cavity_ceiling_bridges(mesh: Mesh, W: int, D: int) -> int:
    """Add quad bridges at each internal cell boundary on the cavity ceiling
    plane to close the gaps left by partition removal. Returns count of
    bridges added.
    """
    if W <= 1 and D <= 1:
        return 0
    wall_thickness = _estimate_wall_thickness_from_cell()
    if wall_thickness <= 1e-3:
        return 0

    # Figure out cavity_top_y from the cell reference.
    cell = _load_reference(_CELL_REF)
    cell.flush()
    cv = cell.vertices
    body_top_y = _CELL_REF.height_plates * _PLATE_SIZE
    # cavity_top_y: the unique Y where verts cluster at cavity inset (not
    # outer perimeter).
    outer_extent = _STUD_SIZE / 2.0  # but cell is corner-at-origin, so outer is 0/STUD
    cavity_top_y = None
    for y in sorted(set(round(float(yy), 3) for yy in cv[:, 1])):
        if y >= body_top_y - 0.05:
            continue
        if y <= 0.05:
            continue
        # Verts at this Y level: their X/Z extents.
        mask = np.abs(cv[:, 1] - y) < 0.05
        pts = cv[mask]
        if len(pts) == 0:
            continue
        xs_min = float(pts[:, 0].min())
        xs_max = float(pts[:, 0].max())
        # Cell is at corner-at-origin, so outer X is at 0 and stud_size.
        # Cavity inset would be at wt and stud_size - wt.
        if xs_min > wall_thickness * 0.5 and xs_max < _STUD_SIZE - wall_thickness * 0.5:
            cavity_top_y = y
            break
    if cavity_top_y is None:
        return 0

    stud = _STUD_SIZE
    wt = wall_thickness
    bridges = 0
    new_verts = []
    new_faces = []

    def emit_vert(x, y, z) -> int:
        new_verts.append((x, y, z))
        return len(new_verts) - 1

    # X bridges: at each internal X boundary k (0 < k < W), strip across
    # full cavity Z (Z from wt to D*stud - wt).
    for k in range(1, W):
        x_lo = k * stud - wt
        x_hi = k * stud + wt
        z_lo = wt
        z_hi = D * stud - wt
        a = emit_vert(x_lo, cavity_top_y, z_lo)
        b = emit_vert(x_hi, cavity_top_y, z_lo)
        c = emit_vert(x_hi, cavity_top_y, z_hi)
        d = emit_vert(x_lo, cavity_top_y, z_hi)
        new_faces.append((a, b, c, d))
        bridges += 1

    # Z bridges: at each internal Z boundary j (0 < j < D), strip across
    # full cavity X (X from wt to W*stud - wt).
    for j in range(1, D):
        z_lo = j * stud - wt
        z_hi = j * stud + wt
        x_lo = wt
        x_hi = W * stud - wt
        a = emit_vert(x_lo, cavity_top_y, z_lo)
        b = emit_vert(x_hi, cavity_top_y, z_lo)
        c = emit_vert(x_hi, cavity_top_y, z_hi)
        d = emit_vert(x_lo, cavity_top_y, z_hi)
        new_faces.append((a, b, c, d))
        bridges += 1

    if not new_faces:
        return 0

    # Add new verts to the mesh (offset face indices by current vert count).
    mesh.flush()
    base = mesh.num_verts
    mesh.append_verts(np.asarray(new_verts, dtype=np.float64))
    mesh.add_group_faces(
        "ceiling_bridge",
        [tuple(base + i for i in f) for f in new_faces],
    )
    return bridges


def _delete_internal_partitions(mesh: Mesh, W: int, D: int) -> int:
    """Delete faces inside the wall-thickness-wide strips at each internal
    cell boundary. This removes outer walls between cells, cavity walls
    facing those boundaries, and bottom-rim sections at cell boundaries —
    making the cavity continuous through the assembled brick.

    Detection: face's centroid is within wall_thickness of any internal
    cell-boundary plane (X=k*stud or Z=j*stud for 0<k<W, 0<j<D), AND the
    face is below the top face (Y < body_top - margin) so we don't delete
    the top or studs.

    Wall thickness is auto-detected from the reference cell: the smallest
    inset of cavity verts from the outer perimeter.
    """
    mesh.flush()
    v = mesh.vertices
    if len(v) == 0:
        return 0

    # Estimate body_top: the Y level just below where studs begin. For a
    # tiled brick with stud_height ≈ 1.76 above body_top, find the
    # densest-vertex Y plane that's not the stud top.
    # Simpler heuristic: body_top is at Y = ref.height_plates * plate_size
    # (= 6.4 for h2p ref). After cell-tile, that holds before Y stretch.
    body_top_y = _CELL_REF.height_plates * _PLATE_SIZE
    margin_y = 0.1

    # Estimate wall_thickness: the cell reference's outer extent minus
    # cavity inset. For the user's 1x1 ref, that's ~0.81 in BrickIt units.
    # Since we don't have explicit cavity bounds here, use a conservative
    # value derived from the ref: scan for the second-most-extreme X value
    # at Y=0 (rim layer) — the gap from outer to first inset.
    wall_thickness = _estimate_wall_thickness_from_cell()

    internal_x_bounds = [k * _STUD_SIZE for k in range(1, W)]
    internal_z_bounds = [j * _STUD_SIZE for j in range(1, D)]
    if not internal_x_bounds and not internal_z_bounds:
        return 0  # 1x1, no internal partitions

    strip_radius = wall_thickness * 1.1  # small slack for FP

    to_drop: set = set()
    for fi, face in enumerate(mesh.faces):
        pts = v[list(face)]
        cy = float(pts[:, 1].mean())
        if cy >= body_top_y - margin_y:
            continue  # skip top face + stud
        cx = float(pts[:, 0].mean())
        cz = float(pts[:, 2].mean())
        in_x_strip = any(abs(cx - b) < strip_radius for b in internal_x_bounds)
        in_z_strip = any(abs(cz - b) < strip_radius for b in internal_z_bounds)
        if in_x_strip or in_z_strip:
            to_drop.add(fi)

    if not to_drop:
        return 0

    new_faces = []
    old_to_new: Dict[int, int] = {}
    for old_i, face in enumerate(mesh.faces):
        if old_i in to_drop:
            continue
        old_to_new[old_i] = len(new_faces)
        new_faces.append(face)
    new_groups: Dict[str, List[int]] = {}
    for g, idxs in mesh.groups.items():
        new_groups[g] = [old_to_new[i] for i in idxs if i in old_to_new]
    mesh.faces = new_faces
    mesh.groups = new_groups
    return len(to_drop)


def _estimate_wall_thickness_from_cell() -> float:
    """Inspect the cell reference's vertex distribution at Y=body_bottom
    (rim layer) to derive wall thickness as outer-extent minus second-most-
    extreme X."""
    cell = _load_reference(_CELL_REF)
    cell.flush()
    v = cell.vertices
    rim_y = float(v[:, 1].min())
    rim_mask = np.abs(v[:, 1] - rim_y) < 0.1
    rim_pts = v[rim_mask]
    if len(rim_pts) == 0:
        return 0.81  # fallback
    xs = sorted(set(round(float(x), 3) for x in rim_pts[:, 0]))
    if len(xs) < 2:
        return 0.81
    # Outer X = xs[-1] (max), inset = xs[-2]. Wall thickness = outer - inset.
    return max(0.1, xs[-1] - xs[-2])


# ---------------------------------------------------------------------------
# Variant-based synthesis — load + classify the 4 top-piece variants, extract
# walls per side from the full 1x1 reference, dispatch per cell position.
# ---------------------------------------------------------------------------


def _parse_multi_obj(path: str) -> Dict[str, Mesh]:
    """Parse a multi-object OBJ. Returns dict {object_name: Mesh}, where each
    Mesh has its OWN local vertex indexing (subset of the global vert pool,
    only the verts referenced by that object's faces)."""
    verts_global = []
    object_faces: Dict[str, List[Tuple[int, ...]]] = {}
    current = None
    with open(path, "r") as f:
        for line in f:
            head = line[:2]
            if head == "v ":
                p = line.split()
                verts_global.append((float(p[1]), float(p[2]), float(p[3])))
            elif head == "o ":
                current = line[2:].strip()
                object_faces[current] = []
            elif head == "f " and current is not None:
                indices = []
                for tok in line.split()[1:]:
                    indices.append(int(tok.split("/", 1)[0]) - 1)
                object_faces[current].append(tuple(indices))

    out: Dict[str, Mesh] = {}
    for name, faces in object_faces.items():
        if not faces:
            continue
        used = sorted(set(v for f in faces for v in f))
        old_to_new = {old: new for new, old in enumerate(used)}
        local_verts = np.array([verts_global[v] for v in used], dtype=np.float64)
        local_faces = [tuple(old_to_new[v] for v in face) for face in faces]
        m = Mesh()
        m.vertices = local_verts
        m.add_group_faces("body", local_faces)
        out[name] = m
    return out


def _rotate_mesh_y_deg(mesh: Mesh, deg: int) -> Mesh:
    """Rotate mesh around Y axis (CCW from +Y). Mutates and returns mesh.
    For deg in {0, 90, 180, 270} this preserves vertex positions exactly
    (no float rounding) so welds at cell boundaries stay aligned.
    Convention: (X, Y, Z) -> (Z, Y, -X) at +90°.
    """
    deg = int(deg) % 360
    if deg == 0:
        return mesh
    mesh.flush()
    v = mesh.vertices
    new_v = v.copy()
    if deg == 90:
        new_v[:, 0] = v[:, 2]
        new_v[:, 2] = -v[:, 0]
    elif deg == 180:
        new_v[:, 0] = -v[:, 0]
        new_v[:, 2] = -v[:, 2]
    elif deg == 270:
        new_v[:, 0] = -v[:, 2]
        new_v[:, 2] = v[:, 0]
    else:
        raise ValueError("rotation must be in {0, 90, 180, 270}")
    mesh.vertices = new_v
    return mesh


def _classify_variant(
    mesh: Mesh, body_top_y: float, cavity_top_y: float, outer_extent: float,
) -> Tuple[Optional[str], int]:
    """Identify a variant by which sides have cavity ceiling INSET (= walls).

    Returns (variant_name, rotation_to_canonical) where applying
    `rotation_to_canonical` to `mesh` aligns its wall configuration to the
    canonical orientation:
      - 'edge'    : wall on -X.
      - 'corner'  : walls on -X, -Z (adjacent).
      - 'tunnel'  : walls on -X, +X (parallel).
      - 'end_cap' : walls on -X, +X, -Z (open +Z).
      - 'interior': no walls.
    """
    mesh.flush()
    v = mesh.vertices
    eps_y = 0.05

    # Find verts at Y == cavity_top (the cavity ceiling layer).
    cv_mask = np.abs(v[:, 1] - cavity_top_y) < eps_y
    cv = v[cv_mask]
    if len(cv) == 0:
        return None, 0

    cu_min = float(cv[:, 0].min()); cu_max = float(cv[:, 0].max())
    cw_min = float(cv[:, 2].min()); cw_max = float(cv[:, 2].max())

    # The brick's outer extent is at ±outer_extent in centered frame. After
    # any centering, the outer perimeter X/Z is at ±outer_extent.
    inset_eps = outer_extent * 0.1  # ~10% of outer extent
    inset_minus_x = (cu_min - (-outer_extent)) > inset_eps
    inset_plus_x = (outer_extent - cu_max) > inset_eps
    inset_minus_z = (cw_min - (-outer_extent)) > inset_eps
    inset_plus_z = (outer_extent - cw_max) > inset_eps

    walls = set()
    if inset_minus_x:
        walls.add("-X")
    if inset_plus_x:
        walls.add("+X")
    if inset_minus_z:
        walls.add("-Z")
    if inset_plus_z:
        walls.add("+Z")

    n = len(walls)
    if n == 0:
        return "interior", 0
    if n == 1:
        s = next(iter(walls))
        # Canonical wall is -X. Rotation to bring s to -X.
        # Rotation that sends +X→-X is 180; -Z→-X is 90; +Z→-X is 270.
        rot_map = {"-X": 0, "+X": 180, "-Z": 90, "+Z": 270}
        return "edge", rot_map[s]
    if n == 2:
        if walls == {"-X", "+X"}:
            return "tunnel", 0
        if walls == {"-Z", "+Z"}:
            return "tunnel", 90  # rotate 90° to bring -Z,+Z onto -X,+X
        # Adjacent corner. Canonical {-X, -Z}.
        # Find rotation mapping authored walls onto {-X, -Z}.
        rot_map_corner = {
            frozenset({"-X", "-Z"}): 0,
            frozenset({"-X", "+Z"}): 270,
            frozenset({"+X", "+Z"}): 180,
            frozenset({"+X", "-Z"}): 90,
        }
        return "corner", rot_map_corner[frozenset(walls)]
    if n == 3:
        # End-cap. Canonical walls -X, +X, -Z (open +Z).
        open_side = ({"-X", "+X", "-Z", "+Z"} - walls).pop()
        # Rotation that brings open_side to +Z (canonical open).
        rot_map_endcap = {"+Z": 0, "+X": 270, "-Z": 180, "-X": 90}
        return "end_cap", rot_map_endcap[open_side]
    return None, 0


def _center_xz(mesh: Mesh) -> Mesh:
    """Translate mesh so X/Z are centered at origin; Y unchanged."""
    mesh.flush()
    v = mesh.vertices.copy()
    cx = 0.5 * (v[:, 0].min() + v[:, 0].max())
    cz = 0.5 * (v[:, 2].min() + v[:, 2].max())
    v[:, 0] -= cx
    v[:, 2] -= cz
    mesh.vertices = v
    return mesh


def _scale_calibrate(mesh: Mesh, target_dim: float) -> Mesh:
    """Scale mesh so its X span equals target_dim (in BrickIt units)."""
    mesh.flush()
    v = mesh.vertices.copy()
    span = float(v[:, 0].max() - v[:, 0].min())
    if span <= 1e-9:
        return mesh
    scale = target_dim / span
    v *= scale
    mesh.vertices = v
    return mesh


def _load_and_classify_variants() -> Dict[str, Mesh]:
    """Parse the multi-object OBJ, identify each variant by inset pattern,
    rotate each to its canonical orientation, return dict by variant name.
    Each variant is centered in X/Z (at origin) and scaled so the cell is
    8x8 BrickIt units. Y is in centered frame (body bottom at -plate_size,
    body top at +plate_size for h2p)."""
    path = os.path.join(_plugin_root(), _VARIANTS_OBJ_REL)
    objects = _parse_multi_obj(path)

    out: Dict[str, Mesh] = {}
    for name, m in objects.items():
        m = _center_xz(m)
        m = _scale_calibrate(m, _STUD_SIZE)
        # Compute reference Y values from this mesh's Y extents.
        v = m.vertices
        y_min = float(v[:, 1].min())
        y_max = float(v[:, 1].max())
        # Top face is the 2nd-highest Y cluster (below stud top).
        # For our refs: body_top ~ +plate_size, cavity_top is a bit below.
        # Use known design: body_top is at the layer with most outer-perim
        # verts; cavity_top is the LOWEST Y (since these top-piece variants
        # only have Y ∈ [cavity_top, stud_top]).
        body_top_y = _PLATE_SIZE  # h2p: body extends [-plate, +plate]
        cavity_top_y = y_min  # the cavity ceiling layer
        outer_extent = _STUD_SIZE / 2.0  # = 4.0
        variant, rot = _classify_variant(m, body_top_y, cavity_top_y, outer_extent)
        if variant is None:
            continue
        if rot != 0:
            _rotate_mesh_y_deg(m, rot)
        if variant in out:
            _brick_log(
                "[brick] OBJ proxy: duplicate variant '{0}' from object '{1}'".format(
                    variant, name
                )
            )
        out[variant] = m
    _brick_log(
        "[brick] OBJ proxy: loaded variants: {0}".format(sorted(out.keys()))
    )
    return out


def _extract_walls_per_side_from_ref1() -> Dict[str, Mesh]:
    """From the full 1x1 reference, extract wall material (walls + rim +
    body slab side, excluding top face / cavity ceiling / stud) split by
    side. Returns dict {'-X': mesh, '+X': mesh, '-Z': mesh, '+Z': mesh}.

    Each mesh is centered at origin in X/Z (matching the variant frames),
    scaled to BrickIt stud_size, and contains the wall material on that
    side (classified by face centroid's dominant axis).
    """
    ref1_path = os.path.join(_plugin_root(), _FULL_REF_OBJ_REL)
    raw = _parse_obj(ref1_path)
    raw = _center_xz(raw)
    raw = _scale_calibrate(raw, _STUD_SIZE)

    raw.flush()
    v = raw.vertices
    body_top_y = _PLATE_SIZE  # h2p
    cavity_top_eps = 0.05

    # Identify cavity ceiling Y empirically: the unique Y where verts are
    # at the cavity inset (X/Z distance from origin < outer_extent - 0.1).
    outer_extent = _STUD_SIZE / 2.0
    cavity_top_y = None
    for y in sorted(set(round(float(yy), 3) for yy in v[:, 1])):
        mask = np.abs(v[:, 1] - y) < cavity_top_eps
        pts = v[mask]
        if len(pts) == 0:
            continue
        max_radial = float(np.max(np.abs(pts[:, [0, 2]])))
        if max_radial < outer_extent - 0.1 and y < body_top_y - 0.1:
            cavity_top_y = y
            break

    # Build wall_faces excluding top face, ceiling, stud.
    wall_faces = []
    for face in raw.faces:
        ys = [float(v[i, 1]) for i in face]
        # Skip top face / stud (all verts at body_top or above).
        if min(ys) >= body_top_y - 0.05:
            continue
        # Skip cavity ceiling (planar at cavity_top, all verts at ±inset).
        if cavity_top_y is not None:
            if max(ys) - min(ys) < 0.05 and abs(ys[0] - cavity_top_y) < 0.05:
                # Verify all verts are at cavity inset (not at outer perimeter).
                all_inset = all(
                    max(abs(float(v[i, 0])), abs(float(v[i, 2])))
                    < outer_extent - 0.1
                    for i in face
                )
                if all_inset:
                    continue
        wall_faces.append(face)

    # Classify each wall face into a side by centroid dominant axis.
    sides: Dict[str, List[Tuple[int, ...]]] = {"-X": [], "+X": [], "-Z": [], "+Z": []}
    for face in wall_faces:
        pts = v[list(face)]
        cx = float(pts[:, 0].mean())
        cz = float(pts[:, 2].mean())
        if abs(cx) >= abs(cz):
            sides["-X" if cx <= 0 else "+X"].append(face)
        else:
            sides["-Z" if cz <= 0 else "+Z"].append(face)

    # Build per-side Meshes with local vert renumbering.
    out: Dict[str, Mesh] = {}
    for key, faces in sides.items():
        if not faces:
            out[key] = Mesh()
            out[key].vertices = np.zeros((0, 3), dtype=np.float64)
            continue
        used = sorted(set(i for face in faces for i in face))
        old_to_new = {old: new for new, old in enumerate(used)}
        local_verts = v[used].copy()
        local_faces = [tuple(old_to_new[i] for i in face) for face in faces]
        m = Mesh()
        m.vertices = local_verts
        m.add_group_faces("wall_" + key, local_faces)
        out[key] = m
    return out


def _get_variants_cache() -> Dict[str, Mesh]:
    global _VARIANTS_CACHE
    if _VARIANTS_CACHE is None:
        _VARIANTS_CACHE = _load_and_classify_variants()
    return _VARIANTS_CACHE


def _get_walls_cache() -> Dict[str, Mesh]:
    global _WALLS_PER_SIDE_CACHE
    if _WALLS_PER_SIDE_CACHE is None:
        _WALLS_PER_SIDE_CACHE = _extract_walls_per_side_from_ref1()
    return _WALLS_PER_SIDE_CACHE


def _classify_cell_position(i: int, j: int, W: int, D: int) -> Tuple[str, int]:
    """Given cell (i, j) in a WxD grid, return (variant_name, rotation_deg).
    The rotation is what we apply to the canonical-oriented variant to
    place it correctly at cell (i, j).
    """
    is_left, is_right = (i == 0), (i == W - 1)
    is_front, is_back = (j == 0), (j == D - 1)

    if W == 1 and D == 1:
        return "full", 0
    if W == 1:
        if is_front:
            return "endcap", 0  # canonical end-cap walls -X+X-Z, open +Z
        if is_back:
            return "endcap", 180
        return "tunnel", 0
    if D == 1:
        if is_left:
            return "endcap", 90  # rotate so open faces +X
        if is_right:
            return "endcap", 270
        return "tunnel", 90  # rotate tunnel so walls run along Z

    # W>=2, D>=2.
    n_outward = sum((is_left, is_right, is_front, is_back))
    if n_outward == 0:
        return "interior", 0
    if n_outward == 2:
        # Corner. Canonical {-X, -Z}.
        if is_left and is_front:
            return "corner", 0
        if is_left and is_back:
            return "corner", 90
        if is_right and is_back:
            return "corner", 180
        if is_right and is_front:
            return "corner", 270
    if n_outward == 1:
        # Edge. Canonical wall on -X.
        if is_left:
            return "edge", 0
        if is_back:
            return "edge", 90
        if is_right:
            return "edge", 180
        if is_front:
            return "edge", 270
    raise ValueError(
        "Unexpected outward count {0} at ({1}, {2}) in {3}x{4}".format(
            n_outward, i, j, W, D
        )
    )


def _wall_sides_for_variant_at_rotation(variant: str, rotation: int) -> List[str]:
    """Return the absolute-frame wall sides (in {-X,+X,-Z,+Z}) for a
    variant placed at the given rotation."""
    canonical = {
        "edge": ["-X"],
        "corner": ["-X", "-Z"],
        "tunnel": ["-X", "+X"],
        "endcap": ["-X", "+X", "-Z"],
        "interior": [],
        "full": ["-X", "+X", "-Z", "+Z"],
    }.get(variant, [])
    # Rotate each side around Y by `rotation` degrees.
    # +90 sends -X→+Z, +X→-Z, -Z→-X, +Z→+X (per the (X,Y,Z)→(Z,Y,-X) matrix).
    # Wait — which convention. Using same matrix as _rotate_mesh_y_deg:
    #   (X, Y, Z) → (Z, Y, -X). Vector +X=(1,0,0) → (0,0,-1) = -Z.
    # So at +90°: +X→-Z, -X→+Z, +Z→+X, -Z→-X.
    rotmap = {
        0: {"-X": "-X", "+X": "+X", "-Z": "-Z", "+Z": "+Z"},
        90: {"-X": "+Z", "+X": "-Z", "-Z": "-X", "+Z": "+X"},
        180: {"-X": "+X", "+X": "-X", "-Z": "+Z", "+Z": "-Z"},
        270: {"-X": "-Z", "+X": "+Z", "-Z": "+X", "+Z": "-X"},
    }
    rot = rotation % 360
    return [rotmap[rot][s] for s in canonical]


def _synthesize_by_variants(W: int, D: int, H: int) -> Mesh:
    """Variant-based synthesizer: places the right top-piece variant at each
    cell position, plus the corresponding wall sides extracted from ref 1.
    Produces a continuous-cavity brick (no internal partitions).
    """
    variants = _get_variants_cache()
    walls = _get_walls_cache()
    out = Mesh()
    out.vertices = np.zeros((0, 3), dtype=np.float64)

    for i in range(W):
        for j in range(D):
            variant, rotation = _classify_cell_position(i, j, W, D)

            # Place variant top piece (or full ref for 1x1).
            if variant == "full":
                cell = _load_reference(_CELL_REF)  # full 1x1 with 4 walls
            elif variant == "interior":
                cell = _clone_mesh(variants.get("interior") or _make_empty_interior())
            else:
                cell = _clone_mesh(variants[variant])

            if rotation != 0:
                _rotate_mesh_y_deg(cell, rotation)

            # Translate to cell grid position. Cells are centered in their
            # local frame (0 at cell center); world cell center is
            # ((i+0.5)*stud, *, (j+0.5)*stud). For the load_reference path
            # which reframes corner-at-origin, adjust accordingly.
            cell.flush()
            cv = cell.vertices
            cell_min_x = float(cv[:, 0].min())
            cell_min_z = float(cv[:, 2].min())
            target_min_x = i * _STUD_SIZE
            target_min_z = j * _STUD_SIZE
            _translate_mesh(
                cell,
                dx=target_min_x - cell_min_x,
                dz=target_min_z - cell_min_z,
            )
            out.merge(cell)

            # Place wall sides for this variant.
            if variant != "full":
                for side in _wall_sides_for_variant_at_rotation(variant, rotation):
                    wall = _clone_mesh(walls[side])
                    wall.flush()
                    wv = wall.vertices
                    wall_min_x = float(wv[:, 0].min())
                    wall_min_z = float(wv[:, 2].min())
                    _translate_mesh(
                        wall,
                        dx=target_min_x - wall_min_x,
                        dz=target_min_z - wall_min_z,
                    )
                    out.merge(wall)

    out.flush()
    out.weld_vertices(tol=1e-3)
    # Translate to corner-at-origin Y frame so _scale_to_height works.
    out.flush()
    yv = out.vertices
    y_min = float(yv[:, 1].min())
    if abs(y_min) > 1e-6:
        new_v = yv.copy()
        new_v[:, 1] -= y_min
        out.vertices = new_v
    if H != _CELL_REF.height_plates:
        out = _scale_to_height(out, H, _CELL_REF.height_plates)
    return out


def _align_xz_for_variant(mesh: Mesh) -> Mesh:
    """Align a piece in X/Z. If a piece has full cell width (>= half stud
    span), center it at origin. If it's a thin slab (less than half), snap
    its outer edge to the canonical ±4.942 (in OBJ frame) based on which
    side it's on (sign of bbox center)."""
    mesh.flush()
    v = mesh.vertices.copy()
    # Use the OBJ-frame canonical extent (1 stud wide ≈ 9.884 OBJ units).
    cell_outer_obj = 4.942
    threshold = cell_outer_obj  # span >= 2*threshold/2 => full width

    x_min, x_max = float(v[:, 0].min()), float(v[:, 0].max())
    z_min, z_max = float(v[:, 2].min()), float(v[:, 2].max())
    x_span = x_max - x_min
    z_span = z_max - z_min

    if x_span >= threshold:
        v[:, 0] -= 0.5 * (x_min + x_max)
    else:
        # Thin slab in X — snap outer to ±cell_outer_obj.
        if 0.5 * (x_min + x_max) < 0:
            v[:, 0] += -cell_outer_obj - x_min
        else:
            v[:, 0] += cell_outer_obj - x_max

    if z_span >= threshold:
        v[:, 2] -= 0.5 * (z_min + z_max)
    else:
        if 0.5 * (z_min + z_max) < 0:
            v[:, 2] += -cell_outer_obj - z_min
        else:
            v[:, 2] += cell_outer_obj - z_max

    mesh.vertices = v
    return mesh


def _snap_to_canonical_grid(mesh: Mesh, wall_thickness: float = 0.81) -> Mesh:
    """Snap vertex X/Y/Z to canonical cell-grid positions. Eliminates small
    modeling-imprecision gaps so adjacent cells weld cleanly when tiled.
    """
    mesh.flush()
    v = mesh.vertices.copy()
    cell_outer = _STUD_SIZE / 2.0  # = 4.0 in BrickIt units
    cavity_inset = cell_outer - wall_thickness  # ≈ 3.19

    # Targets include 0 (cell center) so mid-cell subdivision verts that
    # the modeler placed at slight FP offsets (e.g. 0.0688, -0.0014) snap
    # to exactly 0 — required for clean welds across cell boundaries when
    # neighboring cells are placed at different Y rotations.
    xz_targets = (
        -cell_outer, cell_outer,
        -cavity_inset, cavity_inset,
        0.0,
    )
    snap_eps = wall_thickness * 0.4
    for axis in (0, 2):
        for target in xz_targets:
            mask = np.abs(v[:, axis] - target) < snap_eps
            v[mask, axis] = target

    # Y snap to body_bottom, body_top, cavity_top, stud_top in centered frame.
    plate = _PLATE_SIZE
    stud_h = _STUD_SIZE * 0.55 * plate / _STUD_SIZE  # ≈ 1.76
    # Centered frame: body extends -plate to +plate (h2p ref).
    cavity_top_ratio = 2.754 / 6.708  # in OBJ Y range
    cavity_top_y = -plate + cavity_top_ratio * (2 * plate)
    y_targets = (
        -plate,                # body bottom
        plate,                 # body top
        cavity_top_y,          # cavity ceiling
        plate + stud_h,        # stud top
    )
    y_eps = 0.1
    for target in y_targets:
        mask = np.abs(v[:, 1] - target) < y_eps
        v[mask, 1] = target

    mesh.vertices = v
    return mesh


def _load_v4_variants() -> Dict[str, Mesh]:
    """Load 4 complete variant pieces from the user-authored
    `brick_1x1_Proxy_Pieces.obj` file. Each named object is a full
    1x1 brick with the appropriate wall configuration. Returns dict
    keyed by canonical variant name ('edge', 'corner', 'tunnel',
    'endcap'), each Mesh in canonical orientation in BrickIt units
    (X/Z centered).
    """
    path = os.path.join(_plugin_root(), _PIECES_OBJ_REL)
    objects = _parse_multi_obj(path)

    # Map possible authored names to canonical lowercase names.
    name_map = {
        "Edge": "edge", "edge": "edge",
        "Corner": "corner", "corner": "corner",
        "Tunnel": "tunnel", "tunnel": "tunnel",
        "Endcap": "endcap", "endcap": "endcap", "EndCap": "endcap", "End_Cap": "endcap",
    }

    variants: Dict[str, Mesh] = {}
    for authored_name, mesh in objects.items():
        canonical = name_map.get(authored_name)
        if canonical is None:
            continue

        m = _center_xz(mesh)
        m.flush()
        v = m.vertices
        x_span = float(v[:, 0].max() - v[:, 0].min())
        if x_span <= 1e-9:
            continue
        scale = _STUD_SIZE / x_span
        v_scaled = v.copy()
        v_scaled *= scale
        m.vertices = v_scaled

        # Snap to canonical grid to absorb modeling FP noise.
        wall_thickness_brickit = (1.0 / 9.884) * _STUD_SIZE
        _snap_to_canonical_grid(m, wall_thickness=wall_thickness_brickit)
        m.weld_vertices(tol=1e-3)

        combined = m

        # Identify wall sides via inset pattern at cavity ceiling Y.
        cavity_top_y = 2.754 * scale  # ≈ 2.23 BrickIt
        outer_extent = _STUD_SIZE / 2.0
        vy = combined.vertices[:, 1]
        v_at = combined.vertices[np.abs(vy - cavity_top_y) < 0.1]
        sides: set = set()
        if len(v_at) > 0:
            cu_min = float(v_at[:, 0].min()); cu_max = float(v_at[:, 0].max())
            cw_min = float(v_at[:, 2].min()); cw_max = float(v_at[:, 2].max())
            inset_eps = outer_extent * 0.1
            if cu_min - (-outer_extent) > inset_eps:
                sides.add("-X")
            if outer_extent - cu_max > inset_eps:
                sides.add("+X")
            if cw_min - (-outer_extent) > inset_eps:
                sides.add("-Z")
            if outer_extent - cw_max > inset_eps:
                sides.add("+Z")

        # Determine rotation needed to match canonical.
        rot = 0
        if canonical == "edge":
            if "+X" in sides and len(sides) == 1:
                rot = 180
            elif "-Z" in sides and len(sides) == 1:
                rot = 90
            elif "+Z" in sides and len(sides) == 1:
                rot = 270
        elif canonical == "corner":
            if sides == {"-X", "+Z"}:
                rot = 270
            elif sides == {"+X", "+Z"}:
                rot = 180
            elif sides == {"+X", "-Z"}:
                rot = 90
        elif canonical == "tunnel":
            if sides == {"-Z", "+Z"}:
                rot = 90
        elif canonical == "endcap":
            # Canonical: walls -X+X-Z, open +Z.
            open_set = {"-X", "+X", "-Z", "+Z"} - sides
            if open_set == {"+X"}:
                rot = 90
            elif open_set == {"-Z"}:
                rot = 180
            elif open_set == {"-X"}:
                rot = 270

        if rot != 0:
            _rotate_mesh_y_deg(combined, rot)

        variants[canonical] = combined
        _brick_log(
            "[brick] OBJ proxy: V4 loaded variant '{0}' ({1} verts, {2} faces, sides={3}, rot={4})".format(
                canonical, len(combined.vertices), len(combined.faces),
                sorted(sides), rot,
            )
        )

    return variants


def _get_v4_variants() -> Dict[str, Mesh]:
    global _V4_VARIANTS_CACHE
    if _V4_VARIANTS_CACHE is None:
        _V4_VARIANTS_CACHE = _load_v4_variants()
    return _V4_VARIANTS_CACHE


def _synthesize_by_v4_variants(W: int, D: int, H: int) -> Mesh:
    """V4: place complete variant pieces (top + walls) per cell, rotated.
    Welds at cell boundaries to produce continuous geometry."""
    variants = _get_v4_variants()
    if not variants:
        raise RuntimeError("V4: no variants loaded")

    out = Mesh()
    out.vertices = np.zeros((0, 3), dtype=np.float64)

    for i in range(W):
        for j in range(D):
            variant_name, rotation = _classify_cell_position(i, j, W, D)

            if variant_name == "full":
                cell = _load_reference(_CELL_REF)  # full 1x1 standalone
            elif variant_name == "interior":
                # Use ref 2 (top piece, no walls).
                ref2_path = os.path.join(_plugin_root(), "library/brick_1x1_top_h2p.obj")
                cell_raw = _parse_obj(ref2_path)
                cell = _reframe_for_brickit(cell_raw, _Reference("top_only", "", 1, 1, 2))
            else:
                if variant_name not in variants:
                    raise RuntimeError("V4: missing variant '{0}'".format(variant_name))
                cell = _clone_mesh(variants[variant_name])

            if rotation != 0:
                _rotate_mesh_y_deg(cell, rotation)

            # Translate to cell grid position. Cells from V4 are X/Z
            # centered (Y in centered frame too). Translate so cell's
            # min(X, Z) lands at (i*stud, j*stud) absolute.
            cell.flush()
            cv = cell.vertices
            target_min_x = i * _STUD_SIZE
            target_min_z = j * _STUD_SIZE
            cell_min_x = float(cv[:, 0].min())
            cell_min_z = float(cv[:, 2].min())
            _translate_mesh(
                cell,
                dx=target_min_x - cell_min_x,
                dz=target_min_z - cell_min_z,
            )
            out.merge(cell)

    out.flush()
    out.weld_vertices(tol=1e-3)

    # Translate to corner-at-origin Y frame.
    out.flush()
    yv = out.vertices
    y_min = float(yv[:, 1].min())
    if abs(y_min) > 1e-6:
        new_v = yv.copy()
        new_v[:, 1] -= y_min
        out.vertices = new_v

    if H != _CELL_REF.height_plates:
        out = _scale_to_height(out, H, _CELL_REF.height_plates)
    return out


def _make_empty_interior() -> Mesh:
    """Fallback if interior variant isn't loaded — empty mesh."""
    m = Mesh()
    m.vertices = np.zeros((0, 3), dtype=np.float64)
    return m


def _select_reference(W: int, D: int) -> _Reference:
    """Pick the reference that best matches the requested footprint.

    Strategy: prefer exact W match; among those prefer exact D; otherwise
    use the closest W. (D is easy to trim/extend; W is harder because we
    don't extend X — would need a wider reference.)
    """
    by_priority = []
    for ref in _REFERENCES:
        score = (
            0 if ref.width_studs == W else 1,
            abs(ref.width_studs - W),
            0 if ref.depth_studs == D else 1,
            abs(ref.depth_studs - D),
        )
        by_priority.append((score, ref))
    by_priority.sort(key=lambda x: x[0])
    return by_priority[0][1]


# ---------------------------------------------------------------------------
# V5 — 5-piece synthesis. The user authored five 1x1 cell pieces — Corner,
# Edge, Tunnel, Endcap, Center_Fill — in canonical orientation. We tile the
# brick by classifying each cell against its position in the W×D grid and
# placing the right piece with the right rotation. No trimming, no cavity
# walls. 1x1 is a special case that uses the full walls-on-all-sides
# reference brick (`brick_1x1_h2p.obj`).
#
# Canonical orientations:
#   - corner       : walls on -X, -Z (L-shape)
#   - edge         : wall on -X
#   - tunnel       : walls on -X, +X (cavity open on -Z and +Z)
#   - endcap       : walls on -X, +X, -Z (cavity open on +Z)
#   - center_fill  : no walls / no rim — top + cavity ceiling + stud
# ---------------------------------------------------------------------------


def _orient_faces_consistently(mesh: Mesh) -> Mesh:
    """Propagate winding via face-edge adjacency so all faces in a connected
    component have consistent orientation, then flip globally if the
    longest-from-centroid face is back-facing. Required because the
    authored OBJ pieces have inconsistent face winding within each piece.
    """
    mesh.flush()
    n = len(mesh.faces)
    if n == 0:
        return mesh

    # edge_map: undirected_edge_key -> list of (face_idx, directed_edge_tuple)
    edge_map: Dict[Tuple[int, int], List[Tuple[int, Tuple[int, int]]]] = {}
    for fi, face in enumerate(mesh.faces):
        m = len(face)
        for i in range(m):
            a, b = face[i], face[(i + 1) % m]
            key = (min(a, b), max(a, b))
            edge_map.setdefault(key, []).append((fi, (a, b)))

    flipped = [False] * n
    visited = [False] * n
    for start in range(n):
        if visited[start]:
            continue
        visited[start] = True
        stack = [start]
        while stack:
            cur = stack.pop()
            cur_face = mesh.faces[cur]
            if flipped[cur]:
                cur_face = tuple(reversed(cur_face))
            mlen = len(cur_face)
            for i in range(mlen):
                a, b = cur_face[i], cur_face[(i + 1) % mlen]
                key = (min(a, b), max(a, b))
                for nb_fi, (na, nb) in edge_map.get(key, []):
                    if nb_fi == cur or visited[nb_fi]:
                        continue
                    nb_dir_in_cur_view = (na, nb) if not flipped[nb_fi] else (nb, na)
                    # Consistent winding: nb traverses (b, a). Same direction
                    # as cur (a, b) → inconsistent → must flip nb.
                    if nb_dir_in_cur_view == (a, b):
                        flipped[nb_fi] = not flipped[nb_fi]
                    visited[nb_fi] = True
                    stack.append(nb_fi)

    new_faces = [
        tuple(reversed(f)) if flipped[fi] else f
        for fi, f in enumerate(mesh.faces)
    ]

    # Decide whether to globally flip: find an outer-perimeter face (one
    # with the largest |position - centroid|) and check if its normal points
    # outward.
    v = mesh.vertices
    centroid = v.mean(axis=0)
    best_dist = -1.0
    best_dot = 0.0
    for fi, face in enumerate(new_faces):
        if len(face) < 3:
            continue
        p0 = v[face[0]]
        p1 = v[face[1]]
        p2 = v[face[2]]
        normal = np.cross(p1 - p0, p2 - p0)
        nl = float(np.linalg.norm(normal))
        if nl < 1e-9:
            continue
        face_center = v[list(face)].mean(axis=0)
        outward = face_center - centroid
        ol = float(np.linalg.norm(outward))
        if ol > best_dist:
            best_dist = ol
            best_dot = float(np.dot(normal / nl, outward / max(ol, 1e-9)))

    if best_dot < 0:
        new_faces = [tuple(reversed(f)) for f in new_faces]

    mesh.faces = new_faces
    return mesh


def _load_five_pieces() -> Dict[str, Mesh]:
    """Parse `brick_1x1_Proxy_Pieces_V3.obj`, scale-calibrate so each piece's
    X span equals stud_size, center each in X/Z, snap to canonical grid.
    Pieces are already authored in canonical orientation per the comment
    block above.
    """
    path = os.path.join(_plugin_root(), _FIVE_PIECES_OBJ_REL)
    objects = _parse_multi_obj(path)
    name_map = {
        "Corner": "corner", "corner": "corner",
        "Edge": "edge", "edge": "edge",
        "Tunnel": "tunnel", "tunnel": "tunnel",
        "Endcap": "endcap", "endcap": "endcap", "EndCap": "endcap",
        "Center_Fill": "center_fill", "center_fill": "center_fill",
        "CenterFill": "center_fill", "Center": "center_fill",
    }
    out: Dict[str, Mesh] = {}
    wall_thickness_brickit = (1.0 / 9.884) * _STUD_SIZE  # ≈ 0.81
    for authored, mesh in objects.items():
        canonical = name_map.get(authored)
        if canonical is None:
            continue
        m = _center_xz(mesh)
        m.flush()
        v = m.vertices
        x_span = float(v[:, 0].max() - v[:, 0].min())
        if x_span <= 1e-9:
            continue
        scale = _STUD_SIZE / x_span
        v_scaled = v.copy() * scale
        m.vertices = v_scaled
        _snap_to_canonical_grid(m, wall_thickness=wall_thickness_brickit)
        m.weld_vertices(tol=1e-3)
        _orient_faces_consistently(m)
        out[canonical] = m
        _brick_log(
            "[brick] OBJ proxy V5: loaded '{0}' ({1} verts, {2} faces)".format(
                canonical, len(m.vertices), len(m.faces)
            )
        )
    missing = {"corner", "edge", "tunnel", "endcap", "center_fill"} - set(out.keys())
    if missing:
        raise RuntimeError("V5: missing piece(s) {0}".format(sorted(missing)))
    return out


def _get_five_pieces() -> Dict[str, Mesh]:
    global _FIVE_PIECES_CACHE
    if _FIVE_PIECES_CACHE is None:
        _FIVE_PIECES_CACHE = _load_five_pieces()
    return _FIVE_PIECES_CACHE


def _classify_cell_5piece(i: int, j: int, W: int, D: int) -> Tuple[str, int]:
    """For a cell in a W×D grid (W>=1, D>=1, but not 1x1), return (piece_name,
    rotation_deg). Caller must handle 1x1 separately."""
    is_left, is_right = (i == 0), (i == W - 1)
    is_front, is_back = (j == 0), (j == D - 1)

    if W == 1:
        # Cell is 1-stud-wide. Both -X and +X are outer walls.
        if is_front:
            return "endcap", 0   # canonical -X+X-Z, open +Z
        if is_back:
            return "endcap", 180  # rotate so open faces -Z
        return "tunnel", 0  # canonical -X+X, open -Z+Z
    if D == 1:
        if is_left:
            return "endcap", 90   # rotate so open faces +X
        if is_right:
            return "endcap", 270  # rotate so open faces -X
        return "tunnel", 90  # rotate so walls run -Z+Z

    # W>=2, D>=2.
    n_outward = sum((is_left, is_right, is_front, is_back))
    if n_outward == 0:
        return "center_fill", 0
    if n_outward == 2:
        if is_left and is_front:
            return "corner", 0
        if is_left and is_back:
            return "corner", 90
        if is_right and is_back:
            return "corner", 180
        if is_right and is_front:
            return "corner", 270
    if n_outward == 1:
        if is_left:
            return "edge", 0
        if is_back:
            return "edge", 90
        if is_right:
            return "edge", 180
        if is_front:
            return "edge", 270
    raise ValueError(
        "_classify_cell_5piece: unexpected outward count {0} at ({1},{2}) in {3}x{4}".format(
            n_outward, i, j, W, D
        )
    )


def _is_convex_polygon(pts: np.ndarray) -> bool:
    """Return True if a Y-planar polygon (ordered) is convex in XZ."""
    n = len(pts)
    if n < 4:
        return True
    sign = 0
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        c = pts[(i + 2) % n]
        cross_y = (b[0] - a[0]) * (c[2] - b[2]) - (b[2] - a[2]) * (c[0] - b[0])
        if abs(cross_y) < 1e-9:
            continue
        s = 1 if cross_y > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def _ear_clip_planar(face: List[int], v: np.ndarray) -> List[List[int]]:
    """Triangulate a Y-planar polygon by ear-clipping.  Returns list of tri-faces.

    Operates in 2D (XZ) and assumes the input is Y-planar.  Does not modify
    the original face's winding direction.
    """
    indices = list(face)
    if len(indices) <= 3:
        return [indices]

    # Determine signed-area sign of the polygon to detect winding.
    pts = v[indices][:, [0, 2]]
    area = 0.0
    for i in range(len(indices)):
        x1, z1 = pts[i]
        x2, z2 = pts[(i + 1) % len(indices)]
        area += x1 * z2 - x2 * z1
    ccw = area > 0

    def is_convex(i_prev: int, i_curr: int, i_next: int) -> bool:
        a = v[indices[i_prev]]
        b = v[indices[i_curr]]
        c = v[indices[i_next]]
        cross_y = (b[0] - a[0]) * (c[2] - b[2]) - (b[2] - a[2]) * (c[0] - b[0])
        return (cross_y > 0) if ccw else (cross_y < 0)

    def point_in_triangle(p, a, b, c) -> bool:
        # Barycentric in XZ
        d_ab = (b[0] - a[0]) * (p[2] - a[2]) - (b[2] - a[2]) * (p[0] - a[0])
        d_bc = (c[0] - b[0]) * (p[2] - b[2]) - (c[2] - b[2]) * (p[0] - b[0])
        d_ca = (a[0] - c[0]) * (p[2] - c[2]) - (a[2] - c[2]) * (p[0] - c[0])
        if ccw:
            return d_ab >= -1e-9 and d_bc >= -1e-9 and d_ca >= -1e-9
        return d_ab <= 1e-9 and d_bc <= 1e-9 and d_ca <= 1e-9

    triangles: List[List[int]] = []
    remaining = list(range(len(indices)))
    safety = len(indices) * len(indices)
    while len(remaining) > 3 and safety > 0:
        safety -= 1
        ear_found = False
        for k in range(len(remaining)):
            i_prev = remaining[(k - 1) % len(remaining)]
            i_curr = remaining[k]
            i_next = remaining[(k + 1) % len(remaining)]
            if not is_convex(i_prev, i_curr, i_next):
                continue
            a = v[indices[i_prev]]
            b = v[indices[i_curr]]
            c = v[indices[i_next]]
            inside = False
            for j in remaining:
                if j in (i_prev, i_curr, i_next):
                    continue
                if point_in_triangle(v[indices[j]], a, b, c):
                    inside = True
                    break
            if inside:
                continue
            triangles.append([indices[i_prev], indices[i_curr], indices[i_next]])
            remaining.pop(k)
            ear_found = True
            break
        if not ear_found:
            break  # polygon may be degenerate; bail out
    if len(remaining) == 3:
        triangles.append([indices[remaining[0]], indices[remaining[1]], indices[remaining[2]]])
    return triangles


def _split_concave_polygons(mesh: Mesh) -> None:
    """Replace concave Y-planar polygons with their ear-clipped triangulation.

    Concave polygons (e.g. the L-shaped bottom rim at each brick corner)
    can be triangulated incorrectly by C4D's viewport, producing visual
    tears.  Pre-triangulating them as triangle fans avoids the issue.
    """
    mesh.flush()
    v = mesh.vertices
    new_faces: List[List[int]] = []
    for f in mesh.faces:
        if len(f) <= 3:
            new_faces.append(f)
            continue
        pts = v[list(f)]
        if float(pts[:, 1].max() - pts[:, 1].min()) > 0.05:
            new_faces.append(f)  # not Y-planar — leave alone
            continue
        if _is_convex_polygon(pts):
            new_faces.append(f)
            continue
        new_faces.extend(_ear_clip_planar(list(f), v))
    mesh.faces = new_faces


def _remove_degenerate_faces(mesh: Mesh) -> None:
    """Remove faces whose first three vertices are collinear (zero cross-product area)."""
    mesh.flush()
    v = mesh.vertices
    good = []
    for f in mesh.faces:
        if len(f) < 3:
            continue
        p0, p1, p2 = v[f[0]], v[f[1]], v[f[2]]
        if np.linalg.norm(np.cross(p1 - p0, p2 - p0)) > 1e-6:
            good.append(f)
    mesh.faces = good


def _cap_open_loops(mesh: Mesh) -> None:
    """Find all open boundary loops and add a planar cap face for each.

    Each boundary loop must be planar (all verts share the same Y) for the
    cap to be correct — which holds for the cavity-ceiling gaps left after
    welding the 5-piece tiling.  Loops that aren't Y-planar are skipped.
    The new faces are appended to mesh.faces in-place; mesh is flushed first.
    """
    mesh.flush()
    v = mesh.vertices
    faces = list(mesh.faces)

    # Build edge → face-count map.
    ec: Dict[Tuple[int, int], int] = {}
    for f in faces:
        n = len(f)
        for k in range(n):
            a, b = f[k], f[(k + 1) % n]
            key = (min(a, b), max(a, b))
            ec[key] = ec.get(key, 0) + 1

    # Collect boundary (open) edges.
    boundary_adj: Dict[int, List[int]] = {}
    for (a, b), cnt in ec.items():
        if cnt == 1:
            boundary_adj.setdefault(a, []).append(b)
            boundary_adj.setdefault(b, []).append(a)

    if not boundary_adj:
        return

    # Chain boundary edges into loops.
    visited: set = set()
    loops: List[List[int]] = []
    for start in list(boundary_adj.keys()):
        if start in visited:
            continue
        loop: List[int] = [start]
        visited.add(start)
        prev: Optional[int] = None
        cur: int = start
        while True:
            neighbors = [n for n in boundary_adj.get(cur, []) if n != prev]
            if not neighbors:
                break
            nxt = neighbors[0]
            if nxt == start:
                break
            if nxt in visited:
                break
            visited.add(nxt)
            loop.append(nxt)
            prev, cur = cur, nxt
        if len(loop) >= 3:
            loops.append(loop)

    # Add a cap face for each Y-planar loop.
    new_faces = list(mesh.faces)
    for loop in loops:
        ys = v[loop, 1]
        if float(ys.max() - ys.min()) > 0.05:
            continue  # not Y-planar — skip
        new_faces.append(loop)

    mesh.faces = new_faces


def _synthesize_5piece(W: int, D: int, H: int) -> Mesh:
    """V5 entry point. Tile a W×D brick from the 5 pieces (or use the full
    1x1 reference for the W=D=1 case). Returns a watertight, single-island
    mesh in corner-at-origin frame, height-scaled to `H` plates.
    """
    if W == 1 and D == 1:
        # Special case: needs walls on all 4 sides. Use the full reference.
        cell = _load_reference(_CELL_REF)
        if H != _CELL_REF.height_plates:
            cell = _scale_to_height(cell, H, _CELL_REF.height_plates)
        return cell

    pieces = _get_five_pieces()
    out = Mesh()
    out.vertices = np.zeros((0, 3), dtype=np.float64)
    for i in range(W):
        for j in range(D):
            piece_name, rotation = _classify_cell_5piece(i, j, W, D)
            cell = _clone_mesh(pieces[piece_name])
            if rotation != 0:
                _rotate_mesh_y_deg(cell, rotation)
            cell.flush()
            cv = cell.vertices
            cell_min_x = float(cv[:, 0].min())
            cell_min_z = float(cv[:, 2].min())
            target_min_x = i * _STUD_SIZE
            target_min_z = j * _STUD_SIZE
            _translate_mesh(
                cell,
                dx=target_min_x - cell_min_x,
                dz=target_min_z - cell_min_z,
            )
            out.merge(cell)
    out.flush()
    out.weld_vertices(tol=1e-3)
    _remove_coincident_face_pairs(out)
    _remove_degenerate_faces(out)
    _cap_open_loops(out)
    _split_concave_polygons(out)

    # Shift Y to corner-at-origin (pieces are in centered Y frame).
    out.flush()
    yv = out.vertices
    y_min = float(yv[:, 1].min())
    if abs(y_min) > 1e-6:
        new_v = yv.copy()
        new_v[:, 1] -= y_min
        out.vertices = new_v

    if H != _CELL_REF.height_plates:
        out = _scale_to_height(out, H, _CELL_REF.height_plates)
    return out


def _apply_scene_scale(mesh: Mesh, stud_size: float) -> None:
    """Scale mesh vertices in-place by (stud_size / _STUD_SIZE).

    The synthesizer always works at _STUD_SIZE=8.0.  If the scene uses a
    different stud_size the caller passes it here so the proxy matches the
    physical dimensions of draft/standard quality bricks.
    """
    factor = float(stud_size) / _STUD_SIZE
    if abs(factor - 1.0) < 1e-9:
        return
    mesh.flush()
    mesh.vertices = mesh.vertices * factor


def is_supported(brick_type, *, smooth: bool) -> bool:
    """Return True if synthesis can produce a watertight mesh for the
    requested brick.

    Today the cell-tile path covers any W>=1, D>=1, H>=1 (using the 1x1
    reference). Smooth-cap not yet implemented; falls back.
    """
    if smooth:
        return False
    W = int(getattr(brick_type, "width", 0))
    D = int(getattr(brick_type, "depth", 0))
    H = int(getattr(brick_type, "height", 0))
    return W >= 1 and D >= 1 and H >= 1


def synthesize_proxy(
    brick_type,
    *,
    smooth: bool = False,
    stud_size: float = _STUD_SIZE,
    plate_size: float = _PLATE_SIZE,
) -> Mesh:
    """Return a watertight proxy Mesh for the requested brick.

    Caller must check `is_supported` first.  The mesh is generated at
    the canonical BrickIt scale (_STUD_SIZE=8.0) and then uniformly scaled
    to match the caller's stud_size so it matches draft/standard quality.
    """
    if not is_supported(brick_type, smooth=smooth):
        raise NotImplementedError(
            "OBJ proxy: unsupported W={0} D={1} H={2} smooth={3}".format(
                getattr(brick_type, "width", "?"),
                getattr(brick_type, "depth", "?"),
                getattr(brick_type, "height", "?"),
                smooth,
            )
        )

    W = int(brick_type.width)
    D = int(brick_type.depth)
    H = int(brick_type.height)

    # V5 path: 5-piece scheme — Corner, Edge, Tunnel, Endcap, Center_Fill —
    # placed per cell with rotation. Covers every (W, D) without trimming.
    try:
        mesh = _synthesize_5piece(W, D, H)
        _apply_scene_scale(mesh, stud_size)
        return mesh
    except Exception as exc:
        _brick_log(
            "[brick] OBJ proxy: V5 failed ({0}); falling back to V4".format(exc)
        )
    try:
        mesh = _synthesize_by_v4_variants(W, D, H)
        _apply_scene_scale(mesh, stud_size)
        return mesh
    except Exception as exc:
        _brick_log(
            "[brick] OBJ proxy: V4 failed ({0}); falling back to V3 cell-tile".format(exc)
        )
        mesh = _synthesize_by_cell_tile(W, D, H)
        _apply_scene_scale(mesh, stud_size)
        return mesh

    ref = _select_reference(W, D)
    mesh = _load_reference(ref)

    # X trim if requested W < reference W (e.g. 1xN from 2x4 ref).
    if W < ref.width_studs:
        target_x = W * _STUD_SIZE
        mesh = _trim_along_axis(mesh, axis=0, cut=target_x, keep_below=True)

    # Z trim if requested D < reference D; otherwise extend by tiling.
    if D < ref.depth_studs:
        target_z = D * _STUD_SIZE
        mesh = _trim_along_axis(mesh, axis=2, cut=target_z, keep_below=True)
    elif D > ref.depth_studs:
        mesh = _extend_along_axis(mesh, ref.depth_studs, D, axis=2)

    # Vertical stretch to target height.
    if H != ref.height_plates:
        mesh = _scale_to_height(mesh, H, ref.height_plates)

    _brick_log(
        "[brick] OBJ proxy: synthesized W={0} D={1} H={2} from ref '{3}'".format(
            W, D, H, ref.name
        )
    )
    return mesh
