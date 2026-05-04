"""BrickIt source-deformation binding.

Binds each brick placement to the closest triangle on the rest-pose source
mesh at fit time, so per-frame eval can reconstruct deformed brick centers
from the live source's polygon points without re-running the fitter. Stretch
cull hides bricks whose anchor triangle area shrinks below a ratio of its
rest-pose area, preventing visible overlap in compression zones.

Coordinate frame invariant (see brick.md "Effector evaluation frame" and the
runtime root.Ml setup): all binding math is authored and consumed in
source-axis-local space. Bind-time data uses `frame_inv = ~source_obj.GetMg()`
applied during `_polygon_object_to_arrays`. Per-frame eval applies the same
inverse to a fresh deformed snapshot. Static `_placement_scene_center`
output already lives in this frame, so bound centers compose correctly with
the integrated MoGraph root Null and effector frame_matrix plumbing.
"""
import time

import c4d

from logo_helpers import baked_polygon_object_with_metadata as _baked_polygon_object_with_metadata
from plugin_bootstrap import brick_log as _brick_log
from source_geometry import polygon_object_to_arrays as _polygon_object_to_arrays


_BIND_K = 8


def _safe_import_numpy():
    try:
        import numpy as np
        return np
    except Exception:
        return None


def _safe_import_cKDTree():
    try:
        from scipy.spatial import cKDTree
        return cKDTree
    except Exception:
        return None


def _placement_rest_centers(placements, info, params):
    """Replicates _placement_scene_center static math for the rest pose.

    Returns list of (cx, cy, cz) aligned with `placements`. These are
    source-axis-local positions matching what the fitter authored, so
    closest-triangle search hits the right triangle on the cached source
    snapshot.
    """
    from brick.separation import placement_assembly_center, separated_center

    origin = info.get("origin")
    if origin is None:
        return None
    stud_size = float(info.get("stud_size", 8.0))
    plate_size = float(info.get("plate_size", 3.2))
    brick_separation = float(params.get("brick_separation", 0.0) or 0.0)
    separation_center = placement_assembly_center(placements, stud_size, plate_size)

    centers = []
    for p in placements:
        sx, sy, sz = separated_center(
            p,
            stud_size,
            plate_size,
            brick_separation,
            assembly_center=separation_center,
        )
        centers.append(
            (
                float(origin[0] + sx),
                float(origin[1] + sy),
                float(origin[2] + sz),
            )
        )
    return centers


def _closest_point_on_triangle(p, a, b, c):
    """Closest point on triangle (a,b,c) to point p plus barycentric coords.

    Standard Real-Time Collision Detection algorithm. Returns
    (closest_point, (b0, b1, b2)).
    """
    np = _safe_import_numpy()
    if np is None:
        return None, None
    ab = b - a
    ac = c - a
    ap = p - a
    d1 = float(np.dot(ab, ap))
    d2 = float(np.dot(ac, ap))
    if d1 <= 0.0 and d2 <= 0.0:
        return a, (1.0, 0.0, 0.0)
    bp = p - b
    d3 = float(np.dot(ab, bp))
    d4 = float(np.dot(ac, bp))
    if d3 >= 0.0 and d4 <= d3:
        return b, (0.0, 1.0, 0.0)
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        denom = d1 - d3 if (d1 - d3) != 0.0 else 1.0
        v = d1 / denom
        return a + ab * v, (1.0 - v, v, 0.0)
    cp = p - c
    d5 = float(np.dot(ab, cp))
    d6 = float(np.dot(ac, cp))
    if d6 >= 0.0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        denom = d2 - d6 if (d2 - d6) != 0.0 else 1.0
        w = d2 / denom
        return a + ac * w, (1.0 - w, 0.0, w)
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        denom = (d4 - d3) + (d5 - d6)
        w = (d4 - d3) / denom if denom != 0.0 else 0.0
        return b + (c - b) * w, (0.0, 1.0 - w, w)
    denom = 1.0 / (va + vb + vc) if (va + vb + vc) != 0.0 else 1.0
    v = vb * denom
    w = vc * denom
    return a + ab * v + ac * w, (1.0 - v - w, v, w)


