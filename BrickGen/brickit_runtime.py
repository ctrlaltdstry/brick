"""BrickIt ObjectData runtime evaluation."""
import time

import c4d

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from plugin_bootstrap import (
    brick_log as _brick_log,
    ensure_brick_on_path as _ensure_brick_on_path,
)


def GetVirtualObjects(self, op, hh):
    # First-eval stage timings: log only once per BrickIt per session so we
    # can attribute scene-open freeze cost to a specific stage.
    log_first_eval = not getattr(self, "_first_eval_logged", False)

    t_path0 = time.perf_counter() if log_first_eval else 0.0
    _ensure_brick_on_path()
    path_seconds = (time.perf_counter() - t_path0) if log_first_eval else 0.0

    t_imp0 = time.perf_counter() if log_first_eval else 0.0
    try:
        import brick.pipeline  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Failed to import brick.pipeline. Ensure the brick "
            "package is reachable and numpy/scipy are installed in "
            "Cinema 4D's Python environment."
        ) from exc
    import_seconds = (time.perf_counter() - t_imp0) if log_first_eval else 0.0

    if op[BRICKIFYASSEMBLY_SOURCE] is None:
        self._restore_managed_source()
        return None

    # Defer the first heavy GVO eval after this Python instance was
    # constructed (i.e. after scene-load deserialization). Returning a
    # cheap empty placeholder lets the Object Manager become responsive
    # while the real refit+hierarchy build runs on the next eval pass.
    # New objects created via Init() clear the flag so they don't defer.
    if getattr(self, "_deferred_first_build_pending", False):
        self._deferred_first_build_pending = False
        try:
            op.SetDirty(c4d.DIRTYFLAGS_DATA)
            c4d.SpecialEventAdd(c4d.EVMSG_CHANGE)
        except Exception:
            try:
                c4d.EventAdd()
            except Exception:
                pass
        try:
            placeholder = c4d.BaseObject(c4d.Onull)
            placeholder.SetName("BrickIt (loading...)")
            return placeholder
        except Exception:
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

    # Structural part of the hierarchy key: anything that, when changed,
    # forces a full hierarchy rebuild (re-create instance children, recompute
    # matrices/colors, etc.). Excludes the four cap-subset params below.
    structural_hierarchy_key = (
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
        bool(params.get("build_scale_in", False)),
        bool(params.get("build_subtle_rotation", False)),
        round(float(params.get("build_tilt_amount", 5.0)), 3),
        params.get("build_custom_curve_key"),
        round(float(params.get("top_surface_start", 0.85)), 5),
        round(float(params.get("top_surface_phase", 0.15)), 5),
        bool(params.get("top_surface_blend", False)),
        round(float(params.get("brick_separation", 0.0)), 5),
        bool(params.get("humanize_bricks", False)),
        int(params.get("humanize_seed", 1)),
        round(float(params.get("humanize_position", 0.0)), 5),
        round(float(params.get("humanize_rotation", 0.0)), 5),
        params.get("mograph_effectors_key"),
        params["lib_mask"],
    )
    # Cap-subset part: cheap to apply by mutating template references on
    # an existing instance hierarchy without rebuilding it.
    cap_subset_key = (
        round(float(params.get("top_surface_coverage", 1.0)), 5),
        bool(params.get("top_surface_random_order", False)),
        int(params.get("cap_style", 0)),
        int(params.get("cap_random_seed", 0)),
    )
    hierarchy_key = (structural_hierarchy_key, cap_subset_key)

    cached = op.GetCache(hh)
    if (
        not self._force_rebuild
        and cached is not None
        and self._hierarchy_cache_key == hierarchy_key
    ):
        return cached

    # Fast path: structural side of the hierarchy is unchanged and only the
    # cap subset (coverage / cap style / cap seed / random order) differs,
    # AND we're at the final build progress (so per-placement matrices and
    # colors are cap-independent — only template references need updating).
    fast_path_eligible = (
        not self._force_rebuild
        and cached is not None
        and isinstance(self._hierarchy_cache_key, tuple)
        and len(self._hierarchy_cache_key) == 2
        and self._hierarchy_cache_key[0] == structural_hierarchy_key
        and self._hierarchy_cache_key[1] != cap_subset_key
        and float(params.get("build_progress", 1.0)) >= 0.9999
        and params.get("visualization_mode") == BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE
        and getattr(self, "_fast_cap_state", None) is not None
    )
    if fast_path_eligible:
        try:
            t0 = time.perf_counter()
            updated = self._apply_cap_subset_fast_path(op, params)
            fast_seconds = time.perf_counter() - t0
            if updated is not None:
                self._hierarchy_cache_key = hierarchy_key
                try:
                    _brick_log(
                        "[brick] Cap subset fast path: {0:.3f}s, placements={1}".format(
                            float(fast_seconds), len(self._fit_placements or [])
                        )
                    )
                except Exception:
                    pass
                return updated
        except Exception as exc:
            try:
                _brick_log("[brick] Cap subset fast path failed, falling back: {0}".format(exc))
            except Exception:
                pass

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
    if params.get("visualization_mode") == BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE:
        result = self._build_integrated_mograph_hierarchy(op, params=params)
    else:
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
    if log_first_eval:
        # Stage breakdown for the very first GVO evaluation of this BrickIt
        # in the current C4D session. This is the cost the user feels as
        # "scene-open freeze". Subsequent evaluations skip this log line.
        try:
            stage_breakdown = getattr(self, "_first_eval_stage_breakdown", None) or {}
            _brick_log(
                "[brick] First-eval stages: ensure_path={0:.3f}s, "
                "import_brick={1:.3f}s, source_bake={2:.3f}s, "
                "voxelize={3:.3f}s, brick_mesh={4:.3f}s, refit_other={5:.3f}s, "
                "hierarchy={6:.3f}s, total={7:.3f}s, "
                "verts={8}, faces={9}".format(
                    float(path_seconds),
                    float(import_seconds),
                    float(stage_breakdown.get("source_bake", 0.0)),
                    float(stage_breakdown.get("voxelize", 0.0)),
                    float(stage_breakdown.get("brick_mesh", 0.0)),
                    float(
                        max(
                            0.0,
                            float(refit_seconds)
                            - float(stage_breakdown.get("source_bake", 0.0))
                            - float(stage_breakdown.get("voxelize", 0.0))
                            - float(stage_breakdown.get("brick_mesh", 0.0)),
                        )
                    ),
                    float(hierarchy_seconds),
                    float(path_seconds + import_seconds + total_seconds),
                    int(stage_breakdown.get("mesh_verts", 0)),
                    int(stage_breakdown.get("mesh_faces", 0)),
                )
            )
        except Exception:
            pass
        self._first_eval_logged = True
        self._first_eval_stage_breakdown = None
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
