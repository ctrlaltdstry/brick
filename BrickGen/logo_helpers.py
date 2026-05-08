"""Logo baking and placement helpers for BrickGen/BrickIt."""
import os
import c4d


BRICKGEN_LOGO_FILL_UI_DEFAULT = 0.0
BRICKGEN_LOGO_FILL_MIN_RATIO = 0.25
BRICKGEN_LOGO_FILL_MAX_RATIO = 0.40
BRICKGEN_LOGO_DEFAULT_SINK = 0.015
BRICKGEN_LOGO_BASE_OUTSET_RATIO = 0.006
BRICKGEN_LOGO_BASE_BEVEL_HEIGHT_RATIO = 0.018


def _logo_log_enabled():
    return os.environ.get("BRICKIT_LOG_LOGO", "").strip().lower() not in ("", "0", "false", "no")


def _logo_log(message):
    if not _logo_log_enabled():
        return
    try:
        c4d.GePrint("[brick] {0}".format(message))
    except Exception:
        try:
            print("[brick] {0}".format(message))
        except Exception:
            pass


# Last-known-good cache for transiently-failing LINK resolution. Keyed by
# (op GUID, param id); value is the C4D object we last successfully resolved.
# When both op[LINK_ID] and GetParameter+GetLink return None — which happens
# during nested message dispatch in C4D 2026 even though the link is set —
# we hand back the cached object so the rebuild doesn't drop the logo. The
# next clean rebuild repopulates the cache with a freshly-resolved value.
_logo_link_cache = {}


def _logo_link_cache_key(op, link_param_id):
    try:
        return (int(op.GetGUID()), int(link_param_id))
    except Exception:
        return None


def resolve_logo_source_link(op, link_param_id):
    """Resolve a LINK parameter's target with a doc-context fallback chain.

    `op[LINK_ID]` shorthand resolves the BaseLink against `op.GetDocument()`,
    which can transiently return None during nested message dispatch in some
    C4D 2026 configurations. When that happens, the logo silently disappears.
    Falling back to GetParameter + an explicit GetLink(doc) with the active
    document recovers the link in those cases. As a final safety net, when
    both resolution paths fail we return the most recent successful result so
    a transient hiccup doesn't drop the logo for a whole rebuild cycle.
    Returns None only when no link has ever been resolved for this op/param.
    """
    if op is None:
        return None
    cache_key = _logo_link_cache_key(op, link_param_id)
    target = None
    try:
        target = op[link_param_id]
    except Exception:
        target = None
    if target is not None:
        if cache_key is not None:
            _logo_link_cache[cache_key] = target
        return target

    doc = None
    try:
        doc = op.GetDocument()
    except Exception:
        doc = None
    if doc is None:
        try:
            doc = c4d.documents.GetActiveDocument()
        except Exception:
            doc = None

    try:
        link = op.GetParameter(c4d.DescID(link_param_id), c4d.DESCFLAGS_GET_NONE)
    except Exception:
        link = None
    if link is not None:
        for resolver in ("GetLink", "GetLinkAtom", "GetObject"):
            getter = getattr(link, resolver, None)
            if getter is None:
                continue
            try:
                resolved = getter(doc) if doc is not None else getter()
            except TypeError:
                try:
                    resolved = getter()
                except Exception:
                    resolved = None
            except Exception:
                resolved = None
            if resolved is not None:
                _logo_log(
                    "Logo link recovered via {0} for param id={1}".format(resolver, link_param_id)
                )
                if cache_key is not None:
                    _logo_link_cache[cache_key] = resolved
                return resolved

    if cache_key is not None:
        cached = _logo_link_cache.get(cache_key)
        if cached is not None:
            # Distinguish "transient resolution failure (link is still set
            # but C4D returned None mid-message-dispatch)" from "user
            # deleted the source mesh or cleared the link." In the first
            # case the cached object is still in the scene tree and
            # cached.GetDocument() returns the active doc. In the second
            # case the cached object is orphaned — IsAlive() may still
            # return True because of undo retention, but GetDocument()
            # returns None once the object is no longer in any doc tree.
            # Only reuse the cache when the cached object is still alive
            # AND still in a document. Otherwise drop the cache so a
            # subsequent Enable-Logo toggle doesn't resurrect a deleted
            # source.
            try:
                cached_alive = bool(cached.IsAlive())
            except Exception:
                cached_alive = False
            try:
                cached_doc = cached.GetDocument() if cached_alive else None
            except Exception:
                cached_doc = None
            if cached_alive and cached_doc is not None:
                _logo_log(
                    "Logo link transient resolution failed; reusing cached source for param id={0}".format(
                        link_param_id
                    )
                )
                return cached
            _logo_link_cache.pop(cache_key, None)
    return None