def bind_placements_to_source(self, params):
    """Compute and cache bind records for `self._fit_placements`.

    Returns the list of bind records (one per placement, aligned) on
    success, or None when binding can't be computed (no source data,
    missing dependencies, etc.). Does not raise.
    """
    np = _safe_import_numpy()
    cKDTree = _safe_import_cKDTree()
    if np is None or cKDTree is None:
        _brick_log("[brick] Bind to Source Deformation: numpy/scipy unavailable; bind skipped")
        return None
    placements = list(self._fit_placements or [])
    info = self._fit_info or {}
    if not placements or not info:
        return None
    src_data = self._source_cache_data
    if not src_data or len(src_data) < 6:
        return None
    _baked, verts, faces, _frame_inv, _islands, tri_geom = src_data
    if tri_geom is None or len(faces) == 0:
        return None
    centroids = tri_geom.get("centroids")
    normals = tri_geom.get("normals")
    areas = tri_geom.get("areas")
    if centroids is None or normals is None or areas is None:
        return None

    centers = _placement_rest_centers(placements, info, params)
    if centers is None:
        return None

    t0 = time.perf_counter()
    tree = cKDTree(centroids)
    centers_arr = np.asarray(centers, dtype=np.float64)
    k = min(_BIND_K, int(centroids.shape[0]))
    _dists, idx_grid = tree.query(centers_arr, k=k)
    if k == 1:
        idx_grid = idx_grid.reshape(-1, 1)


    bind_records = []
    residuals = []
    for i, center in enumerate(centers_arr):
        best = None
        for j in range(idx_grid.shape[1]):
            tri_idx = int(idx_grid[i, j])
            tri = faces[tri_idx]
            a = verts[tri[0]]
            b = verts[tri[1]]
            c = verts[tri[2]]
            closest, bary = _closest_point_on_triangle(center, a, b, c)
            if closest is None:
                continue
            d = float(np.linalg.norm(center - closest))
            if best is None or d < best[0]:
                best = (d, tri_idx, bary, closest)
        if best is None:
            bind_records.append(None)
            continue
        d, tri_idx, bary, closest = best
        normal = normals[tri_idx]
        normal_offset = float(np.dot(center - closest, normal))
        rest_area = float(areas[tri_idx])
        bind_records.append(
            {
                "tri_idx": int(tri_idx),
                "bary": (float(bary[0]), float(bary[1]), float(bary[2])),
                "normal_offset": normal_offset,
                "rest_area": rest_area,
                "residual": d,
            }
        )
        residuals.append(d)

    elapsed = time.perf_counter() - t0
    bound = sum(1 for r in bind_records if r is not None)
    avg_res = float(np.mean(residuals)) if residuals else 0.0
    max_res = float(np.max(residuals)) if residuals else 0.0
    avg_area = float(np.mean(areas)) if areas.size > 0 else 0.0
    self._bind_diagnostics = {
        "bound": bound,
        "total": len(placements),
        "avg_residual": avg_res,
        "max_residual": max_res,
        "avg_rest_area": avg_area,
        "bind_seconds": elapsed,
    }
    _brick_log(
        "[brick] Bind to Source Deformation: bound={0}/{1}, K={2}, "
        "avg_residual={3:.4f}, max_residual={4:.4f}, "
        "avg_rest_area={5:.3f}, bind_s={6:.3f}".format(
            bound, len(placements), k, avg_res, max_res, avg_area, elapsed
        )
    )
    return bind_records


def _evaluate_deformed_source_arrays(op, source_obj, doc):
    """Read the current frame's deformed source as (verts, faces, frame_inv).

    Strategy: force a fresh `MCOMMAND_CURRENTSTATETOOBJECT` evaluation on
    every call. This triggers full evaluation of the source object's tag
    chain (including cloth/dynamics caches and deformers) at the current
    document time, returning the live deformed mesh. We deliberately skip
    `GetDeformCache()` and `GetCache()` here because for non-deformer
    dynamics like Cloth the cache returns rest pose, which would silently
    freeze the bricks at the bind-time pose.
    """
    np = _safe_import_numpy()
    if np is None:
        return None
    try:
        frame_inv = ~source_obj.GetMg()
    except Exception:
        frame_inv = None

    baked = None
    try:
        result = c4d.utils.SendModelingCommand(
            command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,
            list=[source_obj],
            mode=c4d.MODELINGCOMMANDMODE_ALL,
            doc=doc,
        )
        if result and isinstance(result, list) and result:
            baked = result[0]
        elif result and not isinstance(result, list):
            baked = result
    except Exception:
        baked = None

    if baked is not None and baked.CheckType(c4d.Opolygon) and baked.GetPointCount() > 0:
        verts, faces = _polygon_object_to_arrays(baked, frame_inv=frame_inv)
        if len(faces) > 0:
            return verts, faces, frame_inv

    # Fallback: source PolygonObject's own points (works when CSTO fails).
    if source_obj.CheckType(c4d.Opolygon):
        try:
            verts, faces = _polygon_object_to_arrays(source_obj, frame_inv=frame_inv)
            if len(faces) > 0:
                return verts, faces, frame_inv
        except Exception:
            pass

    baked, _meta = _baked_polygon_object_with_metadata(source_obj, doc)
    if baked is None or baked.GetPointCount() == 0:
        return None
    verts, faces = _polygon_object_to_arrays(baked, frame_inv=frame_inv)
    if len(faces) == 0:
        return None
    return verts, faces, frame_inv


