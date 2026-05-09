"""BrickIt library selection and pipeline refit helpers."""
import time

import c4d

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from library_panel import (
    BRICK_TOGGLE_NAMES,
    PLATE_LIBRARY_NAMES,
    apply_library_mask_to_toggles as _apply_library_mask_to_toggles,
    read_library_mask as _read_library_mask,
    toggle_id as _toggle_id,
)
from logo_helpers import baked_polygon_object_with_metadata as _baked_polygon_object_with_metadata
from plugin_bootstrap import brick_log as _brick_log
from source_geometry import (
    c4d_volume_voxels_from_polygon_object as _c4d_volume_voxels_from_polygon_object,
    placement_grouping_for_islands as _placement_grouping_for_islands,
    polygon_object_to_arrays as _polygon_object_to_arrays,
    source_polygon_islands as _source_polygon_islands,
)

from .brickit_sources import (
    BRICKIFYASSEMBLY_SOURCE_MODE_UNION as _SOURCE_MODE_UNION,
    bake_brickit_sources_per_mode as _bake_brickit_sources_per_mode,
    primary_source_child as _primary_source_child,
    sources_state_key as _sources_state_key,
    voxelize_brickit_sources as _voxelize_brickit_sources,
)


BRICKIT_DEFAULT_RGB = (180, 180, 180)
PRUNE_AUTO_DISABLE_MIX_THRESHOLD = 0.55


def _get_active_library(self, op):
    """Return a brick.BrickLibrary filtered to enabled toggles.
    """
    from brick.library import BrickLibrary, BrickType, DEFAULT_LIBRARY

    # Keep legacy bool toggles in sync with native custom GUI bitmask.
    _apply_library_mask_to_toggles(op, _read_library_mask(op))

    enabled = []
    by_name = {b.name: b for b in DEFAULT_LIBRARY}
    toggled_names = set(BRICK_TOGGLE_NAMES)
    selected_toggle_names = set()
    try:
        enable_plates = bool(op[BRICKIFYASSEMBLY_ENABLE_PLATES])
    except Exception:
        enable_plates = False

    for i, name in enumerate(BRICK_TOGGLE_NAMES):
        try:
            on = bool(op[_toggle_id(i)])
        except Exception:
            on = True
        if on and name in by_name:
            selected_toggle_names.add(name)
            enabled.append(by_name[name])

    # If everything is off, intentionally return an empty library so users
    # can build selections tile-by-tile from a blank slate.
    if not selected_toggle_names:
        return BrickLibrary([])

    selected_brick_footprints = {
        (by_name[name].width, by_name[name].depth)
        for name in selected_toggle_names
        if name in by_name
    }

    if enable_plates:
        for name in PLATE_LIBRARY_NAMES:
            bt = by_name.get(name)
            if bt is None:
                continue
            # Plate support should follow the selected brick footprints.
            # Previously this added every plate footprint, which then
            # caused the synthetic-height expansion below to recreate most
            # of the full brick library even when one thumbnail was active.
            if (
                (bt.width, bt.depth) in selected_brick_footprints
                or (bt.depth, bt.width) in selected_brick_footprints
            ):
                enabled.append(bt)

    # Add non-toggle variants (extra heights) only for footprints that are
    # currently selected by toggle controls.
    selected_footprints = {
        (b.width, b.depth) for b in enabled
    }
    for b in DEFAULT_LIBRARY:
        if b.name in toggled_names:
            # Canonical toggle-controlled members are already handled above.
            continue
        if b.name in PLATE_LIBRARY_NAMES:
            # Plate entries are handled above for selected footprints.
            continue
        if (b.width, b.depth) in selected_footprints:
            enabled.append(b)

    # Defensive expansion: guarantee meaningful max-height options 1..6
    # per enabled footprint even if a stale/default library only carries
    # plate (h=1) and brick (h=3) entries in this C4D session.
    by_key = {(b.width, b.depth, b.height): b for b in enabled}
    footprints = {(b.width, b.depth) for b in enabled}
    # Height-1 source voxels still need a legal coverage candidate when the
    # user disables official plates. Keep those as synthetic brick_h1_* parts;
    # the plate toggle only controls plate library entries and smooth caps.
    allowed_heights = (1, 2, 3, 4, 5, 6)
    for w, d in footprints:
        for h in allowed_heights:
            key = (w, d, h)
            if key in by_key:
                continue
            bt = BrickType(
                "brick_h{0}_{1}x{2}".format(h, w, d),
                w,
                d,
                h,
                "custom_h{0}_{1}x{2}".format(h, w, d),
            )
            enabled.append(bt)
            by_key[key] = bt
    return BrickLibrary(enabled)


