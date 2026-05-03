"""BrickIt parameter resolution helpers."""

import c4d

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from library_panel import (
    BRICK_TOGGLE_NAMES,
    apply_library_mask_to_toggles as _apply_library_mask_to_toggles,
    read_library_mask as _read_library_mask,
)
from logo_helpers import (
    BRICKGEN_LOGO_FILL_UI_DEFAULT,
    logo_fill_to_diameter_ratio as _logo_fill_to_diameter_ratio,
)
from quality_presets import ASSEMBLY_QUALITY_PRESETS
from .brickit_animation import custom_curve_signature


# Voxel-resolution slider mapping. The UI is 0..1 normalized; internally
# we drive studs_across through an exponential/detail curve. This makes the
# middle of the slider useful instead of bunching common low-res values near
# zero: 1.0=8 (chunky), 0.55~25, 0.46~32, 0.37~40, 0.1=80 (detailed).
VOXEL_RES_MIN_STUDS = 8
VOXEL_RES_MAX_STUDS = 80
# Default 1.0 = chunkiest mesh (fewest studs across); safest first-open behavior.
VOXEL_RES_DEFAULT = 1.0
# After Live Update slider motion stops, wait this long before rebuilding (seconds).
RESOLUTION_LIVE_DEBOUNCE_SEC = 0.28
INTERACTIVE_PREVIEW_MAX_STUDS = 16
INTERACTIVE_PREVIEW_EDIT_WINDOW = 0.45


def _snap_voxel_resolution(value):
    """Clamp to 0.1..1.0 and snap to 0.1 increments (matches AM slider)."""
    v = max(0.1, min(1.0, float(value)))
    return round(v * 10.0) / 10.0


def _voxel_resolution_to_studs(value):
    v = _snap_voxel_resolution(value)
    # UI direction is intentionally inverted for artist ergonomics:
    # larger numeric slider value -> chunkier (fewer studs across).
    t = (v - 0.1) / 0.9
    detail_t = 1.0 - t
    ratio = float(VOXEL_RES_MAX_STUDS) / float(VOXEL_RES_MIN_STUDS)
    return int(round(float(VOXEL_RES_MIN_STUDS) * (ratio ** detail_t)))


def _param_linear_timeline(op, param_id, fallback_progress):
    try:
        doc = op.GetDocument()
    except Exception:
        doc = None
    if doc is None:
        return fallback_progress
    try:
        fps = max(1, int(doc.GetFps()))
        current_frame = float(doc.GetTime().GetFrame(fps))
    except Exception:
        return fallback_progress

    desc_ids = []
    try:
        desc_ids.append(c4d.DescID(c4d.DescLevel(param_id)))
    except Exception:
        pass
    try:
        desc_ids.append(
            c4d.DescID(
                c4d.DescLevel(
                    param_id,
                    c4d.DTYPE_REAL,
                    ID_BRICKIFYASSEMBLY,
                )
            )
        )
    except Exception:
        pass

    tracks = []
    for desc_id in desc_ids:
        try:
            track = op.FindCTrack(desc_id)
        except Exception:
            track = None
        if track is not None:
            tracks.append(track)
    if not tracks:
        return fallback_progress

    frames = []
    for track in tracks:
        try:
            curve = track.GetCurve()
            key_count = int(curve.GetKeyCount())
        except Exception:
            continue
        for i in range(key_count):
            try:
                frames.append(float(curve.GetKey(i).GetTime().GetFrame(fps)))
            except Exception:
                pass
    if len(frames) < 2:
        return fallback_progress

    start = min(frames)
    end = max(frames)
    if end <= start:
        return fallback_progress
    return max(0.0, min(1.0, (current_frame - start) / (end - start)))


