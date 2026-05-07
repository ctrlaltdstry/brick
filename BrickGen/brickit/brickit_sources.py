"""Volume-Builder-style source list for BrickIt.

The BRICKIFYASSEMBLY_SOURCES InExcludeData parameter is the source of truth
for which scene objects feed the bricking pipeline. Per-source Mode
(Union/Subtract/Intersect) is stored in each entry's flags slot.

Direct children of the BrickIt op auto-append to the list as a convenience
(handled by the native BrickSourcesCustomGui), but the list can also hold
links to objects parented anywhere in the scene. That's option B: removing
an object from BrickIt's children does NOT remove it from the list; deleting
an object from the OM entirely does (the InExcludeData self-prunes when the
link goes stale).

Cycle/self-reference filter: a BrickIt op is never a valid source for
another BrickIt — it would recurse during bake and either freeze C4D or
trash both ops' caches. The native GUI rejects such drops up front; this
module also filters at the bake step as defense-in-depth for scenes loaded
from before the filter existed.
"""
import c4d

from c4d_symbols import (  # noqa: F401 - C4D resource IDs are constants.
    BRICKIFYASSEMBLY_SOURCES,
    BRICKIFYASSEMBLY_SOURCE_MODE_UNION,
    BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT,
    BRICKIFYASSEMBLY_SOURCE_MODE_INTERSECT,
    BRICKIFYASSEMBLY_SOURCE_MODE_MASK,
    BRICKIFYASSEMBLY_SOURCE_FLAG_AUTO_ADDED,
    ID_BRICKIFYASSEMBLY,
)
from logo_helpers import baked_polygon_object_with_metadata


def mode_from_flags(flags):
    """Extract the Mode bits (0-1) from a per-entry flags int."""
    try:
        m = int(flags) & int(BRICKIFYASSEMBLY_SOURCE_MODE_MASK)
    except Exception:
        m = BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    if m not in VALID_MODES:
        m = BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    return m


def is_auto_added(flags):
    """Return True if the entry was auto-added because the object was
    parented under the BrickIt (vs drag-dropped from anywhere). Drives the
    auto-remove behavior in _sync_source_visibility — only auto-added
    entries get pruned when the object stops being a child of the host.
    """
    try:
        return bool(int(flags) & int(BRICKIFYASSEMBLY_SOURCE_FLAG_AUTO_ADDED))
    except Exception:
        return False


def pack_flags(mode, auto_added):
    """Pack mode + auto-added bit into the per-entry flags int."""
    try:
        m = int(mode) & int(BRICKIFYASSEMBLY_SOURCE_MODE_MASK)
    except Exception:
        m = BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    return m | (int(BRICKIFYASSEMBLY_SOURCE_FLAG_AUTO_ADDED) if auto_added else 0)


VALID_MODES = (
    BRICKIFYASSEMBLY_SOURCE_MODE_UNION,
    BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT,
    BRICKIFYASSEMBLY_SOURCE_MODE_INTERSECT,
)


def _direct_children(op):
    """Return the direct children of `op` in scene-graph order."""
    out = []
    try:
        ch = op.GetDown()
    except Exception:
        ch = None
    while ch is not None:
        out.append(ch)
        try:
            ch = ch.GetNext()
        except Exception:
            ch = None
    return out


def _mode_lookup(data, doc):
    """Return a {GUID: mode_int} map from the InExcludeData entries.

    Modes are stored in bits 0-1 of each entry's flags slot. Entries that
    resolve to a now-deleted object are skipped. Bit 2 (AUTO_ADDED) is
    masked off here — readers that need it should use is_auto_added().
    """
    lookup = {}
    if data is None:
        return lookup
    try:
        count = int(data.GetObjectCount())
    except Exception:
        return lookup
    for i in range(count):
        try:
            obj = data.ObjectFromIndex(doc, i)
        except Exception:
            obj = None
        if obj is None:
            continue
        try:
            flags = int(data.GetFlags(i))
        except Exception:
            flags = 0
        try:
            lookup[obj.GetGUID()] = mode_from_flags(flags)
        except Exception:
            pass
    return lookup


def mode_for_child(brickit_op, child):
    """Return the Mode integer for a given child of `brickit_op`.

    Children that have not been added to the InExcludeData yet (e.g.
    just dragged under the BrickIt) default to Union.
    """
    if child is None:
        return BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    try:
        data = brickit_op[BRICKIFYASSEMBLY_SOURCES]
    except Exception:
        data = None
    try:
        doc = brickit_op.GetDocument()
    except Exception:
        doc = None
    lookup = _mode_lookup(data, doc)
    try:
        guid = child.GetGUID()
    except Exception:
        return BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    return lookup.get(guid, BRICKIFYASSEMBLY_SOURCE_MODE_UNION)


