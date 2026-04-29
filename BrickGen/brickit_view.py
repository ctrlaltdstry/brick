"""BrickIt generated hierarchy and debug visualization builders."""
from collections import defaultdict
from types import SimpleNamespace

import c4d

from brickit_animation import (
    exposed_top_cap_ids,
    phased_build_animation_states,
    smooth_top_cap_placements_for_coverage,
)
from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from logo_helpers import (
    BRICKGEN_LOGO_DEFAULT_SINK,
    apply_logo_quarter_turn as _apply_logo_quarter_turn,
)
from mesh_bridge import mesh_to_polygon_object
from plugin_bootstrap import brick_log as _brick_log


def _build_hierarchy(self, op):
    info = self._fit_info or {}
    params = self._resolve_params(op, op[BRICKIFYASSEMBLY_SOURCE])
    visualization_mode = params["visualization_mode"]

    # Voxel Debug must work even when there are no placements yet (e.g.
    # nothing in the brick library, or pipeline returned nothing because
    # of pruning). Otherwise the user has no way to inspect the voxel
    # grid. So defer the empty-placements early-return to non-debug modes.
    if not self._fit_placements and visualization_mode != BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG:
        return None
    if not info:
        return None

    stud_size = info.get("stud_size", 8.0)
    plate_size = info.get("plate_size", 3.2)
    origin = info.get("origin")
    if origin is None:
        return None
    quality = params["quality"]

    result = c4d.BaseObject(c4d.Onull)
    source_obj = op[BRICKIFYASSEMBLY_SOURCE]
    src_name = source_obj.GetName() if source_obj is not None else "mesh"
    result.SetName("Brickified_{0}".format(src_name))
    doc = op.GetDocument()

    templates_root = c4d.BaseObject(c4d.Onull)
    templates_root.SetName("brick_templates")
    TEMPLATES_PARK_Y = 1.0e9
    park_m = c4d.Matrix()
    park_m.off = c4d.Vector(0.0, TEMPLATES_PARK_Y, 0.0)
    templates_root.SetMl(park_m)
    templates_root.InsertUnder(result)

    instances_root = c4d.BaseObject(c4d.Onull)
    instances_root.SetName("bricks")
    instances_root.InsertUnder(result)

    logo_template = self._get_logo_template_obj(
        params,
        doc,
        stud_size,
        plate_size,
    )
    if logo_template is not None:
        logo_template.InsertUnder(templates_root)

    type_to_template = {}

    def _get_template_obj(
        brick_type,
        variant_key=None,
        smooth_plate_visual=True,
        force_smooth_top=False,
    ):
        tkey = (
            brick_type.width,
            brick_type.depth,
            brick_type.height,
            variant_key,
            int(bool(smooth_plate_visual)),
            int(bool(force_smooth_top)),
        )
        if tkey in type_to_template:
            return type_to_template[tkey]
        cache_key = (
            brick_type.width,
            brick_type.depth,
            brick_type.height,
            quality,
            round(float(stud_size), 6),
            round(float(plate_size), 6),
            int(bool(smooth_plate_visual)),
            int(bool(force_smooth_top)),
        )
        template_cache = getattr(self, "_template_obj_cache", None)
        if template_cache is None:
            template_cache = {}
            self._template_obj_cache = template_cache
        source_obj = template_cache.get(cache_key)
        if source_obj is None:
            mesh = self._get_template_mesh(
                brick_type,
                quality,
                stud_size,
                plate_size,
                smooth_plate_visual=smooth_plate_visual,
                force_smooth_top=force_smooth_top,
            )
            source_obj = mesh_to_polygon_object(
                mesh, name="tmpl_{0}x{1}x{2}p".format(
                    brick_type.width, brick_type.depth, brick_type.height
                )
            )
            template_cache[cache_key] = source_obj
        try:
            t_obj = source_obj.GetClone(c4d.COPYFLAGS_NONE)
        except Exception:
            t_obj = source_obj
        t_obj.InsertUnder(templates_root)
        type_to_template[tkey] = t_obj
        return t_obj

    mi_mode = getattr(c4d, "INSTANCEOBJECT_RENDERINSTANCE_MODE_MULTIINSTANCE", 2)

    from collections import defaultdict
    shell_depths = info.get("placement_shell_depths") or []
    depth_by_obj = {
        id(p): int(shell_depths[i])
        for i, p in enumerate(self._fit_placements)
        if i < len(shell_depths)
    }
    animation_placements = list(self._fit_placements or [])
    smooth_cap_ids = set()
    if bool(params.get("surface_only_plates")):
        smooth_cap_ids = exposed_top_cap_ids(animation_placements)
        generated_caps = smooth_top_cap_placements_for_coverage(
            animation_placements,
            params.get("top_surface_coverage", 1.0),
        )
        animation_placements.extend(generated_caps)
        smooth_cap_ids.update(id(p) for p in generated_caps)
    smooth_top_by_obj = {cap_id: True for cap_id in smooth_cap_ids}

    smooth_plate_visual = False
    animation_states = phased_build_animation_states(
        animation_placements,
        params.get("build_progress", 1.0),
        top_cap_ids=smooth_cap_ids,
        top_surface_phase=params.get("top_surface_phase", 0.15),
        y_offset=params.get("build_y_offset", 25.0),
        stagger=params.get("build_stagger", 0.10),
        motion_curve=params.get("build_motion_curve", 4),
        custom_curve=params.get("build_custom_curve"),
    )
    visible_placements = [
        state.placement
        for state in animation_states
        if state.local_progress > 0.0
    ]
    animation_state_by_obj = {
        id(state.placement): state
        for state in animation_states
    }

    by_type = defaultdict(list)
    for p in visible_placements:
        # Keep 90-degree placements in separate batches so we can use
        # swapped-footprint templates and avoid per-instance rotation
        # offset ambiguity in C4D matrix space.
        smooth_top_visual = int(bool(smooth_top_by_obj.get(id(p), False)))
        tkey = (
            p.brick.width,
            p.brick.depth,
            p.brick.height,
            p.rotation_y,
            smooth_top_visual,
        )
        by_type[tkey].append(p)

    def _lerp(a, b, t):
        return a + (b - a) * max(0.0, min(1.0, t))

    def _debug_color(p):
        if visualization_mode == BRICKIFYASSEMBLY_VISUALIZATION_MODE_BRICK_SIZE:
            footprint = max(1, int(p.w * p.d))
            t = min(1.0, (footprint - 1.0) / 15.0)
            return c4d.Vector(
                _lerp(0.10, 1.0, t),
                _lerp(0.35, 0.20, t),
                _lerp(1.0, 0.05, t),
            )
        if visualization_mode in (
            BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_DEPTH,
            BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME,
        ):
            depth = max(1, depth_by_obj.get(id(p), 1))
            t = min(1.0, (depth - 1.0) / 5.0)
            return c4d.Vector(
                _lerp(1.0, 0.05, t),
                _lerp(0.35, 0.75, t),
                _lerp(0.05, 1.0, t),
            )
        return c4d.Vector(0.58, 0.58, 0.58)

    def _color_key(v):
        return (
            int(round(max(0.0, min(1.0, v.x)) * 255.0)),
            int(round(max(0.0, min(1.0, v.y)) * 255.0)),
            int(round(max(0.0, min(1.0, v.z)) * 255.0)),
        )

    def _apply_object_color(obj, color):
        try:
            obj[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
            obj[c4d.ID_BASEOBJECT_COLOR] = color
        except Exception:
            pass

    def _make_wire_spline(name, placements):
        edge_count = len(placements) * 12
        point_count = edge_count * 2
        spline = c4d.SplineObject(point_count, c4d.SPLINETYPE_LINEAR)
        spline.SetName(name)
        try:
            spline.ResizeObject(point_count, edge_count)
        except Exception:
            pass

        edges = (
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        )
        point_idx = 0
        segment_idx = 0
        for p in placements:
            x0 = float(origin[0] + p.x * stud_size)
            y0 = float(origin[1] + p.y * plate_size)
            z0 = float(origin[2] + p.z * stud_size)
            x1 = x0 + float(p.w * stud_size)
            y1 = y0 + float(p.h * plate_size)
            z1 = z0 + float(p.d * stud_size)
            pts = (
                c4d.Vector(x0, y0, z0),
                c4d.Vector(x1, y0, z0),
                c4d.Vector(x1, y0, z1),
                c4d.Vector(x0, y0, z1),
                c4d.Vector(x0, y1, z0),
                c4d.Vector(x1, y1, z0),
                c4d.Vector(x1, y1, z1),
                c4d.Vector(x0, y1, z1),
            )
            for a, b in edges:
                spline.SetPoint(point_idx, pts[a])
                spline.SetPoint(point_idx + 1, pts[b])
                try:
                    spline.SetSegment(segment_idx, 2, False)
                except Exception:
                    pass
                point_idx += 2
                segment_idx += 1
        spline.Message(c4d.MSG_UPDATE)
        return spline

    def _make_fill_boxes(name, boxes):
        point_count = len(boxes) * 8
        poly_count = len(boxes) * 6
        obj = c4d.PolygonObject(point_count, poly_count)
        obj.SetName(name)
        pi = 0
        fi = 0
        for x, y, z, w, h, d in boxes:
            x0 = float(origin[0] + x * stud_size)
            y0 = float(origin[1] + y * plate_size)
            z0 = float(origin[2] + z * stud_size)
            x1 = x0 + float(w * stud_size)
            y1 = y0 + float(h * plate_size)
            z1 = z0 + float(d * stud_size)
            pts = (
                c4d.Vector(x0, y0, z0),
                c4d.Vector(x1, y0, z0),
                c4d.Vector(x1, y0, z1),
                c4d.Vector(x0, y0, z1),
                c4d.Vector(x0, y1, z0),
                c4d.Vector(x1, y1, z0),
                c4d.Vector(x1, y1, z1),
                c4d.Vector(x0, y1, z1),
            )
            for offset, point in enumerate(pts):
                obj.SetPoint(pi + offset, point)
            faces = (
                (0, 1, 2, 3),
                (4, 7, 6, 5),
                (0, 4, 5, 1),
                (1, 5, 6, 2),
                (2, 6, 7, 3),
                (3, 7, 4, 0),
            )
            for face in faces:
                obj.SetPolygon(
                    fi,
                    c4d.CPolygon(
                        pi + face[0],
                        pi + face[1],
                        pi + face[2],
                        pi + face[3],
                    ),
                )
                fi += 1
            pi += 8
        obj.Message(c4d.MSG_UPDATE)
        return obj

    if visualization_mode == BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG:
        occ_cells = info.get("occupancy_cells")
        occ_list = list(occ_cells) if occ_cells else []
        n_placements = len(self._fit_placements or [])
        try:
            _brick_log(
                "[brick] Voxel Debug: n_voxels={0}, n_placements={1}, "
                "grid_dims={2}, voxel_components={3}, voxels_dropped={4}".format(
                    len(occ_list),
                    n_placements,
                    info.get("grid_dims"),
                    info.get("voxel_components"),
                    info.get("n_voxels_dropped"),
                )
            )
        except Exception:
            pass

        vox_color = c4d.Vector(1.0, 0.55, 0.10)

        try:
            if occ_list:
                vox_boxes = [(x, y, z, 1, 1, 1) for x, y, z in occ_list]
                vox_obj = _make_fill_boxes(
                    "voxel_debug_occupancy", vox_boxes
                )
                _apply_object_color(vox_obj, vox_color)
                vox_obj.InsertUnder(instances_root)
            elif self._fit_placements:
                # Fallback: pipeline didn't supply occupancy cells (stale
                # module load, etc.). Render the union of placement
                # footprints so the debug view always shows SOMETHING.
                fb_color = c4d.Vector(1.0, 0.20, 0.20)
                fb_boxes = [
                    (p.x, p.y, p.z, p.w, p.h, p.d)
                    for p in self._fit_placements
                ]
                fb_obj = _make_fill_boxes(
                    "voxel_debug_placements_fallback", fb_boxes
                )
                _apply_object_color(fb_obj, fb_color)
                fb_obj.InsertUnder(instances_root)
            else:
                try:
                    _brick_log(
                        "[brick] Voxel Debug: no occupancy_cells "
                        "and no placements. Pipeline produced nothing."
                    )
                except Exception:
                    pass
        except Exception as exc:
            try:
                _brick_log(
                    "[brick] Voxel Debug: error rendering "
                    "boxes: {0}".format(exc)
                )
            except Exception:
                pass
        return result

    if visualization_mode == BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME:
        void_cells = info.get("interior_void_cells") or []
        if void_cells:
            void_boxes = [(x, y, z, 1, 1, 1) for x, y, z in void_cells]
            void_color = c4d.Vector(0.10, 0.55, 1.0)
            fill = _make_fill_boxes("hollow_interior_fill", void_boxes)
            _apply_object_color(fill, void_color)
            fill.InsertUnder(instances_root)

        wire_batches = defaultdict(list)
        for p in self._fit_placements:
            wire_batches[_color_key(_debug_color(p))].append(p)
        for color_key, batch in wire_batches.items():
            color = _debug_color(batch[0])
            wire = _make_wire_spline(
                "shell_wire_{0}_{1}_{2}".format(*color_key),
                batch,
            )
            _apply_object_color(wire, color)
            wire.InsertUnder(instances_root)
        return result

    for tkey, plist in by_type.items():
        batches = defaultdict(list)
        if visualization_mode == BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE:
            batches[None] = plist
        else:
            for p in plist:
                batches[_color_key(_debug_color(p))].append(p)

        for color_key, batch in batches.items():
            batch_color = _debug_color(batch[0])
            template_variant = None
            smooth_top_visual = bool(tkey[4]) if len(tkey) > 4 else False
            if visualization_mode != BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE:
                template_variant = color_key

            p0 = batch[0]
            if p0.rotation_y == 90:
                from types import SimpleNamespace
                template_brick = SimpleNamespace(
                    width=p0.brick.depth,
                    depth=p0.brick.width,
                    height=p0.brick.height,
                )
            else:
                template_brick = p0.brick
            template = _get_template_obj(
                template_brick,
                template_variant,
                smooth_plate_visual=smooth_plate_visual,
                force_smooth_top=smooth_top_visual,
            )
            _apply_object_color(template, batch_color)

            inst = c4d.BaseObject(c4d.Oinstance)
            if color_key is None:
                inst.SetName(
                    "bricks_{0}x{1}x{2}p_r{3}".format(
                        tkey[0], tkey[1], tkey[2], tkey[3]
                    )
                )
            else:
                inst.SetName(
                    "bricks_{0}x{1}x{2}p_r{3}_dbg_{4}_{5}_{6}".format(
                        tkey[0], tkey[1], tkey[2],
                        tkey[3],
                        color_key[0], color_key[1], color_key[2],
                    )
                )
            inst[c4d.INSTANCEOBJECT_LINK] = template
            _apply_object_color(inst, batch_color)
            try:
                inst[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = int(mi_mode)
            except Exception:
                pass

            matrices = []
            for p in batch:
                wx = float(origin[0] + p.x * stud_size)
                state = animation_state_by_obj.get(id(p))
                y_offset = float(state.y_offset) if state is not None else 0.0
                wy = float(origin[1] + p.y * plate_size + y_offset)
                wz = float(origin[2] + p.z * stud_size)
                m = c4d.Matrix()
                m.off = c4d.Vector(wx, wy, wz)
                matrices.append(m)

            try:
                inst.SetInstanceMatrices(matrices)
            except AttributeError:
                inst[c4d.INSTANCEOBJECT_MULTIPOSITIONS] = matrices

            inst.InsertUnder(instances_root)

    if logo_template is not None:
        logo_matrices = []
        stud_h = float(plate_size) * 0.55
        logo_rotation = int(params.get("logo_rotation", 0) or 0) % 4
        logo_sink = max(0.0, min(0.05, float(params.get("logo_sink", BRICKGEN_LOGO_DEFAULT_SINK))))
        logo_surface_bias = -float(plate_size) * logo_sink
        for p in visible_placements:
            state = animation_state_by_obj.get(id(p))
            y_offset = float(state.y_offset) if state is not None else 0.0
            smooth_top_visual = bool(smooth_top_by_obj.get(id(p), False))
            if smooth_top_visual:
                continue
            if int(getattr(p.brick, "height", 0)) == 1 and smooth_plate_visual:
                continue
            top_y = float(
                origin[1]
                + (p.y + p.h) * plate_size
                + stud_h
                + logo_surface_bias
                + y_offset
            )
            for sx in range(int(p.w)):
                for sz in range(int(p.d)):
                    m = c4d.Matrix()
                    m.off = c4d.Vector(
                        float(origin[0] + (p.x + sx + 0.5) * stud_size),
                        top_y,
                        float(origin[2] + (p.z + sz + 0.5) * stud_size),
                    )
                    _apply_logo_quarter_turn(m, logo_rotation)
                    logo_matrices.append(m)
        if logo_matrices:
            logo_inst = c4d.BaseObject(c4d.Oinstance)
            logo_inst.SetName("stud_logos")
            logo_inst[c4d.INSTANCEOBJECT_LINK] = logo_template
            try:
                logo_inst[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = int(mi_mode)
            except Exception:
                pass
            try:
                logo_inst.SetInstanceMatrices(logo_matrices)
            except AttributeError:
                logo_inst[c4d.INSTANCEOBJECT_MULTIPOSITIONS] = logo_matrices
            logo_inst.InsertUnder(instances_root)

    return result

