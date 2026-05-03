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