def _is_invalid_source(obj, host):
    """Return True if `obj` would be a cycle hazard as a source of `host`.

    Filters:
      - obj is host itself
      - obj is another BrickIt op (would recurse into its own GVO on bake)
      - obj is an ANCESTOR of host (baking obj would CSTO host's subtree
        and re-trigger this BrickIt's GVO, looping)

    Note the cycle direction: obj being *inside* host's subtree (e.g. a
    direct child) is NOT a cycle — that's the intended auto-append path.
    The freeze case is the reverse: obj's CSTO would walk through host.
    """
    if obj is None or host is None:
        return True
    if obj is host:
        return True
    try:
        if obj.IsInstanceOf(ID_BRICKIFYASSEMBLY):
            return True
    except Exception:
        pass
    try:
        a = host.GetUp()
        while a is not None:
            if a is obj:
                return True
            a = a.GetUp()
    except Exception:
        pass
    return False


def enumerate_brickit_sources(brickit_op):
    """Return [(source_obj, mode_int), ...] in InExcludeData order.

    The InExcludeData is the source of truth (option B). Direct children of
    the BrickIt that aren't in the list yet are appended to the result with
    Union default — this is the legacy fallback for scenes saved before the
    native GUI auto-appends children, and it keeps the test smoke from
    regressing. Newly-added InExclude entries are returned in the order the
    user added them.
    """
    if brickit_op is None:
        return []
    try:
        data = brickit_op[BRICKIFYASSEMBLY_SOURCES]
    except Exception:
        data = None
    try:
        doc = brickit_op.GetDocument()
    except Exception:
        doc = None

    pairs = []
    seen_guids = set()

    if data is not None:
        try:
            count = int(data.GetObjectCount())
        except Exception:
            count = 0
        for i in range(count):
            try:
                obj = data.ObjectFromIndex(doc, i)
            except Exception:
                obj = None
            if obj is None:
                continue
            if _is_invalid_source(obj, brickit_op):
                continue
            try:
                flags = int(data.GetFlags(i))
            except Exception:
                flags = 0
            mode = mode_from_flags(flags)
            try:
                guid = obj.GetGUID()
            except Exception:
                guid = None
            if guid is not None:
                seen_guids.add(guid)
            pairs.append((obj, mode))

    # Fallback: any direct child not already in the list (option B keeps the
    # children-as-input convenience for users who haven't interacted with the
    # GUI yet, and for scenes saved before the auto-append landed).
    for child in _direct_children(brickit_op):
        if _is_invalid_source(child, brickit_op):
            continue
        try:
            guid = child.GetGUID()
        except Exception:
            guid = None
        if guid is not None and guid in seen_guids:
            continue
        pairs.append((child, BRICKIFYASSEMBLY_SOURCE_MODE_UNION))
        if guid is not None:
            seen_guids.add(guid)

    return pairs


def set_mode_for_row(brickit_op, row_index, mode):
    """Persist a Mode change for the row at `row_index` in scene order.

    Looks up the corresponding child via enumerate_brickit_sources, then
    rewrites the InExcludeData so that child's entry has the new mode in
    its flags slot. Children that aren't yet present in the InExcludeData
    are appended on first write so subsequent reads return the chosen
    mode instead of falling back to the implicit Union default.

    Returns True iff something changed (caller can use this to decide
    whether to dirty the op for rebuild).
    """
    if mode not in VALID_MODES:
        return False
    pairs = enumerate_brickit_sources(brickit_op)
    if not (0 <= row_index < len(pairs)):
        return False
    target_child, current_mode = pairs[row_index]
    if target_child is None:
        return False
    if int(current_mode) == int(mode):
        return False

    try:
        target_guid = target_child.GetGUID()
    except Exception:
        target_guid = None
    if target_guid is None:
        return False

    try:
        data = brickit_op[BRICKIFYASSEMBLY_SOURCES]
    except Exception:
        data = None
    try:
        doc = brickit_op.GetDocument()
    except Exception:
        doc = None

    new_data = c4d.InExcludeData()
    if data is not None:
        try:
            count = int(data.GetObjectCount())
        except Exception:
            count = 0
        replaced = False
        for i in range(count):
            try:
                obj = data.ObjectFromIndex(doc, i)
            except Exception:
                obj = None
            try:
                flags = int(data.GetFlags(i))
            except Exception:
                flags = BRICKIFYASSEMBLY_SOURCE_MODE_UNION
            if obj is None:
                continue
            try:
                obj_guid = obj.GetGUID()
            except Exception:
                obj_guid = None
            if obj_guid == target_guid:
                # Preserve the AUTO_ADDED bit while updating Mode bits.
                new_flags = pack_flags(mode, is_auto_added(flags))
                new_data.InsertObject(obj, int(new_flags))
                replaced = True
            else:
                new_data.InsertObject(obj, int(flags))
        if not replaced:
            # Target child wasn't in the list yet; defaulting AUTO_ADDED
            # to True since this path is only hit when the target was
            # implied by being a direct child (the InExcludeData fallback).
            new_data.InsertObject(target_child, int(pack_flags(mode, True)))
    else:
        new_data.InsertObject(target_child, int(pack_flags(mode, True)))

    try:
        brickit_op[BRICKIFYASSEMBLY_SOURCES] = new_data
    except Exception:
        return False
    return True


