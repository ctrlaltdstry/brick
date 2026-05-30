"""BrickIt Follow Surface tag — drives proxy bricks along a deforming source.

Stamped on a Make-Proxies hierarchy when source-deformation binding is on.
Each frame, `Execute()` reads its parameters (Source link, Bind Records JSON,
Orientation Mode, Orientation Smoothing) and updates every bound carrier's
local matrix to its deformed-mesh position. Designed to act as the
keyframed target for Cinema 4D Rigid Body dynamics — Follow Position /
Follow Rotation springs pull each brick toward its deformed target while
collisions push neighbors apart.

Registered as a real Python TagData plugin (vs. the earlier TPython-tag
prototype) because programmatically setting `TPYTHON_CODE` does not
reliably trigger compilation in Cinema 4D 2026 — the tag stays inert. A
TagData plugin sidesteps that with a normal C++-style `Execute()` callback
and a proper Attribute Manager UI driven by `Tbrickitfollowsurface.res`.
"""
import json

import c4d
from c4d import plugins

from c4d_symbols import (
    ID_BRICKIFYASSEMBLY,
    ID_BRICKIT_FOLLOW_SURFACE_TAG,
    IDS_BRICKIT_FOLLOW_SURFACE_TAG,
    BRICKIT_FOLLOW_SURFACE_ENABLED,
    BRICKIT_FOLLOW_SURFACE_SOURCE,
    BRICKIT_FOLLOW_SURFACE_RECORDS,
    BRICKIT_FOLLOW_SURFACE_ORIENT_MODE,
    BRICKIT_FOLLOW_SURFACE_ORIENT_SMOOTHING,
    BRICKIT_FOLLOW_SURFACE_BAKE_BUTTON,
    BRICKIT_FOLLOW_SURFACE_SWAP_HERO_BUTTON,
    BRICKIT_FOLLOW_SURFACE_SWAP_QUALITY,
    BRICKIT_FOLLOW_SURFACE_BRICKIT_OP,
    BRICKIT_FOLLOW_SURFACE_ORIENT_WORLD_UP,
)
from quality_presets import (
    QUALITY_DRAFT,
    QUALITY_STANDARD,
    QUALITY_HERO,
)
from plugin_bootstrap import brick_log as _brick_log


def _load_tag_icon():
    return None


def _record_psr_at_time(obj, time):
    """Record position + rotation keyframes at `time` from the object's
    current local matrix. Six tracks total (PX/PY/PZ + RH/RP/RB)."""
    ml = obj.GetMl()
    pos = ml.off
    try:
        rot = c4d.utils.MatrixToHPB(ml)
    except Exception:
        rot = c4d.Vector(0, 0, 0)
    components = (
        (c4d.ID_BASEOBJECT_REL_POSITION, c4d.VECTOR_X, pos.x),
        (c4d.ID_BASEOBJECT_REL_POSITION, c4d.VECTOR_Y, pos.y),
        (c4d.ID_BASEOBJECT_REL_POSITION, c4d.VECTOR_Z, pos.z),
        (c4d.ID_BASEOBJECT_REL_ROTATION, c4d.VECTOR_X, rot.x),
        (c4d.ID_BASEOBJECT_REL_ROTATION, c4d.VECTOR_Y, rot.y),
        (c4d.ID_BASEOBJECT_REL_ROTATION, c4d.VECTOR_Z, rot.z),
    )
    for param_id, axis_id, value in components:
        desc_id = c4d.DescID(
            c4d.DescLevel(param_id, c4d.DTYPE_VECTOR, 0),
            c4d.DescLevel(axis_id, c4d.DTYPE_REAL, 0),
        )
        track = obj.FindCTrack(desc_id)
        if track is None:
            track = c4d.CTrack(obj, desc_id)
            obj.InsertTrackSorted(track)
        curve = track.GetCurve()
        result = curve.AddKey(time)
        if result is None:
            continue
        key = result.get("key") if isinstance(result, dict) else None
        if key is None:
            continue
        try:
            key.SetValue(curve, float(value))
        except Exception:
            pass


