"""C4D source-object geometry extraction for BrickIt."""
import c4d


def generator_document(op, hh):
    """Resolve a document for modeling/baking inside ObjectData.GetVirtualObjects."""
    doc = op.GetDocument()
    if doc is None and hh is not None:
        try:
            doc = hh.GetDocument()
        except Exception:
            pass
    if doc is None:
        try:
            doc = c4d.documents.GetActiveDocument()
        except Exception:
            pass
    return doc


def polygon_object_to_arrays(poly_obj, frame_inv=None):
    """Return geometry arrays for BrickIt fitting."""
    import numpy as np

    n_pts = poly_obj.GetPointCount()
    pts = poly_obj.GetAllPoints()
    polys = poly_obj.GetAllPolygons()

    mg = poly_obj.GetMg()
    verts = np.empty((n_pts, 3), dtype=np.float64)
    for i, p in enumerate(pts):
        wp = mg * p
        if frame_inv is not None:
            wp = frame_inv * wp
        verts[i, 0] = wp.x
        verts[i, 1] = wp.y
        verts[i, 2] = wp.z

    tris = []
    for fp in polys:
        a, b, c, d = fp.a, fp.b, fp.c, fp.d
        if c == d:
            tris.append((a, b, c))
        else:
            tris.append((a, b, c))
            tris.append((a, c, d))
    faces = np.array(tris, dtype=np.int64) if tris else np.zeros((0, 3), dtype=np.int64)
    return verts, faces


def _polygon_vertices(fp):
    verts = [int(fp.a), int(fp.b), int(fp.c)]
    if fp.c != fp.d:
        verts.append(int(fp.d))
    return verts


