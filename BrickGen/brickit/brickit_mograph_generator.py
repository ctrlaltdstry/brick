"""Integrated BrickIt MoGraph output for the live generator."""
import math
from types import SimpleNamespace

import c4d

from .brickit_animation import (
    build_scale_for_progress,
    build_tilt_clearance,
    build_tilt_for_progress,
    ordered_placements,
    phased_build_animation_states,
    shell_smooth_top_target_cells,
    smooth_top_cap_selection_for_coverage,
)
from .brickit_humanize import apply_humanize_to_center_matrix
from .brickit_groups import grouped_parent_for_placement
from .brickit_sources import primary_source_child as _primary_source_child
from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from logo_helpers import (
    BRICKGEN_LOGO_DEFAULT_SINK,
    apply_logo_quarter_turn as _apply_logo_quarter_turn,
    brick_logo_rotation_degrees,
)
from mesh_bridge import mesh_to_polygon_object
from plugin_bootstrap import brick_log as _brick_log
from quality_presets import QUALITY_PROXY
from source_geometry import source_axis_local_matrix


def _hide_object_in_editor_and_render(obj):
    if obj is None:
        return
    try:
        obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = c4d.OBJECT_OFF
        obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = c4d.OBJECT_OFF
    except Exception:
        pass


def _color_vector_from_rgb(rgb):
    try:
        r, g, b = rgb
    except Exception:
        return c4d.Vector(1.0, 1.0, 1.0)
    scale = 255.0 if max(float(r), float(g), float(b)) > 1.0 else 1.0
    return c4d.Vector(
        max(0.0, min(1.0, float(r) / scale)),
        max(0.0, min(1.0, float(g) / scale)),
        max(0.0, min(1.0, float(b) / scale)),
    )