def _params_include_debug_info(params):
    """True when the fit pipeline should populate the debug-only info
    arrays (occupancy_cells, shell_depth, etc.) the debug viz modes need.
    Mirrored in `_make_fit_key` so toggling a viz mode that turns this
    flag on busts the fit cache and forces a fresh fit with debug data.
    """
    if params.get("visualization_mode") in (
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_DEPTH,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG,
    ):
        return True
    if (
        str(params.get("voxel_mode", "")).lower() == "shell"
        and bool(params.get("surface_only_plates", False))
    ):
        return True
    return False


def _make_fit_key(self, op, params):
    return (
        _sources_state_key(op),
        params["studs_across"],
        params["use_manual_stud_size"],
        params["stud_size"],
        params["voxel_backend"],
        params["voxel_mode"],
        params["shell_thickness"],
        params["detail_mode"],
        params["max_brick_height"],
        params["randomize_heights"],
        params["height_mix_seed"],
        params["height_mix_amount"],
        params["merge_plates"],
        params["prune"],
        params["relaxed_boundary_fit"],
        params["cleanup_protrusions"],
        params["preserve_silhouette"],
        params["preserve_tiny_gaps"],
        params["enable_plates"],
        params["lib_mask"],
        params.get("mirror_x", False),
        # Bust on debug-info toggle so switching to Shell Wireframe (etc.)
        # forces a fresh fit that populates the debug arrays the viz needs.
        _params_include_debug_info(params),
    )

def _make_voxel_key(self, op, params, stud_size, plate_size):
    return (
        _sources_state_key(op),
        params["voxel_backend"],
        params["studs_across"],
        params["use_manual_stud_size"],
        round(float(stud_size), 6),
        round(float(plate_size), 6),
        params["voxel_mode"],
        params["shell_thickness"],
    )


