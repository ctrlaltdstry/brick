"""Per-frame deformation follower implementation.

Used by the BrickIt Follow Surface tag (registered in
`brickit_follow_surface_tag.py`) to drive each bound carrier under a
proxy hierarchy at the deformed-mesh position read from the live source.
Each frame the tag's `Execute` calls `apply_follow_surface(...)` here.

This module reads the live deformed source via
`SendModelingCommand(MCOMMAND_CURRENTSTATETOOBJECT)` — the same path the
integrated-MoGraph live preview uses — so cloth/dynamics on the source
are reflected in the proxy bricks before any RBD simulation runs.
"""
import c4d

from source_geometry import polygon_object_to_arrays as _polygon_object_to_arrays


# User-data ID stamped on each carrier (instance or post-bake polygon)
# so the follower can match carriers to bind records by index.
UD_CARRIER_BIND_INDEX = 1

ORIENT_MODE_WORLD_UP = 0
ORIENT_MODE_FOLLOW_NORMAL = 1


def _evaluate_deformed_source(source_obj, doc):
    try:
        result = c4d.utils.SendModelingCommand(
            command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,
            list=[source_obj],
            mode=c4d.MODELINGCOMMANDMODE_ALL,
            doc=doc,
        )
    except Exception:
        return None
    if not result:
        return None
    baked = None
    if isinstance(result, list):
        if result and result[0] is not None:
            baked = result[0]
    else:
        baked = result
    if baked is None or not baked.CheckType(c4d.Opolygon):
        return None
    if baked.GetPointCount() == 0:
        return None
    try:
        frame_inv = ~source_obj.GetMg()
    except Exception:
        frame_inv = None
    verts, faces = _polygon_object_to_arrays(baked, frame_inv=frame_inv)
    if len(faces) == 0:
        return None
    return verts, faces


def _collect_carriers_by_index(host_op):
    carriers = {}
    if host_op is None:
        return carriers
    stack = [host_op]
    while stack:
        n = stack.pop()
        try:
            idx_val = n[c4d.ID_USERDATA, UD_CARRIER_BIND_INDEX]
        except Exception:
            idx_val = None
        if idx_val is not None:
            try:
                idx = int(idx_val)
                # 0 used as sentinel "not set" because BaseContainer ints
                # default to 0 — store with a +1 offset on bake.
                if idx > 0:
                    carriers[idx - 1] = n
            except Exception:
                pass
        c = n.GetDown()
        while c:
            stack.append(c)
            c = c.GetNext()
    return carriers


def _vertex_normals(np, verts, faces):
    try:
        f0 = faces[:, 0]
        f1 = faces[:, 1]
        f2 = faces[:, 2]
        v0 = verts[f0]
        v1 = verts[f1]
        v2 = verts[f2]
        cross = np.cross(v1 - v0, v2 - v0)
        vn = np.zeros_like(verts)
        np.add.at(vn, f0, cross)
        np.add.at(vn, f1, cross)
        np.add.at(vn, f2, cross)
        lens = np.linalg.norm(vn, axis=1).reshape(-1, 1)
        safe = np.where(lens > 1e-20, lens, 1.0)
        return vn / safe
    except Exception:
        return None


