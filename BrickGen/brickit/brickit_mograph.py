"""BrickIt MoGraph handoff construction."""
import json
import time
from types import SimpleNamespace

import c4d

from .brickit_animation import (
    ordered_placements,
    smooth_top_cap_selection_for_coverage,
)
from .brickit_bind import deformed_centers_for_frame
from .brickit_bind_follower import UD_CARRIER_BIND_INDEX
from .brickit_groups import grouped_parent_for_placement
from .brickit_humanize import apply_humanize_to_low_corner_matrix
from .brickit_mograph_generator import (
    _color_vector_from_rgb as _color_vector_from_rgb_for_proxy,
    _evaluate_native_mograph as _evaluate_native_mograph_for_proxy,
    _has_mograph_effectors as _has_mograph_effectors_for_proxy,
)
from .brickit_runtime import _maybe_rebind
from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from logo_helpers import (
    BRICKGEN_LOGO_DEFAULT_SINK,
    apply_logo_quarter_turn as _apply_logo_quarter_turn,
)
from mesh_bridge import mesh_to_polygon_object
from plugin_bootstrap import (
    brick_log as _brick_log,
    ensure_brick_on_path as _ensure_brick_on_path,
)
from quality_presets import QUALITY_HERO
from source_geometry import source_axis_local_matrix


_BIND_FOLLOWER_TAG_NAME = "BrickIt Follow Surface"


def _stamp_carrier_bind_index(carrier, idx):
    """Stamp a hidden 'bind_index' user-data field on a proxy carrier.

    The follower walks the proxy hierarchy and matches carriers to bind
    records by this id. Stored as `idx + 1` so a default-zero on a non-
    bound carrier is distinguishable from index 0.
    """
    try:
        bc = c4d.GetCustomDataTypeDefault(c4d.DTYPE_LONG)
        bc[c4d.DESC_NAME] = "bind_index"
        try:
            bc[c4d.DESC_HIDE] = True
        except Exception:
            pass
        ud_id = carrier.AddUserData(bc)
        carrier[ud_id] = int(idx) + 1
    except Exception:
        pass


def _attach_bind_follower_tag(host, source_obj, records, params, brickit_op=None):
    """Add a BrickIt Follow Surface tag to `host` that drives proxy
    carriers from per-frame source deformation. `brickit_op` is the
    BrickIt generator that produced the proxies — stored on the tag so
    the post-bake "Swap to Hero" can reuse its template builder. Returns
    the tag or None on failure.
    """
    try:
        tag = host.MakeTag(ID_BRICKIT_FOLLOW_SURFACE_TAG)
    except Exception as exc:
        _brick_log("[brick] FollowSurface: MakeTag failed: {0}".format(exc))
        return None
    if tag is None:
        _brick_log(
            "[brick] FollowSurface: MakeTag returned None (is the tag plugin "
            "registered? restart Cinema 4D after first install)"
        )
        return None
    tag.SetName(_BIND_FOLLOWER_TAG_NAME)
    try:
        tag[BRICKIT_FOLLOW_SURFACE_ENABLED] = True
        tag[BRICKIT_FOLLOW_SURFACE_SOURCE] = source_obj
        tag[BRICKIT_FOLLOW_SURFACE_RECORDS] = json.dumps(records)
        tag[BRICKIT_FOLLOW_SURFACE_ORIENT_MODE] = int(
            params.get("bind_orientation_mode", 0) or 0
        )
        tag[BRICKIT_FOLLOW_SURFACE_ORIENT_SMOOTHING] = float(
            params.get("bind_orient_smoothing", 0.7) or 0.0
        )
        if brickit_op is not None:
            try:
                tag[BRICKIT_FOLLOW_SURFACE_BRICKIT_OP] = brickit_op
            except Exception:
                pass
    except Exception as exc:
        _brick_log("[brick] FollowSurface: param set failed: {0}".format(exc))
    try:
        tag.SetDirty(c4d.DIRTYFLAGS_DATA)
        host.SetDirty(c4d.DIRTYFLAGS_DATA)
    except Exception:
        pass
    return tag


def _hide_object_in_editor_and_render(obj):
    if obj is None:
        return
    try:
        obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = c4d.OBJECT_OFF
        obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = c4d.OBJECT_OFF
    except Exception:
        pass


def _set_document_to_frame_zero(doc):
    if doc is None:
        return
    try:
        doc.SetTime(c4d.BaseTime(0, doc.GetFps()))
    except Exception:
        try:
            doc.SetTime(c4d.BaseTime(0))
        except Exception:
            pass


