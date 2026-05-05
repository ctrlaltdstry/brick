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


def resolve_logo_source_link(op, link_param_id):
    """Resolve a LINK parameter's target with a doc-context fallback chain.

    `op[LINK_ID]` shorthand resolves the BaseLink against `op.GetDocument()`,
    which can transiently return None during nested message dispatch in some
    C4D 2026 configurations. When that happens, the logo silently disappears.
    Falling back to GetParameter + an explicit GetLink(doc) with the active
    document recovers the link in those cases. Returns None when no link is
    set or when the link target genuinely does not exist.
    """
    if op is None:
        return None
    target = None
    try:
        target = op[link_param_id]
    except Exception:
        target = None
    if target is not None:
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
    if link is None:
        return None

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
            return resolved
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


def apply_logo_quarter_turn(matrix, quarter_turns):
    """Rotate a logo transform around Y in 90-degree steps."""
    q = int(quarter_turns or 0) % 4
    matrix.v2 = c4d.Vector(0.0, 1.0, 0.0)
    if q == 1:
        matrix.v1 = c4d.Vector(0.0, 0.0, -1.0)
        matrix.v3 = c4d.Vector(1.0, 0.0, 0.0)
    elif q == 2:
        matrix.v1 = c4d.Vector(-1.0, 0.0, 0.0)
        matrix.v3 = c4d.Vector(0.0, 0.0, -1.0)
    elif q == 3:
        matrix.v1 = c4d.Vector(0.0, 0.0, 1.0)
        matrix.v3 = c4d.Vector(-1.0, 0.0, 0.0)
    else:
        matrix.v1 = c4d.Vector(1.0, 0.0, 0.0)
        matrix.v3 = c4d.Vector(0.0, 0.0, 1.0)
    return matrix


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