def _bake_keyframes(tag):
    """Iterate the document's preview range, evaluate the bind at each
    frame, and write PSR keyframes on every bound carrier. After bake,
    disable the tag so its per-frame Execute doesn't fight the tracks.
    """
    if tag is None:
        return False
    doc = tag.GetDocument()
    if doc is None:
        _brick_log("[brick] FollowSurface bake: no document")
        return False
    host = tag.GetObject()
    if host is None:
        _brick_log("[brick] FollowSurface bake: tag has no host")
        return False
    source_obj = tag[BRICKIT_FOLLOW_SURFACE_SOURCE]
    records_json = tag[BRICKIT_FOLLOW_SURFACE_RECORDS] or ""
    if source_obj is None or not records_json:
        _brick_log("[brick] FollowSurface bake: source/records missing")
        return False
    try:
        records = json.loads(records_json)
    except Exception as exc:
        _brick_log("[brick] FollowSurface bake: records parse failed: {0}".format(exc))
        return False
    try:
        orient_mode = int(tag[BRICKIT_FOLLOW_SURFACE_ORIENT_MODE] or 0)
    except Exception:
        orient_mode = 0
    try:
        smoothing = float(tag[BRICKIT_FOLLOW_SURFACE_ORIENT_SMOOTHING] or 0.0)
    except Exception:
        smoothing = 0.7

    from .brickit_bind_follower import (
        apply_follow_surface,
        _collect_carriers_by_index,
    )

    fps = doc.GetFps()
    start_frame = doc.GetMinTime().GetFrame(fps)
    end_frame = doc.GetMaxTime().GetFrame(fps)
    if end_frame < start_frame:
        end_frame = start_frame
    saved_time = doc.GetTime()

    carriers = _collect_carriers_by_index(host)
    if not carriers:
        _brick_log("[brick] FollowSurface bake: no bound carriers found")
        return False

    import time as _t

    t0 = _t.perf_counter()
    frames_done = 0
    for frame in range(start_frame, end_frame + 1):
        bt = c4d.BaseTime(frame, fps)
        try:
            doc.SetTime(bt)
            doc.ExecutePasses(
                None,
                animation=True,
                expressions=True,
                caches=True,
                flags=c4d.BUILDFLAGS_NONE,
            )
        except Exception:
            pass
        # Drive the carriers at this frame using the bind directly. We
        # don't rely on the tag's own Execute() running during the bake
        # (it would, but this guards against priority/eval surprises).
        try:
            apply_follow_surface(
                host, doc, source_obj, records, orient_mode, smoothing
            )
        except Exception:
            pass
        for carrier in carriers.values():
            _record_psr_at_time(carrier, bt)
        frames_done += 1

    try:
        doc.SetTime(saved_time)
        doc.ExecutePasses(
            None,
            animation=True,
            expressions=True,
            caches=True,
            flags=c4d.BUILDFLAGS_NONE,
        )
    except Exception:
        pass

    # Stop driving the carriers — keyframes are now authoritative.
    try:
        tag[BRICKIT_FOLLOW_SURFACE_ENABLED] = False
    except Exception:
        pass

    # Capture the proxy Fracture's effector-evaluated colors onto the
    # carriers BEFORE Instance→polygon conversion. Without this, any
    # color mutation from a Plain effector (with Random Field, gradient,
    # etc.) sitting on the Fracture's effector list lives only in the
    # Fracture's per-frame MoData and gets thrown away when the Fracture
    # is removed during bake. Stamping the evaluated color onto each
    # carrier's `ID_BASEOBJECT_COLOR` lets `_convert_instance_to_polygon`
    # carry it onto the polygon, where any material set up to read the
    # display color (e.g. RS Color User Data → "Display Color") picks
    # it up correctly post-bake.
    effector_color_stamped = _stamp_fracture_effector_colors(host, carriers.values())
    if effector_color_stamped > 0:
        _brick_log(
            "[brick] FollowSurface bake: stamped effector colors onto {0} carriers".format(
                effector_color_stamped
            )
        )

    # Make every brick instance editable (real polygon mesh). C4D PBD
    # doesn't simulate InstanceObjects directly; converting them gives
    # each brick its own polygon for collision-shape generation.
    # Animation tracks transfer to the new polygon objects.
    editable_carriers = _make_carriers_editable(host, doc)

    # Flatten: move every editable brick under a single "bricks" Null and
    # delete the now-empty Fracture / island Nulls so the OM shows just
    # `<root> / bricks / brick_*`.
    flat_carriers = _flatten_bricks(host, editable_carriers)

    # Add a per-brick Rigid Body tag with sensible defaults. We do this
    # AFTER make-editable + flatten so the tags land on the real polygons
    # under the flat parent.
    rbd_added = _add_per_brick_rigid_body(flat_carriers)

    elapsed = _t.perf_counter() - t0
    _brick_log(
        "[brick] FollowSurface bake: frames={0} ({1}-{2}), carriers={3}, "
        "made-editable={4}, flattened={5}, RBD-tags={6}, elapsed={7:.2f}s; "
        "tag disabled".format(
            frames_done,
            start_frame,
            end_frame,
            len(carriers),
            len(editable_carriers),
            len(flat_carriers),
            rbd_added,
            elapsed,
        )
    )
    try:
        c4d.EventAdd()
    except Exception:
        pass
    return True