def _configure_proxy_rigid_body(fracture):
    if fracture is None:
        return False
    tag_type = getattr(c4d, "Trigidbody", None)
    if tag_type is None:
        _brick_log("[brick] Proxy rig: Rigid Body tag type is unavailable")
        return False
    tag = fracture.GetTag(tag_type)
    if tag is None:
        tag = fracture.MakeTag(tag_type)
    if tag is None:
        _brick_log("[brick] Proxy rig: could not add Rigid Body tag")
        return False
    tag.SetName("proxy_rigid_body")
    settings = (
        # Tag ships disabled — user opts in by checking Enabled when ready.
        ("RIGIDBODY_USE", False),
        ("RIGIDBODY_PBD_SYNC_MOGRAPH_MATRIX", True),
        (
            "RIGIDBODY_PBD_MASS_SELECTION",
            getattr(c4d, "RIGIDBODY_PBD_USE_CUSTOM_MASS", None),
        ),
        (
            "RIGIDBODY_PBD_COLLISION_SHAPES",
            getattr(c4d, "RIGIDBODY_PBD_COLLISION_SHAPES_CONVEX_HULLS", None),
        ),
        ("RIGIDBODY_PBD_CONVEXDECOMPOSITION_ACCURACY", 10.0),
    )
    for param_name, value in settings:
        param_id = getattr(c4d, param_name, None)
        if param_id is None or value is None:
            continue
        try:
            tag[param_id] = value
        except Exception:
            pass
    try:
        fracture.Message(c4d.MSG_UPDATE)
    except Exception:
        pass
    return True


_PROXY_TEMPLATE_NAME_RE = None


def _parse_proxy_template_name(name):
    """Parse "proxy_brick_WxDxHp[_smooth]" into (w, d, h, smooth_top)."""
    global _PROXY_TEMPLATE_NAME_RE
    import re
    if _PROXY_TEMPLATE_NAME_RE is None:
        _PROXY_TEMPLATE_NAME_RE = re.compile(
            r"^proxy_brick_(\d+)x(\d+)_h(\d+)p(_smooth)?$"
        )
    if not name:
        return None
    match = _PROXY_TEMPLATE_NAME_RE.match(str(name))
    if match is None:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        match.group(4) is not None,
    )


def _collect_polygon_objects_with_matrices_top(obj, parent_m=None):
    """Module-level walker — duplicate of the nested closure for the swap path."""
    if obj is None:
        return []
    if parent_m is None:
        parent_m = c4d.Matrix()
    try:
        local_m = parent_m * obj.GetMl()
    except Exception:
        local_m = parent_m
    found = []
    if obj.GetType() == c4d.Opolygon:
        found.append((obj, local_m))
    child = obj.GetDown()
    while child is not None:
        found.extend(_collect_polygon_objects_with_matrices_top(child, local_m))
        child = child.GetNext()
    return found


def _merge_polygon_objects_local_top(objects_with_matrices, name):
    """Module-level merger — duplicate of the nested closure for the swap path."""
    objects_with_matrices = [
        (obj, matrix)
        for obj, matrix in (objects_with_matrices or [])
        if obj is not None and obj.GetType() == c4d.Opolygon
    ]
    if not objects_with_matrices:
        return None
    total_points = sum(obj.GetPointCount() for obj, _ in objects_with_matrices)
    total_polys = sum(obj.GetPolygonCount() for obj, _ in objects_with_matrices)
    merged = c4d.PolygonObject(total_points, total_polys)
    merged.SetName(name)
    point_offset = 0
    poly_offset = 0
    for obj, matrix in objects_with_matrices:
        try:
            points = obj.GetAllPoints()
            polygons = obj.GetAllPolygons()
        except Exception:
            continue
        for i, point in enumerate(points):
            try:
                merged.SetPoint(point_offset + i, matrix * point)
            except Exception:
                merged.SetPoint(point_offset + i, point)
        for j, poly in enumerate(polygons):
            merged.SetPolygon(
                poly_offset + j,
                c4d.CPolygon(
                    int(poly.a) + point_offset,
                    int(poly.b) + point_offset,
                    int(poly.c) + point_offset,
                    int(poly.d) + point_offset,
                ),
            )
        point_offset += obj.GetPointCount()
        poly_offset += obj.GetPolygonCount()
    try:
        phong = merged.MakeTag(c4d.Tphong)
        phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
        phong[c4d.PHONGTAG_PHONG_ANGLE] = c4d.utils.DegToRad(40.0)
    except Exception:
        pass
    merged.Message(c4d.MSG_UPDATE)
    return merged


