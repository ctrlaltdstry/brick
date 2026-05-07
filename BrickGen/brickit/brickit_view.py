"""BrickIt generated hierarchy and debug visualization builders."""
from collections import defaultdict
from types import SimpleNamespace

import c4d

from .brickit_animation import (
    build_scale_for_progress,
    build_tilt_clearance,
    build_tilt_for_progress,
    phased_build_animation_states,
    shell_smooth_top_target_cells,
    smooth_top_cap_selection_for_coverage,
)
from .brickit_humanize import apply_humanize_to_center_matrix
from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from logo_helpers import (
    BRICKGEN_LOGO_DEFAULT_SINK,
)
from mesh_bridge import mesh_to_polygon_object
from plugin_bootstrap import brick_log as _brick_log
from source_geometry import source_axis_local_matrix


def _build_hierarchy(self, op):
    from .brickit_sources import primary_source_child as _primary_source_child

    info = self._fit_info or {}
    params = self._resolve_params(op, _primary_source_child(op))
    visualization_mode = params["visualization_mode"]

    # Voxel Debug must work even when there are no placements yet (e.g.
    # nothing in the brick library, or pipeline returned nothing because
    # of pruning). Otherwise the user has no way to inspect the voxel
    # grid. So defer the empty-placements early-return to non-debug modes.
    if (
        not self._fit_placements
        and visualization_mode not in (
            BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME,
            BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG,
        )
    ):
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
    source_obj = _primary_source_child(op)
    if source_obj is not None:
        src_name = source_obj.GetName()
    else:
        try:
            src_name = op.GetName() or "mesh"
        except Exception:
            src_name = "mesh"
    result.SetName("Brickified_{0}".format(src_name))
    result.SetMl(source_axis_local_matrix(op, source_obj))
    doc = op.GetDocument()

    if visualization_mode in (
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG,
    ):
        instances_root = c4d.BaseObject(c4d.Onull)
        instances_root.SetName("bricks")
        instances_root.InsertUnder(result)

        shell_depths = info.get("placement_shell_depths") or []
        depth_by_obj = {
            id(p): int(shell_depths[i])
            for i, p in enumerate(self._fit_placements or [])
            if i < len(shell_depths)
        }

        def _lerp(a, b, t):
            return a + (b - a) * max(0.0, min(1.0, t))

        def _debug_color(p):
            depth = max(1, depth_by_obj.get(id(p), 1))
            t = min(1.0, (depth - 1.0) / 5.0)
            return c4d.Vector(
                _lerp(1.0, 0.05, t),
                _lerp(0.35, 0.75, t),
                _lerp(0.05, 1.0, t),
            )

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

        debug_materials = {}

        def _get_debug_material(color_key, color, transparent=False):
            if color_key is None or doc is None:
                return None
            mat_key = (color_key, bool(transparent))
            if mat_key in debug_materials:
                return debug_materials[mat_key]
            suffix = "Fill" if transparent else "Line"
            name = "Brick_Debug_{0}_{1}_{2}_{3}".format(
                color_key[0], color_key[1], color_key[2], suffix
            )
            try:
                mat = doc.SearchMaterial(name)
            except Exception:
                mat = None
            if mat is None:
                mat = c4d.BaseMaterial(c4d.Mmaterial)
                mat.SetName(name)
                doc.InsertMaterial(mat)
            try:
                mat[c4d.MATERIAL_COLOR_COLOR] = color
                mat[c4d.MATERIAL_COLOR_BRIGHTNESS] = 1.0
                if transparent:
                    mat[c4d.MATERIAL_USE_TRANSPARENCY] = True
                    mat[c4d.MATERIAL_TRANSPARENCY_BRIGHTNESS] = 0.72
                    mat[c4d.MATERIAL_TRANSPARENCY_COLOR] = color
                else:
                    mat[c4d.MATERIAL_USE_TRANSPARENCY] = False
                mat.Message(c4d.MSG_UPDATE)
            except Exception:
                pass
            debug_materials[mat_key] = mat
            return mat

        def _apply_material(obj, mat):
            if mat is None:
                return
            try:
                tag = c4d.TextureTag()
            except AttributeError:
                tag = c4d.BaseTag(c4d.Ttexture)
            tag[c4d.TEXTURETAG_MATERIAL] = mat
            obj.InsertTag(tag)

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

        def _make_wire_boxes(name, boxes):
            edge_count = len(boxes) * 12
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
            try:
                _brick_log(
                    "[brick] Voxel Debug: n_voxels={0}, n_placements={1}, "
                    "grid_dims={2}, voxel_components={3}, voxels_dropped={4}".format(
                        len(occ_list),
                        len(self._fit_placements or []),
                        info.get("grid_dims"),
                        info.get("voxel_components"),
                        info.get("n_voxels_dropped"),
                    )
                )
            except Exception:
                pass

            vox_color = c4d.Vector(1.0, 0.55, 0.10)
            vox_key = _color_key(vox_color)
            if occ_list:
                vox_obj = _make_fill_boxes(
                    "voxel_debug_occupancy",
                    [(x, y, z, 1, 1, 1) for x, y, z in occ_list],
                )
                _apply_object_color(vox_obj, vox_color)
                _apply_material(
                    vox_obj,
                    _get_debug_material(vox_key, vox_color, transparent=True),
                )
                vox_obj.InsertUnder(instances_root)
            elif self._fit_placements:
                fb_color = c4d.Vector(1.0, 0.20, 0.20)
                fb_key = _color_key(fb_color)
                fb_obj = _make_fill_boxes(
                    "voxel_debug_placements_fallback",
                    [(p.x, p.y, p.z, p.w, p.h, p.d) for p in self._fit_placements],
                )
                _apply_object_color(fb_obj, fb_color)
                _apply_material(
                    fb_obj,
                    _get_debug_material(fb_key, fb_color, transparent=True),
                )
                fb_obj.InsertUnder(instances_root)
            return result

        void_cells = info.get("interior_void_cells") or []
        occ_cells = info.get("occupancy_cells") or []
        try:
            _brick_log(
                "[brick] Shell Wireframe: placements={0}, void_cells={1}, "
                "occupancy_cells={2}, grid_dims={3}".format(
                    len(self._fit_placements or []),
                    len(void_cells),
                    len(occ_cells),
                    info.get("grid_dims"),
                )
            )
        except Exception:
            pass
        if void_cells:
            void_color = c4d.Vector(0.10, 0.55, 1.0)
            void_key = _color_key(void_color)
            fill = _make_fill_boxes(
                "hollow_interior_fill",
                [(x, y, z, 1, 1, 1) for x, y, z in void_cells],
            )
            _apply_object_color(fill, void_color)
            _apply_material(
                fill,
                _get_debug_material(void_key, void_color, transparent=True),
            )
            fill.InsertUnder(instances_root)

        shell_fill_boxes = [
            (p.x, p.y, p.z, p.w, p.h, p.d)
            for p in (self._fit_placements or [])
        ]
        if not shell_fill_boxes and occ_cells:
            shell_fill_boxes = [(x, y, z, 1, 1, 1) for x, y, z in occ_cells]
        if shell_fill_boxes:
            # Use polygon boxes, not only splines, so Shell Wireframe has a
            # visible viewport fallback whenever C4D drops generated splines.
            shell_fill_color = c4d.Vector(0.10, 0.80, 1.0)
            shell_fill_key = _color_key(shell_fill_color)
            shell_fill = _make_fill_boxes(
                "shell_wireframe_visible_fill",
                shell_fill_boxes,
            )
            _apply_object_color(shell_fill, shell_fill_color)
            _apply_material(
                shell_fill,
                _get_debug_material(
                    shell_fill_key,
                    shell_fill_color,
                    transparent=True,
                ),
            )
            shell_fill.InsertUnder(instances_root)

        try:
            wire_batches = defaultdict(list)
            for p in self._fit_placements or []:
                wire_batches[_color_key(_debug_color(p))].append(p)
            for color_key, batch in wire_batches.items():
                color = _debug_color(batch[0])
                wire = _make_wire_spline(
                    "shell_wire_{0}_{1}_{2}".format(*color_key),
                    batch,
                )
                _apply_object_color(wire, color)
                _apply_material(
                    wire,
                    _get_debug_material(color_key, color, transparent=False),
                )
                wire.InsertUnder(instances_root)
            if not wire_batches and occ_cells:
                # If fitting produced no placements, still show the sampled shell
                # cells so this preview mode never collapses to an empty object.
                shell_color = c4d.Vector(0.10, 0.80, 1.0)
                shell_key = _color_key(shell_color)
                wire = _make_wire_boxes(
                    "shell_wire_occupancy_fallback",
                    [(x, y, z, 1, 1, 1) for x, y, z in occ_cells],
                )
                _apply_object_color(wire, shell_color)
                _apply_material(
                    wire,
                    _get_debug_material(shell_key, shell_color, transparent=False),
                )
                wire.InsertUnder(instances_root)
        except Exception as exc:
            try:
                _brick_log(
                    "[brick] Shell Wireframe: wire spline generation skipped: {0}".format(
                        exc
                    )
                )
            except Exception:
                pass
        return result

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

    def _center_polygon_object(obj, brick_type):
        offset = c4d.Vector(
            -float(brick_type.width) * float(stud_size) * 0.5,
            -float(brick_type.height) * float(plate_size) * 0.5,
            -float(brick_type.depth) * float(stud_size) * 0.5,
        )
        try:
            points = obj.GetAllPoints()
            for i, point in enumerate(points):
                obj.SetPoint(i, point + offset)
            obj.Message(c4d.MSG_UPDATE)
        except Exception:
            pass
        return obj

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
            "center_pivot",
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
            _center_polygon_object(source_obj, brick_type)
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
    smooth_target_cells = None
    if (
        str(params.get("voxel_mode", "")).lower() == "shell"
        and info.get("occupancy_cells")
        and info.get("grid_dims")
    ):
        smooth_target_cells = shell_smooth_top_target_cells(
            animation_placements,
            info.get("occupancy_cells"),
            info.get("grid_dims"),
            interior_void_cells=info.get("interior_void_cells"),
        )
    if bool(params.get("surface_only_plates")):
        smooth_cap_ids, generated_caps = smooth_top_cap_selection_for_coverage(
            animation_placements,
            params.get("top_surface_coverage", 1.0),
            random_order=params.get("top_surface_random_order", False),
            cap_style=int(params.get("cap_style", 0)),
            library=None,
            seed=int(params.get("cap_random_seed", 0)),
            target_top_cells=smooth_target_cells,
        )
        animation_placements.extend(generated_caps)
        smooth_cap_ids.update(id(p) for p in generated_caps)
    smooth_top_by_obj = {cap_id: True for cap_id in smooth_cap_ids}

    smooth_plate_visual = False
    animation_states = phased_build_animation_states(
        animation_placements,
        params.get("build_progress", 1.0),
        time_progress=params.get("build_progress_time", params.get("build_progress", 1.0)),
        top_progress=params.get("smooth_top_progress", 1.0),
        top_time_progress=params.get("smooth_top_progress_time", params.get("smooth_top_progress", 1.0)),
        top_cap_ids=smooth_cap_ids,
        top_surface_start=params.get("top_surface_start", 0.85),
        top_surface_phase=params.get("top_surface_phase", 0.15),
        blend_top_surface=params.get("top_surface_blend", False),
        y_offset=params.get("build_y_offset", 25.0),
        stagger=params.get("build_stagger", 0.10),
        hang_time=params.get("build_hang_time", 0.0),
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
    scale_bricks_in = bool(params.get("build_scale_in", False))
    subtle_rotation = bool(params.get("build_subtle_rotation", False))
    tilt_amount = float(params.get("build_tilt_amount", 5.0))
    from brick.separation import (
        placement_assembly_center,
        separated_center,
        separated_low_corner,
    )
    brick_separation = float(params.get("brick_separation", 0.0) or 0.0)
    separation_center = placement_assembly_center(animation_placements, stud_size, plate_size)

    def _placement_scene_low_corner(p):
        sx, sy, sz = separated_low_corner(
            p,
            stud_size,
            plate_size,
            brick_separation,
            assembly_center=separation_center,
        )
        return (
            float(origin[0] + sx),
            float(origin[1] + sy),
            float(origin[2] + sz),
        )

    def _placement_scene_center(p):
        support = getattr(p, "support", None)
        if support is not None:
            ssx, ssy, ssz = separated_center(
                support,
                stud_size,
                plate_size,
                brick_separation,
                assembly_center=separation_center,
            )
            cx_local = (float(p.x) + float(p.w) * 0.5) * float(stud_size)
            cz_local = (float(p.z) + float(p.d) * 0.5) * float(stud_size)
            sx_local = (float(support.x) + float(support.w) * 0.5) * float(stud_size)
            sz_local = (float(support.z) + float(support.d) * 0.5) * float(stud_size)
            wy = (
                ssy
                + float(support.h) * 0.5 * float(plate_size)
                + float(p.h) * 0.5 * float(plate_size)
            )
            return (
                float(origin[0] + ssx + (cx_local - sx_local)),
                float(origin[1] + wy),
                float(origin[2] + ssz + (cz_local - sz_local)),
            )
        sx, sy, sz = separated_center(
            p,
            stud_size,
            plate_size,
            brick_separation,
            assembly_center=separation_center,
        )
        return (
            float(origin[0] + sx),
            float(origin[1] + sy),
            float(origin[2] + sz),
        )

    def _box_scene_low_corner(x, y, z, w, h, d):
        proxy = SimpleNamespace(x=x, y=y, z=z, w=w, h=h, d=d)
        sx, sy, sz = separated_low_corner(
            proxy,
            stud_size,
            plate_size,
            brick_separation,
            assembly_center=separation_center,
        )
        return (
            float(origin[0] + sx),
            float(origin[1] + sy),
            float(origin[2] + sz),
        )

    def _apply_tilt_clearance(p, wx, wz, clearance):
        if clearance <= 0.0:
            return wx, wz
        scene_center_x = float(origin[0] + separation_center[0])
        scene_center_z = float(origin[2] + separation_center[2])
        dx = wx - scene_center_x
        dz = wz - scene_center_z
        length = (dx * dx + dz * dz) ** 0.5
        if length <= 1.0e-6:
            dx = (float(p.x) + float(p.w) * 0.5) - float(separation_center[0] / stud_size)
            dz = (float(p.z) + float(p.d) * 0.5) - float(separation_center[2] / stud_size)
            length = (dx * dx + dz * dz) ** 0.5
        if length <= 1.0e-6:
            dx = 1.0
            dz = 0.0
            length = 1.0
        return (
            wx + (dx / length) * clearance,
            wz + (dz / length) * clearance,
        )

    def _local_offset(matrix, x, y, z):
        return (
            (matrix.v1 * float(x))
            + (matrix.v2 * float(y))
            + (matrix.v3 * float(z))
        )

    def _apply_logo_quarter_turn_local(matrix, degrees):
        """Rotate a logo's local matrix around its v2 axis by `degrees`."""
        import math
        angle_deg = float(degrees or 0.0) % 360.0
        rad = math.radians(angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        base_v1 = matrix.v1
        base_v3 = matrix.v3
        # New v1 = base_v1*cos - base_v3*sin; new v3 = base_v1*sin + base_v3*cos.
        matrix.v1 = base_v1 * cos_a + base_v3 * (-sin_a)
        matrix.v3 = base_v1 * sin_a + base_v3 * cos_a
        return matrix

    def _make_centered_brick_matrix(p, state):
        wx, wy, wz = _placement_scene_center(p)
        y_offset = float(state.y_offset) if state is not None else 0.0
        wy += y_offset
        local_progress = state.local_progress if state is not None else 1.0

        m = c4d.Matrix()
        tilt_x, tilt_z = build_tilt_for_progress(
            p,
            local_progress,
            enabled=subtle_rotation,
            amount_degrees=tilt_amount,
        )
        if tilt_x or tilt_z:
            try:
                m = (
                    c4d.utils.MatrixRotX(tilt_x)
                    * c4d.utils.MatrixRotZ(tilt_z)
                )
            except Exception:
                m = c4d.Matrix()

        clearance = build_tilt_clearance(
            tilt_x,
            tilt_z,
            p.h,
            plate_size,
            enabled=subtle_rotation,
        )
        wx, wz = _apply_tilt_clearance(p, wx, wz, clearance)

        scale = build_scale_for_progress(
            local_progress,
            scale_bricks_in,
        )
        m.v1 *= scale
        m.v2 *= scale
        m.v3 *= scale
        m.off = c4d.Vector(wx, wy, wz)
        m = apply_humanize_to_center_matrix(m, p, params)
        return m

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

    debug_materials = {}

    def _get_debug_material(color_key, color, transparent=False):
        if color_key is None or doc is None:
            return None
        mat_key = (color_key, bool(transparent))
        if mat_key in debug_materials:
            return debug_materials[mat_key]
        suffix = "Fill" if transparent else "Line"
        name = "Brick_Debug_{0}_{1}_{2}_{3}".format(
            color_key[0], color_key[1], color_key[2], suffix
        )
        try:
            mat = doc.SearchMaterial(name)
        except Exception:
            mat = None
        if mat is None:
            mat = c4d.BaseMaterial(c4d.Mmaterial)
            mat.SetName(name)
            doc.InsertMaterial(mat)
        try:
            mat[c4d.MATERIAL_COLOR_COLOR] = color
            mat[c4d.MATERIAL_COLOR_BRIGHTNESS] = 1.0
            if transparent:
                mat[c4d.MATERIAL_USE_TRANSPARENCY] = True
                mat[c4d.MATERIAL_TRANSPARENCY_BRIGHTNESS] = 0.72
                mat[c4d.MATERIAL_TRANSPARENCY_COLOR] = color
            else:
                mat[c4d.MATERIAL_USE_TRANSPARENCY] = False
            mat.Message(c4d.MSG_UPDATE)
        except Exception:
            pass
        debug_materials[mat_key] = mat
        return mat

    def _apply_material(obj, mat):
        if mat is None:
            return
        try:
            tag = c4d.TextureTag()
        except AttributeError:
            tag = c4d.BaseTag(c4d.Ttexture)
        tag[c4d.TEXTURETAG_MATERIAL] = mat
        obj.InsertTag(tag)

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
            x0, y0, z0 = _placement_scene_low_corner(p)
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
            x0, y0, z0 = _box_scene_low_corner(x, y, z, w, h, d)
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
        vox_key = _color_key(vox_color)

        try:
            if occ_list:
                vox_boxes = [(x, y, z, 1, 1, 1) for x, y, z in occ_list]
                vox_obj = _make_fill_boxes(
                    "voxel_debug_occupancy", vox_boxes
                )
                _apply_object_color(vox_obj, vox_color)
                _apply_material(
                    vox_obj,
                    _get_debug_material(vox_key, vox_color, transparent=True),
                )
                vox_obj.InsertUnder(instances_root)
            elif self._fit_placements:
                # Fallback: pipeline didn't supply occupancy cells (stale
                # module load, etc.). Render the union of placement
                # footprints so the debug view always shows SOMETHING.
                fb_color = c4d.Vector(1.0, 0.20, 0.20)
                fb_key = _color_key(fb_color)
                fb_boxes = [
                    (p.x, p.y, p.z, p.w, p.h, p.d)
                    for p in self._fit_placements
                ]
                fb_obj = _make_fill_boxes(
                    "voxel_debug_placements_fallback", fb_boxes
                )
                _apply_object_color(fb_obj, fb_color)
                _apply_material(
                    fb_obj,
                    _get_debug_material(fb_key, fb_color, transparent=True),
                )
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
            void_key = _color_key(void_color)
            fill = _make_fill_boxes("hollow_interior_fill", void_boxes)
            _apply_object_color(fill, void_color)
            _apply_material(
                fill,
                _get_debug_material(void_key, void_color, transparent=True),
            )
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
            _apply_material(
                wire,
                _get_debug_material(color_key, color, transparent=False),
            )
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
            if smooth_top_visual:
                from types import SimpleNamespace
                template_brick = SimpleNamespace(
                    width=int(getattr(p0, "w", getattr(p0.brick, "width", 1))),
                    depth=int(getattr(p0, "d", getattr(p0.brick, "depth", 1))),
                    height=int(getattr(p0, "h", getattr(p0.brick, "height", 1))),
                )
            elif p0.rotation_y == 90:
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
                state = animation_state_by_obj.get(id(p))
                matrices.append(_make_centered_brick_matrix(p, state))

            try:
                inst.SetInstanceMatrices(matrices)
            except AttributeError:
                inst[c4d.INSTANCEOBJECT_MULTIPOSITIONS] = matrices

            inst.InsertUnder(instances_root)

    if logo_template is not None:
        from logo_helpers import brick_logo_rotation_degrees as _brick_logo_rotation_degrees
        logo_matrices = []
        stud_h = float(plate_size) * 0.55
        logo_rotation = float(params.get("logo_rotation", 0) or 0) % 360.0
        logo_mix_flip = bool(params.get("logo_mix_flip", False))
        logo_mix_amount = max(0.0, min(1.0, float(params.get("logo_mix_amount", 0.0) or 0.0)))
        logo_mix_seed = int(params.get("logo_mix_seed", 0) or 0)
        logo_sink = max(0.0, min(0.05, float(params.get("logo_sink", BRICKGEN_LOGO_DEFAULT_SINK))))
        logo_surface_bias = -float(plate_size) * logo_sink
        for p in visible_placements:
            state = animation_state_by_obj.get(id(p))
            smooth_top_visual = bool(smooth_top_by_obj.get(id(p), False))
            if smooth_top_visual:
                continue
            if int(getattr(p.brick, "height", 0)) == 1 and smooth_plate_visual:
                continue
            brick_m = _make_centered_brick_matrix(p, state)
            half_w = float(p.w) * float(stud_size) * 0.5
            half_h = float(p.h) * float(plate_size) * 0.5
            half_d = float(p.d) * float(stud_size) * 0.5
            per_brick_rot = _brick_logo_rotation_degrees(
                p, logo_rotation, logo_mix_flip, logo_mix_amount, logo_mix_seed,
            )
            for sx in range(int(p.w)):
                for sz in range(int(p.d)):
                    m = c4d.Matrix()
                    m.v1 = brick_m.v1
                    m.v2 = brick_m.v2
                    m.v3 = brick_m.v3
                    local = _local_offset(
                        brick_m,
                        ((float(sx) + 0.5) * float(stud_size)) - half_w,
                        (float(p.h) * float(plate_size) + stud_h + logo_surface_bias) - half_h,
                        ((float(sz) + 0.5) * float(stud_size)) - half_d,
                    )
                    m.off = brick_m.off + local
                    _apply_logo_quarter_turn_local(m, per_brick_rot)
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