def _find_proxy_fracture(host):
    """Return the proxy Fracture under `host` (the Make-Proxies handoff
    creates exactly one Omgfracture). None if not found."""
    if host is None:
        return None
    fracture_type = getattr(c4d, "Omgfracture", None)
    if fracture_type is None:
        return None
    stack = [host]
    while stack:
        n = stack.pop()
        try:
            if n.GetType() == fracture_type:
                return n
        except Exception:
            pass
        c = n.GetDown()
        while c:
            stack.append(c)
            c = c.GetNext()
    return None


def _read_fracture_effectors(fracture):
    """Return the Fracture's effectors as an InExcludeData (the format
    `_evaluate_native_mograph` accepts), or None if empty / unavailable."""
    if fracture is None:
        return None
    try:
        in_exclude = fracture[c4d.ID_MG_MOTIONGENERATOR_EFFECTORLIST]
    except Exception:
        return None
    if in_exclude is None:
        return None
    try:
        count = int(in_exclude.GetObjectCount())
    except Exception:
        return None
    if count <= 0:
        return None
    return in_exclude


def _stamp_fracture_effector_colors(host, carriers):
    """Evaluate the proxy Fracture's effector list against the current
    carriers and stamp the per-clone color onto each carrier's
    ID_BASEOBJECT_COLOR. Returns the number of carriers stamped, or 0 if
    no effector evaluation was applicable.

    Uses the BrickIt native MoGraph evaluator tag the integrated path
    already relies on, which honors Plain effector color modes + Field
    color sampling exactly the way the live preview does.
    """
    fracture = _find_proxy_fracture(host)
    if fracture is None:
        return 0
    effectors = _read_fracture_effectors(fracture)
    if effectors is None:
        return 0
    carriers = list(carriers or [])
    if not carriers:
        return 0
    # Sort by bind index so the matrices/colors order matches what each
    # carrier expects to receive back.
    indexed = []
    for c in carriers:
        try:
            idx = int(c[c4d.ID_USERDATA, 1] or 0)
        except Exception:
            idx = 0
        # Bind index is stored +1 (0 = sentinel "not set"); skip sentinels.
        if idx > 0:
            indexed.append((idx - 1, c))
    if not indexed:
        return 0
    indexed.sort(key=lambda t: t[0])

    matrices = []
    colors = []
    for _idx, c in indexed:
        try:
            matrices.append(c.GetMl())
        except Exception:
            matrices.append(c4d.Matrix())
        try:
            col = c[c4d.ID_BASEOBJECT_COLOR]
            colors.append(col if col is not None else c4d.Vector(1, 1, 1))
        except Exception:
            colors.append(c4d.Vector(1, 1, 1))

    # The integrated MoGraph evaluator helper lives in the generator
    # module; it expects `op` to be the generator that "owns" the clones,
    # which here is the Fracture itself. Effectors interpret matrices as
    # local to op_mg, and our carrier matrices are already in fracture-
    # local space (carriers are direct children of the Fracture in the
    # proxy hierarchy), so no frame_matrix conversion is needed.
    try:
        from .brickit_mograph_generator import _evaluate_native_mograph
    except Exception as exc:
        _brick_log(
            "[brick] FollowSurface bake: native evaluator import failed: {0}".format(exc)
        )
        return 0
    try:
        _out_mats, out_colors, _out_visible = _evaluate_native_mograph(
            fracture,
            matrices,
            colors,
            effectors,
            skip_field_override=True,
            label="bake_proxy",
            frame_matrix=None,
        )
    except Exception as exc:
        _brick_log(
            "[brick] FollowSurface bake: effector eval failed: {0}".format(exc)
        )
        return 0
    if out_colors is None or len(out_colors) != len(indexed):
        return 0

    stamped = 0
    for (idx_in_records, carrier), new_color in zip(indexed, out_colors):
        if new_color is None:
            continue
        try:
            carrier[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
            carrier[c4d.ID_BASEOBJECT_COLOR] = new_color
            stamped += 1
        except Exception:
            pass
    return stamped


def _make_carriers_editable(host, doc):
    """Replace each InstanceObject brick under `host` with a polygon clone
    of its template's mesh. Animation tracks and user data transfer to the
    new polygon. C4D's `MCOMMAND_MAKEEDITABLE` produced inconsistent
    results on instances pointing at Null-wrapped templates, so this does
    the conversion manually for reliability.
    """
    if host is None:
        return []
    # Snapshot the instance bricks (those with our bind_index user-data
    # field at ID 1) before mutating the hierarchy.
    originals = []
    stack = [host]
    while stack:
        n = stack.pop()
        try:
            ud_id = n[c4d.ID_USERDATA, 1]
        except Exception:
            ud_id = None
        if ud_id is not None and isinstance(ud_id, int) and ud_id > 0:
            originals.append(n)
        c = n.GetDown()
        while c:
            stack.append(c)
            c = c.GetNext()
    new_carriers = []
    for instance in originals:
        polygon = _convert_instance_to_polygon(instance)
        if polygon is not None:
            new_carriers.append(polygon)
    return new_carriers


def _find_template_polygon(template):
    """Return the polygon mesh inside a BrickIt template (Null wrapping a
    single polygon child) or `None` if the template can't be unwrapped."""
    if template is None:
        return None
    if template.CheckType(c4d.Opolygon):
        return template
    c = template.GetDown()
    while c is not None:
        if c.CheckType(c4d.Opolygon):
            return c
        # One-level recurse for nested wrappers.
        inner = c.GetDown()
        while inner is not None:
            if inner.CheckType(c4d.Opolygon):
                return inner
            inner = inner.GetNext()
        c = c.GetNext()
    return None


def _convert_instance_to_polygon(instance):
    """Replace `instance` with a polygon clone of its template's mesh.
    Preserves transform, color, animation tracks, and user data. Records
    the source template's name as `template_key` user-data so the
    Swap-to-Hero pass can find a matching hero template later."""
    if instance is None:
        return None
    parent = instance.GetUp()
    pred = instance.GetPred()
    try:
        template = instance[c4d.INSTANCEOBJECT_LINK]
    except Exception:
        template = None
    template_polygon = _find_template_polygon(template)
    if template_polygon is None:
        return None
    template_key = ""
    try:
        if template is not None:
            template_key = template.GetName() or ""
    except Exception:
        template_key = ""
    polygon = template_polygon.GetClone(c4d.COPYFLAGS_NONE)
    if polygon is None:
        return None
    polygon.SetName(instance.GetName())
    try:
        polygon.SetMl(instance.GetMl())
    except Exception:
        pass
    # Display color (used for per-brick palette).
    try:
        polygon[c4d.ID_BASEOBJECT_USECOLOR] = instance[c4d.ID_BASEOBJECT_USECOLOR]
        polygon[c4d.ID_BASEOBJECT_COLOR] = instance[c4d.ID_BASEOBJECT_COLOR]
    except Exception:
        pass
    # Move animation tracks from the instance to the new polygon. Tracks
    # are owned by the object they're attached to; Remove() detaches and
    # InsertTrackSorted reattaches.
    try:
        track = instance.GetFirstCTrack()
        while track is not None:
            next_track = track.GetNext()
            try:
                track.Remove()
                polygon.InsertTrackSorted(track)
            except Exception:
                pass
            track = next_track
    except Exception:
        pass
    # Copy user data (bind_index etc.) so post-bake passes can still find
    # the brick. AddUserData wants a fresh BaseContainer descriptor;
    # we re-insert each entry from the instance's user data container.
    try:
        ud_container = instance.GetUserDataContainer()
        for desc_id, desc_bc in ud_container:
            try:
                new_id = polygon.AddUserData(desc_bc)
                polygon[new_id] = instance[desc_id]
            except Exception:
                pass
    except Exception:
        pass
    # Stamp template_key so Swap-to-Hero can match by name later.
    if template_key:
        try:
            bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_STRING)
            bc[c4d.DESC_NAME] = "template_key"
            try:
                bc[c4d.DESC_HIDE] = True
            except Exception:
                pass
            ud_id = polygon.AddUserData(bc)
            polygon[ud_id] = template_key
        except Exception:
            pass
    # Insert the polygon where the instance was, then remove the instance.
    try:
        if pred is not None:
            polygon.InsertAfter(pred)
        elif parent is not None:
            polygon.InsertUnder(parent)
        instance.Remove()
    except Exception:
        pass
    return polygon