def _library_ui_state(op, *, sync_toggles=False):
    """Return the shared library predicates used by UI and fitting logic."""
    lib_mask = _read_library_mask(op)
    if sync_toggles:
        _apply_library_mask_to_toggles(op, lib_mask)
    try:
        enable_plates = bool(op[BRICKIFYASSEMBLY_ENABLE_PLATES])
    except Exception:
        enable_plates = False
    selected_toggle_names = [
        name
        for i, name in enumerate(BRICK_TOGGLE_NAMES)
        if bool(int(lib_mask) & (1 << i))
    ]
    only_2x_library = (not enable_plates) and bool(selected_toggle_names) and all(
        ("_2x" in n) for n in selected_toggle_names
    )
    only_1x1_library = (not enable_plates) and bool(selected_toggle_names) and all(
        (n.endswith("_1x1") or n.endswith("1x1")) for n in selected_toggle_names
    )
    try:
        max_bh = max(1, min(6, int(op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT])))
    except Exception:
        max_bh = 3
    return {
        "lib_mask": lib_mask,
        "enable_plates": enable_plates,
        "selected_toggle_names": selected_toggle_names,
        "only_1x1_library": only_1x1_library,
        "only_2x_library": only_2x_library,
        "max_brick_height": max_bh,
    }


def _interactive_preview_params(self, params):
    preview = dict(params)
    preview["interactive_preview"] = True
    preview["interactive_preview_actual_studs_across"] = int(params["studs_across"])
    if not bool(params.get("use_manual_stud_size")):
        preview["studs_across"] = min(
            int(params["studs_across"]),
            INTERACTIVE_PREVIEW_MAX_STUDS,
        )
    preview["quality"] = BRICKIFYASSEMBLY_QUALITY_PROXY
    # Detail bands are expensive and noisy while dragging controls; the
    # settled rebuild restores the exact requested detail mode.
    preview["detail_mode"] = "off"
    return preview


def _inexclude_signature(data, doc):
    if data is None:
        return ()
    try:
        count = int(data.GetObjectCount())
    except Exception:
        return ()
    out = []
    for i in range(count):
        try:
            obj = data.ObjectFromIndex(doc, i)
        except Exception:
            obj = None
        try:
            flags = int(data.GetFlags(i))
        except Exception:
            flags = 0
        if obj is None:
            out.append((None, flags))
            continue
        try:
            dirty = int(obj.GetDirty(c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_MATRIX))
        except Exception:
            dirty = 0
        try:
            name = obj.GetName()
        except Exception:
            name = ""
        out.append((name, dirty, flags))
    return tuple(out)