def logo_fill_to_diameter_ratio(value):
    """Map the UI fill percent (0..100) to actual stud-diameter fill."""
    try:
        fill_percent = float(value)
    except Exception:
        fill_percent = BRICKGEN_LOGO_FILL_UI_DEFAULT
    fill01 = max(0.0, min(1.0, fill_percent / 100.0))
    return (
        BRICKGEN_LOGO_FILL_MIN_RATIO
        + fill01 * (BRICKGEN_LOGO_FILL_MAX_RATIO - BRICKGEN_LOGO_FILL_MIN_RATIO)
    )


def apply_logo_y_rotation(matrix, degrees):
    """Rotate a logo transform around Y by an arbitrary number of degrees.

    Pure Y-axis rotation: v2 stays (0,1,0); v1 and v3 spin in the XZ plane.
    Accepts any float; the value is taken modulo 360.
    """
    import math
    angle_deg = float(degrees or 0.0) % 360.0
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    matrix.v1 = c4d.Vector(cos_a, 0.0, -sin_a)
    matrix.v2 = c4d.Vector(0.0, 1.0, 0.0)
    matrix.v3 = c4d.Vector(sin_a, 0.0, cos_a)
    return matrix


# Backward-compat shim — old call sites passed quarter-turn integers.  We
# now take degrees, but keep the old name working as `apply_logo_quarter_turn`
# so any external code or saved scripts still find it.  The argument is now
# interpreted as DEGREES, not quarter-turns.
def apply_logo_quarter_turn(matrix, degrees):
    return apply_logo_y_rotation(matrix, degrees)


def brick_logo_rotation_degrees(placement, base_rotation_deg, mix_flip, mix_amount, mix_seed):
    """Per-brick logo Y-rotation in degrees.

    When `mix_flip` is on, a stable hash of the brick's grid position decides
    whether to rotate this brick's logos. All studs on the same brick share
    the same rotation decision (the hash uses the placement origin, not
    per-stud coordinates), so a brick reads as one consistently-oriented
    LEGO piece. `mix_amount` is the fraction (0..1) of bricks that get a
    non-base rotation. `mix_seed` makes the choice reproducible.

    Rotation choices depend on brick footprint:
      - 1x1 bricks have four valid orientations (0/90/180/270), since the
        footprint is square; we split the rotated-bucket evenly across the
        three non-zero quarter-turns to get more variety.
      - Non-1x1 bricks (1xN, NxN where N>1, etc.) only have two valid
        orientations because rotating 90 degrees changes the footprint
        and would collide with neighbors. We keep the original 0/180 flip.
    """
    base = float(base_rotation_deg or 0.0) % 360.0
    if not mix_flip:
        return base
    amount = max(0.0, min(1.0, float(mix_amount or 0.0)))
    if amount <= 0.0:
        return base
    if placement is None:
        return base

    pw = int(getattr(placement, "w", 1))
    pd = int(getattr(placement, "d", 1))
    is_one_by_one = (pw == 1 and pd == 1)

    if amount >= 1.0:
        # All-bricks-rotated case. For 1x1, hash picks among the three
        # non-zero quarter turns; for the rest, just the 180 flip.
        if not is_one_by_one:
            return (base + 180.0) % 360.0

    # Hash the brick's grid origin + footprint into a stable integer in [0, 2^32).
    px = int(getattr(placement, "x", 0))
    py = int(getattr(placement, "y", 0))
    pz = int(getattr(placement, "z", 0))
    seed = int(mix_seed or 0)
    h = (
        (px * 0x1f1f1f1f)
        ^ (py * 0x9e3779b1)
        ^ (pz * 0x85ebca6b)
        ^ (pw * 0xc2b2ae35)
        ^ (pd * 0x27d4eb2f)
        ^ (seed * 0x165667b1)
    ) & 0xFFFFFFFF
    # Map hash to [0, 1) and compare against amount.
    bucket = (h * 2.3283064365386963e-10)  # 1/2^32

    if bucket >= amount:
        return base

    if is_one_by_one:
        # Pick from {90, 180, 270} via a second hash derived from the
        # first so the three options are reproducible per brick.
        sub = ((h >> 16) ^ (h * 0x45d9f3b)) & 0xFFFF
        idx = sub % 3
        delta = (idx + 1) * 90.0  # 90, 180, or 270
        return (base + delta) % 360.0
    return (base + 180.0) % 360.0