def _flatten_bricks(host, carriers):
    """Reparent every carrier directly under a single 'bricks' Null and
    remove the now-empty Fracture / island-group nulls between them.
    Returns the (possibly re-collected) carrier list rooted under the
    flat parent."""
    if host is None:
        return list(carriers or [])
    bricks_null = c4d.BaseObject(c4d.Onull)
    bricks_null.SetName("bricks")
    bricks_null.InsertUnder(host)
    fracture_types = tuple(
        t for t in (
            getattr(c4d, "Omgfracture", None),
            getattr(c4d, "Omograph_fracture", None),
            getattr(c4d, "Ovoronoifracture", None),
            getattr(c4d, "Ovoronoi_fracture", None),
        )
        if t is not None
    )
    parents_to_check = set()
    flat_list = []
    for carrier in carriers:
        if carrier is None:
            continue
        try:
            parent = carrier.GetUp()
            if parent is not None and parent is not bricks_null:
                parents_to_check.add(id(parent))
            carrier.Remove()
            carrier.InsertUnder(bricks_null)
            flat_list.append(carrier)
        except Exception:
            pass
    # Sweep the host hierarchy: remove empty Nulls / Fractures that used
    # to be carrier parents. Repeat until stable so chained empties go.
    def _is_disposable(node):
        if node is host or node is bricks_null:
            return False
        try:
            if node.GetDown() is not None:
                return False
        except Exception:
            return False
        if node.CheckType(c4d.Onull):
            return True
        for t in fracture_types:
            try:
                if node.CheckType(t):
                    return True
            except Exception:
                pass
        return False

    for _ in range(8):  # ample iterations for nested empties
        to_remove = []
        stack = [host]
        while stack:
            n = stack.pop()
            c = n.GetDown()
            while c:
                stack.append(c)
                c = c.GetNext()
            if _is_disposable(n):
                # Don't remove BRICK_LIBRARY_* template nulls — the bricks
                # don't reference them anymore but the user may want to
                # inspect what was used.
                name = n.GetName() or ""
                if name.startswith("BRICK_LIBRARY"):
                    continue
                to_remove.append(n)
        if not to_remove:
            break
        for n in to_remove:
            try:
                n.Remove()
            except Exception:
                pass
    return flat_list