def _build_render_template_proto(
    self, brick_type, smooth_top, render_root, params, info, doc, target_name
):
    """Build one render template Null + baked mesh under render_root.

    Used by `_swap_proxy_to_render_handoff` to lazily produce the render
    template the user is requesting. The template mesh is built at the
    BrickIt's current `Brick Mesh Detail` quality (params["quality"]) so
    swapping respects the user's chosen render fidelity rather than always
    forcing Hero. Stud logos are baked into a single merged polygon to keep
    the Redshift `Oinstance` reference shape `Null { merged_polygon }`.
    """
    from quality_presets import QUALITY_PROXY

    stud_size = float(info.get("stud_size", 8.0))
    plate_size = float(info.get("plate_size", 3.2))

    quality = int(params["quality"])
    # Render templates intentionally never use Proxy quality — that defeats
    # the swap. Clamp up to Draft when the BrickIt is at Proxy.
    if quality == int(QUALITY_PROXY):
        from quality_presets import QUALITY_DRAFT
        quality = int(QUALITY_DRAFT)

    mesh = self._get_template_mesh(
        brick_type,
        quality,
        stud_size,
        plate_size,
        smooth_plate_visual=False,
        force_smooth_top=bool(smooth_top),
    )
    proto = c4d.BaseObject(c4d.Onull)
    proto.SetName(target_name)
    mesh_obj = mesh_to_polygon_object(mesh, name="mesh_{0}".format(target_name))

    logo_template = self._get_logo_template_obj(params, doc, stud_size, plate_size)
    has_logos = (
        logo_template is not None
        and not bool(smooth_top)
        and int(getattr(brick_type, "height", 0)) >= 1
    )
    if has_logos:
        logo_rotation = int(params.get("logo_rotation", 0) or 0) % 4
        logo_sink = max(0.0, min(0.05, float(params.get("logo_sink", BRICKGEN_LOGO_DEFAULT_SINK))))
        logo_surface_bias = -plate_size * logo_sink
        objects = _collect_polygon_objects_with_matrices_top(mesh_obj)
        top_y = (
            float(brick_type.height) * plate_size
            + plate_size * 0.55
            + logo_surface_bias
        )
        for sx in range(int(brick_type.width)):
            for sz in range(int(brick_type.depth)):
                logo_obj = logo_template.GetClone(c4d.COPYFLAGS_NONE)
                if logo_obj is None:
                    continue
                m = c4d.Matrix()
                m.off = c4d.Vector(
                    float((sx + 0.5) * stud_size),
                    float(top_y),
                    float((sz + 0.5) * stud_size),
                )
                _apply_logo_quarter_turn(m, logo_rotation)
                try:
                    logo_obj.SetMl(m)
                except Exception:
                    pass
                objects.extend(_collect_polygon_objects_with_matrices_top(logo_obj))
        baked = _merge_polygon_objects_local_top(objects, mesh_obj.GetName())
        if baked is not None:
            mesh_obj = baked

    mesh_obj.InsertUnder(proto)
    proto.InsertUnder(render_root)
    return proto


def _create_mograph_handoff(self, op):
    return _create_mograph_handoff_impl(self, op, proxy=False)


def _create_proxy_mograph_handoff(self, op):
    return _create_mograph_handoff_impl(self, op, proxy=True)