def soften_raised_logo_contact(poly_obj, stud_size, plate_size, blend=1.0):
    """Add a tiny beveled base flare so raised logos read as molded-on."""
    if poly_obj is None or poly_obj.GetPointCount() <= 0:
        return
    blend = max(0.0, min(1.0, float(blend)))
    if blend <= 1.0e-6:
        return
    try:
        points = list(poly_obj.GetAllPoints())
    except Exception:
        return
    if not points:
        return

    min_y = min(float(p.y) for p in points)
    max_y = max(float(p.y) for p in points)
    logo_h = max_y - min_y
    if logo_h <= 1.0e-6:
        return

    contact_h = min(
        logo_h * 0.45,
        float(plate_size) * BRICKGEN_LOGO_BASE_BEVEL_HEIGHT_RATIO,
    )
    contact_h *= blend
    outset = float(stud_size) * BRICKGEN_LOGO_BASE_OUTSET_RATIO * blend
    if contact_h <= 1.0e-6 or outset <= 1.0e-6:
        return

    for i, p in enumerate(points):
        y = float(p.y)
        if y > min_y + contact_h:
            continue
        radial = (1.0 - ((y - min_y) / contact_h)) * outset
        x = float(p.x)
        z = float(p.z)
        length = (x * x + z * z) ** 0.5
        if length <= 1.0e-6:
            continue
        scale = (length + radial) / length
        poly_obj.SetPoint(i, c4d.Vector(x * scale, y, z * scale))

    try:
        phong = poly_obj.GetTag(c4d.Tphong) or poly_obj.MakeTag(c4d.Tphong)
        if phong is not None:
            phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
            phong[c4d.PHONGTAG_PHONG_ANGLE] = c4d.utils.DegToRad(80.0)
    except Exception:
        pass
    poly_obj.Message(c4d.MSG_UPDATE)


def _object_label(obj, fallback):
    try:
        name = obj.GetName()
        if name:
            return str(name)
    except Exception:
        pass
    return fallback


def _polygon_group_meta(obj, point_start, point_count, poly_start, poly_count, fallback):
    return {
        "name": _object_label(obj, fallback),
        "point_start": int(point_start),
        "point_end": int(point_start + point_count),
        "poly_start": int(poly_start),
        "poly_end": int(poly_start + poly_count),
    }