def _add_per_brick_rigid_body(carriers):
    """Add a Rigid Body tag to each carrier with PBD defaults that work
    for animated bricks: enabled, follow position/rotation = 1.0, convex-
    hull collision shape."""
    rbd_type = getattr(c4d, "Trigidbody", None)
    if rbd_type is None:
        return 0
    added = 0
    for carrier in carriers:
        if carrier is None:
            continue
        try:
            existing = carrier.GetTag(rbd_type)
            tag = existing if existing is not None else carrier.MakeTag(rbd_type)
        except Exception:
            tag = None
        if tag is None:
            continue
        try:
            tag.SetName("brick_rigid_body")
        except Exception:
            pass
        for param_name, value in (
            ("RIGIDBODY_USE", True),
            (
                "RIGIDBODY_PBD_COLLISION_SHAPES",
                getattr(c4d, "RIGIDBODY_PBD_COLLISION_SHAPES_CONVEX_HULLS", None),
            ),
            ("RIGIDBODY_PBD_FOLLOW_POSITION", 1.0),
            ("RIGIDBODY_PBD_FOLLOW_ROTATION", 1.0),
            ("RIGIDBODY_PBD_FOLLOW_POSITION_STRENGTH", 1.0),
            ("RIGIDBODY_PBD_FOLLOW_ROTATION_STRENGTH", 1.0),
            ("RIGIDBODY_FOLLOW_POSITION", 1.0),
            ("RIGIDBODY_FOLLOW_ROTATION", 1.0),
        ):
            pid = getattr(c4d, param_name, None)
            if pid is None or value is None:
                continue
            try:
                tag[pid] = value
            except Exception:
                pass
        added += 1
    return added


def _read_template_key(obj):
    """Return the template_key user-data string stamped by the bake's
    instance→polygon conversion, or "" when not found."""
    if obj is None:
        return ""
    try:
        ud = obj.GetUserDataContainer()
    except Exception:
        return ""
    for desc_id, desc_bc in ud:
        try:
            name = desc_bc[c4d.DESC_NAME]
        except Exception:
            name = ""
        if str(name) == "template_key":
            try:
                return str(obj[desc_id] or "")
            except Exception:
                return ""
    return ""