def _resolve_params(self, op, source_obj):
    # Model Resolution slider (0.1..1.0). When "Live Update" is off,
    # `_built_voxel_resolution` holds the last baked value until Rebuild.
    resolution_live = bool(op[BRICKIFYASSEMBLY_AUTO_REBUILD])
    voxel_res = op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION]
    voxel_resolution_ui = None
    voxel_resolution_effective = None
    if voxel_res is None:
        studs_across = max(VOXEL_RES_MIN_STUDS,
                           int(op[BRICKIFYASSEMBLY_STUDS_ACROSS] or 16))
    else:
        voxel_resolution_ui = _snap_voxel_resolution(voxel_res)
        effective_voxel_res = voxel_resolution_ui
        if (
            (not resolution_live)
            and (not self._force_rebuild)
            and (self._built_voxel_resolution is not None)
        ):
            effective_voxel_res = float(self._built_voxel_resolution)
        voxel_resolution_effective = effective_voxel_res
        studs_across = _voxel_resolution_to_studs(effective_voxel_res)
    studs_across = max(VOXEL_RES_MIN_STUDS,
                       min(VOXEL_RES_MAX_STUDS, studs_across))
    use_manual_stud_size = bool(op[BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE])
    manual_stud_size = max(0.001, float(op[BRICKIFYASSEMBLY_STUD_SIZE] or 8.0))
    stud_size = manual_stud_size if use_manual_stud_size else None
    try:
        voxel_backend_id = int(op[BRICKIFYASSEMBLY_VOXEL_BACKEND])
    except Exception:
        voxel_backend_id = BRICKIFYASSEMBLY_VOXEL_BACKEND_INTERNAL
    voxel_backend = (
        "c4d_volume"
        if voxel_backend_id == BRICKIFYASSEMBLY_VOXEL_BACKEND_C4D_VOLUME
        else "internal"
    )
    voxel_mode_id = int(op[BRICKIFYASSEMBLY_VOXEL_MODE])
    voxel_mode = "shell" if voxel_mode_id == BRICKIFYASSEMBLY_VOXEL_MODE_SHELL else "solid"
    shell_thickness = max(1, min(8, int(op[BRICKIFYASSEMBLY_SHELL_THICKNESS] or 3)))
    detail_mode_id = int(op[BRICKIFYASSEMBLY_DETAIL_MODE] or 0)
    detail_mode = {
        BRICKIFYASSEMBLY_DETAIL_MODE_BALANCED: "balanced",
        BRICKIFYASSEMBLY_DETAIL_MODE_PRESERVE: "preserve",
    }.get(detail_mode_id, "off")
    quality = int(op[BRICKIFYASSEMBLY_QUALITY])
    if quality not in ASSEMBLY_QUALITY_PRESETS:
        quality = BRICKIFYASSEMBLY_QUALITY_STANDARD
    # Library now exposes synthetic height variants so this cap is
    # meaningfully controllable from 1..6 plate units.
    max_bh = max(1, min(6, int(op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT])))
    randomize_heights = bool(op[BRICKIFYASSEMBLY_HEIGHT_VARIATION])
    seed_raw = op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED]
    if seed_raw is None:
        seed_raw = 1
    height_mix_seed = max(0, min(1000000, int(seed_raw)))

    mix_raw = op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT]
    if mix_raw is None:
        mix_raw = 0.6
    # Perceptual response shaping: keep the stronger look of the original
    # mix behavior while spreading control a bit more evenly across 0..1.
    mix_linear = max(0.0, min(1.0, float(mix_raw)))
    height_mix_amount = mix_linear ** 1.3
    # When max_bh < 3, plates can't be promoted into bricks. The merge
    # step therefore must be suppressed so the fitter's plate output
    # stays plates.
    merge_plates_user = bool(op[BRICKIFYASSEMBLY_MERGE_PLATES])
    merge_plates = merge_plates_user and max_bh >= 3
    # Track library composition for resolution/detail heuristics below.
    # Do not auto-override the physically accurate checkbox from these modes.
    library_state = _library_ui_state(op, sync_toggles=True)
    lib_mask = library_state["lib_mask"]
    enable_plates = library_state["enable_plates"]
    only_2x_library = library_state["only_2x_library"]
    only_1x1_library = library_state["only_1x1_library"]
    # With 2x-only libraries, detail-band restrictions can over-constrain
    # the fitter and produce carved-out facades. Force detail strategy off
    # so coverage stays stable for "2x only" workflows.
    if only_2x_library and detail_mode != "off":
        detail_mode = "off"
        try:
            op[BRICKIFYASSEMBLY_DETAIL_MODE] = BRICKIFYASSEMBLY_DETAIL_MODE_OFF
        except Exception:
            pass
    if only_2x_library and (not use_manual_stud_size):
        # 2x-only footprints tile in 2-cell quanta. At odd voxel resolution
        # widths (common around ~0.7 slider values), one-cell perimeter
        # strips become impossible to cover and look like "missing mass".
        # Snap auto resolution to an even studs-across value in this mode.
        if studs_across % 2 != 0:
            studs_across = min(VOXEL_RES_MAX_STUDS, studs_across + 1)
    # Read bool params defensively from C4D containers (0/1, GeData, or bool).
    # Using explicit int coercion avoids "truthy object" edge cases that can
    # make a checkbox appear permanently enabled.
    try:
        prune_user_raw = op[BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY]
        prune_user = bool(int(prune_user_raw))
    except Exception:
        prune_user = bool(op[BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY])
    # Respect explicit user intent: this checkbox is the sole control for
    # connectivity pruning behavior.
    prune = prune_user
    prune_auto_disabled = False
    prune_auto_reason = ""
    cleanup_protrusions = max(0, int(op[BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS]
                                     or 0))
    # In 1x1-only mode, protrusion cleanup tends to remove valid shelf/
    # ledge boundaries. Prioritize silhouette fidelity over cleanup.
    if only_1x1_library:
        cleanup_protrusions = 0
    # Preserve horizontal silhouette bands for 1x1 runs so stepped base
    # shelves stay intact instead of fragmenting into sparse leftovers.
    preserve_silhouette = bool(only_1x1_library or only_2x_library)
    preserve_tiny_gaps = bool(op[BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS])
    # UI override for plate placement policy.
    surface_only_plates_ui = bool(op[BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES])
    # Apply in both solid and shell voxel modes, but only when plate usage
    # itself is enabled.
    surface_only_plates = bool(surface_only_plates_ui and enable_plates)
    raw_visualization_mode = int(op[BRICKIFYASSEMBLY_VISUALIZATION_MODE] or 0)
    # The UI cycle now exposes only Source/Shell/Voxel. Depending on the C4D
    # resource load, the cycle can arrive as either the symbol value (0/3/4)
    # or the compact menu index (0/1/2). Normalize both forms here.
    if raw_visualization_mode == 1:
        visualization_mode = BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME
    elif raw_visualization_mode == 2:
        visualization_mode = BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG
    else:
        visualization_mode = raw_visualization_mode
    logo_enabled = bool(op[BRICKIFYASSEMBLY_ENABLE_LOGO])
    logo_source = op[BRICKIFYASSEMBLY_LOGO_SOURCE]
    logo_rotation = int(op[BRICKIFYASSEMBLY_LOGO_ROTATION] or 0) % 4
    logo_diameter = _logo_fill_to_diameter_ratio(op[BRICKIFYASSEMBLY_LOGO_DIAMETER])
    logo_height = max(0.02, min(0.25, float(op[BRICKIFYASSEMBLY_LOGO_HEIGHT] or 0.06)))
    logo_blend = max(0.0, min(1.0, float(op[BRICKIFYASSEMBLY_LOGO_BLEND] or 0.0)))
    logo_sink = max(0.0, min(0.05, float(op[BRICKIFYASSEMBLY_LOGO_SINK] or 0.0)))
    build_progress_raw = op[BRICKIFYASSEMBLY_BUILD_PROGRESS]
    if build_progress_raw is None:
        build_progress_raw = 100.0
    build_progress = max(0.0, min(1.0, float(build_progress_raw) / 100.0))
    build_progress_time = _param_linear_timeline(
        op,
        BRICKIFYASSEMBLY_BUILD_PROGRESS,
        build_progress,
    )
    smooth_top_progress_raw = op[BRICKIFYASSEMBLY_SMOOTH_TOP_PROGRESS]
    if smooth_top_progress_raw is None:
        smooth_top_progress_raw = 100.0
    smooth_top_progress = max(0.0, min(1.0, float(smooth_top_progress_raw) / 100.0))
    smooth_top_progress_time = _param_linear_timeline(
        op,
        BRICKIFYASSEMBLY_SMOOTH_TOP_PROGRESS,
        smooth_top_progress,
    )
    build_y_offset_raw = op[BRICKIFYASSEMBLY_BUILD_Y_OFFSET]
    if build_y_offset_raw is None:
        build_y_offset_raw = 25.0
    build_y_offset = max(0.0, min(100.0, float(build_y_offset_raw)))
    build_stagger_raw = op[BRICKIFYASSEMBLY_BUILD_STAGGER]
    if build_stagger_raw is None:
        build_stagger_raw = 10.0
    build_stagger = max(0.0, min(1.0, float(build_stagger_raw) / 100.0))
    build_hang_time_raw = op[BRICKIFYASSEMBLY_BUILD_HANG_TIME]
    if build_hang_time_raw is None:
        build_hang_time_raw = 0.0
    build_hang_time = max(0.0, min(1.0, float(build_hang_time_raw) / 100.0))
    build_motion_curve = int(
        op[BRICKIFYASSEMBLY_BUILD_MOTION_CURVE]
        or BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_SLAM
    )
    if build_motion_curve not in (
        BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_EASE,
        BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_EASE_IN,
        BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_EASE_OUT,
        BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_SPRING,
        BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_SLAM,
        BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_QUADRATIC,
        BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_CUSTOM,
        BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_BOUNCE,
    ):
        build_motion_curve = BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_SLAM
    build_scale_in = bool(op[BRICKIFYASSEMBLY_BUILD_SCALE_IN])
    build_subtle_rotation = bool(op[BRICKIFYASSEMBLY_BUILD_SUBTLE_ROTATION])
    build_tilt_amount_raw = op[BRICKIFYASSEMBLY_BUILD_TILT_AMOUNT]
    if build_tilt_amount_raw is None:
        build_tilt_amount_raw = 5.0
    build_tilt_amount = max(0.0, min(360.0, float(build_tilt_amount_raw)))
    build_custom_curve = op[BRICKIFYASSEMBLY_BUILD_CUSTOM_CURVE]
    build_custom_curve_key = custom_curve_signature(build_custom_curve)
    top_surface_start = 0.35
    top_surface_phase = 0.15
    top_surface_blend = bool(op[BRICKIFYASSEMBLY_TOP_SURFACE_BLEND])
    top_surface_coverage_raw = op[BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE]
    if top_surface_coverage_raw is None:
        top_surface_coverage_raw = 100.0
    top_surface_coverage = max(0.0, min(1.0, float(top_surface_coverage_raw) / 100.0))
    top_surface_random_order = bool(op[BRICKIFYASSEMBLY_TOP_SURFACE_RANDOM_ORDER])
    cap_style_raw = op[BRICKIFYASSEMBLY_CAP_STYLE]
    cap_style = int(cap_style_raw) if cap_style_raw is not None else BRICKIFYASSEMBLY_CAP_STYLE_MATCH_BELOW
    if cap_style not in (
        BRICKIFYASSEMBLY_CAP_STYLE_MATCH_BELOW,
        BRICKIFYASSEMBLY_CAP_STYLE_MERGED_COVER,
        BRICKIFYASSEMBLY_CAP_STYLE_RANDOM_MIX,
    ):
        cap_style = BRICKIFYASSEMBLY_CAP_STYLE_MATCH_BELOW
    cap_random_seed_raw = op[BRICKIFYASSEMBLY_CAP_RANDOM_SEED]
    cap_random_seed = max(0, int(cap_random_seed_raw)) if cap_random_seed_raw is not None else 0
    brick_separation_raw = op[BRICKIFYASSEMBLY_BRICK_SEPARATION]
    if brick_separation_raw is None:
        brick_separation_raw = 0.0
    brick_separation = max(0.0, min(1.0, float(brick_separation_raw)))
    humanize_bricks = bool(op[BRICKIFYASSEMBLY_HUMANIZE_BRICKS])
    humanize_seed_raw = op[BRICKIFYASSEMBLY_HUMANIZE_SEED]
    if humanize_seed_raw is None:
        humanize_seed_raw = 1
    humanize_seed = max(0, min(1000000, int(humanize_seed_raw)))
    humanize_position_raw = op[BRICKIFYASSEMBLY_HUMANIZE_POSITION]
    if humanize_position_raw is None:
        humanize_position_raw = 0.0
    humanize_position = max(0.0, min(1.0, float(humanize_position_raw)))
    humanize_rotation_raw = op[BRICKIFYASSEMBLY_HUMANIZE_ROTATION]
    if humanize_rotation_raw is None:
        humanize_rotation_raw = 0.0
    humanize_rotation = max(0.0, min(2.0, float(humanize_rotation_raw)))
    try:
        mograph_effectors = op[BRICKIFYASSEMBLY_MOGRAPH_EFFECTORS]
    except Exception:
        mograph_effectors = None
    try:
        doc = op.GetDocument()
    except Exception:
        doc = None
    mograph_effectors_key = _inexclude_signature(mograph_effectors, doc)

    try:
        bind_to_source_deformation = bool(op[BRICKIFYASSEMBLY_BIND_TO_SOURCE_DEFORMATION])
    except Exception:
        bind_to_source_deformation = False
    try:
        bind_reference_frame = int(op[BRICKIFYASSEMBLY_BIND_REFERENCE_FRAME] or 0)
    except Exception:
        bind_reference_frame = 0
    try:
        bind_orientation_mode = int(op[BRICKIFYASSEMBLY_BIND_ORIENTATION_MODE] or 0)
    except Exception:
        bind_orientation_mode = BRICKIFYASSEMBLY_BIND_ORIENT_WORLD_UP
    try:
        bind_stretch_cull_ratio = float(op[BRICKIFYASSEMBLY_BIND_STRETCH_CULL_RATIO])
    except Exception:
        bind_stretch_cull_ratio = 0.6
    bind_stretch_cull_ratio = max(0.0, min(1.0, bind_stretch_cull_ratio))
    try:
        bind_orient_smoothing = float(op[BRICKIFYASSEMBLY_BIND_ORIENT_SMOOTHING])
    except Exception:
        bind_orient_smoothing = 0.7
    bind_orient_smoothing = max(0.0, min(1.0, bind_orient_smoothing))

    # Library curation key — bitmask over brick toggles. Goes
    # into the fit cache key so toggling a brick reruns the fitter.
    lib_mask = _read_library_mask(op)

    return {
        "studs_across": studs_across,
        "use_manual_stud_size": use_manual_stud_size,
        "stud_size": stud_size,
        "voxel_backend": voxel_backend,
        "voxel_mode": voxel_mode,
        "shell_thickness": shell_thickness,
        "detail_mode": detail_mode,
        "quality": quality,
        "max_brick_height": max_bh,
        "randomize_heights": randomize_heights,
        "height_mix_seed": height_mix_seed,
        "height_mix_amount": height_mix_amount,
        "height_mix_amount_ui": mix_linear,
        "merge_plates": merge_plates,
        "prune": prune,
        "prune_user": prune_user,
        "relaxed_boundary_fit": not prune,
        "prune_auto_disabled": prune_auto_disabled,
        "prune_auto_reason": prune_auto_reason,
        "only_1x1_library": only_1x1_library,
        "cleanup_protrusions": cleanup_protrusions,
        "preserve_silhouette": preserve_silhouette,
        "preserve_tiny_gaps": preserve_tiny_gaps,
        "surface_only_plates": surface_only_plates,
        "cap_style": cap_style,
        "cap_random_seed": cap_random_seed,
        "enable_plates": enable_plates,
        "visualization_mode": visualization_mode,
        "resolution_live": resolution_live,
        "voxel_resolution_ui": voxel_resolution_ui,
        "voxel_resolution_effective": voxel_resolution_effective,
        "logo_enabled": logo_enabled,
        "logo_source": logo_source,
        "logo_rotation": logo_rotation,
        "logo_diameter": logo_diameter,
        "logo_height": logo_height,
        "logo_blend": logo_blend,
        "logo_sink": logo_sink,
        "build_progress": build_progress,
        "build_progress_time": build_progress_time,
        "smooth_top_progress": smooth_top_progress,
        "smooth_top_progress_time": smooth_top_progress_time,
        "build_y_offset": build_y_offset,
        "build_stagger": build_stagger,
        "build_hang_time": build_hang_time,
        "build_motion_curve": build_motion_curve,
        "build_scale_in": build_scale_in,
        "build_subtle_rotation": build_subtle_rotation,
        "build_tilt_amount": build_tilt_amount,
        "build_custom_curve": build_custom_curve,
        "build_custom_curve_key": build_custom_curve_key,
        "top_surface_start": top_surface_start,
        "top_surface_phase": top_surface_phase,
        "top_surface_blend": top_surface_blend,
        "top_surface_coverage": top_surface_coverage,
        "top_surface_random_order": top_surface_random_order,
        "brick_separation": brick_separation,
        "humanize_bricks": humanize_bricks,
        "humanize_seed": humanize_seed,
        "humanize_position": humanize_position,
        "humanize_rotation": humanize_rotation,
        "mograph_effectors": mograph_effectors,
        "mograph_effectors_key": mograph_effectors_key,
        "bind_to_source_deformation": bind_to_source_deformation,
        "bind_reference_frame": bind_reference_frame,
        "bind_orientation_mode": bind_orientation_mode,
        "bind_stretch_cull_ratio": bind_stretch_cull_ratio,
        "bind_orient_smoothing": bind_orient_smoothing,
        "lib_mask": lib_mask,
        "interactive_preview": False,
        "interactive_preview_actual_studs_across": studs_across,
    }


def _resolution_key(self, params):
    return (
        params["studs_across"],
        bool(params["use_manual_stud_size"]),
        round(float(params["stud_size"] or -1.0), 6),
    )

