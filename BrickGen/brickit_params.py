"""BrickIt parameter resolution helpers."""

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from library_panel import (
    BRICK_TOGGLE_NAMES,
    apply_library_mask_to_toggles as _apply_library_mask_to_toggles,
    read_library_mask as _read_library_mask,
    toggle_id as _toggle_id,
)
from logo_helpers import (
    BRICKGEN_LOGO_FILL_UI_DEFAULT,
    logo_fill_to_diameter_ratio as _logo_fill_to_diameter_ratio,
)
from quality_presets import ASSEMBLY_QUALITY_PRESETS
from brickit_animation import custom_curve_signature


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

def _interactive_preview_params(self, params):
    preview = dict(params)
    preview["interactive_preview"] = True
    preview["interactive_preview_actual_studs_across"] = int(params["studs_across"])
    if not bool(params.get("use_manual_stud_size")):
        preview["studs_across"] = min(
            int(params["studs_across"]),
            INTERACTIVE_PREVIEW_MAX_STUDS,
        )
    preview["quality"] = BRICKIFYASSEMBLY_QUALITY_DRAFT
    # Detail bands are expensive and noisy while dragging controls; the
    # settled rebuild restores the exact requested detail mode.
    preview["detail_mode"] = "off"
    return preview


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
    lib_mask = _read_library_mask(op)
    # Keep legacy toggles synced before classifying library mode. The
    # native GUI writes a bitmask, while older scenes rely on per-toggle
    # bools; syncing here avoids stale mode detection.
    _apply_library_mask_to_toggles(op, lib_mask)
    try:
        enable_plates = bool(op[BRICKIFYASSEMBLY_ENABLE_PLATES])
    except Exception:
        enable_plates = False
    selected_toggle_names = []
    for i, name in enumerate(BRICK_TOGGLE_NAMES):
        try:
            if bool(op[_toggle_id(i)]):
                selected_toggle_names.append(name)
        except Exception:
            # If a toggle read fails, treat it as enabled to avoid
            # accidentally entering restrictive auto-modes.
            selected_toggle_names.append(name)
    only_2x_library = (not enable_plates) and bool(selected_toggle_names) and all(
        ("_2x" in n) for n in selected_toggle_names
    )
    only_1x1_library = (not enable_plates) and bool(selected_toggle_names) and all(
        (n.endswith("_1x1") or n.endswith("1x1")) for n in selected_toggle_names
    )
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
    visualization_mode = int(op[BRICKIFYASSEMBLY_VISUALIZATION_MODE] or 0)
    # "Brick Size" and "Shell Depth" were removed from the UI cycle.
    # Coerce legacy scene values to Source so old files remain valid.
    if visualization_mode in (
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_BRICK_SIZE,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_DEPTH,
    ):
        visualization_mode = BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE
        try:
            op[BRICKIFYASSEMBLY_VISUALIZATION_MODE] = visualization_mode
        except Exception:
            pass
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
    build_y_offset_raw = op[BRICKIFYASSEMBLY_BUILD_Y_OFFSET]
    if build_y_offset_raw is None:
        build_y_offset_raw = 25.0
    build_y_offset = max(0.0, min(100.0, float(build_y_offset_raw)))
    build_stagger_raw = op[BRICKIFYASSEMBLY_BUILD_STAGGER]
    if build_stagger_raw is None:
        build_stagger_raw = 10.0
    build_stagger = max(0.0, min(1.0, float(build_stagger_raw) / 100.0))
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
    ):
        build_motion_curve = BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_SLAM
    build_custom_curve = op[BRICKIFYASSEMBLY_BUILD_CUSTOM_CURVE]
    build_custom_curve_key = custom_curve_signature(build_custom_curve)
    top_surface_phase_raw = op[BRICKIFYASSEMBLY_TOP_SURFACE_PHASE]
    if top_surface_phase_raw is None:
        top_surface_phase_raw = 15.0
    top_surface_phase = max(0.0, min(1.0, float(top_surface_phase_raw) / 100.0))
    top_surface_coverage_raw = op[BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE]
    if top_surface_coverage_raw is None:
        top_surface_coverage_raw = 100.0
    top_surface_coverage = max(0.0, min(1.0, float(top_surface_coverage_raw) / 100.0))

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
        "build_y_offset": build_y_offset,
        "build_stagger": build_stagger,
        "build_motion_curve": build_motion_curve,
        "build_custom_curve": build_custom_curve,
        "build_custom_curve_key": build_custom_curve_key,
        "top_surface_phase": top_surface_phase,
        "top_surface_coverage": top_surface_coverage,
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