def _get_cached_source_arrays(self, op, doc, force_csto=False):
    """Bake the Union-merged source mesh and return fitting arrays.

    Multi-source: this returns geometry for the **Union bucket only**
    (subtract/intersect children carve the voxel grid in
    voxelize_brickit_sources but never contribute to fitting verts/faces
    — they have no "positive" volume to fit bricks into). The frame_inv
    and bind reference are taken from the first Union child so the
    source-axis-local frame stays stable across rebuilds.
    """
    source_key = _sources_state_key(op)
    if (
        not force_csto
        and self._source_cache_key == source_key
        and self._source_cache_data is not None
    ):
        return self._source_cache_data

    # Re-entrancy guard. When the deforming source is a child of BrickIt,
    # CSTO triggers C4D's document evaluator, which can re-enter BrickIt's
    # GVO → _refit_if_needed → _get_cached_source_arrays. Without a guard
    # this loops until C4D hard-freezes (no status output, force-quit only).
    # On re-entry, return the most recent source data instead of recursing;
    # callers tolerate stale data on this single tick and the next outer
    # GVO will refresh it.
    if getattr(self, "_csto_in_progress", False):
        return self._source_cache_data

    primary = _primary_source_child(op)
    if primary is None:
        self._source_cache_key = None
        self._source_cache_data = None
        return None

    log_first_eval = not getattr(self, "_first_eval_logged", False)
    t_bake0 = time.perf_counter() if log_first_eval else 0.0
    baked = None
    source_metadata = None
    # When source-deformation binding is active, force CSTO so the fit-time
    # source bake sees the same current-frame deformed mesh that the
    # per-frame eval reads. Without this, the GetDeformCache/GetCache fall-
    # back chain may return rest-pose for cloth-driven sources, so clicking
    # "Re-bind to Current Frame" would always fit to rest pose regardless of
    # the document time.
    if force_csto:
        # Bind-to-source-deformation traces the primary Union child. We
        # used to call `SendModelingCommand(MCOMMAND_CURRENTSTATETOOBJECT,
        # doc=doc)` directly here to force the full tag chain (cloth/
        # dynamics). That path turned out to be broken in two ways when
        # the source is a child of BrickIt:
        #   1) CSTO with `doc=doc` re-enters the document evaluator while
        #      BrickIt is mid-evaluation, causing a hard freeze.
        #   2) The CSTO clone's GetMg() does NOT match `primary.GetMg()`,
        #      so the standard `frame_inv = ~primary.GetMg()` math puts
        #      verts in the wrong frame — the assembly renders much
        #      smaller and offset from the source.
        # Use the standard cache-roots path instead. For cloth/dynamics
        # sources whose deformation doesn't surface through GetCache(),
        # this falls back to CSTO via the helper but with proper handling
        # of the matrix and child polygons. The user can Re-bind at the
        # bind-reference frame (typically frame 0 = rest pose) and that
        # is the canonical bind workflow.
        baked, source_metadata = _baked_polygon_object_with_metadata(primary, doc)
    else:
        per_mode = _bake_brickit_sources_per_mode(op, doc)
        union_entry = per_mode.get(_SOURCE_MODE_UNION)
        if union_entry is not None:
            baked, source_metadata = union_entry
    if log_first_eval:
        breakdown = getattr(self, "_first_eval_stage_breakdown", None) or {}
        breakdown["source_bake"] = (
            float(breakdown.get("source_bake", 0.0))
            + (time.perf_counter() - t_bake0)
        )
        self._first_eval_stage_breakdown = breakdown
    if baked is None or baked.GetPointCount() == 0:
        self._source_cache_key = None
        self._source_cache_data = None
        return None

    try:
        frame_inv = ~primary.GetMg()
    except Exception:
        frame_inv = None
    verts, faces = _polygon_object_to_arrays(baked, frame_inv=frame_inv)
    if len(faces) == 0:
        self._source_cache_key = None
        self._source_cache_data = None
        return None
    source_islands = _source_polygon_islands(
        baked,
        source_metadata=source_metadata,
        frame_inv=frame_inv,
    )
    tri_geom = _compute_triangle_geometry(verts, faces)

    self._source_cache_key = source_key
    self._source_cache_data = (baked, verts, faces, frame_inv, source_islands, tri_geom)
    return self._source_cache_data


def _compute_triangle_geometry(verts, faces):
    """Return per-triangle centroid, normal, and area arrays for binding.

    Computed alongside `_polygon_object_to_arrays` so the bind step can
    reuse the same source-axis-local frame the fitter sees. All output
    arrays are aligned with `faces[i]`.
    """
    try:
        import numpy as np
    except Exception:
        return None
    try:
        v = np.asarray(verts, dtype=np.float64)
        f = np.asarray(faces, dtype=np.int64)
        if f.size == 0:
            return None
        v0 = v[f[:, 0]]
        v1 = v[f[:, 1]]
        v2 = v[f[:, 2]]
        centroids = (v0 + v1 + v2) / 3.0
        cross = np.cross(v1 - v0, v2 - v0)
        areas2 = np.linalg.norm(cross, axis=1)
        areas = areas2 * 0.5
        # Avoid division by zero for degenerate triangles; bind-time the
        # closest-point step will reject these via large residuals.
        safe = np.where(areas2 > 1e-20, areas2, 1.0).reshape(-1, 1)
        normals = cross / safe
        return {
            "centroids": centroids,
            "normals": normals,
            "areas": areas,
        }
    except Exception:
        return None