def _shortest_arc_basis(nx, ny, nz):
    """Return (v1, v2, v3) tuples — twist-stable rotation taking world-Y
    to (nx, ny, nz). Same math as the live integrated MoGraph follow-
    normal path.
    """
    if ny > 0.999999:
        return (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    if ny < -0.999999:
        return (1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)
    inv_one_plus_y = 1.0 / (1.0 + ny)
    return (
        (1.0 - nx * nx * inv_one_plus_y, -nx, -nx * nz * inv_one_plus_y),
        (nx, ny, nz),
        (-nx * nz * inv_one_plus_y, -nz, 1.0 - nz * nz * inv_one_plus_y),
    )


def apply_follow_surface(host_op, doc, source_obj, records, orient_mode, smoothing):
    """Pure per-frame update: drive each bound carrier under `host_op`
    to its deformed position on `source_obj` using `records`. Returns
    True on success.
    """
    try:
        import numpy as np
    except Exception:
        return False
    if source_obj is None or not records:
        return False
    arrays = _evaluate_deformed_source(source_obj, doc)
    if arrays is None:
        return False
    verts, faces = arrays
    n_faces = len(faces)
    carriers = _collect_carriers_by_index(host_op)
    if not carriers:
        return False
    vertex_normals = None
    if orient_mode == ORIENT_MODE_FOLLOW_NORMAL and smoothing > 0.0:
        vertex_normals = _vertex_normals(np, verts, faces)
    for idx, record in enumerate(records):
        if record is None:
            continue
        carrier = carriers.get(idx)
        if carrier is None:
            continue
        try:
            tri_idx = int(record["tri_idx"])
        except Exception:
            continue
        if tri_idx < 0 or tri_idx >= n_faces:
            continue
        tri = faces[tri_idx]
        a = verts[tri[0]]
        b = verts[tri[1]]
        c = verts[tri[2]]
        try:
            b0, b1, b2 = record["bary"]
            normal_offset = float(record["normal_offset"])
        except Exception:
            continue
        on_surface = a * b0 + b * b1 + c * b2
        cross = np.cross(b - a, c - a)
        norm_len = float(np.linalg.norm(cross))
        if norm_len <= 1e-20:
            continue
        normal = cross / norm_len
        if vertex_normals is not None and smoothing > 0.0:
            try:
                vn0 = vertex_normals[tri[0]]
                vn1 = vertex_normals[tri[1]]
                vn2 = vertex_normals[tri[2]]
                smooth_normal = vn0 * b0 + vn1 * b1 + vn2 * b2
                blended = normal * (1.0 - smoothing) + smooth_normal * smoothing
                bn_len = float(np.linalg.norm(blended))
                if bn_len > 1e-20:
                    normal = blended / bn_len
            except Exception:
                pass
        deformed_center = on_surface + normal * normal_offset
        m = c4d.Matrix()
        if orient_mode == ORIENT_MODE_FOLLOW_NORMAL:
            v1, v2, v3 = _shortest_arc_basis(
                float(normal[0]), float(normal[1]), float(normal[2])
            )
            m.v1 = c4d.Vector(*v1)
            m.v2 = c4d.Vector(*v2)
            m.v3 = c4d.Vector(*v3)
        else:
            v1 = (1.0, 0.0, 0.0)
            v2 = (0.0, 1.0, 0.0)
            v3 = (0.0, 0.0, 1.0)
        # Proxy carriers reference low-corner-pivoted templates, so the
        # deformed CENTER needs to be shifted by the brick's half-extents
        # (rotated through the orient basis when in follow-normal mode) to
        # land the brick correctly. Records authored without `half_size`
        # (e.g. for hypothetical center-pivoted carriers) skip this step.
        try:
            half_size = record.get("half_size") or None
        except Exception:
            half_size = None
        if half_size and len(half_size) == 3:
            hx, hy, hz = float(half_size[0]), float(half_size[1]), float(half_size[2])
            shift_x = v1[0] * hx + v2[0] * hy + v3[0] * hz
            shift_y = v1[1] * hx + v2[1] * hy + v3[1] * hz
            shift_z = v1[2] * hx + v2[2] * hy + v3[2] * hz
            m.off = c4d.Vector(
                float(deformed_center[0]) - shift_x,
                float(deformed_center[1]) - shift_y,
                float(deformed_center[2]) - shift_z,
            )
        else:
            m.off = c4d.Vector(
                float(deformed_center[0]),
                float(deformed_center[1]),
                float(deformed_center[2]),
            )
        try:
            carrier.SetMl(m)
        except Exception:
            pass
    return True