def primary_source_child(brickit_op):
    """Return the first Union child of `brickit_op`, or None.

    The "primary source" replaces the legacy LinkBox source for
    operations that still need a single reference scene object —
    bind-to-source-deformation tracking, the source-axis-local matrix
    used by the MoGraph rig, and the visualization name fallback. Phase
    3 collapses these readers onto this helper so they keep functioning
    with the child-list input model.
    """
    for child, mode in enumerate_brickit_sources(brickit_op):
        if mode == BRICKIFYASSEMBLY_SOURCE_MODE_UNION:
            return child
    return None


def has_any_source(brickit_op):
    """True if `brickit_op` has at least one source.

    A source is either a direct child of the BrickIt or a drag-dropped
    entry in the InExcludeData. The early-return GVO gate uses this to
    short-circuit a fresh BrickIt with nothing to bake.

    Bug history: previously only checked `op.GetDown()`, which broke the
    drag-drop path — a cube dragged from elsewhere lived in the
    InExcludeData but wasn't a child, so this returned False and GVO
    bailed before the bake stage.
    """
    if brickit_op is None:
        return False
    try:
        if brickit_op.GetDown() is not None:
            return True
    except Exception:
        pass
    try:
        data = brickit_op[BRICKIFYASSEMBLY_SOURCES]
        if data is not None and int(data.GetObjectCount()) > 0:
            return True
    except Exception:
        pass
    return False


def bake_brickit_sources(brickit_op, doc):
    """Bake every direct child via baked_polygon_object_with_metadata.

    Returns:
        per_mode: dict[int, list[(baked_polygon_obj, source_metadata, child_obj)]]
            Buckets keyed by Mode. Each entry preserves the per-child
            baked PolygonObject and the metadata returned by the bake
            helper (whose `groups` list already names the source so the
            existing `Island_Selections` flow keeps working).
        all_groups: list[dict]
            Flattened groups metadata across all children, in the same
            order as the children. Each group dict carries a "mode" key
            in addition to the existing point/poly range fields.

    A child that bakes to no polygons is dropped silently — the caller
    can detect "no Union sources" by checking the Union bucket length.
    """
    per_mode = {m: [] for m in VALID_MODES}
    all_groups = []
    if brickit_op is None:
        return per_mode, all_groups
    for child, mode in enumerate_brickit_sources(brickit_op):
        baked, metadata = baked_polygon_object_with_metadata(child, doc)
        if baked is None:
            continue
        try:
            point_count = int(baked.GetPointCount())
        except Exception:
            point_count = 0
        if point_count == 0:
            continue
        per_mode[mode].append((baked, metadata, child))
        groups = (metadata or {}).get("groups", []) if metadata else []
        for g in groups:
            tagged = dict(g)
            tagged["mode"] = mode
            all_groups.append(tagged)
    return per_mode, all_groups


def _matrix_key(obj):
    try:
        mg = obj.GetMg()
        return (
            round(float(mg.off.x), 6),
            round(float(mg.off.y), 6),
            round(float(mg.off.z), 6),
            round(float(mg.v1.x), 6),
            round(float(mg.v1.y), 6),
            round(float(mg.v1.z), 6),
            round(float(mg.v2.x), 6),
            round(float(mg.v2.y), 6),
            round(float(mg.v2.z), 6),
            round(float(mg.v3.x), 6),
            round(float(mg.v3.y), 6),
            round(float(mg.v3.z), 6),
        )
    except Exception:
        return ()