def _refit_if_needed(self, op, doc, params=None):
    from brick.pipeline import brick_mesh, auto_stud_size
    from brick.voxelize import PLATE_RATIO

    source_obj = _primary_source_child(op)
    if source_obj is None:
        self._fit_cache_key = None
        self._fit_placements = None
        self._fit_info = None
        self._voxel_cache_key = None
        self._voxel_cache_voxels = None
        self._preview_voxel_cache_key = None
        self._preview_voxel_cache_voxels = None
        self._source_cache_key = None
        self._source_cache_data = None
        return False

    if params is None:
        params = self._resolve_params(op, source_obj)
    fit_key = self._make_fit_key(op, params)
    if self._fit_cache_key == fit_key and self._fit_placements is not None:
        return True

    active_library = self._get_active_library(op)
    try:
        has_bricks = bool(getattr(active_library, "bricks", []))
    except Exception:
        has_bricks = True
    if not has_bricks:
        self._fit_cache_key = fit_key
        self._fit_placements = []
        self._fit_info = {"note": "No brick types selected."}
        return True

    force_csto_bake = bool(params.get("bind_to_source_deformation"))
    source_data = self._get_cached_source_arrays(op, doc, force_csto=force_csto_bake)
    if source_data is None:
        self._fit_cache_key = None
        self._fit_placements = None
        self._voxel_cache_key = None
        self._voxel_cache_voxels = None
        self._preview_voxel_cache_key = None
        self._preview_voxel_cache_voxels = None
        return False
    if len(source_data) == 6:
        baked, verts, faces, frame_inv, source_islands, _tri_geom = source_data
    elif len(source_data) == 5:
        baked, verts, faces, frame_inv, source_islands = source_data
    elif len(source_data) == 4:
        baked, verts, faces, frame_inv = source_data
        source_islands = None
    else:
        baked, verts, faces = source_data
        frame_inv = None
        source_islands = None

    precomputed_voxels = None
    call_stud_size = params["stud_size"]
    if params.get("voxel_backend") == "c4d_volume":
        resolved_stud_size = call_stud_size
        if resolved_stud_size is None:
            resolved_stud_size = auto_stud_size(verts, params["studs_across"])
        resolved_plate_size = resolved_stud_size * PLATE_RATIO
        voxel_key = self._make_voxel_key(
            op,
            params,
            resolved_stud_size,
            resolved_plate_size,
        )
        try:
            if bool(params.get("interactive_preview", False)):
                cache_key = self._preview_voxel_cache_key
                cache_voxels = self._preview_voxel_cache_voxels
            else:
                cache_key = self._voxel_cache_key
                cache_voxels = self._voxel_cache_voxels
            if (
                cache_key == voxel_key
                and cache_voxels is not None
            ):
                occupancy, colors, origin, backend_info = cache_voxels
                backend_info = dict(backend_info or {})
                original_volume_s = float(
                    backend_info.get("voxel_backend_volume_seconds", 0.0) or 0.0
                )
                original_sample_s = float(
                    backend_info.get("voxel_backend_sample_seconds", 0.0) or 0.0
                )
                backend_info["voxel_backend_cache_hit"] = True
                backend_info["voxel_backend_cached_volume_seconds"] = original_volume_s
                backend_info["voxel_backend_cached_sample_seconds"] = original_sample_s
                backend_info["voxel_backend_volume_seconds"] = 0.0
                backend_info["voxel_backend_sample_seconds"] = 0.0
                backend_info["voxel_backend_note"] = (
                    str(backend_info.get("voxel_backend_note", ""))
                    + (
                        " Reused cached sampled voxels; original volume={0:.2f}s, "
                        "sample={1:.2f}s."
                    ).format(original_volume_s, original_sample_s)
                ).strip()
                precomputed_voxels = (occupancy, colors, origin, backend_info)
            else:
                _log_first_eval = not getattr(self, "_first_eval_logged", False)
                _t_vox0 = time.perf_counter() if _log_first_eval else 0.0
                precomputed_voxels = _voxelize_brickit_sources(
                    op,
                    doc,
                    params,
                    resolved_stud_size,
                    resolved_plate_size,
                    BRICKIT_DEFAULT_RGB,
                    frame_inv=frame_inv,
                )
                if _log_first_eval:
                    _bd = getattr(self, "_first_eval_stage_breakdown", None) or {}
                    _bd["voxelize"] = (
                        float(_bd.get("voxelize", 0.0))
                        + (time.perf_counter() - _t_vox0)
                    )
                    self._first_eval_stage_breakdown = _bd
                precomputed_voxels[3]["voxel_backend_cache_hit"] = False
                if bool(params.get("interactive_preview", False)):
                    self._preview_voxel_cache_key = voxel_key
                    self._preview_voxel_cache_voxels = precomputed_voxels
                else:
                    self._voxel_cache_key = voxel_key
                    self._voxel_cache_voxels = precomputed_voxels
            call_stud_size = resolved_stud_size
        except Exception as exc:
            try:
                _brick_log("[brick] C4D Volume backend fallback: {0}".format(exc))
            except Exception:
                pass
            if bool(params.get("interactive_preview", False)):
                self._preview_voxel_cache_key = None
                self._preview_voxel_cache_voxels = None
            else:
                self._voxel_cache_key = None
                self._voxel_cache_voxels = None
            precomputed_voxels = None

    # Internal backend with carving (Subtract/Intersect children present):
    # we need to precompute the composed grid so the boolean carving
    # reaches brick_mesh's fitter. Pure-Union with no carving falls
    # through unchanged so the existing per-vertex color path is preserved.
    if precomputed_voxels is None and params.get("voxel_backend") != "c4d_volume":
        from .brickit_sources import enumerate_brickit_sources as _enum_sources
        has_carving = any(
            mode != _SOURCE_MODE_UNION
            for _child, mode in _enum_sources(op)
        )
        if has_carving:
            resolved_stud_size = call_stud_size
            if resolved_stud_size is None:
                resolved_stud_size = auto_stud_size(verts, params["studs_across"])
            resolved_plate_size = resolved_stud_size * PLATE_RATIO
            try:
                precomputed_voxels = _voxelize_brickit_sources(
                    op,
                    doc,
                    params,
                    resolved_stud_size,
                    resolved_plate_size,
                    BRICKIT_DEFAULT_RGB,
                    frame_inv=frame_inv,
                )
                if precomputed_voxels is not None:
                    call_stud_size = resolved_stud_size
            except Exception as exc:
                try:
                    _brick_log(
                        "[brick] Internal backend carving fallback: {0}".format(exc)
                    )
                except Exception:
                    pass
                precomputed_voxels = None

    include_debug_info = _params_include_debug_info(params)

    _log_first_eval_bm = not getattr(self, "_first_eval_logged", False)
    _t_bm0 = time.perf_counter() if _log_first_eval_bm else 0.0

    def _status_progress(stage, pct):
        # C4D status bar lives on the bottom of the main UI. Setting bar
        # AND text gives the user both visual progress and a stage label.
        try:
            c4d.StatusSetText("BrickIt: {0}...".format(stage))
            c4d.StatusSetBar(int(max(0, min(100, pct))))
        except Exception:
            pass

    try:
        _status_progress("starting", 1)
        placements, info = brick_mesh(
            verts, faces,
            default_color=BRICKIT_DEFAULT_RGB,
            studs_across=params["studs_across"],
            stud_size=call_stud_size,
            voxel_backend=params["voxel_backend"],
            voxel_mode=params["voxel_mode"],
            shell_thickness=params["shell_thickness"],
            detail_mode=params["detail_mode"],
            max_brick_height=params["max_brick_height"],
            randomize_heights=params["randomize_heights"],
            height_mix_seed=params["height_mix_seed"],
            height_mix_amount=params["height_mix_amount"],
            merge_plates=params["merge_plates"],
            prune_connectivity=params["prune"],
            cleanup_protrusions=params["cleanup_protrusions"],
            preserve_silhouette=params["preserve_silhouette"],
            preserve_tiny_gaps=params["preserve_tiny_gaps"],
            surface_only_plates=False,
            relaxed_boundary_fit=params["relaxed_boundary_fit"],
            library=active_library,
            min_column_voxels=0,
            precomputed_voxels=precomputed_voxels,
            include_debug_info=include_debug_info,
            progress_callback=_status_progress,
            mirror_x=bool(params.get("mirror_x", False)),
        )
        _status_progress("building output", 90)
    finally:
        # Status is cleared by the caller after the MoGraph hierarchy
        # build finishes; see _clear_brick_status below. We intentionally
        # don't clear here because the caller has more work to do that
        # the user should see progress for.
        pass
    if _log_first_eval_bm:
        _bd = getattr(self, "_first_eval_stage_breakdown", None) or {}
        _bd["brick_mesh"] = (
            float(_bd.get("brick_mesh", 0.0))
            + (time.perf_counter() - _t_bm0)
        )
        _bd["mesh_verts"] = int(len(verts))
        _bd["mesh_faces"] = int(len(faces))
        self._first_eval_stage_breakdown = _bd
    try:
        _brick_log(
            "[brick] Fit completed: placements={0} grid_dims={1} stud_size={2} "
            "studs_across={3} lib_mask={4} bind={5} voxel_mode={6} backend={7} "
            "voxel_cache_hit={8}".format(
                len(placements) if placements is not None else 0,
                info.get("grid_dims"),
                info.get("stud_size"),
                params.get("studs_across"),
                params.get("lib_mask"),
                bool(params.get("bind_to_source_deformation")),
                params.get("voxel_mode"),
                params.get("voxel_backend"),
                bool((info.get("voxel_backend_info") or {}).get("voxel_backend_cache_hit"))
                if info.get("voxel_backend_info") is not None
                else "?",
            )
        )
    except Exception:
        pass
    info["prune_auto_disabled"] = bool(params.get("prune_auto_disabled"))
    info["prune_auto_reason"] = str(params.get("prune_auto_reason") or "")
    info["prune_user"] = bool(params.get("prune_user"))
    info["height_mix_amount_ui"] = float(params.get("height_mix_amount_ui", 0.0))
    info["source_island_groups"] = _placement_grouping_for_islands(
        placements,
        source_islands,
        info.get("origin"),
        info.get("stud_size", 8.0),
        info.get("plate_size", 3.2),
    )
    try:
        final_buildability = info.get("final_buildability") or {}
        physical_repair = info.get("physical_repair") or {}
        coverage = info.get("coverage") or {}
        repair_summary = info.get("buildability_repair") or {}
        _brick_log(
            "[brick] Physically Accurate: ui={0}, effective={1}, dropped={2}, "
            "components_before={3}, components_after={4}, coverage={5:.3f}, "
            "uncovered={6}, buildable={7}, ungrounded={8}, repair={9}, "
            "repair_rounds={10}, rotated={11}, shifted={12}, "
            "downsized={13}, dropped_unrepairable={14}, "
            "fill_added={15}, fill_cells={16}, fill_needed={17}, "
            "fill_skip_no_support={18}, fill_skip_outside_sil={19}, "
            "fill_skip_no_candidate={20}, fill_skip_collision={21}, "
            "fill_skip_outside_grid={22}, library_heights={23}, "
            "library_has_1x1x1={24}, library_n_orientations={25}, "
            "anchors_planted={26}".format(
                bool(params.get("prune_user")),
                bool(info.get("prune_connectivity_effective", False)),
                int(info.get("n_dropped", 0) or 0),
                int((info.get("connectivity") or {}).get("n_components", 0) or 0),
                int((info.get("final_connectivity") or {}).get("n_components", 0) or 0),
                float(coverage.get("coverage_ratio", 1.0) or 0.0),
                int(coverage.get("uncovered", 0) or 0),
                bool(final_buildability.get("buildable", False)),
                int(final_buildability.get("n_ungrounded", 0) or 0),
                str(physical_repair.get("status", "")),
                int(repair_summary.get("rounds", 0) or 0),
                int(repair_summary.get("repaired_rotated", 0) or 0),
                int(repair_summary.get("repaired_shifted", 0) or 0),
                int(repair_summary.get("repaired_downsized", 0) or 0),
                int(repair_summary.get("dropped_unrepairable", 0) or 0),
                int(repair_summary.get("fill_added_bricks", 0) or 0),
                int(repair_summary.get("fill_cells_filled", 0) or 0),
                int(repair_summary.get("fill_cells_needed", 0) or 0),
                int(repair_summary.get("fill_skipped_no_support", 0) or 0),
                int(repair_summary.get("fill_skipped_outside_silhouette", 0) or 0),
                int(repair_summary.get("fill_skipped_no_candidate", 0) or 0),
                int(repair_summary.get("fill_skipped_collision", 0) or 0),
                int(repair_summary.get("fill_skipped_outside_grid", 0) or 0),
                list(repair_summary.get("fill_library_heights", []) or []),
                bool(repair_summary.get("fill_library_has_1x1x1", False)),
                int(repair_summary.get("fill_library_n_orientations", 0) or 0),
                int(repair_summary.get("anchors_planted", 0) or 0),
            )
        )
        try:
            fail_y_ns = dict(repair_summary.get("fail_y_no_support") or {})
            fail_y_nc = dict(repair_summary.get("fail_y_no_candidate") or {})
            fail_y_co = dict(repair_summary.get("fail_y_collision") or {})
            fail_y_ps = dict(repair_summary.get("fail_y_partial_silhouette") or {})
            fail_y_og = dict(repair_summary.get("fail_y_outside_grid") or {})
            fail_y_oh = dict(repair_summary.get("overhang_by_y") or {})
            if (
                fail_y_ns or fail_y_nc or fail_y_co
                or fail_y_ps or fail_y_og or fail_y_oh
            ):
                _brick_log(
                    "[brick] Physically Accurate fail histogram: "
                    "no_support_by_y={0}  no_candidate_by_y={1}  "
                    "collision_by_y={2}  partial_sil_by_y={3}  "
                    "outside_grid_by_y={4}  overhang_by_y={5}".format(
                        sorted(fail_y_ns.items()),
                        sorted(fail_y_nc.items()),
                        sorted(fail_y_co.items()),
                        sorted(fail_y_ps.items()),
                        sorted(fail_y_og.items()),
                        sorted(fail_y_oh.items()),
                    )
                )
        except Exception:
            pass
    except Exception:
        pass
    if params.get("voxel_backend") == "c4d_volume":
        try:
            occ_cells = info.get("occupancy_cells")
            occ_count = (
                len(occ_cells)
                if occ_cells
                else int(info.get("voxel_backend_raw_occupied", 0) or 0)
            )
            _brick_log(
                "[brick] Voxel backend: requested={0}, used={1}, "
                "fallback={2}, grid={3}, occupied={4}, raw={5}, "
                "threshold={6}, volume_s={7}, sample_s={8}, samples={9}, "
                "cache={10}, note={11}".format(
                    info.get("voxel_backend_requested", "unknown"),
                    info.get("voxel_backend", "unknown"),
                    bool(info.get("voxel_backend_fallback")),
                    info.get("grid_dims", "?"),
                    occ_count,
                    info.get("voxel_backend_raw_occupied", "?"),
                    info.get("voxel_backend_sdf_threshold", "?"),
                    info.get("voxel_backend_volume_seconds", "?"),
                    info.get("voxel_backend_sample_seconds", "?"),
                    info.get("voxel_backend_sample_count", "?"),
                    bool(info.get("voxel_backend_cache_hit", False)),
                    info.get("voxel_backend_note", ""),
                )
            )
        except Exception:
            pass
    try:
        timings = dict(info.get("timings") or {})
        if timings:
            _brick_log(
                "[brick] Pipeline timings: total={0:.3f}s, fit={1:.3f}s, "
                "detail={2:.3f}s, merge_v={3:.3f}s, merge_h={4:.3f}s, "
                "connect={5:.3f}s, prune={6:.3f}s, info={7:.3f}s, "
                "shell_depth={8:.3f}s, void={9:.3f}s, occ_list={10:.3f}s".format(
                    float(timings.get("pipeline_total_seconds", 0.0)),
                    float(timings.get("fit_seconds", 0.0)),
                    float(timings.get("detail_mask_seconds", 0.0)),
                    float(timings.get("merge_vertical_seconds", 0.0)),
                    float(timings.get("merge_horizontal_seconds", 0.0)),
                    float(timings.get("connectivity_seconds", 0.0)),
                    float(timings.get("placement_prune_seconds", 0.0)),
                    float(timings.get("info_payload_seconds", 0.0)),
                    float(timings.get("placement_shell_depths_seconds", 0.0)),
                    float(timings.get("interior_void_seconds", 0.0)),
                    float(timings.get("occupancy_cells_seconds", 0.0)),
                )
            )
    except Exception:
        pass
    if params.get("prune_auto_disabled"):
        warn_key = (
            source_obj.GetGUID(),
            bool(params.get("prune_user")),
            bool(params.get("randomize_heights")),
            round(float(params.get("height_mix_amount_ui", 0.0)), 3),
            str(params.get("prune_auto_reason") or ""),
        )
        if warn_key != self._last_prune_warning_key:
            try:
                _brick_log(
                    "[brick] Make Physically Accurate auto-disabled ({0}). "
                    "Reason: {1}. Set Height Mix below {2:.2f} or disable "
                    "Height Mix to re-enable it.".format(
                        "ON" if bool(params.get("prune_user")) else "OFF",
                        params.get("prune_auto_reason") or "n/a",
                        PRUNE_AUTO_DISABLE_MIX_THRESHOLD,
                    )
                )
            except Exception:
                pass
            self._last_prune_warning_key = warn_key
    else:
        self._last_prune_warning_key = None
    self._fit_cache_key = fit_key
    self._fit_placements = placements
    self._fit_info = info
    return True