def source_polygon_islands(poly_obj, source_metadata=None, frame_inv=None):
    """Return disconnected polygon-island summaries in source-local space."""
    import numpy as np

    if poly_obj is None:
        return {"islands": []}

    pts = poly_obj.GetAllPoints()
    polys = poly_obj.GetAllPolygons()
    n_pts = int(poly_obj.GetPointCount())
    n_polys = int(poly_obj.GetPolygonCount())
    if n_pts <= 0 or n_polys <= 0:
        return {"islands": []}

    mg = poly_obj.GetMg()
    vertices = np.empty((n_pts, 3), dtype=np.float64)
    for i, p in enumerate(pts):
        wp = mg * p
        if frame_inv is not None:
            wp = frame_inv * wp
        vertices[i, 0] = float(wp.x)
        vertices[i, 1] = float(wp.y)
        vertices[i, 2] = float(wp.z)

    groups = []
    try:
        groups = list((source_metadata or {}).get("groups") or [])
    except Exception:
        groups = []
    if not groups:
        groups = [{
            "name": "Source",
            "poly_start": 0,
            "poly_end": n_polys,
        }]

    islands = []

    def _find(parent, x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(parent, a, b):
        ra = _find(parent, a)
        rb = _find(parent, b)
        if ra != rb:
            parent[rb] = ra

    for group_index, group in enumerate(groups):
        start = max(0, min(n_polys, int(group.get("poly_start", 0) or 0)))
        end = max(start, min(n_polys, int(group.get("poly_end", n_polys) or n_polys)))
        poly_indices = list(range(start, end))
        if not poly_indices:
            continue

        parent = {idx: idx for idx in poly_indices}
        edges = {}
        for idx in poly_indices:
            verts_for_poly = _polygon_vertices(polys[idx])
            for a, b in zip(verts_for_poly, verts_for_poly[1:] + verts_for_poly[:1]):
                edge = tuple(sorted((int(a), int(b))))
                prev = edges.get(edge)
                if prev is None:
                    edges[edge] = idx
                else:
                    _union(parent, prev, idx)

        components = {}
        for idx in poly_indices:
            root = _find(parent, idx)
            components.setdefault(root, []).append(idx)

        group_name = str(group.get("name") or "Source")
        for island_index, component_polys in enumerate(
            sorted(components.values(), key=lambda rows: min(rows))
        ):
            point_ids = set()
            for poly_idx in component_polys:
                point_ids.update(_polygon_vertices(polys[poly_idx]))
            if not point_ids:
                continue
            coords = vertices[list(sorted(point_ids))]
            bbox_min = coords.min(axis=0)
            bbox_max = coords.max(axis=0)
            center = coords.mean(axis=0)
            islands.append({
                "key": "g{0:03d}_i{1:03d}".format(group_index + 1, island_index + 1),
                "group_index": int(group_index),
                "island_index": int(island_index),
                "source_name": group_name,
                "island_name": "Island {0:03d}".format(island_index + 1),
                "bbox_min": tuple(float(v) for v in bbox_min),
                "bbox_max": tuple(float(v) for v in bbox_max),
                "center": tuple(float(v) for v in center),
                "polygon_count": int(len(component_polys)),
            })

    return {"islands": islands}


def placement_group_key(placement):
    """Stable key for looking up grouping metadata for a fitted placement."""
    brick = getattr(placement, "brick", None)
    brick_name = str(getattr(brick, "name", "brick"))
    return (
        int(getattr(placement, "x", 0)),
        int(getattr(placement, "y", 0)),
        int(getattr(placement, "z", 0)),
        int(getattr(placement, "w", getattr(brick, "width", 1))),
        int(getattr(placement, "h", getattr(brick, "height", 1))),
        int(getattr(placement, "d", getattr(brick, "depth", 1))),
        int(getattr(placement, "rotation_y", 0)),
        brick_name,
    )


def placement_grouping_for_islands(placements, island_metadata, origin, stud_size, plate_size):
    """Classify fitted placements to nearest source child/polygon island."""
    import numpy as np

    islands = list((island_metadata or {}).get("islands") or [])
    if not placements or not islands or origin is None:
        return {"groups": [], "placement_groups": {}}

    origin = np.asarray(origin, dtype=np.float64)
    island_rows = []
    for island in islands:
        try:
            bbox_min = np.asarray(island.get("bbox_min"), dtype=np.float64)
            bbox_max = np.asarray(island.get("bbox_max"), dtype=np.float64)
            center = np.asarray(island.get("center"), dtype=np.float64)
        except Exception:
            continue
        if bbox_min.shape != (3,) or bbox_max.shape != (3,) or center.shape != (3,):
            continue
        island_rows.append((island, bbox_min, bbox_max, center))
    if not island_rows:
        return {"groups": [], "placement_groups": {}}

    groups = {}
    placement_groups = {}

    def _score(center, bbox_min, bbox_max, island_center):
        outside = np.maximum(0.0, np.maximum(bbox_min - center, center - bbox_max))
        return float(np.dot(outside, outside)), float(np.sum((center - island_center) ** 2))

    for placement in placements:
        brick = getattr(placement, "brick", None)
        w = float(getattr(placement, "w", getattr(brick, "width", 1)))
        h = float(getattr(placement, "h", getattr(brick, "height", 1)))
        d = float(getattr(placement, "d", getattr(brick, "depth", 1)))
        center = origin + np.array([
            (float(getattr(placement, "x", 0)) + w * 0.5) * float(stud_size),
            (float(getattr(placement, "y", 0)) + h * 0.5) * float(plate_size),
            (float(getattr(placement, "z", 0)) + d * 0.5) * float(stud_size),
        ], dtype=np.float64)
        island, _bbox_min, _bbox_max, _center = min(
            island_rows,
            key=lambda row: _score(center, row[1], row[2], row[3]),
        )
        group_key = str(island.get("key") or "ungrouped")
        groups[group_key] = {
            "key": group_key,
            "source_name": str(island.get("source_name") or "Source"),
            "island_name": str(island.get("island_name") or "Island"),
            "group_index": int(island.get("group_index", 0) or 0),
            "island_index": int(island.get("island_index", 0) or 0),
        }
        placement_groups[placement_group_key(placement)] = group_key

    return {
        "groups": sorted(
            groups.values(),
            key=lambda row: (int(row.get("group_index", 0)), int(row.get("island_index", 0))),
        ),
        "placement_groups": placement_groups,
    }


def c4d_volume_voxels_from_polygon_object(
    poly_obj,
    verts,
    params,
    stud_size,
    plate_size,
    default_color,
    frame_inv=None,
):
    """Experimental C4D Volume backend: sample MeshToVolume into LEGO cells."""
    import time
    import numpy as np
    import maxon
    from maxon.frameworks import volume as maxon_volume

    if poly_obj is None or poly_obj.GetPointCount() <= 0 or poly_obj.GetPolygonCount() <= 0:
        raise ValueError("source polygon object is empty")

    voxel_mm = np.array([float(stud_size), float(plate_size), float(stud_size)], dtype=np.float64)
    bbox_min = verts.min(axis=0)
    bbox_max = verts.max(axis=0)
    grid_min = np.floor((bbox_min - voxel_mm) / voxel_mm) * voxel_mm
    grid_max = np.ceil((bbox_max + voxel_mm) / voxel_mm) * voxel_mm
    dims = np.maximum(1, np.round((grid_max - grid_min) / voxel_mm).astype(int))
    nx, ny, nz = (int(dims[0]), int(dims[1]), int(dims[2]))

    pts = poly_obj.GetAllPoints()
    polys = poly_obj.GetAllPolygons()
    mg = poly_obj.GetMg()

    volume_vertices = maxon.BaseArray(maxon.Vector)
    for p in pts:
        wp = mg * p
        if frame_inv is not None:
            wp = frame_inv * wp
        volume_vertices.Append(maxon.Vector(float(wp.x), float(wp.y), float(wp.z)))

    volume_polys = maxon.BaseArray(maxon_volume.VolumeConversionPolygon)
    for fp in polys:
        vp = maxon_volume.VolumeConversionPolygon()
        vp.a = int(fp.a)
        vp.b = int(fp.b)
        vp.c = int(fp.c)
        if fp.c == fp.d:
            vp.SetTriangle()
        else:
            vp.d = int(fp.d)
        volume_polys.Append(vp)

    grid_size = float(plate_size)
    band = max(3, int(params.get("shell_thickness", 1) or 1) + 2)
    t0 = time.perf_counter()
    volume = maxon_volume.VolumeToolsInterface.MeshToVolume(
        volume_vertices,
        volume_polys,
        maxon.Matrix(),
        grid_size,
        band,
        band,
        maxon.ThreadRef(),
        maxon.POLYGONCONVERSIONFLAGS.NONE,
        None,
    )
    t_volume = time.perf_counter()

    accessor = maxon_volume.GridAccessorInterface.Create(maxon.Float32)
    accessor.Init(volume, maxon.VOLUMESAMPLER.NEAREST)

    occupancy = np.zeros((nx, ny, nz), dtype=bool)
    voxel_mode = str(params.get("voxel_mode") or "solid").lower()
    shell_threshold = max(float(plate_size), float(params.get("shell_thickness", 1) or 1) * float(plate_size))
    threshold = shell_threshold if voxel_mode == "shell" else 0.0
    pos = maxon.Vector()
    for x in range(nx):
        pos.x = float(grid_min[0] + (x + 0.5) * voxel_mm[0])
        for y in range(ny):
            pos.y = float(grid_min[1] + (y + 0.5) * voxel_mm[1])
            for z in range(nz):
                pos.z = float(grid_min[2] + (z + 0.5) * voxel_mm[2])
                sdf = float(accessor.GetValue(pos))
                if voxel_mode == "shell":
                    occupancy[x, y, z] = abs(sdf) <= shell_threshold
                else:
                    occupancy[x, y, z] = sdf <= threshold

    occupied = int(occupancy.sum())
    t_sample = time.perf_counter()

    if not occupancy.any():
        raise ValueError("C4D Volume sampling returned no occupied voxels")

    colors = np.zeros((nx, ny, nz, 3), dtype=np.uint8)
    colors[:, :, :, 0] = int(default_color[0])
    colors[:, :, :, 1] = int(default_color[1])
    colors[:, :, :, 2] = int(default_color[2])

    return occupancy, colors, grid_min.astype(np.float64), {
        "voxel_backend": "c4d_volume",
        "voxel_backend_requested": "c4d_volume",
        "voxel_backend_fallback": False,
        "voxel_backend_raw_occupied": occupied,
        "voxel_backend_sdf_threshold": threshold,
        "voxel_backend_volume_seconds": float(t_volume - t0),
        "voxel_backend_sample_seconds": float(t_sample - t_volume),
        "voxel_backend_sample_count": int(nx * ny * nz),
        "voxel_backend_note": (
            "C4D Volume MeshToVolume sampled in Python; threshold={0:.4f}; "
            "volume={1:.2f}s, sample={2:.2f}s, samples={3}."
        ).format(threshold, t_volume - t0, t_sample - t_volume, int(nx * ny * nz)),
    }


def source_axis_local_matrix(op, source_obj):
    """Return the source axis matrix in the BrickIt generator's local frame."""
    if source_obj is None:
        return c4d.Matrix()
    try:
        source_mg = source_obj.GetMg()
    except Exception:
        return c4d.Matrix()
    try:
        op_mg = op.GetMg()
        return ~op_mg * source_mg
    except Exception:
        return source_mg