def _child_state_key(child, mode):
    if child is None:
        return (None, mode)
    try:
        guid = child.GetGUID()
    except Exception:
        guid = None
    try:
        dirty = int(child.GetDirty(c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_CACHE))
    except Exception:
        dirty = 0
    return (guid, dirty, _matrix_key(child), int(mode))


def bake_brickit_sources_per_mode(brickit_op, doc):
    """Bake one merged PolygonObject per non-empty Mode bucket.

    Children are grouped by Mode, then `baked_polygon_object_with_metadata`
    is called once per bucket with the bucket's children as a list root.
    The bake helper already merges multiple roots into one PolygonObject
    while emitting per-source `groups` metadata, so the existing
    `Island_Selections` flow keeps working unchanged.

    Returns:
        per_mode: dict[int, (baked_merged_poly, groups_metadata)]
            One entry per mode that had at least one child contributing
            geometry. Modes with no children (or only empty children)
            are absent from the dict, not present with a None value —
            callers should use ``mode in per_mode`` to test.
    """
    per_mode = {}
    if brickit_op is None:
        return per_mode
    by_mode = {m: [] for m in VALID_MODES}
    for child, mode in enumerate_brickit_sources(brickit_op):
        by_mode[mode].append(child)
    for mode, children in by_mode.items():
        if not children:
            continue
        baked, metadata = baked_polygon_object_with_metadata(children, doc)
        if baked is None:
            continue
        try:
            point_count = int(baked.GetPointCount())
        except Exception:
            point_count = 0
        if point_count == 0:
            continue
        per_mode[mode] = (baked, metadata or {"groups": []})
    return per_mode


def _voxel_mm(stud_size, plate_size):
    import numpy as np

    return np.array(
        [float(stud_size), float(plate_size), float(stud_size)],
        dtype=np.float64,
    )


def _grid_offset_in_voxels(grid_min, union_min, voxel_mm):
    """Integer voxel offset from `union_min` to `grid_min`.

    Both grids are anchored to the same world-axis lattice (because both
    use identical voxel_mm and the same floor() snap), so the offset is
    always an integer in voxel units.
    """
    import numpy as np

    delta = (grid_min - union_min) / voxel_mm
    return np.round(delta).astype(np.int64)