def _create_mograph_handoff_impl(self, op, *, proxy=False):
    """Create a real scene-level MoGraph rig from the current BrickIt fit."""
    _t_total0 = time.perf_counter()
    _ensure_brick_on_path()
    doc = op.GetDocument()
    source_obj = op[BRICKIFYASSEMBLY_SOURCE]
    if doc is None or source_obj is None:
        _brick_log("[brick] MoGraph handoff: no document/source object")
        return False

    _t_refit0 = time.perf_counter()
    params = self._resolve_params(op, source_obj)
    if not self._refit_if_needed(op, doc, params):
        _brick_log("[brick] MoGraph handoff: fit is not available")
        return False
    bind_active = bool(params.get("bind_to_source_deformation"))
    if bind_active and proxy:
        # Ensure self._bind_records reflects the current fit/source pose so
        # the proxy carriers are baked at the deformed centers and the
        # follower tag has matching records to drive each frame.
        try:
            _maybe_rebind(self, params)
        except Exception as _bind_exc:
            _brick_log("[brick] MoGraph handoff: bind step failed: {0}".format(_bind_exc))
            bind_active = False
    _t_refit = time.perf_counter() - _t_refit0
    placements = ordered_placements(self._fit_placements or [])
    info = self._fit_info or {}
    if not placements or not info:
        _brick_log("[brick] MoGraph handoff: no placements to hand off")
        return False

    fracture_type = (
        getattr(c4d, "Omgfracture", None)
        or getattr(c4d, "Omograph_fracture", None)
        or 1018791
    )
    root = c4d.BaseObject(c4d.Onull)
    src_name = source_obj.GetName() if source_obj is not None else "mesh"
    if proxy:
        root.SetName("BrickIt_ProxySim_{0}".format(src_name))
    else:
        root.SetName("BrickIt_MoGraph_{0}".format(src_name))
    try:
        root.SetMg(source_obj.GetMg())
    except Exception:
        pass

    templates_root = c4d.BaseObject(c4d.Onull)
    templates_root.SetName("BRICK_LIBRARY_PROXY" if proxy else "BRICK_LIBRARY")
    park_m = c4d.Matrix()
    park_m.off = c4d.Vector(0.0, 1.0e9, 0.0)
    templates_root.SetMl(park_m)
    _hide_object_in_editor_and_render(templates_root)
    templates_root.InsertUnder(root)

    render_templates_root = None
    if proxy:
        render_templates_root = c4d.BaseObject(c4d.Onull)
        render_templates_root.SetName("BRICK_LIBRARY_RENDER")
        render_templates_root.SetMl(park_m)
        _hide_object_in_editor_and_render(render_templates_root)
        render_templates_root.InsertUnder(root)

    fracture = c4d.BaseObject(fracture_type)
    if fracture is None:
        _brick_log("[brick] MoGraph handoff: could not create Fracture object")
        return False
    fracture.SetName("bricks_mograph_fracture")
    try:
        fracture[c4d.MGFRACTUREOBJECT_MODE] = c4d.MGFRACTUREOBJECT_MODE_NONE
    except Exception:
        pass
    fracture.InsertUnder(root)

    stud_size = info.get("stud_size", 8.0)
    plate_size = info.get("plate_size", 3.2)
    origin = info.get("origin")
    if origin is None:
        _brick_log("[brick] MoGraph handoff: fit origin is missing")
        return False
    quality = params["quality"]
    smooth_plate_visual = False
    smooth_cap_ids = set()
    if bool(params.get("surface_only_plates")):
        smooth_cap_ids, generated_caps = smooth_top_cap_selection_for_coverage(
            placements,
            params.get("top_surface_coverage", 1.0),
            random_order=params.get("top_surface_random_order", False),
            cap_style=int(params.get("cap_style", 0)),
            library=None,
            seed=int(params.get("cap_random_seed", 0)),
        )
        placements = ordered_placements(list(placements) + generated_caps)
        smooth_cap_ids.update(id(p) for p in generated_caps)
    mi_mode = getattr(c4d, "INSTANCEOBJECT_RENDERINSTANCE_MODE_RENDERINSTANCE", 1)
    from brick.separation import placement_assembly_center, separated_low_corner
    brick_separation = float(params.get("brick_separation", 0.0) or 0.0)
    separation_center = placement_assembly_center(placements, stud_size, plate_size)

    type_to_template = {}
    type_to_render_template = {}
    logo_template = self._get_logo_template_obj(params, doc, stud_size, plate_size)
    logo_rotation = int(params.get("logo_rotation", 0) or 0) % 4
    logo_sink = max(0.0, min(0.05, float(params.get("logo_sink", BRICKGEN_LOGO_DEFAULT_SINK))))
    logo_surface_bias = -float(plate_size) * logo_sink

    def _brick_has_template_logos(brick_type, smooth_top=False):
        if logo_template is None:
            return False
        if bool(smooth_top):
            return False
        if int(getattr(brick_type, "height", 0)) == 1 and smooth_plate_visual:
            return False
        return True

    def _add_template_logo_children(proto, brick_type, smooth_top=False):
        if not _brick_has_template_logos(brick_type, smooth_top=smooth_top):
            return 0
        logos_root = c4d.BaseObject(c4d.Onull)
        logos_root.SetName("stud_logos")
        logos_root.InsertUnder(proto)
        top_y = (
            float(brick_type.height) * float(plate_size)
            + float(plate_size) * 0.55
            + logo_surface_bias
        )
        count = 0
        for sx in range(int(brick_type.width)):
            for sz in range(int(brick_type.depth)):
                logo_obj = logo_template.GetClone(c4d.COPYFLAGS_NONE)
                if logo_obj is None:
                    continue
                logo_obj.SetName("stud_logo")
                m = c4d.Matrix()
                m.off = c4d.Vector(
                    float((sx + 0.5) * stud_size),
                    float(top_y),
                    float((sz + 0.5) * stud_size),
                )
                _apply_logo_quarter_turn(m, logo_rotation)
                logo_obj.SetMl(m)
                logo_obj.InsertUnder(logos_root)
                count += 1
        return count

    def _collect_polygon_objects_with_matrices(obj, parent_m=None):
        if obj is None:
            return []
        if parent_m is None:
            parent_m = c4d.Matrix()
        try:
            local_m = parent_m * obj.GetMl()
        except Exception:
            local_m = parent_m
        found = []
        if obj.GetType() == c4d.Opolygon:
            found.append((obj, local_m))
        child = obj.GetDown()
        while child is not None:
            found.extend(_collect_polygon_objects_with_matrices(child, local_m))
            child = child.GetNext()
        return found

    def _merge_polygon_objects_local(objects_with_matrices, name):
        objects_with_matrices = list(objects_with_matrices or [])
        objects_with_matrices = [
            (obj, matrix)
            for obj, matrix in objects_with_matrices
            if obj is not None and obj.GetType() == c4d.Opolygon
        ]
        if not objects_with_matrices:
            return None
        total_points = sum(obj.GetPointCount() for obj, _ in objects_with_matrices)
        total_polys = sum(obj.GetPolygonCount() for obj, _ in objects_with_matrices)
        merged = c4d.PolygonObject(total_points, total_polys)
        merged.SetName(name)
        point_offset = 0
        poly_offset = 0
        for obj, matrix in objects_with_matrices:
            try:
                points = obj.GetAllPoints()
                polygons = obj.GetAllPolygons()
            except Exception:
                continue
            for i, point in enumerate(points):
                try:
                    merged.SetPoint(point_offset + i, matrix * point)
                except Exception:
                    merged.SetPoint(point_offset + i, point)
            for j, poly in enumerate(polygons):
                merged.SetPolygon(
                    poly_offset + j,
                    c4d.CPolygon(
                        int(poly.a) + point_offset,
                        int(poly.b) + point_offset,
                        int(poly.c) + point_offset,
                        int(poly.d) + point_offset,
                    ),
                )
            point_offset += obj.GetPointCount()
            poly_offset += obj.GetPolygonCount()
        try:
            phong = merged.MakeTag(c4d.Tphong)
            phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
            phong[c4d.PHONGTAG_PHONG_ANGLE] = c4d.utils.DegToRad(40.0)
        except Exception:
            pass
        merged.Message(c4d.MSG_UPDATE)
        return merged

    def _bake_template_logos_into_mesh(mesh_obj, brick_type, smooth_top=False):
        if mesh_obj is None or not _brick_has_template_logos(brick_type, smooth_top=smooth_top):
            return mesh_obj
        objects = _collect_polygon_objects_with_matrices(mesh_obj)
        top_y = (
            float(brick_type.height) * float(plate_size)
            + float(plate_size) * 0.55
            + logo_surface_bias
        )
        for sx in range(int(brick_type.width)):
            for sz in range(int(brick_type.depth)):
                logo_obj = logo_template.GetClone(c4d.COPYFLAGS_NONE)
                if logo_obj is None:
                    continue
                m = c4d.Matrix()
                m.off = c4d.Vector(
                    float((sx + 0.5) * stud_size),
                    float(top_y),
                    float((sz + 0.5) * stud_size),
                )
                _apply_logo_quarter_turn(m, logo_rotation)
                try:
                    logo_obj.SetMl(m)
                except Exception:
                    pass
                objects.extend(_collect_polygon_objects_with_matrices(logo_obj))
        baked = _merge_polygon_objects_local(objects, mesh_obj.GetName())
        return baked if baked is not None else mesh_obj

    def _stable_template_name(brick_type):
        return "brick_{0}x{1}_h{2}p".format(
            int(brick_type.width),
            int(brick_type.depth),
            int(brick_type.height),
        )

    def _get_template_obj(brick_type, smooth_top=False, render_template=False):
        if proxy:
            tkey = (
                "render" if render_template else "proxy",
                brick_type.width,
                brick_type.depth,
                brick_type.height,
                int(bool(smooth_top)),
            )
            cache = type_to_render_template if render_template else type_to_template
            if tkey in cache:
                return cache[tkey]

            base_name = _stable_template_name(brick_type)
            name = "{0}_{1}".format(
                "render" if render_template else "proxy",
                base_name,
            )
            if bool(smooth_top):
                name += "_smooth"
            if render_template:
                mesh = self._get_template_mesh(
                    brick_type,
                    QUALITY_HERO,
                    stud_size,
                    plate_size,
                    smooth_plate_visual=smooth_plate_visual,
                    force_smooth_top=bool(smooth_top),
                )
            else:
                mesh = self._get_proxy_template_mesh(
                    brick_type,
                    stud_size,
                    plate_size,
                    force_smooth_top=bool(smooth_top),
                )
            proto = c4d.BaseObject(c4d.Onull)
            proto.SetName(name)
            mesh_obj = mesh_to_polygon_object(
                mesh,
                name="mesh_{0}".format(name),
            )
            if render_template:
                mesh_obj = _bake_template_logos_into_mesh(
                    mesh_obj,
                    brick_type,
                    smooth_top=smooth_top,
                )
            mesh_obj.InsertUnder(proto)
            if render_template:
                proto.InsertUnder(render_templates_root)
            else:
                proto.InsertUnder(templates_root)
            cache[tkey] = proto
            return proto

        tkey = (
            brick_type.width,
            brick_type.depth,
            brick_type.height,
            int(bool(smooth_top)),
        )
        if tkey in type_to_template:
            return type_to_template[tkey]
        name = "brick_{0}x{1}".format(
            int(brick_type.width),
            int(brick_type.depth),
        )
        if int(brick_type.height) != 3:
            name += "_h{0}".format(int(brick_type.height))
        if bool(smooth_top):
            name += "_smooth"

        mesh = self._get_template_mesh(
            brick_type,
            quality,
            stud_size,
            plate_size,
            smooth_plate_visual=smooth_plate_visual,
            force_smooth_top=bool(smooth_top),
        )
        proto = c4d.BaseObject(c4d.Onull)
        proto.SetName(name)
        mesh_obj = mesh_to_polygon_object(
            mesh,
            name="mesh_{0}x{1}x{2}p".format(
                brick_type.width, brick_type.depth, brick_type.height
            ),
        )
        mesh_obj.InsertUnder(proto)
        _add_template_logo_children(proto, brick_type, smooth_top=smooth_top)
        proto.InsertUnder(templates_root)
        type_to_template[tkey] = proto
        return proto

    smooth_top_by_obj = {cap_id: True for cap_id in smooth_cap_ids}

    from types import SimpleNamespace

    _t_pre_loop0 = time.perf_counter()
    doc.StartUndo()
    try:
        try:
            root.InsertAfter(op)
        except Exception:
            doc.InsertObject(root)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, root)

        created_instances = 0
        logo_count = 0
        group_parent_cache = {}

        def _parent_for_placement(placement):
            if not proxy:
                return fracture
            return grouped_parent_for_placement(
                info,
                placement,
                fracture,
                group_parent_cache,
            )

        # When source-deformation binding is on, fetch the current-frame
        # deformed brick centers + orient basis from the bind. The proxy
        # carriers are then baked at those deformed positions (so the proxy
        # starts in the same pose the live preview shows), and the bind
        # records get mirrored onto a follower tag below so the proxies
        # continue tracking deformation per frame.
        bind_center_by_obj = None
        bind_orient_by_obj = None
        bind_record_by_obj = None
        if bind_active and proxy:
            try:
                centers, _vis, _ratios, orient_basis = deformed_centers_for_frame(
                    self, op, source_obj, doc, params
                )
            except Exception:
                centers = None
                orient_basis = None
            fit_placements = list(self._fit_placements or [])
            bind_records = self._bind_records or []
            if (
                centers is not None
                and bind_records
                and len(bind_records) == len(fit_placements)
            ):
                bind_center_by_obj = {}
                bind_record_by_obj = {}
                follow_normal = (
                    int(params.get("bind_orientation_mode", 0) or 0)
                    == BRICKIFYASSEMBLY_BIND_ORIENT_FOLLOW_NORMAL
                )
                if follow_normal and orient_basis is not None:
                    bind_orient_by_obj = {}
                for fi, fp in enumerate(fit_placements):
                    if fi < len(centers) and centers[fi] is not None:
                        bind_center_by_obj[id(fp)] = centers[fi]
                    if fi < len(bind_records) and bind_records[fi] is not None:
                        bind_record_by_obj[id(fp)] = bind_records[fi]
                    if (
                        bind_orient_by_obj is not None
                        and fi < len(orient_basis)
                        and orient_basis[fi] is not None
                    ):
                        bind_orient_by_obj[id(fp)] = orient_basis[fi]

        # Compute pre-effector matrices and colors in source-frame coordinates,
        # one per placement, in the same order the carrier-creation loop will
        # iterate. `root.SetMg(source_obj.GetMg())` above means root world ==
        # source_mg, so each placement's `m` (built from origin + separated_*
        # offsets) is already in the carrier's parent-local frame.
        _t_prematrices0 = time.perf_counter()
        pre_matrices = []
        pre_colors = []
        for p in placements:
            m = c4d.Matrix()
            sx, sy, sz = separated_low_corner(
                p,
                stud_size,
                plate_size,
                brick_separation,
                assembly_center=separation_center,
            )
            m.off = c4d.Vector(
                float(origin[0] + sx),
                float(origin[1] + sy),
                float(origin[2] + sz),
            )
            m = apply_humanize_to_low_corner_matrix(
                m,
                p,
                params,
                stud_size,
                plate_size,
            )
            if bind_center_by_obj is not None and id(p) in bind_center_by_obj:
                cx, cy, cz = bind_center_by_obj[id(p)]
                hx = 0.5 * float(getattr(p, "w", 1)) * stud_size
                hy = 0.5 * float(getattr(p, "h", 1)) * plate_size
                hz = 0.5 * float(getattr(p, "d", 1)) * stud_size
                m = c4d.Matrix()
                ob = (
                    bind_orient_by_obj.get(id(p))
                    if bind_orient_by_obj is not None
                    else None
                )
                if ob is not None:
                    v1, v2, v3 = ob
                    m.v1 = c4d.Vector(float(v1[0]), float(v1[1]), float(v1[2]))
                    m.v2 = c4d.Vector(float(v2[0]), float(v2[1]), float(v2[2]))
                    m.v3 = c4d.Vector(float(v3[0]), float(v3[1]), float(v3[2]))
                    shift_x = m.v1.x * hx + m.v2.x * hy + m.v3.x * hz
                    shift_y = m.v1.y * hx + m.v2.y * hy + m.v3.y * hz
                    shift_z = m.v1.z * hx + m.v2.z * hy + m.v3.z * hz
                    m.off = c4d.Vector(cx - shift_x, cy - shift_y, cz - shift_z)
                else:
                    m.off = c4d.Vector(cx - hx, cy - hy, cz - hz)
                m = apply_humanize_to_low_corner_matrix(
                    m, p, params, stud_size, plate_size,
                )
            pre_matrices.append(m)
            pre_colors.append(_color_vector_from_rgb_for_proxy(
                getattr(p, "rgb", (255, 255, 255))
            ))
        _t_prematrices = time.perf_counter() - _t_prematrices0

        # If MoGraph effectors are wired into BrickIt, run them through the
        # native evaluator with the same source-axis frame conversion the live
        # output uses. Each carrier is then created with the effector-resolved
        # matrix/color so the baked proxy hierarchy reflects what the user
        # sees in the live preview — useful as a "starting position" for a
        # downstream simulation.
        _t_eval0 = time.perf_counter()
        effector_visible = None
        if _has_mograph_effectors_for_proxy(params.get("mograph_effectors")):
            matrices, colors, effector_visible = _evaluate_native_mograph_for_proxy(
                op,
                pre_matrices,
                pre_colors,
                params.get("mograph_effectors"),
                skip_field_override=True,
                label="proxy_handoff" if proxy else "mograph_handoff",
                frame_matrix=source_axis_local_matrix(op, source_obj),
            )
        else:
            matrices, colors = pre_matrices, pre_colors
        _t_eval = time.perf_counter() - _t_eval0

        _t_carriers0 = time.perf_counter()
        follower_records = [] if (bind_active and proxy) else None
        for i, p in enumerate(placements):
            if (
                effector_visible is not None
                and i < len(effector_visible)
                and not bool(effector_visible[i])
            ):
                # Effector Visibility hid this clone — keep it out of the
                # baked hierarchy so the proxy matches the live render.
                continue

            if p.rotation_y == 90:
                template_brick = SimpleNamespace(
                    width=p.brick.depth,
                    depth=p.brick.width,
                    height=p.brick.height,
                )
            else:
                template_brick = p.brick
            smooth_top = bool(smooth_top_by_obj.get(id(p), False))
            if proxy:
                template = _get_template_obj(
                    template_brick,
                    smooth_top=smooth_top,
                    render_template=False,
                )
                # Render-quality templates are deferred to the first
                # Proxy/High Res swap. Pre-building them here at hero quality
                # for every unique brick type used to dominate Create Proxies
                # time (~36ms/brick × hundreds of placements). The swap path
                # builds them on demand from `BRICK_LIBRARY_RENDER` lazily.
            else:
                template = _get_template_obj(template_brick, smooth_top=smooth_top)
            if _brick_has_template_logos(template_brick, smooth_top=smooth_top):
                logo_count += int(template_brick.width) * int(template_brick.depth)

            name_prefix = "proxy_brick" if proxy else "brick"
            child_name = (
                "{0}_{1}x{2}x{3}p_{4:04d}".format(
                    name_prefix,
                    int(template_brick.width),
                    int(template_brick.depth),
                    int(template_brick.height),
                    created_instances,
                )
            )
            m = matrices[i] if i < len(matrices) else pre_matrices[i]
            color = colors[i] if i < len(colors) else pre_colors[i]
            child = c4d.BaseObject(c4d.Oinstance)
            child.SetName(child_name)
            child[c4d.INSTANCEOBJECT_LINK] = template
            try:
                if proxy:
                    child[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = int(
                        getattr(c4d, "INSTANCEOBJECT_RENDERINSTANCE_MODE_NONE", 0)
                    )
                else:
                    child[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = int(mi_mode)
            except Exception:
                pass
            child.SetMl(m)
            try:
                child[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
                child[c4d.ID_BASEOBJECT_COLOR] = color
            except Exception:
                pass
            child.InsertUnder(_parent_for_placement(p))
            if (
                follower_records is not None
                and bind_record_by_obj is not None
                and id(p) in bind_record_by_obj
            ):
                rec = bind_record_by_obj[id(p)]
                hx = 0.5 * float(getattr(p, "w", 1)) * stud_size
                hy = 0.5 * float(getattr(p, "h", 1)) * plate_size
                hz = 0.5 * float(getattr(p, "d", 1)) * stud_size
                idx = len(follower_records)
                follower_records.append(
                    {
                        "tri_idx": int(rec["tri_idx"]),
                        "bary": [
                            float(rec["bary"][0]),
                            float(rec["bary"][1]),
                            float(rec["bary"][2]),
                        ],
                        "normal_offset": float(rec["normal_offset"]),
                        "half_size": [hx, hy, hz],
                    }
                )
                _stamp_carrier_bind_index(child, idx)
            created_instances += 1
        _t_carriers = time.perf_counter() - _t_carriers0

        if (
            bind_active
            and proxy
            and follower_records
        ):
            _attach_bind_follower_tag(
                root, source_obj, follower_records, params, brickit_op=op
            )
            _brick_log(
                "[brick] MoGraph handoff: attached bind follower tag, "
                "records={0}".format(len(follower_records))
            )

        _t_finalize0 = time.perf_counter()
        if proxy:
            # Skip the frame-zero reset when binding is on; the follower
            # tag drives carrier transforms each frame and the user
            # explicitly chose the click-time pose as the dynamics start.
            if not bind_active:
                _set_document_to_frame_zero(doc)
            _configure_proxy_rigid_body(fracture)
            try:
                fracture.Message(c4d.MSG_UPDATE)
            except Exception:
                pass

        doc.SetActiveObject(fracture)
        c4d.EventAdd()
        _t_finalize = time.perf_counter() - _t_finalize0
        _t_total = time.perf_counter() - _t_total0
        _t_pre_loop = time.perf_counter() - _t_pre_loop0
        _brick_log(
            "[brick] MoGraph handoff: created {0}Fracture rig, bricks={1}, logos={2}, library_items={3}".format(
                "proxy " if proxy else "",
                created_instances,
                logo_count,
                len(type_to_template) + len(type_to_render_template),
            )
        )
        _brick_log(
            "[brick] MoGraph handoff timings: total={0:.3f}s, refit={1:.3f}s, "
            "pre_loop_setup={2:.3f}s, prematrices={3:.3f}s, effector_eval={4:.3f}s, "
            "carriers={5:.3f}s, finalize={6:.3f}s, placements={7}".format(
                float(_t_total),
                float(_t_refit),
                float(_t_pre_loop - _t_prematrices - _t_eval - _t_carriers - _t_finalize),
                float(_t_prematrices),
                float(_t_eval),
                float(_t_carriers),
                float(_t_finalize),
                int(len(placements)),
            )
        )
    finally:
        doc.EndUndo()
    return True


def _iter_scene_objects(root):
    obj = root
    while obj is not None:
        yield obj
        child = obj.GetDown()
        if child is not None:
            for nested in _iter_scene_objects(child):
                yield nested
        obj = obj.GetNext()


def _find_child(parent, name):
    child = parent.GetDown() if parent is not None else None
    while child is not None:
        if child.GetName() == name:
            return child
        child = child.GetNext()
    return None


def _child_name_map(parent):
    out = {}
    child = parent.GetDown() if parent is not None else None
    while child is not None:
        out[child.GetName()] = child
        child = child.GetNext()
    return out


def _swap_proxy_to_render_handoff(self, op):
    """Toggle generated proxy sim instances between proxy and render templates.

    Render templates are built lazily on first swap-to-render. Create Proxies
    skips the (expensive) render-template build, and the render mesh is only
    materialized when the user actually clicks Proxy/High Res. The render
    quality matches the BrickIt's current `Brick Mesh Detail` setting so the
    swap respects user intent (Standard / Hero), instead of always forcing
    Hero like the previous always-pre-built path did.
    """
    doc = op.GetDocument()
    if doc is None:
        _brick_log("[brick] Proxy swap: no document")
        return False

    # Resolve params and info once for any lazy render-template build below.
    swap_params = None
    swap_info = None
    swap_t_lazy_total = 0.0
    swap_lazy_built = 0
    try:
        source_obj = op[BRICKIFYASSEMBLY_SOURCE]
    except Exception:
        source_obj = None
    if source_obj is not None:
        try:
            swap_params = self._resolve_params(op, source_obj)
            self._refit_if_needed(op, doc, swap_params)
            swap_info = self._fit_info or {}
        except Exception as exc:
            _brick_log("[brick] Proxy swap: param resolve failed: {0}".format(exc))

    swapped = 0
    rig_count = 0
    doc.StartUndo()
    try:
        for root in _iter_scene_objects(doc.GetFirstObject()):
            proxy_root = _find_child(root, "BRICK_LIBRARY_PROXY")
            render_root = _find_child(root, "BRICK_LIBRARY_RENDER")
            if proxy_root is None or render_root is None:
                continue
            proxy_templates = _child_name_map(proxy_root)
            render_templates = _child_name_map(render_root)
            rig_instances = []
            target_mode = None
            for obj in _iter_scene_objects(root.GetDown()):
                if obj.GetType() != c4d.Oinstance:
                    continue
                linked = obj[c4d.INSTANCEOBJECT_LINK]
                if linked is None:
                    continue
                linked_name = linked.GetName()
                if linked_name.startswith("proxy_"):
                    rig_instances.append((obj, linked_name, "render"))
                    if target_mode is None:
                        target_mode = "render"
                elif linked_name.startswith("render_"):
                    rig_instances.append((obj, linked_name, "proxy"))
                    if target_mode is None:
                        target_mode = "proxy"
            if target_mode is None:
                continue
            rig_swaps = 0
            for obj, linked_name, available_target in rig_instances:
                if available_target != target_mode:
                    continue
                if target_mode == "render":
                    target_name = "render_" + linked_name[len("proxy_"):]
                    target_template = render_templates.get(target_name)
                    # Lazy-build the render template using the current
                    # Brick Mesh Detail. The proxy template name encodes the
                    # brick dims and the smooth-top flag, so we can derive
                    # the brick_type spec without crawling the rig further.
                    if (
                        target_template is None
                        and swap_params is not None
                        and swap_info is not None
                    ):
                        spec = _parse_proxy_template_name(linked_name)
                        if spec is not None:
                            w, d, h, smooth_top = spec
                            brick_type = SimpleNamespace(
                                width=int(w), depth=int(d), height=int(h)
                            )
                            try:
                                _t_lazy0 = time.perf_counter()
                                target_template = _build_render_template_proto(
                                    self,
                                    brick_type,
                                    smooth_top,
                                    render_root,
                                    swap_params,
                                    swap_info,
                                    doc,
                                    target_name,
                                )
                                swap_t_lazy_total += (time.perf_counter() - _t_lazy0)
                                swap_lazy_built += 1
                                render_templates[target_name] = target_template
                                doc.AddUndo(
                                    c4d.UNDOTYPE_NEWOBJ, target_template
                                )
                            except Exception as exc:
                                _brick_log(
                                    "[brick] Proxy swap: lazy render template "
                                    "build failed for {0}: {1}".format(
                                        target_name, exc,
                                    )
                                )
                                target_template = None
                else:
                    target_name = "proxy_" + linked_name[len("render_"):]
                    target_template = proxy_templates.get(target_name)
                if target_template is None:
                    continue
                doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)
                obj[c4d.INSTANCEOBJECT_LINK] = target_template
                try:
                    # Keep cached simulation children as normal instances.
                    # Switching to render-instance mode can detach them from
                    # cached Rigid Body playback in C4D's Fracture rig.
                    obj[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = int(
                        getattr(c4d, "INSTANCEOBJECT_RENDERINSTANCE_MODE_NONE", 0)
                    )
                except Exception:
                    pass
                rig_swaps += 1
            if rig_swaps:
                rig_count += 1
                swapped += rig_swaps
        c4d.EventAdd()
    finally:
        doc.EndUndo()

    if swapped:
        if swap_lazy_built:
            _brick_log(
                "[brick] Proxy swap: relinked {0} instances across {1} rig(s) "
                "(built {2} render templates lazily in {3:.3f}s)".format(
                    swapped, rig_count, swap_lazy_built, swap_t_lazy_total,
                )
            )
        else:
            _brick_log(
                "[brick] Proxy swap: relinked {0} instances across {1} rig(s)".format(
                    swapped, rig_count,
                )
            )
        return True
    _brick_log("[brick] Proxy swap: no proxy instances found")
    return False