def baked_polygon_object_with_metadata(source_obj, doc):
    """Return a polygon-only baked clone plus source child range metadata."""
    if source_obj is None:
        return None, {"groups": []}

    def _collect_polygons(root):
        found = []

        def _walk(o):
            if o is None:
                return
            if o.GetType() == c4d.Opolygon:
                found.append(o)
            ch = o.GetDown()
            while ch is not None:
                _walk(ch)
                ch = ch.GetNext()

        if isinstance(root, list):
            for r in root:
                _walk(r)
        else:
            _walk(root)
        return found

    def _merge_polygon_objects(found):
        if not found:
            return None
        if len(found) == 1:
            try:
                merged = found[0].GetClone(c4d.COPYFLAGS_NONE)
            except Exception:
                merged = found[0]
            return merged, {
                "groups": [
                    _polygon_group_meta(
                        found[0],
                        0,
                        found[0].GetPointCount(),
                        0,
                        found[0].GetPolygonCount(),
                        "source",
                    )
                ]
            }
        total_v = sum(o.GetPointCount() for o in found)
        total_f = sum(o.GetPolygonCount() for o in found)
        merged = c4d.PolygonObject(total_v, total_f)
        merged_uvw = None
        try:
            if any(o.GetTag(c4d.Tuvw) is not None for o in found):
                merged_uvw = c4d.UVWTag(total_f)
        except Exception:
            merged_uvw = None
        v_off = 0
        f_off = 0
        groups = []
        for o in found:
            pts = o.GetAllPoints()
            polys = o.GetAllPolygons()
            mg = o.GetMg()
            uvw = None
            try:
                uvw = o.GetTag(c4d.Tuvw)
            except Exception:
                uvw = None
            for i, p in enumerate(pts):
                merged.SetPoint(v_off + i, mg * p)
            for j, fp in enumerate(polys):
                merged.SetPolygon(
                    f_off + j,
                    c4d.CPolygon(fp.a + v_off, fp.b + v_off, fp.c + v_off, fp.d + v_off),
                )
                if merged_uvw is not None and uvw is not None:
                    try:
                        merged_uvw.SetSlow(f_off + j, uvw.GetSlow(j))
                    except Exception:
                        pass
            groups.append(
                _polygon_group_meta(
                    o,
                    v_off,
                    len(pts),
                    f_off,
                    len(polys),
                    "source_{0:03d}".format(len(groups) + 1),
                )
            )
            v_off += len(pts)
            f_off += len(polys)
        if merged_uvw is not None:
            try:
                merged.InsertTag(merged_uvw)
            except Exception:
                pass
        merged.Message(c4d.MSG_UPDATE)
        return merged, {"groups": groups}

    # Multi-input: when caller passes a list of scene objects, bake each
    # individually using the per-child path (which already handles
    # generators via cache walks and falls back to CSTO), then explicitly
    # apply each ORIGINAL child's GetMg() to lift its baked verts from
    # local space to world space. The orphaned-clone GetMg() is unreliable,
    # so we never trust it — we always use the live source's matrix.
    if isinstance(source_obj, list):
        sources = [s for s in source_obj if s is not None]
        if not sources:
            return None, {"groups": []}

        per_child_world = []  # list of (world_pts, polys, original_obj)
        total_v = 0
        total_f = 0
        for s in sources:
            try:
                src_mg = s.GetMg()
            except Exception:
                src_mg = c4d.Matrix()
            baked_one, _meta = baked_polygon_object_with_metadata(s, doc)
            if baked_one is None:
                continue
            try:
                pts = baked_one.GetAllPoints()
                polys = baked_one.GetAllPolygons()
            except Exception:
                continue
            if not polys or not pts:
                continue
            # The baked clone's points are in the ORIGINAL child's local
            # space (GetClone preserves the .GetMl() which holds the local
            # offset). Apply the original child's world matrix to lift to
            # world. We deliberately do NOT touch baked_one.GetMg() since
            # an orphan returns identity from GetMg().
            world_pts = [src_mg * p for p in pts]
            per_child_world.append((world_pts, polys, s))
            total_v += len(world_pts)
            total_f += len(polys)

        if not per_child_world or total_v == 0 or total_f == 0:
            return None, {"groups": []}

        merged = c4d.PolygonObject(total_v, total_f)
        groups = []
        v_off = 0
        f_off = 0
        seen_originals = []
        for world_pts, polys, original in per_child_world:
            for i, wp in enumerate(world_pts):
                merged.SetPoint(v_off + i, wp)
            for j, fp in enumerate(polys):
                merged.SetPolygon(
                    f_off + j,
                    c4d.CPolygon(
                        fp.a + v_off, fp.b + v_off, fp.c + v_off, fp.d + v_off
                    ),
                )
            # One group per original child (collapse multiple polygon
            # shards from the same original into a single contiguous
            # range when possible).
            if seen_originals and seen_originals[-1] is original:
                # Extend the previous group's range.
                last = groups[-1]
                last["point_end"] = v_off + len(world_pts)
                last["poly_end"] = f_off + len(polys)
            else:
                groups.append(
                    _polygon_group_meta(
                        original,
                        v_off,
                        len(world_pts),
                        f_off,
                        len(polys),
                        "source_{0:03d}".format(len(groups) + 1),
                    )
                )
                seen_originals.append(original)
            v_off += len(world_pts)
            f_off += len(polys)
        merged.Message(c4d.MSG_UPDATE)
        return merged, {"groups": groups}

    if source_obj.GetType() == c4d.Opolygon:
        try:
            baked = source_obj.GetClone(c4d.COPYFLAGS_NONE)
        except Exception:
            baked = source_obj
        return baked, {
            "groups": [
                _polygon_group_meta(
                    source_obj,
                    0,
                    source_obj.GetPointCount(),
                    0,
                    source_obj.GetPolygonCount(),
                    "source",
                )
            ]
        }

    cache_roots = []
    try:
        dc = source_obj.GetDeformCache()
        if dc is not None:
            cache_roots.append(dc)
    except Exception:
        pass
    try:
        cc = source_obj.GetCache()
        if cc is not None:
            cache_roots.append(cc)
    except Exception:
        pass
    for root in cache_roots:
        merged = _merge_polygon_objects(_collect_polygons(root))
        if merged is not None and merged[0] is not None and merged[0].GetPointCount() > 0:
            return merged

    csto_doc = doc
    if csto_doc is None:
        try:
            csto_doc = source_obj.GetDocument()
        except Exception:
            csto_doc = None
    if csto_doc is None:
        try:
            csto_doc = c4d.documents.GetActiveDocument()
        except Exception:
            csto_doc = None
    result = c4d.utils.SendModelingCommand(
        command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,
        list=[source_obj],
        mode=c4d.MODELINGCOMMANDMODE_ALL,
        doc=csto_doc,
    )
    if not result:
        _logo_log(
            "baked_polygon_object: CSTO returned no result for source={0!r} (doc={1})".format(
                source_obj.GetName() if source_obj is not None else None,
                "set" if csto_doc is not None else "None",
            )
        )
        return None, {"groups": []}
    merged = _merge_polygon_objects(_collect_polygons(result))
    if merged is not None and merged[0] is not None:
        return merged
    return None, {"groups": []}