def compose_voxel_grids(per_bucket_results, voxel_mm, default_color):
    """Lattice-align and boolean-compose per-bucket voxel grids.

    Args:
        per_bucket_results: dict[int, (occupancy, colors, origin, info)]
            One entry per Mode bucket that voxelized successfully. Empty
            modes must be absent from the dict. All entries must share
            the same `voxel_mm`; their `origin`s are floor-snapped to a
            shared world-axis lattice so cell-level composition is exact.
        voxel_mm: shape-(3,) float64 array, the per-axis cell size.
        default_color: RGB tuple used when a composed cell has no source
            color (e.g. only an Intersect bucket had it).

    Returns:
        (occupancy, colors, origin, backend_info) — same tuple shape the
        single-source backend returns today, ready to feed brick_mesh as
        ``precomputed_voxels``.

        Returns None if the composed occupancy is empty (no Union cells,
        all Union cells subtracted away, etc.). Callers treat this the
        same as a single source that voxelized to nothing.
    """
    import numpy as np

    if not per_bucket_results:
        return None

    union_mode = BRICKIFYASSEMBLY_SOURCE_MODE_UNION
    subtract_mode = BRICKIFYASSEMBLY_SOURCE_MODE_SUBTRACT
    intersect_mode = BRICKIFYASSEMBLY_SOURCE_MODE_INTERSECT

    if union_mode not in per_bucket_results:
        # No Union sources means no positive volume to start from.
        return None

    # Union AABB across every bucket so every per-bucket grid fits.
    grid_mins = []
    grid_maxs = []
    for mode, (occ, _colors, origin, _info) in per_bucket_results.items():
        gmin = np.asarray(origin, dtype=np.float64)
        gmax = gmin + np.asarray(occ.shape, dtype=np.float64) * voxel_mm
        grid_mins.append(gmin)
        grid_maxs.append(gmax)
    union_min = np.min(np.stack(grid_mins, axis=0), axis=0)
    union_max = np.max(np.stack(grid_maxs, axis=0), axis=0)
    union_dims = np.maximum(
        1,
        np.round((union_max - union_min) / voxel_mm).astype(np.int64),
    )
    NX, NY, NZ = int(union_dims[0]), int(union_dims[1]), int(union_dims[2])

    def _empty_bool():
        return np.zeros((NX, NY, NZ), dtype=bool)

    union_occ = _empty_bool()
    subtract_occ = _empty_bool()
    intersect_occ = _empty_bool() if intersect_mode in per_bucket_results else None

    # Color assembly: keep the first-paint color from any Union bucket
    # (deterministic, since Phase 2 has only one Union bucket — multi-
    # bucket Union is collapsed to one merged poly upstream). Subtract
    # and Intersect buckets don't paint colors; they only carve.
    composed_colors = np.zeros((NX, NY, NZ, 3), dtype=np.uint8)
    composed_colors[..., 0] = int(default_color[0])
    composed_colors[..., 1] = int(default_color[1])
    composed_colors[..., 2] = int(default_color[2])
    color_painted = _empty_bool()

    backend_label_seen = None
    backend_fallback_any = False
    raw_occupied_total = 0
    volume_seconds_sum = 0.0
    sample_seconds_sum = 0.0
    sample_count_sum = 0
    note_fragments = []

    for mode, (occ, colors, origin, info) in per_bucket_results.items():
        offset = _grid_offset_in_voxels(
            np.asarray(origin, dtype=np.float64), union_min, voxel_mm
        )
        ox, oy, oz = int(offset[0]), int(offset[1]), int(offset[2])
        ex, ey, ez = ox + occ.shape[0], oy + occ.shape[1], oz + occ.shape[2]
        # Defensive clamp — should never trigger if grids are
        # lattice-aligned, but guards against a backend that snaps
        # origin differently.
        if ox < 0 or oy < 0 or oz < 0 or ex > NX or ey > NY or ez > NZ:
            continue
        if mode == union_mode:
            union_occ[ox:ex, oy:ey, oz:ez] |= occ
            paint_mask = occ & ~color_painted[ox:ex, oy:ey, oz:ez]
            if paint_mask.any():
                target_slice = composed_colors[ox:ex, oy:ey, oz:ez, :]
                target_slice[paint_mask] = colors[paint_mask]
                color_painted[ox:ex, oy:ey, oz:ez] |= occ
        elif mode == subtract_mode:
            subtract_occ[ox:ex, oy:ey, oz:ez] |= occ
        elif mode == intersect_mode:
            intersect_occ[ox:ex, oy:ey, oz:ez] |= occ
        else:
            continue

        backend_label = (info or {}).get("voxel_backend")
        if backend_label_seen is None:
            backend_label_seen = backend_label
        elif backend_label != backend_label_seen:
            backend_label_seen = "mixed"
        backend_fallback_any = backend_fallback_any or bool(
            (info or {}).get("voxel_backend_fallback", False)
        )
        raw_occupied_total += int((info or {}).get("voxel_backend_raw_occupied", 0) or 0)
        volume_seconds_sum += float((info or {}).get("voxel_backend_volume_seconds", 0.0) or 0.0)
        sample_seconds_sum += float((info or {}).get("voxel_backend_sample_seconds", 0.0) or 0.0)
        sample_count_sum += int((info or {}).get("voxel_backend_sample_count", 0) or 0)
        note = (info or {}).get("voxel_backend_note")
        if note:
            note_fragments.append("[mode={0}] {1}".format(mode, note))

    composed_occ = union_occ.copy()
    composed_occ &= ~subtract_occ
    if intersect_occ is not None:
        composed_occ &= intersect_occ

    if not composed_occ.any():
        return None

    backend_info = {
        "voxel_backend": backend_label_seen or "internal",
        "voxel_backend_requested": backend_label_seen or "internal",
        "voxel_backend_fallback": bool(backend_fallback_any),
        "voxel_backend_raw_occupied": int(raw_occupied_total),
        "voxel_backend_volume_seconds": float(volume_seconds_sum),
        "voxel_backend_sample_seconds": float(sample_seconds_sum),
        "voxel_backend_sample_count": int(sample_count_sum),
        "voxel_backend_composed_buckets": tuple(sorted(per_bucket_results.keys())),
        "voxel_backend_note": (
            "Composed {0} buckets; ".format(len(per_bucket_results))
            + " | ".join(note_fragments)
        ).strip(),
    }
    origin = union_min.astype(__import__("numpy").float64)
    return composed_occ, composed_colors, origin, backend_info