def _replace_polygon_mesh(target, source):
    """Replace `target`'s points/polygons with `source`'s, in place.
    Object identity (Python ref, animation tracks, tags, parent) is
    preserved — only mesh data changes. Returns True on success."""
    if target is None or source is None:
        return False
    try:
        pts = source.GetAllPoints()
        polys = source.GetAllPolygons()
    except Exception:
        return False
    try:
        if not target.ResizeObject(len(pts), len(polys)):
            return False
        target.SetAllPoints(pts)
        for i, p in enumerate(polys):
            target.SetPolygon(i, p)
        target.Message(c4d.MSG_UPDATE)
        return True
    except Exception:
        return False


def _find_render_library(host):
    """Return the BRICK_LIBRARY_RENDER Null under `host` (created by
    Make Proxies)."""
    if host is None:
        return None
    c = host.GetDown()
    while c is not None:
        try:
            name = c.GetName() or ""
        except Exception:
            name = ""
        if name == "BRICK_LIBRARY_RENDER":
            return c
        c = c.GetNext()
    return None


def _find_template_under(root, name):
    """Find a template Null with `name` directly under `root`."""
    if root is None or not name:
        return None
    c = root.GetDown()
    while c is not None:
        try:
            n = c.GetName() or ""
        except Exception:
            n = ""
        if n == name:
            return c
        c = c.GetNext()
    return None


def _proxy_to_render_template_name(proxy_name):
    """Map a proxy template name to its render counterpart."""
    if not proxy_name:
        return ""
    if proxy_name.startswith("proxy_"):
        return "render_" + proxy_name[len("proxy_"):]
    return ""