def baked_polygon_object(source_obj, doc):
    """Return a polygon-only baked clone of `source_obj`."""
    baked, _metadata = baked_polygon_object_with_metadata(source_obj, doc)
    return baked


def logo_source_state_key(source_obj):
    """GUID + dirty flags + matrix snapshot; invalidates cached baked meshes."""
    if source_obj is None:
        return None
    src_dirty = source_obj.GetDirty(
        c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_CACHE
    )
    try:
        mg = source_obj.GetMg()
        matrix_key = (
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
        matrix_key = ()
    return (source_obj.GetGUID(), src_dirty, matrix_key)


def logo_link_identity_key(source_obj):
    """Stable identity for BrickGen caches while orbiting the viewport."""
    if source_obj is None:
        return None
    src_dirty = source_obj.GetDirty(c4d.DIRTYFLAGS_DATA)
    try:
        mg = source_obj.GetMg()
        matrix_key = (
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
        matrix_key = ()
    return (source_obj.GetGUID(), src_dirty, matrix_key)


def normalized_logo_mesh_object(
    source_obj,
    doc,
    stud_size,
    plate_size,
    *,
    diameter_ratio=BRICKGEN_LOGO_FILL_MIN_RATIO,
    height_ratio=0.06,
    blend=1.0,
):
    """Bake and normalize a logo as a local-XY stamp on the stud top."""
    if source_obj is None:
        _logo_log("normalized_logo_mesh_object: source_obj is None")
        return None
    if doc is None:
        try:
            doc = source_obj.GetDocument()
        except Exception:
            doc = None
    if doc is None:
        try:
            doc = c4d.documents.GetActiveDocument()
        except Exception:
            doc = None
    baked = baked_polygon_object(source_obj, doc)
    if baked is None:
        _logo_log(
            "normalized_logo_mesh_object: baked_polygon_object returned None for {0!r} (type={1})".format(
                source_obj.GetName() if source_obj is not None else None,
                source_obj.GetType() if source_obj is not None else None,
            )
        )
        return None
    if baked.GetPointCount() <= 0:
        _logo_log("normalized_logo_mesh_object: baked polygon has 0 points")
        return None
    try:
        pts = list(baked.GetAllPoints())
        mg = baked.GetMg()
    except Exception as exc:
        _logo_log("normalized_logo_mesh_object: failed reading baked points: {0}".format(exc))
        return None
    if not pts:
        _logo_log("normalized_logo_mesh_object: baked points list is empty")
        return None

    try:
        source_inv = ~source_obj.GetMg()
    except Exception:
        source_inv = c4d.Matrix()

    stamp = [source_inv * (mg * p) for p in pts]
    min_x = min(float(p.x) for p in stamp)
    max_x = max(float(p.x) for p in stamp)
    min_y = min(float(p.y) for p in stamp)
    max_y = max(float(p.y) for p in stamp)
    min_z = min(float(p.z) for p in stamp)
    max_z = max(float(p.z) for p in stamp)
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5
    xy_span = max(max_x - min_x, max_y - min_y)
    z_span = max_z - min_z
    xz_scale = (
        (float(stud_size) * float(diameter_ratio)) / xy_span
        if xy_span > 1.0e-8 else 1.0
    )
    y_scale = (
        (float(plate_size) * float(height_ratio)) / z_span
        if z_span > 1.0e-8 else xz_scale
    )
    for i, p in enumerate(stamp):
        baked.SetPoint(
            i,
            c4d.Vector(
                (float(p.x) - cx) * xz_scale,
                (float(p.z) - min_z) * y_scale,
                (float(p.y) - cy) * xz_scale,
            ),
        )
    soften_raised_logo_contact(baked, stud_size, plate_size, blend=blend)
    try:
        baked.SetMg(c4d.Matrix())
    except Exception:
        pass
    baked.SetName("tmpl_stud_logo_source")
    baked.Message(c4d.MSG_UPDATE)
    return baked