def voxelize_brickit_sources(
    brickit_op,
    doc,
    params,
    stud_size,
    plate_size,
    default_color,
    frame_inv=None,
):
    """Bake → voxelize → compose all child sources into one occupancy grid.

    Returns a precomputed_voxels tuple shaped exactly like the existing
    single-source backends:
        (occupancy, colors, origin, backend_info)
    or None if there are no Union children, or composition cancels out
    to nothing.

    Backend dispatch follows ``params["voxel_backend"]`` (`"c4d_volume"`
    or `"internal"`). All buckets use the same backend so their grids
    share the lattice snap.
    """
    import numpy as np

    from source_geometry import (
        c4d_volume_voxels_from_polygon_object,
        polygon_object_to_arrays,
    )

    per_mode_polys = bake_brickit_sources_per_mode(brickit_op, doc)
    if not per_mode_polys:
        return None
    if BRICKIFYASSEMBLY_SOURCE_MODE_UNION not in per_mode_polys:
        return None

    backend_key = str(params.get("voxel_backend") or "internal").lower()
    voxel_mm = _voxel_mm(stud_size, plate_size)

    per_bucket_voxels = {}
    for mode, (baked, _metadata) in per_mode_polys.items():
        try:
            n_pts = int(baked.GetPointCount())
            n_polys = int(baked.GetPolygonCount())
        except Exception:
            n_pts = 0
            n_polys = 0
        if n_pts <= 0 or n_polys <= 0:
            continue
        verts, faces = polygon_object_to_arrays(baked, frame_inv=frame_inv)
        if len(faces) == 0:
            continue
        if backend_key == "c4d_volume":
            try:
                result = c4d_volume_voxels_from_polygon_object(
                    baked,
                    verts,
                    params,
                    stud_size,
                    plate_size,
                    default_color,
                    frame_inv=frame_inv,
                )
            except Exception:
                # An empty/invalid bucket falls back to the internal
                # backend so a single bad mesh doesn't kill the whole
                # composition. The composed backend_info will record
                # the fallback.
                result = None
            if result is None:
                from brick.voxelize import voxelize_mesh
                try:
                    occ, col, origin = voxelize_mesh(
                        verts,
                        faces,
                        default_color=default_color,
                        mode=str(params.get("voxel_mode") or "solid"),
                        shell_thickness=int(params.get("shell_thickness", 1) or 1),
                        stud_size=float(stud_size),
                        plate_size=float(plate_size),
                    )
                except Exception:
                    continue
                result = (
                    occ,
                    col,
                    np.asarray(origin, dtype=np.float64),
                    {
                        "voxel_backend": "internal",
                        "voxel_backend_requested": "c4d_volume",
                        "voxel_backend_fallback": True,
                        "voxel_backend_note": "Bucket fell back to internal voxelizer.",
                    },
                )
        else:
            from brick.voxelize import voxelize_mesh
            try:
                occ, col, origin = voxelize_mesh(
                    verts,
                    faces,
                    default_color=default_color,
                    mode=str(params.get("voxel_mode") or "solid"),
                    shell_thickness=int(params.get("shell_thickness", 1) or 1),
                    stud_size=float(stud_size),
                    plate_size=float(plate_size),
                )
            except Exception:
                continue
            result = (
                occ,
                col,
                np.asarray(origin, dtype=np.float64),
                {
                    "voxel_backend": "internal",
                    "voxel_backend_requested": "internal",
                    "voxel_backend_fallback": False,
                    "voxel_backend_note": "",
                },
            )
        per_bucket_voxels[mode] = result

    if not per_bucket_voxels:
        return None
    if BRICKIFYASSEMBLY_SOURCE_MODE_UNION not in per_bucket_voxels:
        # If the only Union mesh failed to voxelize, treat as empty.
        return None

    return compose_voxel_grids(per_bucket_voxels, voxel_mm, default_color)


def sources_state_key(brickit_op):
    """Deterministic key over the full sources list for cache invalidation.

    Children are sorted by GUID so reordering siblings in the OM doesn't
    spuriously invalidate the cache; the per-child Mode is part of the
    tuple so changing a row's Mode does invalidate it.
    """
    pairs = enumerate_brickit_sources(brickit_op)
    keyed = [_child_state_key(c, m) for (c, m) in pairs]
    keyed.sort(key=lambda t: (t[0] if t[0] is not None else -1))
    return tuple(keyed)