def _apply_object_color(obj, color):
    if obj is None:
        return
    try:
        obj[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
        obj[c4d.ID_BASEOBJECT_COLOR] = color
    except Exception:
        pass


def _set_object_visible(obj, visible):
    if obj is None:
        return
    flag = c4d.OBJECT_UNDEF if bool(visible) else c4d.OBJECT_OFF
    try:
        obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = flag
        obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = flag
    except Exception:
        pass


def _update_object(obj):
    if obj is None:
        return
    try:
        obj.Message(c4d.MSG_UPDATE)
    except Exception:
        pass


def _matrix_for_visibility(matrix, visible):
    if bool(visible):
        return matrix
    parked = c4d.Matrix()
    parked.off = c4d.Vector(0.0, 1.0e9, 0.0)
    return parked


def _is_finite_vector(v):
    try:
        return (
            math.isfinite(float(v.x))
            and math.isfinite(float(v.y))
            and math.isfinite(float(v.z))
        )
    except Exception:
        return False


def _is_sane_effector_matrix(matrix):
    try:
        return (
            _is_finite_vector(matrix.off)
            and _is_finite_vector(matrix.v1)
            and _is_finite_vector(matrix.v2)
            and _is_finite_vector(matrix.v3)
            and abs(float(matrix.off.x)) < 1.0e8
            and abs(float(matrix.off.y)) < 1.0e8
            and abs(float(matrix.off.z)) < 1.0e8
        )
    except Exception:
        return False


def _has_mograph_effectors(effectors):
    if effectors is None:
        return False
    try:
        return int(effectors.GetObjectCount()) > 0
    except Exception:
        pass
    return bool(effectors)


def _resolve_bind_state(self, op, source_obj, doc, params):
    """Return (bind_center_by_obj, bind_visible_by_obj, bind_orient_by_obj)
    for the active frame.

    All dicts are keyed by `id(placement)`. Returns (None, None, None) when
    binding is off, records are missing, or per-frame eval failed.
    `bind_orient_by_obj` is only populated when orientation_mode is
    Follow-Surface-Normal; otherwise None to skip the rotation override.
    """
    if not params.get("bind_to_source_deformation"):
        return None, None, None
    if source_obj is None:
        return None, None, None
    bind_records = getattr(self, "_bind_records", None)
    placements = list(self._fit_placements or [])
    if not bind_records or not placements or len(bind_records) != len(placements):
        return None, None, None
    try:
        from .brickit_bind import deformed_centers_for_frame
    except Exception:
        return None, None, None
    centers, visible, _ratios, orient_basis = deformed_centers_for_frame(
        self, op, source_obj, doc, params
    )
    if centers is None:
        return None, None, None
    bind_center_by_obj = {}
    bind_visible_by_obj = {}
    bind_orient_by_obj = None
    follow_normal = (
        int(params.get("bind_orientation_mode", 0))
        == BRICKIFYASSEMBLY_BIND_ORIENT_FOLLOW_NORMAL
    )
    if follow_normal and orient_basis is not None:
        bind_orient_by_obj = {}
    for i, placement in enumerate(placements):
        if i >= len(centers):
            break
        c = centers[i]
        if c is not None:
            bind_center_by_obj[id(placement)] = c
        v = visible[i] if visible is not None and i < len(visible) else True
        bind_visible_by_obj[id(placement)] = bool(v)
        if bind_orient_by_obj is not None and i < len(orient_basis):
            ob = orient_basis[i]
            if ob is not None:
                bind_orient_by_obj[id(placement)] = ob
    if not bind_center_by_obj:
        return None, None, None
    return bind_center_by_obj, bind_visible_by_obj, bind_orient_by_obj


def _smooth_top_target_cells(params, info, placements):
    if str(params.get("voxel_mode", "")).lower() != "shell":
        return None
    cells = info.get("occupancy_cells") if info else None
    dims = info.get("grid_dims") if info else None
    if not cells or not dims:
        return None
    return shell_smooth_top_target_cells(
        placements,
        cells,
        dims,
        interior_void_cells=info.get("interior_void_cells"),
    )


def _collect_polygon_objects_with_matrices(obj, parent_m=None):
    """Walk obj's local hierarchy and return [(poly_obj, world_matrix), ...]."""
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
    """Merge polygon objects (each with its own world matrix) into one PolygonObject.

    Used to bake logo children into the per-template brick mesh so the proto
    contains a single renderable polygon under its Null wrapper. Redshift's
    SceneMesh handling asserts when an Oinstance reference resolves to a
    Null with multiple polygon children, so consolidating into one polygon
    keeps the integrated MoGraph render path quiet.
    """
    objects_with_matrices = [
        (o, m) for o, m in (objects_with_matrices or [])
        if o is not None and o.GetType() == c4d.Opolygon
    ]
    if not objects_with_matrices:
        return None
    total_points = sum(o.GetPointCount() for o, _ in objects_with_matrices)
    total_polys = sum(o.GetPolygonCount() for o, _ in objects_with_matrices)
    merged = c4d.PolygonObject(total_points, total_polys)
    merged.SetName(name)
    point_offset = 0
    poly_offset = 0
    for o, matrix in objects_with_matrices:
        try:
            points = o.GetAllPoints()
            polygons = o.GetAllPolygons()
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
        point_offset += o.GetPointCount()
        poly_offset += o.GetPolygonCount()
    try:
        phong = merged.MakeTag(c4d.Tphong)
        phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
        phong[c4d.PHONGTAG_PHONG_ANGLE] = c4d.utils.DegToRad(40.0)
    except Exception:
        pass
    merged.Message(c4d.MSG_UPDATE)
    return merged


def _format_color_samples(tag, base_id, sample_count):
    samples = []
    for i in range(max(0, min(int(sample_count or 0), 5))):
        try:
            c = tag[base_id + i]
            samples.append("({0:.3f},{1:.3f},{2:.3f})".format(c.x, c.y, c.z))
        except Exception:
            pass
    return "[" + ", ".join(samples) + "]"


def _evaluate_native_mograph(
    op,
    matrices,
    colors,
    effectors,
    *,
    skip_field_override=False,
    label="default",
    frame_matrix=None,
):
    """Evaluate matrices/colors through the native C++ MoData helper tag.

    Returns ``(out_matrices, out_colors, out_visible)`` where ``out_visible``
    is a per-clone list of bools reflecting the effector ``MOGENFLAG_CLONE_ON``
    state after evaluation (``True`` = visible). ``None`` is used when the
    native evaluator is unavailable or fell back, in which case callers
    should treat all clones as visible.

    `frame_matrix` is the input matrices' parent-local matrix relative to op
    (i.e. the integrated root Null's local matrix, ``~op_mg * source_mg``).
    The native evaluator hands `op` to effectors as their generator, so it
    interprets matrices as local to `op_mg`. Our matrices are local to the
    root Null (= local to `source_mg`), so we pre-multiply by `frame_matrix`
    to convert root-local → op-local for the evaluator and post-multiply
    outputs by ``~frame_matrix`` to convert op-local → root-local for the
    carriers. When `frame_matrix` is None or close to identity (BrickIt at
    world identity, or coincident with the source axis) this is a no-op.
    """
    if not matrices:
        return [], [], None
    try:
        tag = c4d.BaseTag(ID_BRICK_MOGRAPH_EVALUATOR_TAG)
    except Exception:
        tag = None
    if tag is None:
        _brick_log("[brick] Integrated MoGraph: native evaluator tag unavailable")
        return matrices, colors, None

    inv_frame = None
    if frame_matrix is not None:
        try:
            inv_frame = ~frame_matrix
            input_matrices = [frame_matrix * m for m in matrices]
        except Exception:
            inv_frame = None
            input_matrices = matrices
    else:
        input_matrices = matrices

    count = len(input_matrices)
    try:
        tag[BRICK_MOGRAPH_EVAL_COUNT] = int(count)
        tag[BRICK_MOGRAPH_EVAL_GENERATOR] = op
        tag[BRICK_MOGRAPH_EVAL_SKIP_FIELD_OVERRIDE] = bool(skip_field_override)
        if effectors is not None:
            tag[BRICK_MOGRAPH_EVAL_EFFECTORS] = effectors
        for i, matrix in enumerate(input_matrices):
            tag[BRICK_MOGRAPH_EVAL_IN_MATRIX_BASE + i] = matrix
            tag[BRICK_MOGRAPH_EVAL_IN_COLOR_BASE + i] = colors[i]
        tag.Message(MSG_BRICK_MOGRAPH_EVALUATE)
        if not bool(tag[BRICK_MOGRAPH_EVAL_OK]):
            _brick_log("[brick] Integrated MoGraph: native evaluator reported no result")
            return matrices, colors, None
        try:
            color_changed = int(tag[BRICK_MOGRAPH_EVAL_COLOR_CHANGED])
            field_color_modes = int(tag[BRICK_MOGRAPH_EVAL_FIELD_COLOR_MODE_COUNT])
            field_color_applied = int(tag[BRICK_MOGRAPH_EVAL_FIELD_COLOR_APPLIED])
            effector_changed = int(tag[BRICK_MOGRAPH_EVAL_EFFECTOR_COLOR_CHANGED])
            post_field_changed = int(tag[BRICK_MOGRAPH_EVAL_POST_FIELD_COLOR_CHANGED])
            manual_skipped = bool(tag[BRICK_MOGRAPH_EVAL_MANUAL_FIELD_SKIPPED])
            sample_count = int(tag[BRICK_MOGRAPH_EVAL_SAMPLE_COUNT])
            if color_changed or field_color_modes:
                _brick_log(
                    "[brick] Integrated MoGraph color[{0}]: changed={1}/{2}, effector_changed={3}, post_field_changed={4}, field_color_effectors={5}, field_samples_applied={6}, manual_field_skipped={7}, effector_samples={8}, final_samples={9}".format(
                        label,
                        color_changed,
                        count,
                        effector_changed,
                        post_field_changed,
                        field_color_modes,
                        field_color_applied,
                        manual_skipped,
                        _format_color_samples(
                            tag,
                            BRICK_MOGRAPH_EVAL_EFFECTOR_COLOR_SAMPLE_BASE,
                            sample_count,
                        ),
                        _format_color_samples(
                            tag,
                            BRICK_MOGRAPH_EVAL_FIELD_COLOR_SAMPLE_BASE,
                            sample_count,
                        ),
                    )
                )
        except Exception:
            pass
        out_matrices = []
        out_colors = []
        out_visible = []
        invalid_matrices = 0
        for i in range(count):
            matrix = tag[BRICK_MOGRAPH_EVAL_OUT_MATRIX_BASE + i]
            if not _is_sane_effector_matrix(matrix):
                # Fall back to the op-local input — the post-multiply below
                # converts back to root-local consistently with sane outputs.
                matrix = input_matrices[i]
                invalid_matrices += 1
            out_matrices.append(matrix)
            out_colors.append(tag[BRICK_MOGRAPH_EVAL_OUT_COLOR_BASE + i])
            try:
                out_visible.append(bool(tag[BRICK_MOGRAPH_EVAL_OUT_VISIBLE_BASE + i]))
            except Exception:
                out_visible.append(True)
        if invalid_matrices:
            _brick_log(
                "[brick] Integrated MoGraph: ignored {0}/{1} invalid effector matrices after field evaluation".format(
                    int(invalid_matrices),
                    int(count),
                )
            )
        try:
            visibility_changed = int(tag[BRICK_MOGRAPH_EVAL_VISIBILITY_CHANGED])
            if visibility_changed:
                _brick_log(
                    "[brick] Integrated MoGraph visibility[{0}]: hidden_by_effectors={1}/{2}".format(
                        label, int(visibility_changed), int(count),
                    )
                )
        except Exception:
            pass
        if inv_frame is not None:
            try:
                out_matrices = [inv_frame * m for m in out_matrices]
            except Exception:
                pass
        return out_matrices, out_colors, out_visible
    except Exception as exc:
        _brick_log("[brick] Integrated MoGraph: native evaluator failed: {0}".format(exc))
        return matrices, colors, None


def _build_integrated_mograph_hierarchy(self, op, params=None):
    """Return a live MoGraph-aware hierarchy without touching handoff commands."""
    # Invalidate any prior fast-path snapshot — it's only valid for the
    # build that's about to produce it.
    self._fast_cap_state = None
    info = self._fit_info or {}
    if not self._fit_placements or not info:
        return None
    if params is None:
        params = self._resolve_params(op, _primary_source_child(op))

    stud_size = info.get("stud_size", 8.0)
    plate_size = info.get("plate_size", 3.2)
    origin = info.get("origin")
    if origin is None:
        return None
    quality = params["quality"]
    is_proxy_quality = int(quality) == int(QUALITY_PROXY)

    source_obj = _primary_source_child(op)
    src_name = source_obj.GetName() if source_obj is not None else "mesh"

    root = c4d.BaseObject(c4d.Onull)
    root.SetName("Brickified_MoGraph_{0}".format(src_name))
    root.SetMl(source_axis_local_matrix(op, source_obj))

    templates_root = c4d.BaseObject(c4d.Onull)
    templates_root.SetName("brick_templates")
    park_m = c4d.Matrix()
    park_m.off = c4d.Vector(0.0, 1.0e9, 0.0)
    templates_root.SetMl(park_m)
    _hide_object_in_editor_and_render(templates_root)
    templates_root.InsertUnder(root)

    instances_root = c4d.BaseObject(c4d.Onull)
    instances_root.SetName("bricks")
    instances_root.InsertUnder(root)

    placements = ordered_placements(self._fit_placements or [])
    smooth_plate_visual = False
    smooth_cap_ids = set()
    smooth_target_cells = _smooth_top_target_cells(params, info, placements)
    if bool(params.get("surface_only_plates")):
        smooth_cap_ids, generated_caps = smooth_top_cap_selection_for_coverage(
            placements,
            params.get("top_surface_coverage", 1.0),
            random_order=params.get("top_surface_random_order", False),
            cap_style=int(params.get("cap_style", 0)),
            library=None,
            seed=int(params.get("cap_random_seed", 0)),
            target_top_cells=smooth_target_cells,
        )
        placements = ordered_placements(list(placements) + generated_caps)
        smooth_cap_ids.update(id(p) for p in generated_caps)
        try:
            target_size = (
                "n/a" if smooth_target_cells is None else len(smooth_target_cells)
            )
            top_y_hist = {}
            for c in generated_caps:
                top_y_hist[int(c.y)] = top_y_hist.get(int(c.y), 0) + 1
            top_y_hist_str = ", ".join(
                "y{0}:{1}".format(k, v) for k, v in sorted(top_y_hist.items())
            )
            _brick_log(
                "[brick] SmoothTop: voxel_mode={0}, coverage={1}, target_top_cells={2}, "
                "structural_placements={3}, existing_selected={4}, generated_caps={5}, "
                "caps_by_y=[{6}]".format(
                    str(params.get("voxel_mode", "")),
                    float(params.get("top_surface_coverage", 1.0) or 0.0),
                    target_size,
                    len(self._fit_placements or []),
                    len(smooth_cap_ids) - len(generated_caps),
                    len(generated_caps),
                    top_y_hist_str,
                )
            )
        except Exception:
            pass
    smooth_top_by_obj = {cap_id: True for cap_id in smooth_cap_ids}

    animation_placements = list(placements)
    animation_states = phased_build_animation_states(
        placements,
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
        settle_length=params.get("build_settle_length", 0.5),
    )
    animation_state_by_obj = {
        id(state.placement): state for state in animation_states
    }
    placements = animation_placements
    scale_bricks_in = bool(params.get("build_scale_in", False))
    subtle_rotation = bool(params.get("build_subtle_rotation", False))
    tilt_amount = float(params.get("build_tilt_amount", 5.0))

    from brick.separation import (
        placement_assembly_center,
        separated_center,
    )

    brick_separation = float(params.get("brick_separation", 0.0) or 0.0)
    separation_center = placement_assembly_center(animation_placements, stud_size, plate_size)

    logo_template = None
    if not is_proxy_quality:
        logo_template = self._get_logo_template_obj(
            params, op.GetDocument(), stud_size, plate_size
        )
    logo_rotation = float(params.get("logo_rotation", 0) or 0) % 360.0
    logo_mix_flip = bool(params.get("logo_mix_flip", False))
    logo_mix_amount = max(0.0, min(1.0, float(params.get("logo_mix_amount", 0.0) or 0.0)))
    logo_mix_seed = int(params.get("logo_mix_seed", 0) or 0)
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

    def _bake_template_logos_into_mesh(mesh_obj, brick_type, smooth_top=False, rotation_deg=None):
        """Merge per-stud logo polygon clones into the brick template mesh.

        Returns either a brand-new combined PolygonObject (logos baked in)
        or the original mesh_obj when this brick has no logos to bake. Each
        per-stud logo position uses the same centered offsets as the
        template mesh, so logo placement on the rendered brick is identical
        to the previous Null-with-logo-children layout.

        Why bake instead of attach as Null children: Redshift's SceneMesh
        handling asserts when an Oinstance reference resolves to a Null with
        multiple polygon children. The integrated MoGraph path puts every
        Oinstance carrier on a per-template proto, so a Null with mesh +
        logos triggers the assertion at render time. A single combined
        polygon child avoids it cleanly.
        """
        if mesh_obj is None or not _brick_has_template_logos(brick_type, smooth_top=smooth_top):
            return mesh_obj
        half_w = float(brick_type.width) * float(stud_size) * 0.5
        half_h = float(brick_type.height) * float(plate_size) * 0.5
        half_d = float(brick_type.depth) * float(stud_size) * 0.5
        top_y = (
            float(brick_type.height) * float(plate_size)
            + float(plate_size) * 0.55
            + logo_surface_bias
        )
        objects = _collect_polygon_objects_with_matrices(mesh_obj)
        for sx in range(int(brick_type.width)):
            for sz in range(int(brick_type.depth)):
                logo_obj = logo_template.GetClone(c4d.COPYFLAGS_NONE)
                if logo_obj is None:
                    continue
                m = c4d.Matrix()
                m.off = c4d.Vector(
                    float((sx + 0.5) * stud_size) - half_w,
                    float(top_y) - half_h,
                    float((sz + 0.5) * stud_size) - half_d,
                )
                _apply_logo_quarter_turn(
                    m,
                    logo_rotation if rotation_deg is None else rotation_deg,
                )
                try:
                    logo_obj.SetMl(m)
                except Exception:
                    pass
                objects.extend(_collect_polygon_objects_with_matrices(logo_obj))
        baked = _merge_polygon_objects_local(objects, mesh_obj.GetName())
        return baked if baked is not None else mesh_obj

    def _center_template_mesh(mesh_obj, brick_type):
        offset = c4d.Vector(
            -float(brick_type.width) * float(stud_size) * 0.5,
            -float(brick_type.height) * float(plate_size) * 0.5,
            -float(brick_type.depth) * float(stud_size) * 0.5,
        )
        try:
            points = mesh_obj.GetAllPoints()
            for i, point in enumerate(points):
                mesh_obj.SetPoint(i, point + offset)
            mesh_obj.Message(c4d.MSG_UPDATE)
        except Exception:
            pass
        return mesh_obj

    type_to_template = {}

    def _stable_template_name(brick_type):
        return "brick_{0}x{1}_h{2}p".format(
            int(brick_type.width),
            int(brick_type.depth),
            int(brick_type.height),
        )

    def _get_template_obj(brick_type, smooth_top=False, rotation_deg=None):
        bake_rot = float(rotation_deg if rotation_deg is not None else logo_rotation) % 360.0
        # Round to a coarse bucket so float jitter doesn't produce many
        # distinct cache entries — only "is this flipped?" matters here.
        rot_key = int(round(bake_rot)) % 360
        tkey = (
            brick_type.width,
            brick_type.depth,
            brick_type.height,
            int(bool(smooth_top)),
            rot_key,
        )
        if tkey in type_to_template:
            return type_to_template[tkey]
        name = _stable_template_name(brick_type)
        if bool(smooth_top):
            name += "_smooth"
        if rot_key:
            name += "_r{0:03d}".format(rot_key)
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
            name="mesh_{0}".format(name),
        )
        _center_template_mesh(mesh_obj, brick_type)
        if not is_proxy_quality:
            mesh_obj = _bake_template_logos_into_mesh(
                mesh_obj, brick_type, smooth_top=smooth_top,
                rotation_deg=bake_rot,
            )
        mesh_obj.InsertUnder(proto)
        proto.InsertUnder(templates_root)
        type_to_template[tkey] = proto
        return proto

    mi_mode = getattr(c4d, "INSTANCEOBJECT_RENDERINSTANCE_MODE_RENDERINSTANCE", 1)

    bind_center_by_obj, bind_visible_by_obj, bind_orient_by_obj = _resolve_bind_state(
        self, op, source_obj, op.GetDocument(), params
    )

    def _placement_scene_center(p):
        # Bind-to-source-deformation: when binding is active and this
        # placement has a record, return the deformed-mesh center. Smooth
        # caps with a `support` placement chain through the support's
        # bound center so a deforming support carries its caps along.
        support = getattr(p, "support", None)
        if bind_center_by_obj is not None:
            bound = bind_center_by_obj.get(id(p))
            if bound is not None:
                return bound
            if support is not None:
                bound_support = bind_center_by_obj.get(id(support))
                if bound_support is not None:
                    # Cap position is computed in the support's LOCAL frame
                    # (lateral X/Z by source-axis stud spacing, vertical by
                    # half-thicknesses) and then projected through the
                    # support's deformed orient basis when in follow-normal
                    # mode. Without the basis projection, caps would stay
                    # axis-aligned in source-axis-local space and slide off
                    # tilted supports.
                    dx_local = (
                        (float(p.x) + float(p.w) * 0.5)
                        - (float(support.x) + float(support.w) * 0.5)
                    ) * float(stud_size)
                    dz_local = (
                        (float(p.z) + float(p.d) * 0.5)
                        - (float(support.z) + float(support.d) * 0.5)
                    ) * float(stud_size)
                    dy_local = (
                        float(support.h) * 0.5 * float(plate_size)
                        + float(p.h) * 0.5 * float(plate_size)
                    )
                    sob = (
                        bind_orient_by_obj.get(id(support))
                        if bind_orient_by_obj is not None
                        else None
                    )
                    if sob is not None:
                        sv1, sv2, sv3 = sob
                        wx = (
                            bound_support[0]
                            + sv1[0] * dx_local + sv2[0] * dy_local + sv3[0] * dz_local
                        )
                        wy = (
                            bound_support[1]
                            + sv1[1] * dx_local + sv2[1] * dy_local + sv3[1] * dz_local
                        )
                        wz = (
                            bound_support[2]
                            + sv1[2] * dx_local + sv2[2] * dy_local + sv3[2] * dz_local
                        )
                        return (float(wx), float(wy), float(wz))
                    return (
                        float(bound_support[0] + dx_local),
                        float(bound_support[1] + dy_local),
                        float(bound_support[2] + dz_local),
                    )
        # Smooth caps with a recorded support placement are anchored to the
        # support's separated top so Brick Separation > 0 doesn't drift them
        # vertically off their underlying brick.
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

    def _bind_visible(p):
        if bind_visible_by_obj is None:
            return True
        if id(p) in bind_visible_by_obj:
            return bool(bind_visible_by_obj[id(p)])
        support = getattr(p, "support", None)
        if support is not None and id(support) in bind_visible_by_obj:
            return bool(bind_visible_by_obj[id(support)])
        return True

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

    def _make_animated_centered_matrix(p):
        state = animation_state_by_obj.get(id(p))
        wx, wy, wz = _placement_scene_center(p)
        y_offset = float(state.y_offset) if state is not None else 0.0
        wy += y_offset
        local_progress = state.local_progress if state is not None else 1.0
        contact_progress = (
            local_progress
            if state is None or getattr(state, "contact_progress", None) is None
            else state.contact_progress
        )

        m = c4d.Matrix()
        ob = bind_orient_by_obj.get(id(p)) if bind_orient_by_obj is not None else None
        if ob is None and bind_orient_by_obj is not None:
            # Generated smooth caps don't have their own bind records, but
            # they're anchored to a support placement that does. Inherit
            # the support's orient so caps tilt with the surface alongside
            # their parent brick instead of staying world-up.
            support = getattr(p, "support", None)
            if support is not None:
                ob = bind_orient_by_obj.get(id(support))
        if ob is not None:
            v1, v2, v3 = ob
            m.v1 = c4d.Vector(float(v1[0]), float(v1[1]), float(v1[2]))
            m.v2 = c4d.Vector(float(v2[0]), float(v2[1]), float(v2[2]))
            m.v3 = c4d.Vector(float(v3[0]), float(v3[1]), float(v3[2]))
        tilt_x, tilt_z = build_tilt_for_progress(
            p,
            contact_progress,
            enabled=subtle_rotation,
            amount_degrees=tilt_amount,
        )
        if (tilt_x or tilt_z) and ob is None:
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
        if ob is None:
            wx, wz = _apply_tilt_clearance(p, wx, wz, clearance)

        scale = build_scale_for_progress(contact_progress, scale_bricks_in)
        m.v1 *= scale
        m.v2 *= scale
        m.v3 *= scale
        m.off = c4d.Vector(wx, wy, wz)
        m = apply_humanize_to_center_matrix(m, p, params)
        return m

    instance_specs = []
    pre_matrices = []
    pre_colors = []
    # Per-instance template-brick descriptors captured for the cap-subset
    # fast path. (template_brick, current_smooth_top_flag, original_placement)
    fast_path_descriptors = []
    for p in placements:
        smooth_top = bool(smooth_top_by_obj.get(id(p), False))
        if smooth_top:
            template_brick = SimpleNamespace(
                width=int(getattr(p, "w", getattr(p.brick, "width", 1))),
                depth=int(getattr(p, "d", getattr(p.brick, "depth", 1))),
                height=int(getattr(p, "h", getattr(p.brick, "height", 1))),
            )
        elif getattr(p, "rotation_y", 0) == 90:
            template_brick = SimpleNamespace(
                width=p.brick.depth,
                depth=p.brick.width,
                height=p.brick.height,
            )
        else:
            template_brick = p.brick
        per_brick_rot = brick_logo_rotation_degrees(
            p, logo_rotation, logo_mix_flip, logo_mix_amount, logo_mix_seed,
        )
        template = _get_template_obj(
            template_brick,
            smooth_top=smooth_top,
            rotation_deg=per_brick_rot,
        )

        m = _make_animated_centered_matrix(p)
        pre_matrices.append(m)
        pre_colors.append(_color_vector_from_rgb(getattr(p, "rgb", (255, 255, 255))))
        instance_specs.append((template_brick, template))
        fast_path_descriptors.append((template_brick, smooth_top, p))

    if _has_mograph_effectors(params.get("mograph_effectors")):
        matrices, colors, effector_visible = _evaluate_native_mograph(
            op,
            pre_matrices,
            pre_colors,
            params.get("mograph_effectors"),
            skip_field_override=True,
            label="effector",
            frame_matrix=source_axis_local_matrix(op, source_obj),
        )
    else:
        matrices, colors, effector_visible = pre_matrices, pre_colors, None

    # Collected per-instance for the cap-subset fast path.
    fast_path_instances = []
    multi_mode = int(
        getattr(c4d, "INSTANCEOBJECT_RENDERINSTANCE_MODE_MULTIINSTANCE", mi_mode)
    )
    created_instances = 0
    group_parent_cache = {}
    for i, (template_brick, template) in enumerate(instance_specs):
        try:
            matrix = matrices[i]
        except Exception:
            matrix = pre_matrices[i]
        color = colors[i] if i < len(colors) else pre_colors[i]
        state = animation_state_by_obj.get(id(fast_path_descriptors[i][2]))
        anim_visible = state is not None and state.local_progress > 0.0
        eff_visible = (
            effector_visible[i]
            if effector_visible is not None and i < len(effector_visible)
            else True
        )
        bind_vis = _bind_visible(fast_path_descriptors[i][2])
        visible = bool(anim_visible) and bool(eff_visible) and bool(bind_vis)
        matrix = _matrix_for_visibility(matrix, visible)
        try:
            child = c4d.InstanceObject()
        except Exception:
            child = c4d.BaseObject(c4d.Oinstance)
        child.SetName(
            "brick_{0}x{1}x{2}p_inst_{3:04d}".format(
                int(template_brick.width),
                int(template_brick.depth),
                int(template_brick.height),
                created_instances,
            )
        )
        try:
            child.SetReferenceObject(template)
        except Exception:
            child[c4d.INSTANCEOBJECT_LINK] = template
        try:
            child[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = multi_mode
        except Exception:
            pass
        try:
            child.SetInstanceMatrices([matrix])
            child.SetInstanceColors([color])
        except Exception:
            child.SetMl(matrix)
        _set_object_visible(child, visible)
        _apply_object_color(child, color)
        _update_object(child)
        group_parent = grouped_parent_for_placement(
            info,
            fast_path_descriptors[i][2],
            instances_root,
            group_parent_cache,
        )
        child.InsertUnder(group_parent)
        fast_path_instances.append(child)
        created_instances += 1

    try:
        _brick_log(
            "[brick] Integrated MoGraph: generated expanded one-instance-per-carrier output (multi-instance + display color), bricks={0}, library_items={1}".format(
                created_instances,
                len(type_to_template),
            )
        )
    except Exception:
        pass
    # Stash everything the cap-subset fast path needs: per-instance
    # template-brick descriptors, the live InstanceObject children, the
    # template factory + its cache, and the params snapshot used to
    # recompute caps. The structural side of the next call must match
    # for this state to be reused.
    self._fast_cap_state = {
        "root": root,
        "instances": fast_path_instances,
        "descriptors": fast_path_descriptors,
        "type_to_template": type_to_template,
        "get_template_obj": _get_template_obj,
        "fit_placements": list(self._fit_placements or []),
        "all_placements": list(placements),
        "params_snapshot": dict(params),
    }
    return root


def _apply_cap_subset_fast_path(self, op, params=None):
    """Re-skin an already-built integrated MoGraph hierarchy when the
    only thing that changed is the cap subset (smooth top coverage,
    cap style, cap random seed, cap random order).

    Walks the cached InstanceObject children captured during the previous
    full build and updates each one's reference template if its smooth-top
    flag changed. Reuses (or creates on demand, via the cached factory)
    smooth-top template prototypes. Avoids the full ~500-instance teardown
    and rebuild that the cache-key change would otherwise trigger.

    Returns the cached root on success, or None to signal the caller
    should fall back to a full rebuild.
    """
    state = getattr(self, "_fast_cap_state", None)
    if state is None:
        return None
    root = state.get("root")
    instances = state.get("instances") or []
    descriptors = state.get("descriptors") or []
    get_template_obj = state.get("get_template_obj")
    if (
        root is None
        or not instances
        or len(instances) != len(descriptors)
        or get_template_obj is None
    ):
        return None

    if params is None:
        params = self._resolve_params(op, _primary_source_child(op))

    # Recompute the cap selection with the new cap-subset params. We use
    # the captured fit_placements (same input the prior full build saw)
    # so generated_caps come back in matching object identities.
    fit_placements = state.get("fit_placements") or []
    structural_placements = ordered_placements(list(fit_placements))
    prior_generated = [
        d[2] for d in descriptors
        if getattr(getattr(d[2], "brick", None), "name", "") == "visual_smooth_cap_1x1"
    ]
    smooth_cap_ids = set()
    smooth_target_cells = _smooth_top_target_cells(
        params,
        self._fit_info or {},
        structural_placements,
    )
    if bool(params.get("surface_only_plates")):
        new_existing_ids, new_generated = smooth_top_cap_selection_for_coverage(
            structural_placements,
            params.get("top_surface_coverage", 1.0),
            random_order=params.get("top_surface_random_order", False),
            cap_style=int(params.get("cap_style", 0)),
            library=None,
            seed=int(params.get("cap_random_seed", 0)),
            target_top_cells=smooth_target_cells,
        )
        # If generated cap COUNT or POSITIONS differ from the prior
        # build, the instance hierarchy can't be reused 1:1 — bail.
        if len(new_generated) != len(prior_generated):
            return None
        def _gen_key(p):
            return (
                int(getattr(p, "x", 0)), int(getattr(p, "y", 0)),
                int(getattr(p, "z", 0)), int(getattr(p, "w", 1)),
                int(getattr(p, "d", 1)), int(getattr(p, "h", 1)),
                int(getattr(p, "rotation_y", 0)),
            )
        prior_keys = sorted(_gen_key(p) for p in prior_generated)
        new_keys = sorted(_gen_key(p) for p in new_generated)
        if prior_keys != new_keys:
            return None

        smooth_cap_ids = set(new_existing_ids)
        # Generated cap placements are always smooth-top, so the
        # original (cached) generated objects stay smooth.
        smooth_cap_ids.update(id(p) for p in prior_generated)

    smooth_top_by_obj = {cap_id: True for cap_id in smooth_cap_ids}

    snap = state.get("params_snapshot") or {}
    snap_logo_rot = float(snap.get("logo_rotation", 0.0) or 0.0) % 360.0
    snap_mix_flip = bool(snap.get("logo_mix_flip", False))
    snap_mix_amount = max(0.0, min(1.0, float(snap.get("logo_mix_amount", 0.0) or 0.0)))
    snap_mix_seed = int(snap.get("logo_mix_seed", 0) or 0)

    swapped = 0
    for inst, (template_brick, prior_smooth_top, p) in zip(instances, descriptors):
        new_smooth_top = bool(smooth_top_by_obj.get(id(p), False))
        if new_smooth_top == bool(prior_smooth_top):
            continue
        per_brick_rot = brick_logo_rotation_degrees(
            p, snap_logo_rot, snap_mix_flip, snap_mix_amount, snap_mix_seed,
        )
        new_template = get_template_obj(
            template_brick, smooth_top=new_smooth_top, rotation_deg=per_brick_rot,
        )
        try:
            inst.SetReferenceObject(new_template)
        except Exception:
            try:
                inst[c4d.INSTANCEOBJECT_LINK] = new_template
            except Exception:
                continue
        swapped += 1

    # Rewrite descriptors to reflect the new flags so the next fast-path
    # call diffs against fresh state.
    state["descriptors"] = [
        (template_brick, bool(smooth_top_by_obj.get(id(p), False)), p)
        for (template_brick, _prev, p) in descriptors
    ]

    if swapped:
        try:
            root.Message(c4d.MSG_UPDATE)
        except Exception:
            pass

    return root


def _apply_integrated_mograph_animation_fast_path(self, op, params=None):
    """Update an existing Source-mode instance hierarchy for animation-only changes."""
    state = getattr(self, "_fast_cap_state", None)
    if state is None:
        return None
    root = state.get("root")
    instances = state.get("instances") or []
    descriptors = state.get("descriptors") or []
    get_template_obj = state.get("get_template_obj")
    if root is None or not instances or len(instances) != len(descriptors):
        return None

    info = self._fit_info or {}
    origin = info.get("origin")
    if origin is None:
        return None
    if params is None:
        params = self._resolve_params(op, _primary_source_child(op))

    multi_mode = int(
        getattr(c4d, "INSTANCEOBJECT_RENDERINSTANCE_MODE_MULTIINSTANCE", 1)
    )
    has_effectors_now = _has_mograph_effectors(params.get("mograph_effectors"))

    stud_size = info.get("stud_size", 8.0)
    plate_size = info.get("plate_size", 3.2)
    animation_placements = [descriptor[2] for descriptor in descriptors]
    smooth_cap_ids = {
        id(descriptor[2])
        for descriptor in descriptors
        if bool(descriptor[1])
    }

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
        settle_length=params.get("build_settle_length", 0.5),
    )
    animation_state_by_obj = {
        id(anim_state.placement): anim_state
        for anim_state in animation_states
    }

    from brick.separation import (
        placement_assembly_center,
        separated_center,
    )

    brick_separation = float(params.get("brick_separation", 0.0) or 0.0)
    separation_center = placement_assembly_center(animation_placements, stud_size, plate_size)
    scale_bricks_in = bool(params.get("build_scale_in", False))
    subtle_rotation = bool(params.get("build_subtle_rotation", False))
    tilt_amount = float(params.get("build_tilt_amount", 5.0))

    bind_center_by_obj, bind_visible_by_obj, bind_orient_by_obj = _resolve_bind_state(
        self, op, _primary_source_child(op), op.GetDocument(), params
    )

    def _placement_scene_center(p):
        support = getattr(p, "support", None)
        if bind_center_by_obj is not None:
            bound = bind_center_by_obj.get(id(p))
            if bound is not None:
                return bound
            if support is not None:
                bound_support = bind_center_by_obj.get(id(support))
                if bound_support is not None:
                    # Cap position is computed in the support's LOCAL frame
                    # (lateral X/Z by source-axis stud spacing, vertical by
                    # half-thicknesses) and then projected through the
                    # support's deformed orient basis when in follow-normal
                    # mode. Without the basis projection, caps would stay
                    # axis-aligned in source-axis-local space and slide off
                    # tilted supports.
                    dx_local = (
                        (float(p.x) + float(p.w) * 0.5)
                        - (float(support.x) + float(support.w) * 0.5)
                    ) * float(stud_size)
                    dz_local = (
                        (float(p.z) + float(p.d) * 0.5)
                        - (float(support.z) + float(support.d) * 0.5)
                    ) * float(stud_size)
                    dy_local = (
                        float(support.h) * 0.5 * float(plate_size)
                        + float(p.h) * 0.5 * float(plate_size)
                    )
                    sob = (
                        bind_orient_by_obj.get(id(support))
                        if bind_orient_by_obj is not None
                        else None
                    )
                    if sob is not None:
                        sv1, sv2, sv3 = sob
                        wx = (
                            bound_support[0]
                            + sv1[0] * dx_local + sv2[0] * dy_local + sv3[0] * dz_local
                        )
                        wy = (
                            bound_support[1]
                            + sv1[1] * dx_local + sv2[1] * dy_local + sv3[1] * dz_local
                        )
                        wz = (
                            bound_support[2]
                            + sv1[2] * dx_local + sv2[2] * dy_local + sv3[2] * dz_local
                        )
                        return (float(wx), float(wy), float(wz))
                    return (
                        float(bound_support[0] + dx_local),
                        float(bound_support[1] + dy_local),
                        float(bound_support[2] + dz_local),
                    )
        # Smooth caps with a recorded support placement are anchored to the
        # support's separated top so Brick Separation > 0 doesn't drift them
        # vertically off their underlying brick.
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

    def _bind_visible(p):
        if bind_visible_by_obj is None:
            return True
        if id(p) in bind_visible_by_obj:
            return bool(bind_visible_by_obj[id(p)])
        support = getattr(p, "support", None)
        if support is not None and id(support) in bind_visible_by_obj:
            return bool(bind_visible_by_obj[id(support)])
        return True

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

    def _make_animated_centered_matrix(p):
        anim_state = animation_state_by_obj.get(id(p))
        wx, wy, wz = _placement_scene_center(p)
        y_offset = float(anim_state.y_offset) if anim_state is not None else 0.0
        wy += y_offset
        local_progress = anim_state.local_progress if anim_state is not None else 1.0
        contact_progress = (
            local_progress
            if anim_state is None or getattr(anim_state, "contact_progress", None) is None
            else anim_state.contact_progress
        )

        matrix = c4d.Matrix()
        ob = bind_orient_by_obj.get(id(p)) if bind_orient_by_obj is not None else None
        if ob is None and bind_orient_by_obj is not None:
            # Generated smooth caps inherit orient from their support so
            # they tilt with the brick beneath them on a deformed surface.
            support = getattr(p, "support", None)
            if support is not None:
                ob = bind_orient_by_obj.get(id(support))
        if ob is not None:
            v1, v2, v3 = ob
            matrix.v1 = c4d.Vector(float(v1[0]), float(v1[1]), float(v1[2]))
            matrix.v2 = c4d.Vector(float(v2[0]), float(v2[1]), float(v2[2]))
            matrix.v3 = c4d.Vector(float(v3[0]), float(v3[1]), float(v3[2]))
        tilt_x, tilt_z = build_tilt_for_progress(
            p,
            contact_progress,
            enabled=subtle_rotation,
            amount_degrees=tilt_amount,
        )
        if (tilt_x or tilt_z) and ob is None:
            try:
                matrix = (
                    c4d.utils.MatrixRotX(tilt_x)
                    * c4d.utils.MatrixRotZ(tilt_z)
                )
            except Exception:
                matrix = c4d.Matrix()

        clearance = build_tilt_clearance(
            tilt_x,
            tilt_z,
            p.h,
            plate_size,
            enabled=subtle_rotation,
        )
        if ob is None:
            wx, wz = _apply_tilt_clearance(p, wx, wz, clearance)

        scale = build_scale_for_progress(contact_progress, scale_bricks_in)
        matrix.v1 *= scale
        matrix.v2 *= scale
        matrix.v3 *= scale
        matrix.off = c4d.Vector(wx, wy, wz)
        return apply_humanize_to_center_matrix(matrix, p, params)

    pre_matrices = []
    pre_colors = []
    visible_flags = []
    for _template_brick, _smooth_top, placement in descriptors:
        anim_state = animation_state_by_obj.get(id(placement))
        visible_flags.append(anim_state is not None and anim_state.local_progress > 0.0)
        pre_matrices.append(_make_animated_centered_matrix(placement))
        pre_colors.append(_color_vector_from_rgb(getattr(placement, "rgb", (255, 255, 255))))

    if _has_mograph_effectors(params.get("mograph_effectors")):
        matrices, colors, effector_visible = _evaluate_native_mograph(
            op,
            pre_matrices,
            pre_colors,
            params.get("mograph_effectors"),
            skip_field_override=True,
            label="effector",
            frame_matrix=source_axis_local_matrix(op, _primary_source_child(op)),
        )
    else:
        matrices, colors, effector_visible = pre_matrices, pre_colors, None

    def _carrier_visible(i):
        anim = bool(visible_flags[i]) if i < len(visible_flags) else True
        eff = (
            effector_visible[i]
            if effector_visible is not None and i < len(effector_visible)
            else True
        )
        bind_vis = True
        if i < len(descriptors):
            bind_vis = _bind_visible(descriptors[i][2])
        return anim and bool(eff) and bool(bind_vis)

    # Recreate InstanceObject carriers under their existing group-null
    # parents on every fast-path call. Mutating cached carriers via
    # `SetInstanceMatrices` can drop the parent transform — bricks render at
    # the raw matrix offset (near world / op origin) instead of
    # `parent.Mg * matrix`. This was first observed with effectors; toggling
    # Humanize Bricks (no effectors) reproduces the same snap. Recreating
    # bypasses the bug — fresh InstanceObjects always render with the correct
    # parent transform — and still reuses the slow parts of the build (refit,
    # templates, group null hierarchy) so it's much cheaper than a full
    # rebuild. The cheap pure-mutation branch is kept only as a fallback when
    # the template factory isn't available.
    if get_template_obj is not None:
        live_logo_rot = float(params.get("logo_rotation", 0) or 0) % 360.0
        live_mix_flip = bool(params.get("logo_mix_flip", False))
        live_mix_amount = max(0.0, min(1.0, float(params.get("logo_mix_amount", 0.0) or 0.0)))
        live_mix_seed = int(params.get("logo_mix_seed", 0) or 0)
        new_instances = []
        for i, instance in enumerate(instances):
            matrix = matrices[i] if i < len(matrices) else pre_matrices[i]
            color = colors[i] if i < len(colors) else pre_colors[i]
            visible = _carrier_visible(i)
            matrix = _matrix_for_visibility(matrix, visible)
            template_brick, smooth_top, _placement = descriptors[i]
            try:
                group_parent = instance.GetUp()
            except Exception:
                group_parent = None
            try:
                instance.Remove()
            except Exception:
                pass
            per_brick_rot = brick_logo_rotation_degrees(
                _placement, live_logo_rot, live_mix_flip, live_mix_amount, live_mix_seed,
            )
            template = get_template_obj(
                template_brick, smooth_top=bool(smooth_top), rotation_deg=per_brick_rot,
            )
            try:
                child = c4d.InstanceObject()
            except Exception:
                child = c4d.BaseObject(c4d.Oinstance)
            child.SetName(
                "brick_{0}x{1}x{2}p_inst_{3:04d}".format(
                    int(template_brick.width),
                    int(template_brick.depth),
                    int(template_brick.height),
                    i,
                )
            )
            if template is not None:
                try:
                    child.SetReferenceObject(template)
                except Exception:
                    try:
                        child[c4d.INSTANCEOBJECT_LINK] = template
                    except Exception:
                        pass
            try:
                child[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = multi_mode
            except Exception:
                pass
            try:
                child.SetInstanceMatrices([matrix])
                child.SetInstanceColors([color])
            except Exception:
                try:
                    child.SetMl(matrix)
                except Exception:
                    pass
            _set_object_visible(child, visible)
            _apply_object_color(child, color)
            _update_object(child)
            if group_parent is not None:
                try:
                    child.InsertUnder(group_parent)
                except Exception:
                    pass
            new_instances.append(child)
        # Future fast-path calls must operate on the recreated InstanceObjects,
        # not the discarded ones.
        state["instances"] = new_instances
    else:
        for i, instance in enumerate(instances):
            matrix = matrices[i] if i < len(matrices) else pre_matrices[i]
            color = colors[i] if i < len(colors) else pre_colors[i]
            visible = _carrier_visible(i)
            matrix = _matrix_for_visibility(matrix, visible)
            try:
                instance.SetInstanceMatrices([matrix])
                instance.SetInstanceColors([color])
            except Exception:
                try:
                    instance.SetMl(matrix)
                except Exception:
                    pass
            _set_object_visible(instance, visible)
            _apply_object_color(instance, color)
            _update_object(instance)

    try:
        root.Message(c4d.MSG_UPDATE)
    except Exception:
        pass
    state["params_snapshot"] = dict(params)
    return root