def _swap_baked_to_hero(tag):
    """Replace each baked brick's mesh data with its hero-quality
    counterpart. Hero templates are built lazily via the BrickIt that
    produced the proxies (linked via the tag's BrickIt link)."""
    if tag is None:
        return False
    doc = tag.GetDocument()
    host = tag.GetObject()
    if doc is None or host is None:
        _brick_log("[brick] FollowSurface Swap to Hero: no doc/host")
        return False
    try:
        brickit_op = tag[BRICKIT_FOLLOW_SURFACE_BRICKIT_OP]
    except Exception:
        brickit_op = None
    if brickit_op is None:
        _brick_log(
            "[brick] FollowSurface Swap to Hero: Cubify link is empty — "
            "the hero builder needs the original Cubify object's brick "
            "library and params. Re-link it via the tag's 'Source Cubify' "
            "field, or re-run Make Proxies."
        )
        return False

    # The link returns the BaseObject. The BrickAssembly Python instance
    # (which holds the cached fit, mesh templates, and method bindings the
    # render-template builder calls) is reached via GetNodeData on the
    # BaseObject. Try several call forms because the C4D 2026 API has
    # variants depending on plugin type.
    brickit_self = None
    for call in (
        lambda o: o.GetNodeData(),
        lambda o: o.GetNodeData(ID_BRICKIFYASSEMBLY),
    ):
        try:
            candidate = call(brickit_op)
        except Exception:
            candidate = None
        if candidate is not None and hasattr(candidate, "_resolve_params"):
            brickit_self = candidate
            break
    if brickit_self is None:
        _brick_log(
            "[brick] FollowSurface Swap to Hero: could not retrieve "
            "BrickIt's Python instance from the linked BaseObject "
            "(GetNodeData returned None or the wrong type). The link "
            "must point at a BrickIt generator."
        )
        return False

    # Resolve params + info via the BrickIt — we need the brick library
    # mask, logo settings, stud/plate sizes, and fit info to drive the
    # render-template builder.
    try:
        from .brickit_sources import primary_source_child as _primary_source_child
        source_obj = _primary_source_child(brickit_op)
    except Exception:
        source_obj = None
    if source_obj is None:
        _brick_log("[brick] FollowSurface Swap to Hero: BrickIt has no source")
        return False
    try:
        params = brickit_self._resolve_params(brickit_op, source_obj)
    except Exception as exc:
        _brick_log(
            "[brick] FollowSurface Swap to Hero: resolve_params failed: {0}".format(exc)
        )
        return False
    # Override the BrickIt's quality with the swap-quality dropdown so the
    # render-template builder uses the user's chosen fidelity rather than
    # whatever's currently set on BrickIt (which is usually Proxy at this
    # point in the workflow). Cycle indices map directly to preset IDs:
    # 0 = Draft, 1 = Standard, 2 = Hero.
    try:
        swap_idx = int(tag[BRICKIT_FOLLOW_SURFACE_SWAP_QUALITY] or 0)
    except Exception:
        swap_idx = QUALITY_HERO
    swap_quality = (QUALITY_DRAFT, QUALITY_STANDARD, QUALITY_HERO)[
        max(0, min(2, swap_idx))
    ]
    params = dict(params)
    params["quality"] = int(swap_quality)
    info = getattr(brickit_self, "_fit_info", None)
    if not info:
        try:
            ok = brickit_self._refit_if_needed(brickit_op, doc, params)
        except Exception as exc:
            _brick_log(
                "[brick] FollowSurface Swap to Hero: refit failed: {0}".format(exc)
            )
            return False
        info = getattr(brickit_self, "_fit_info", None)
        if not ok or not info:
            _brick_log(
                "[brick] FollowSurface Swap to Hero: BrickIt fit unavailable"
            )
            return False

    render_root = _find_render_library(host)
    if render_root is None:
        # BRICK_LIBRARY_RENDER is created by Make Proxies. If it's missing,
        # something's structurally off; create one now to host the heroes.
        render_root = c4d.BaseObject(c4d.Onull)
        render_root.SetName("BRICK_LIBRARY_RENDER")
        park_m = c4d.Matrix()
        park_m.off = c4d.Vector(0.0, 1.0e9, 0.0)
        render_root.SetMl(park_m)
        try:
            render_root[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = c4d.OBJECT_OFF
            render_root[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = c4d.OBJECT_OFF
        except Exception:
            pass
        render_root.InsertUnder(host)

    # Walk baked polygons under host, group by template_key.
    polys_by_key = {}
    stack = [host]
    while stack:
        n = stack.pop()
        if n.CheckType(c4d.Opolygon):
            key = _read_template_key(n)
            if key:
                polys_by_key.setdefault(key, []).append(n)
        c = n.GetDown()
        while c:
            stack.append(c)
            c = c.GetNext()
    if not polys_by_key:
        _brick_log("[brick] FollowSurface Swap to Hero: no baked bricks found")
        return False

    # Build (or reuse) one hero template per unique key, then copy mesh
    # data onto every baked polygon with that key.
    from .brickit_mograph import (
        _build_render_template_proto,
        _parse_proxy_template_name,
    )
    from types import SimpleNamespace

    import time as _t

    t0 = _t.perf_counter()
    built = 0
    swapped = 0
    for key, polys in polys_by_key.items():
        base_target_name = _proxy_to_render_template_name(key)
        if not base_target_name:
            continue
        # Suffix the cached template name with the quality so successive
        # swaps at different qualities don't reuse a stale build.
        target_name = "{0}_q{1}".format(base_target_name, int(swap_quality))
        hero_proto = _find_template_under(render_root, target_name)
        if hero_proto is None:
            spec = _parse_proxy_template_name(key)
            if spec is None:
                continue
            w, d, h, smooth_top = spec
            brick_type = SimpleNamespace(width=w, depth=d, height=h)
            try:
                hero_proto = _build_render_template_proto(
                    brickit_self,
                    brick_type,
                    smooth_top,
                    render_root,
                    params,
                    info,
                    doc,
                    target_name,
                )
                built += 1
            except Exception as exc:
                _brick_log(
                    "[brick] FollowSurface Swap to Hero: build {0} failed: {1}".format(
                        target_name, exc
                    )
                )
                continue
        if hero_proto is None:
            continue
        hero_polygon = _find_template_polygon(hero_proto)
        if hero_polygon is None:
            continue
        for baked in polys:
            if _replace_polygon_mesh(baked, hero_polygon):
                swapped += 1

    elapsed = _t.perf_counter() - t0
    _brick_log(
        "[brick] FollowSurface Swap to Hero: built={0}, swapped={1}, "
        "elapsed={2:.2f}s".format(built, swapped, elapsed)
    )
    try:
        c4d.EventAdd()
    except Exception:
        pass
    return True


class BrickitFollowSurfaceTag(plugins.TagData):
    """Per-frame proxy-brick driver from a deforming source mesh."""

    def GetDEnabling(self, node, desc_id, t_data, flags, itemdesc):
        try:
            pid = desc_id[0].id
        except Exception:
            return True
        if pid == BRICKIT_FOLLOW_SURFACE_BAKE_BUTTON:
            try:
                records = node[BRICKIT_FOLLOW_SURFACE_RECORDS] or ""
                source = node[BRICKIT_FOLLOW_SURFACE_SOURCE]
            except Exception:
                return True
            return bool(records) and source is not None
        if pid in (
            BRICKIT_FOLLOW_SURFACE_SWAP_HERO_BUTTON,
            BRICKIT_FOLLOW_SURFACE_SWAP_QUALITY,
        ):
            try:
                brickit = node[BRICKIT_FOLLOW_SURFACE_BRICKIT_OP]
            except Exception:
                return True
            return brickit is not None
        return True

    def Init(self, node, isCloneInit=False):
        try:
            node[BRICKIT_FOLLOW_SURFACE_ENABLED] = True
            node[BRICKIT_FOLLOW_SURFACE_ORIENT_MODE] = BRICKIT_FOLLOW_SURFACE_ORIENT_WORLD_UP
            node[BRICKIT_FOLLOW_SURFACE_ORIENT_SMOOTHING] = 0.7
            node[BRICKIT_FOLLOW_SURFACE_SWAP_QUALITY] = 2  # cycle index 2 = Hero
            node[BRICKIT_FOLLOW_SURFACE_RECORDS] = ""
        except Exception:
            pass
        return True

    def Message(self, node, msg_type, data):
        if msg_type == c4d.MSG_DESCRIPTION_COMMAND:
            try:
                desc_id = data["id"][0].id
            except Exception:
                desc_id = -1
            if desc_id == BRICKIT_FOLLOW_SURFACE_BAKE_BUTTON:
                try:
                    _bake_keyframes(node)
                except Exception as exc:
                    import traceback
                    _brick_log(
                        "[brick] FollowSurface bake failed: {0}\n{1}".format(
                            exc, traceback.format_exc()
                        )
                    )
                return True
            if desc_id == BRICKIT_FOLLOW_SURFACE_SWAP_HERO_BUTTON:
                try:
                    _swap_baked_to_hero(node)
                except Exception as exc:
                    import traceback
                    _brick_log(
                        "[brick] FollowSurface Swap to Hero failed: {0}\n{1}".format(
                            exc, traceback.format_exc()
                        )
                    )
                return True
        return True

    def Execute(self, tag, doc, op, bt, priority, flags):
        try:
            enabled = bool(tag[BRICKIT_FOLLOW_SURFACE_ENABLED])
        except Exception:
            enabled = True
        if not enabled:
            return c4d.EXECUTIONRESULT_OK
        try:
            source_obj = tag[BRICKIT_FOLLOW_SURFACE_SOURCE]
        except Exception:
            source_obj = None
        if source_obj is None or op is None:
            return c4d.EXECUTIONRESULT_OK
        try:
            records_json = tag[BRICKIT_FOLLOW_SURFACE_RECORDS] or ""
        except Exception:
            records_json = ""
        if not records_json:
            return c4d.EXECUTIONRESULT_OK
        try:
            records = json.loads(records_json)
        except Exception as exc:
            _brick_log("[brick] FollowSurface: records JSON parse failed: {0}".format(exc))
            return c4d.EXECUTIONRESULT_OK
        try:
            orient_mode = int(tag[BRICKIT_FOLLOW_SURFACE_ORIENT_MODE] or 0)
        except Exception:
            orient_mode = 0
        try:
            smoothing = float(tag[BRICKIT_FOLLOW_SURFACE_ORIENT_SMOOTHING] or 0.0)
        except Exception:
            smoothing = 0.7
        smoothing = max(0.0, min(1.0, smoothing))
        try:
            from .brickit_bind_follower import apply_follow_surface
        except Exception as exc:
            _brick_log("[brick] FollowSurface: import failed: {0}".format(exc))
            return c4d.EXECUTIONRESULT_OK
        try:
            apply_follow_surface(op, doc, source_obj, records, orient_mode, smoothing)
        except Exception as exc:
            _brick_log("[brick] FollowSurface: update raised: {0}".format(exc))
        return c4d.EXECUTIONRESULT_OK


# Registration is performed directly from `c4d_brick_generator.pyp` so the
# `__res__` global (auto-injected only in .pyp modules) is in scope when
# `RegisterTagPlugin` looks up `Tbrickitfollowsurface.res`. Calling from a
# package submodule fails with "Could not find required '__res__'".