def deformed_centers_for_frame(self, op, source_obj, doc, params):
    """Return per-placement deformed centers, visible flags, area ratios,
    and per-placement Follow-Surface-Normal orientation basis.

    Aligned 1:1 with `self._fit_placements`. Returns
    (centers, visible, area_ratios, orient_basis) or (None, None, None, None)
    when binding is unavailable / unusable for this frame.

    `centers[i]` is None when the bind record is missing — caller falls back
    to the static `_placement_scene_center` value for that placement.

    `orient_basis[i]` is a (v1, v2, v3) tuple of source-axis-local unit
    vectors representing the deformed triangle's tangent / normal / bitangent
    frame, or None when no record. Only consumed in Follow-Surface-Normal
    mode.
    """
    np = _safe_import_numpy()
    if np is None:
        return None, None, None, None
    if not self._bind_records:
        return None, None, None, None
    arrays = _evaluate_deformed_source_arrays(op, source_obj, doc)
    if arrays is None:
        return None, None, None, None
    verts, faces, _frame_inv = arrays

    bind_face_count = None
    src_data = self._source_cache_data
    if src_data and len(src_data) >= 3:
        bind_face_count = int(len(src_data[2]))
    if bind_face_count is not None and len(faces) != bind_face_count:
        _brick_log(
            "[brick] Bind to Source Deformation: triangle count mismatch "
            "(bind={0}, current={1}); falling back to static centers".format(
                bind_face_count, len(faces)
            )
        )
        return None, None, None, None

    cull_ratio = float(params.get("bind_stretch_cull_ratio", 0.6) or 0.0)
    smoothing = float(params.get("bind_orient_smoothing", 0.7) or 0.0)
    smoothing = max(0.0, min(1.0, smoothing))

    # Per-frame vertex normals (area-weighted average of incident faces).
    # Used to dampen the per-face-normal jitter that small / distorted
    # triangles produce in compression zones; blended by `smoothing`.
    vertex_normals = None
    if smoothing > 0.0:
        try:
            f0 = faces[:, 0]
            f1 = faces[:, 1]
            f2 = faces[:, 2]
            v0 = verts[f0]
            v1 = verts[f1]
            v2 = verts[f2]
            face_cross = np.cross(v1 - v0, v2 - v0)  # length encodes area
            vn = np.zeros_like(verts)
            np.add.at(vn, f0, face_cross)
            np.add.at(vn, f1, face_cross)
            np.add.at(vn, f2, face_cross)
            lens = np.linalg.norm(vn, axis=1)
            safe = np.where(lens > 1e-20, lens, 1.0).reshape(-1, 1)
            vertex_normals = vn / safe
        except Exception:
            vertex_normals = None

    centers = []
    visible = []
    area_ratios = []
    orient_basis = []
    for record in self._bind_records:
        if record is None:
            centers.append(None)
            visible.append(True)
            area_ratios.append(1.0)
            orient_basis.append(None)
            continue
        tri_idx = record["tri_idx"]
        if tri_idx < 0 or tri_idx >= len(faces):
            centers.append(None)
            visible.append(True)
            area_ratios.append(1.0)
            orient_basis.append(None)
            continue
        tri = faces[tri_idx]
        a = verts[tri[0]]
        b = verts[tri[1]]
        c = verts[tri[2]]
        b0, b1, b2 = record["bary"]
        on_surface = a * b0 + b * b1 + c * b2
        edge1 = b - a
        cross = np.cross(edge1, c - a)
        norm_len = float(np.linalg.norm(cross))
        if norm_len <= 1e-20:
            normal = np.array([0.0, 1.0, 0.0])
            current_area = 0.0
        else:
            normal = cross / norm_len
            current_area = norm_len * 0.5
        deformed_center = on_surface + normal * float(record["normal_offset"])
        centers.append(
            (float(deformed_center[0]), float(deformed_center[1]), float(deformed_center[2]))
        )
        rest_area = float(record.get("rest_area", 0.0) or 0.0)
        if rest_area > 1e-20:
            ratio = current_area / rest_area
        else:
            ratio = 1.0
        area_ratios.append(ratio)
        visible.append(ratio >= cull_ratio)
        # Build a twist-stable orient basis using the shortest-arc rotation
        # that takes world-Y to the surface normal. Tangent and bitangent
        # vary smoothly with N everywhere except at the antipodal singular-
        # ity N ≈ -Y (where any twist choice is arbitrary). Compared to
        # projecting world-X onto the tangent plane, this avoids the 90/180°
        # tangent flip that occurs as N sweeps through ±world-X — the cause
        # of the "edge bricks spinning on their Y axis" artifact on highly-
        # deformed cloth folds.
        if norm_len > 1e-20:
            # Optionally blend in the smooth (vertex-interpolated) normal
            # to dampen per-face-normal jitter on small distorted triangles.
            if vertex_normals is not None and smoothing > 0.0:
                vn0 = vertex_normals[tri[0]]
                vn1 = vertex_normals[tri[1]]
                vn2 = vertex_normals[tri[2]]
                smooth_normal = vn0 * b0 + vn1 * b1 + vn2 * b2
                blended = normal * (1.0 - smoothing) + smooth_normal * smoothing
                bn_len = float(np.linalg.norm(blended))
                if bn_len > 1e-20:
                    normal = blended / bn_len
            ny = float(normal[1])
            nx = float(normal[0])
            nz = float(normal[2])
            if ny > 0.999999:
                tangent = np.array([1.0, 0.0, 0.0])
                bitangent = np.array([0.0, 0.0, 1.0])
            elif ny < -0.999999:
                tangent = np.array([1.0, 0.0, 0.0])
                bitangent = np.array([0.0, 0.0, -1.0])
            else:
                inv_one_plus_y = 1.0 / (1.0 + ny)
                tangent = np.array(
                    [
                        1.0 - nx * nx * inv_one_plus_y,
                        -nx,
                        -nx * nz * inv_one_plus_y,
                    ]
                )
                bitangent = np.array(
                    [
                        -nx * nz * inv_one_plus_y,
                        -nz,
                        1.0 - nz * nz * inv_one_plus_y,
                    ]
                )
            orient_basis.append(
                (
                    (float(tangent[0]), float(tangent[1]), float(tangent[2])),
                    (float(normal[0]), float(normal[1]), float(normal[2])),
                    (float(bitangent[0]), float(bitangent[1]), float(bitangent[2])),
                )
            )
            continue
        orient_basis.append(None)

    # Anti-intersection cull: for each visible brick, AABB-test against
    # its precomputed nearest neighbors. Hide the higher-indexed brick of
    # any overlapping pair (deterministic tie-break). Neighbors are fixed
    # at bind time so this is O(N * K) with K ≈ 6 — a few thousand trivial
    # box checks per frame.
    if bool(params.get("bind_prevent_intersection", False)):
        half_extents = getattr(self, "_bind_placement_half_extents", None)
        neighbors = getattr(self, "_bind_placement_neighbors", None)
        if half_extents and neighbors and len(half_extents) == len(centers):
            culled = [False] * len(centers)
            for i in range(len(centers)):
                if culled[i] or not visible[i]:
                    continue
                ci = centers[i]
                if ci is None:
                    continue
                hx_i, hy_i, hz_i = half_extents[i]
                for j in neighbors[i]:
                    if j <= i or j >= len(centers):
                        continue
                    if culled[j] or not visible[j]:
                        continue
                    cj = centers[j]
                    if cj is None:
                        continue
                    hx_j, hy_j, hz_j = half_extents[j]
                    if (
                        abs(ci[0] - cj[0]) < hx_i + hx_j
                        and abs(ci[1] - cj[1]) < hy_i + hy_j
                        and abs(ci[2] - cj[2]) < hz_i + hz_j
                    ):
                        culled[j] = True
                        visible[j] = False
    return centers, visible, area_ratios, orient_basis


def make_bind_cache_key(self, params):
    """Stable key combining fit identity, source identity, and bind ref frame."""
    return (
        self._fit_cache_key,
        getattr(self, "_source_cache_key", None),
        int(params.get("bind_reference_frame", 0) or 0),
    )
