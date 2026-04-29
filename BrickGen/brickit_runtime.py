"""BrickIt ObjectData runtime evaluation."""
import time

import c4d

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from plugin_bootstrap import (
    brick_log as _brick_log,
    ensure_brick_on_path as _ensure_brick_on_path,
)


def GetVirtualObjects(self, op, hh):
    _ensure_brick_on_path()

    try:
        import brick.pipeline  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Failed to import brick.pipeline. Ensure the brick "
            "package is reachable and numpy/scipy are installed in "
            "Cinema 4D's Python environment."
        ) from exc

    if op[BRICKIFYASSEMBLY_SOURCE] is None:
        self._restore_managed_source()
        return None

    source_obj = op[BRICKIFYASSEMBLY_SOURCE]
    self._sync_source_visibility(op)
    params = self._resolve_params(op, source_obj)
    actual_res_key = self._resolution_key(params)
    # Startup responsiveness: first scene-open evaluation runs in draft.
    if self._startup_draft_pending and not self._force_rebuild:
        params = dict(params)
        params["quality"] = BRICKIFYASSEMBLY_QUALITY_DRAFT
    use_interactive_preview = (not self._force_rebuild) and bool(
        self._interactive_preview_active
    )
    if use_interactive_preview:
        params = self._interactive_preview_params(params)
        preview_log_key = (
            params["studs_across"],
            params["quality"],
            params["detail_mode"],
            self._interactive_preview_desc_id,
        )
        if self._interactive_preview_log_key != preview_log_key:
            try:
                _brick_log(
                    "[brick] Interactive preview: using internal "
                    "studs_across={0} (final={1}), quality=draft, "
                    "detail=off while dragging param={2}".format(
                        params["studs_across"],
                        params["interactive_preview_actual_studs_across"],
                        self._interactive_preview_desc_id,
                    )
                )
            except Exception:
                pass
            self._interactive_preview_log_key = preview_log_key

    hierarchy_key = (
        self._source_state_key(source_obj),
        params["studs_across"],
        params["use_manual_stud_size"],
        params["stud_size"],
        params["voxel_backend"],
        params["voxel_mode"],
        params["shell_thickness"],
        params["detail_mode"],
        params["quality"],
        params["max_brick_height"],
        params["randomize_heights"],
        params["height_mix_seed"],
        params["height_mix_amount"],
        params["merge_plates"],
        params["prune"],
        params["cleanup_protrusions"],
        params["preserve_silhouette"],
        params["preserve_tiny_gaps"],
        params["surface_only_plates"],
        params["enable_plates"],
        params["visualization_mode"],
        params["logo_enabled"],
        self._source_state_key(params["logo_source"]) if params.get("logo_source") is not None else None,
        int(params.get("logo_rotation", 0) or 0),
        round(float(params["logo_diameter"]), 4),
        round(float(params["logo_height"]), 4),
        round(float(params["logo_blend"]), 4),
        round(float(params["logo_sink"]), 4),
        round(float(params.get("build_progress", 1.0)), 6),
        round(float(params.get("build_y_offset", 25.0)), 3),
        round(float(params.get("build_stagger", 0.10)), 5),
        int(params.get("build_motion_curve", BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_SLAM)),
        params.get("build_custom_curve_key"),
        round(float(params.get("top_surface_phase", 0.15)), 5),
        round(float(params.get("top_surface_coverage", 1.0)), 5),
        params["lib_mask"],
    )

    cached = op.GetCache(hh)
    if (
        not self._force_rebuild
        and cached is not None
        and self._hierarchy_cache_key == hierarchy_key
    ):
        return cached

    doc = op.GetDocument()
    if doc is None and hh is not None:
        try:
            doc = hh.GetDocument()
        except Exception:
            doc = None

    t_build0 = time.perf_counter()
    t0 = time.perf_counter()
    if not self._refit_if_needed(op, doc, params):
        return None
    refit_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    result = self._build_hierarchy(op)
    hierarchy_seconds = time.perf_counter() - t0
    total_seconds = time.perf_counter() - t_build0
    try:
        _brick_log(
            "[brick] Build timings: total={0:.3f}s, refit={1:.3f}s, "
            "hierarchy={2:.3f}s, placements={3}, interactive_preview={4}".format(
                float(total_seconds),
                float(refit_seconds),
                float(hierarchy_seconds),
                len(self._fit_placements or []),
                bool(params.get("interactive_preview", False)),
            )
        )
    except Exception:
        pass
    self._hierarchy_cache_key = hierarchy_key
    if result is not None:
        try:
            self._last_hierarchy_obj = result.GetClone(c4d.COPYFLAGS_NONE)
        except Exception:
            self._last_hierarchy_obj = None
    else:
        self._last_hierarchy_obj = None
    self._last_resolution_key = actual_res_key
    veff = params.get("voxel_resolution_effective")
    if veff is not None:
        try:
            self._built_voxel_resolution = float(veff)
        except Exception:
            pass
    self._force_rebuild = False
    self._startup_draft_pending = False
    return result
