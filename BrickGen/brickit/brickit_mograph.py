"""BrickIt MoGraph handoff construction."""
from types import SimpleNamespace

import c4d

from .brickit_animation import (
    ordered_placements,
    smooth_top_cap_selection_for_coverage,
)
from .brickit_humanize import apply_humanize_to_low_corner_matrix
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
        ("RIGIDBODY_USE", True),
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


def _create_mograph_handoff(self, op):
    return _create_mograph_handoff_impl(self, op, proxy=False)


def _create_proxy_mograph_handoff(self, op):
    return _create_mograph_handoff_impl(self, op, proxy=True)


def _create_mograph_handoff_impl(self, op, *, proxy=False):
    """Create a real scene-level MoGraph rig from the current BrickIt fit."""
    _ensure_brick_on_path()
    doc = op.GetDocument()
    source_obj = op[BRICKIFYASSEMBLY_SOURCE]
    if doc is None or source_obj is None:
        _brick_log("[brick] MoGraph handoff: no document/source object")
        return False

    params = self._resolve_params(op, source_obj)
    if not self._refit_if_needed(op, doc, params):
        _brick_log("[brick] MoGraph handoff: fit is not available")
        return False
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

    doc.StartUndo()
    try:
        try:
            root.InsertAfter(op)
        except Exception:
            doc.InsertObject(root)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, root)

        created_instances = 0
        logo_count = 0
        for p in placements:
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
                _get_template_obj(
                    template_brick,
                    smooth_top=smooth_top,
                    render_template=True,
                )
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
            child.InsertUnder(fracture)
            created_instances += 1

        if proxy:
            _set_document_to_frame_zero(doc)
            _configure_proxy_rigid_body(fracture)
            try:
                fracture.Message(c4d.MSG_UPDATE)
            except Exception:
                pass

        doc.SetActiveObject(fracture)
        c4d.EventAdd()
        _brick_log(
            "[brick] MoGraph handoff: created {0}Fracture rig, bricks={1}, logos={2}, library_items={3}".format(
                "proxy " if proxy else "",
                created_instances,
                logo_count,
                len(type_to_template) + len(type_to_render_template),
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
    """Toggle generated proxy sim instances between proxy and render templates."""
    doc = op.GetDocument()
    if doc is None:
        _brick_log("[brick] Proxy swap: no document")
        return False

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
        _brick_log(
            "[brick] Proxy swap: relinked {0} instances across {1} rig(s)".format(
                swapped,
                rig_count,
            )
        )
        return True
    _brick_log("[brick] Proxy swap: no proxy instances found")
    return False

