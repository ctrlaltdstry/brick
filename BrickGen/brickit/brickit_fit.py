"""BrickIt library selection and pipeline refit helpers."""
import os
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


def _esc_pressed():
    """True if the user pressed ESC to cancel the long operation.

    Uses C4D's standard escape-test thread (GeGetEscTestThread().TestBreak()),
    the canonical 'did the user abort this long op' check — it works during a
    blocking main-thread loop regardless of which window has focus. Falls back
    to polling the keyboard directly.
    """
    try:
        esc = c4d.threading.GeGetEscTestThread()
        if esc is not None and esc.TestBreak():
            return True
    except Exception:
        pass
    try:
        bc = c4d.BaseContainer()
        if c4d.gui.GetInputState(c4d.BFM_INPUT_KEYBOARD, c4d.KEY_ESC, bc):
            return bool(bc.GetInt32(c4d.BFM_INPUT_VALUE))
    except Exception:
        pass
    return False


def _read_cache_tag_blob(op):
    """Return the per-frame cache blob from the object's enabled Cubify Cache
    tag, or "" if there's no tag, it's disabled, or it's empty. Plain data
    read — safe inside GetVirtualObjects."""
    try:
        tag = op.GetTag(ID_CUBIFY_CACHE_TAG)
        if tag is None:
            return ""
        if not tag[CUBIFY_CACHE_ENABLED]:
            return ""
        return tag[CUBIFY_CACHE_BLOB] or ""
    except Exception:
        return ""


def _current_doc_frame(op, doc):
    """Current document frame as an int, or 0 if unavailable."""
    d = doc
    if d is None:
        try:
            d = op.GetDocument()
        except Exception:
            d = None
    if d is None:
        return 0
    try:
        return int(d.GetTime().GetFrame(d.GetFps()))
    except Exception:
        return 0


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


def _make_per_frame_fit_key(self, op, params):
    """A FRAME-INDEPENDENT validity key for the per-frame fit cache.

    The normal _make_fit_key includes _sources_state_key(op), which folds in
    the source's per-frame dirty/matrix state — so it changes EVERY frame for
    a deforming source. That's correct for the live single-fit cache, but it
    must NOT gate the per-frame cache: there the validity depends only on the
    fit PARAMETERS (which bricks, resolution, etc.) plus the source identity,
    not on which frame's deformation we're on. Otherwise the key never matches
    on a later frame / after reload and the cache is ignored.
    """
    try:
        src = _primary_source_child(op)
        src_id = src.GetGUID() if src is not None else None
    except Exception:
        src_id = None
    return (
        src_id,
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

    # Clear any stale precompute from a prior frame; only a cache hit below
    # repopulates it. (A live fit must NOT reuse another frame's carriers.)
    self._cache_precomp_for_current_frame = None

    # Per-frame fit cache, driven by an auto-created "Cubify Cache" tag. When
    # the object has an enabled cache tag with baked data, play this frame's
    # pre-computed layout instead of re-fitting live. Tag presence+Enabled is
    # the on/off — no separate toggle. Reading the tag's param is a plain data
    # fetch (no Execute / no re-entrancy).
    cache_blob = _read_cache_tag_blob(op)
    if cache_blob:
        frame = _current_doc_frame(op, doc)
        cache = getattr(self, "_frame_fit_cache", None) or {}
        # Re-deserialize only when the tag's blob actually changed (e.g. just
        # opened the scene, or the user re-baked) — keyed by the blob's hash.
        blob_id = hash(cache_blob)
        if not cache or getattr(self, "_frame_fit_blob_id", None) != blob_id:
            try:
                from .brickit_frame_cache import (
                    deserialize as _deserialize_frame_cache,
                )
                cache = _deserialize_frame_cache(cache_blob)
                self._frame_fit_cache = cache
                self._frame_fit_blob_id = blob_id
                # Union of every frame's template keys. Variable brick height
                # makes a brick's height (part of the template key) change
                # frame-to-frame, so new template variants appear on later
                # frames. Pre-creating one carrier per tkey across ALL frames
                # avoids creating carriers mid-playback (which left their
                # parent's cached draw stale -> frozen bricks).
                all_tkeys = set()
                tkey_max = {}
                for _entry in cache.values():
                    pc = _entry[2] if len(_entry) > 2 else None
                    if pc:
                        all_tkeys.update(pc.keys())
                        # Per-template MAX instance count across all frames.
                        # Playback pads each carrier's matrix list to this max
                        # (with parked, off-screen matrices) so the list length
                        # NEVER shrinks — which is what leaves stale "frozen"
                        # ghost bricks in C4D's multi-instance draw cache.
                        for _tk, _pair in pc.items():
                            _n = len(_pair[0])
                            if _n > tkey_max.get(_tk, 0):
                                tkey_max[_tk] = _n
                self._cache_all_tkeys = all_tkeys
                self._cache_tkey_max = tkey_max
                # Force the batched carriers to be rebuilt for the new cache.
                self._cache_batched_carriers_dirty = True
                _brick_log(
                    "[brick] Cubify Cache: loaded {0} frames, {1} template "
                    "variants from tag.".format(len(cache), len(all_tkeys))
                )
            except Exception as exc:
                cache = {}
                _brick_log("[brick] Cubify Cache: load failed: {0}".format(exc))
        if frame in cache:
            entry = cache[frame]
            placements = entry[0]
            info = entry[1] if len(entry) > 1 else None
            # Precomputed batched carrier data for THIS frame (v3 cache) — the
            # playback build pushes these arrays onto reused carriers instead
            # of recomputing ~2600 matrices. None for older caches.
            self._cache_precomp_for_current_frame = (
                entry[2] if len(entry) > 2 else None
            )
            self._fit_cache_key = fit_key
            self._fit_placements = placements
            self._fit_info = info
            return True
        # Frame not baked (e.g. outside the baked range): fall through to a
        # live fit so the viewport still shows something.

    if self._fit_cache_key == fit_key and self._fit_placements is not None:
        return True

    # Per-refit profiler. Unlike the first-eval breakdown (which logs
    # once), this fires on EVERY refit when BRICKIT_PROFILE_FIT is set,
    # so we can watch per-stage cost while dragging a multi-source /
    # boolean scene. Stage times are wall-clock seconds.
    _prof_on = os.environ.get("BRICKIT_PROFILE_FIT", "").strip().lower() not in (
        "", "0", "false", "no"
    )
    _prof = {} if _prof_on else None
    _prof_t0 = time.perf_counter() if _prof_on else 0.0

    def _prof_mark(stage, t_start):
        if _prof is not None:
            _prof[stage] = _prof.get(stage, 0.0) + (time.perf_counter() - t_start)

    _t_src0 = time.perf_counter() if _prof_on else 0.0

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
    _prof_mark("source_bake", _t_src0)
    if _prof is not None:
        try:
            from .brickit_sources import enumerate_brickit_sources as _enum_src
            _prof["n_sources"] = len(list(_enum_src(op)))
        except Exception:
            _prof["n_sources"] = -1

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
                if _prof is not None:
                    _prof["voxel_cache_hit"] = 1
            else:
                _log_first_eval = not getattr(self, "_first_eval_logged", False)
                _t_vox0 = time.perf_counter() if _log_first_eval else 0.0
                _t_voxp = time.perf_counter() if _prof_on else 0.0
                precomputed_voxels = _voxelize_brickit_sources(
                    op,
                    doc,
                    params,
                    resolved_stud_size,
                    resolved_plate_size,
                    BRICKIT_DEFAULT_RGB,
                    frame_inv=frame_inv,
                )
                _prof_mark("voxelize", _t_voxp)
                if _prof is not None:
                    _prof["voxel_cache_hit"] = 0
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
                _t_voxp = time.perf_counter() if _prof_on else 0.0
                precomputed_voxels = _voxelize_brickit_sources(
                    op,
                    doc,
                    params,
                    resolved_stud_size,
                    resolved_plate_size,
                    BRICKIT_DEFAULT_RGB,
                    frame_inv=frame_inv,
                )
                _prof_mark("voxelize_carve", _t_voxp)
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
            c4d.StatusSetText("Cubify: {0}...".format(stage))
            c4d.StatusSetBar(int(max(0, min(100, pct))))
        except Exception:
            pass

    _t_bmp = time.perf_counter() if _prof_on else 0.0
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
        _prof_mark("brick_mesh", _t_bmp)
    if _log_first_eval_bm:
        _bd = getattr(self, "_first_eval_stage_breakdown", None) or {}
        _bd["brick_mesh"] = (
            float(_bd.get("brick_mesh", 0.0))
            + (time.perf_counter() - _t_bm0)
        )
        _bd["mesh_verts"] = int(len(verts))
        _bd["mesh_faces"] = int(len(faces))
        self._first_eval_stage_breakdown = _bd
    if _prof is not None:
        _prof["total"] = time.perf_counter() - _prof_t0
        try:
            vox_s = float(_prof.get("voxelize", 0.0)) + float(
                _prof.get("voxelize_carve", 0.0)
            )
            _brick_log(
                "[brick][PROFILE] refit total={0:.3f}s | source_bake={1:.3f} "
                "voxelize={2:.3f} brick_mesh={3:.3f} | n_sources={4} "
                "studs_across={5} backend={6} vox_cache_hit={7} "
                "preview={8} verts={9} placements={10}".format(
                    float(_prof.get("total", 0.0)),
                    float(_prof.get("source_bake", 0.0)),
                    vox_s,
                    float(_prof.get("brick_mesh", 0.0)),
                    int(_prof.get("n_sources", -1)),
                    params.get("studs_across"),
                    params.get("voxel_backend"),
                    _prof.get("voxel_cache_hit", "n/a"),
                    bool(params.get("interactive_preview", False)),
                    int(len(verts)),
                    len(placements) if placements is not None else 0,
                )
            )
        except Exception:
            pass
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


# Private BaseContainer id used to tag our object so we can find its copy in a
# document clone (GetGUID is NOT preserved across GetClone).
_BAKE_MARKER_ID = 1069994321


def _iter_objects(doc):
    stack = []
    o = doc.GetFirstObject()
    while o:
        stack.append(o)
        o = o.GetNext()
    while stack:
        o = stack.pop()
        yield o
        c = o.GetDown()
        while c:
            stack.append(c)
            c = c.GetNext()


def _find_op_by_marker_in_doc(doc, token):
    """Find the object whose private data container carries our bake token."""
    for o in _iter_objects(doc):
        try:
            if o.GetDataInstance().GetString(_BAKE_MARKER_ID) == token:
                return o
        except Exception:
            pass
    return None


class _BakeState(object):
    """State for a per-frame fit bake.

    The bake re-evaluates the scene at each frame to read the DEFORMED source.
    Doing that against the LIVE document re-enters our own generator's
    evaluation (gv_world) and crashes C4D. The standard, safe pattern is to
    bake on a CLONED document: SetTime + ExecutePasses on the clone never
    touches the live generator that's mid-evaluation. We read the deformed
    source from the clone, fit, and store results into the LIVE object's
    cache. The clone is killed in _bake_finish.
    """

    def __init__(self, live_op, live_doc, clone_doc, clone_op,
                 fps, start_frame, end_frame, fit_key):
        self.live_op = live_op
        self.live_doc = live_doc
        self.clone_doc = clone_doc
        self.clone_op = clone_op
        self.fps = fps
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.fit_key = fit_key
        self.frame = start_frame
        self.new_cache = {}
        self.baked = 0
        self.failed = 0
        self.t0 = time.perf_counter()

    @property
    def total(self):
        return max(1, self.end_frame - self.start_frame + 1)

    @property
    def done(self):
        return self.frame - self.start_frame

    @property
    def finished(self):
        return self.frame > self.end_frame


def _bake_begin(self, op):
    """Set up a cloned-document bake. Returns a _BakeState, or None."""
    live_doc = None
    try:
        live_doc = op.GetDocument()
    except Exception:
        live_doc = None
    if live_doc is None:
        _brick_log("[brick] Bake Fit Cache: no document.")
        return None
    source_obj = _primary_source_child(op)
    if source_obj is None:
        _brick_log("[brick] Bake Fit Cache: no source linked.")
        return None

    fps = live_doc.GetFps()
    start_frame = live_doc.GetMinTime().GetFrame(fps)
    end_frame = live_doc.GetMaxTime().GetFrame(fps)
    params = self._resolve_params(op, source_obj)
    # Frame-INDEPENDENT key so the cache validates on every frame + after
    # reload (the normal fit_key folds in per-frame source-deform state).
    fit_key = _make_per_frame_fit_key(self, op, params)

    # Clone the whole document and bake on the clone (the safe pattern that
    # avoids re-entering the live generator evaluation world). GetGUID is NOT
    # preserved across GetClone, so tag the live object with a unique token,
    # clone, locate the copy by that token, then clear the token everywhere.
    token = "cubit_bake_{0}_{1}".format(id(op), start_frame)
    clone_doc = None
    try:
        op.GetDataInstance().SetString(_BAKE_MARKER_ID, token)
        clone_doc = live_doc.GetClone(c4d.COPYFLAGS_DOCUMENT)
        clone_op = _find_op_by_marker_in_doc(clone_doc, token)
    except Exception as exc:
        _brick_log("[brick] Bake Fit Cache: clone failed: {0}".format(exc))
        clone_op = None
    finally:
        try:
            op.GetDataInstance().SetString(_BAKE_MARKER_ID, "")
        except Exception:
            pass

    if clone_op is None:
        if clone_doc is not None:
            try:
                c4d.documents.KillDocument(clone_doc)
            except Exception:
                pass
        _brick_log("[brick] Bake Fit Cache: could not locate self in clone.")
        return None
    try:
        # Clear the token on the clone copy too so it never persists.
        clone_op.GetDataInstance().SetString(_BAKE_MARKER_ID, "")
    except Exception:
        pass

    _brick_log(
        "[brick] Bake Fit Cache: frames {0}..{1} on a document clone "
        "(ESC or Cancel to stop)".format(start_frame, end_frame)
    )
    return _BakeState(op, live_doc, clone_doc, clone_op,
                      fps, start_frame, end_frame, fit_key)


def _bake_step(self, state):
    """Bake exactly ONE frame against the cloned document. False when done."""
    if state.finished:
        return False
    frame = state.frame
    clone = state.clone_doc
    clone_op = state.clone_op
    try:
        clone.SetTime(c4d.BaseTime(frame, state.fps))
        # Standard bake ExecutePasses on the clone. EXPORTONLY skips
        # editor-only work; positional args match the SDK bake examples.
        clone.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_EXPORTONLY)
    except Exception:
        pass

    # Force a fully fresh fit against THIS frame's deformed pose. We read the
    # deformed source from the CLONE op, and store the result on the LIVE
    # object (self). Drop all caches so the pipeline re-bakes + re-voxelizes.
    self._source_cache_key = None
    self._source_cache_data = None
    self._voxel_cache_key = None
    self._voxel_cache_voxels = None
    self._preview_voxel_cache_key = None
    self._preview_voxel_cache_voxels = None
    self._fit_cache_key = None
    self._fit_placements = None
    try:
        clone_source = _primary_source_child(clone_op)
        fparams = dict(self._resolve_params(clone_op, clone_source))
        fparams["per_frame_fit"] = False
        ok = self._refit_if_needed(clone_op, clone, fparams)
        if ok and self._fit_placements is not None:
            # Precompute the batched carrier data (matrices/colors/template
            # keys) now, so cache playback is a pure array-push with no
            # per-frame recomputation. Bind is off here (per_frame_fit=False
            # clone), so positions are pure — exactly what playback needs.
            precomp = None
            try:
                from .brickit_mograph_generator import (
                    precompute_carrier_buckets as _precompute,
                )
                precomp = _precompute(
                    self, clone_op, self._fit_placements,
                    self._fit_info, fparams,
                )
            except Exception as exc:
                _brick_log(
                    "[brick] Bake: precompute failed (frame {0}): {1}".format(
                        frame, exc
                    )
                )
            state.new_cache[int(frame)] = (
                self._fit_placements, self._fit_info, precomp
            )
            state.baked += 1
        else:
            state.failed += 1
    except Exception as exc:
        state.failed += 1
        _brick_log("[brick] Bake Fit Cache: frame {0} failed: {1}".format(
            frame, exc))

    state.frame += 1
    return not state.finished


def _bake_finish(self, state, cancelled=False):
    """Kill the clone, commit the (possibly partial) cache, persist it."""
    try:
        c4d.documents.KillDocument(state.clone_doc)
    except Exception:
        pass

    self._frame_fit_cache = state.new_cache
    self._frame_fit_cache_key = state.fit_key
    # Persist onto an auto-created "Cubify Cache" tag (the cache's home). The
    # tag saves with the scene and its presence+Enabled drives playback.
    try:
        from .brickit_frame_cache import serialize as _serialize_frame_cache
        blob = _serialize_frame_cache(state.new_cache)
        op = state.live_op
        tag = op.GetTag(ID_CUBIFY_CACHE_TAG) or op.MakeTag(ID_CUBIFY_CACHE_TAG)
        tag[CUBIFY_CACHE_BLOB] = blob
        tag[CUBIFY_CACHE_ENABLED] = True
        tag[CUBIFY_CACHE_INFO] = "{0} frames, {1}..{2}".format(
            state.baked, state.start_frame, state.end_frame
        )
        try:
            tag.SetName("Cubify Cache ({0}f)".format(state.baked))
            tag.SetDirty(c4d.DIRTYFLAGS_DATA)
        except Exception:
            pass
    except Exception as exc:
        _brick_log("[brick] Bake Fit Cache: persist failed: {0}".format(exc))

    self._fit_cache_key = None
    self._fit_placements = None
    self._hierarchy_cache_key = None
    _brick_log(
        "[brick] Bake Fit Cache: {0}. baked={1} failed={2} in {3:.1f}s".format(
            "cancelled" if cancelled else "done",
            state.baked, state.failed, time.perf_counter() - state.t0
        )
    )
    return state.baked > 0


def _bake_frame_fit_cache(self, op):
    """Entry point: open the Timer-driven progress dialog, which steps the
    clone-based bake one frame per tick. Because the bake runs on a CLONED
    document (never re-entering the live generator) and is driven by the
    dialog Timer (returning to C4D's event loop between frames), the native
    progress bar animates and Cancel / ESC stay responsive — a blocking
    main-thread loop cannot do either (C4D exposes no message pump)."""
    state = _bake_begin(self, op)
    if state is None:
        return False
    try:
        from . import brickit_bake_progress as _bake_progress
        return _bake_progress.run_bake(self, state)
    except Exception as exc:
        _brick_log(
            "[brick] Bake Fit Cache: dialog unavailable ({0}); "
            "blocking fallback.".format(exc)
        )
        cancelled = False
        while not state.finished:
            if _esc_pressed():
                cancelled = True
                break
            _bake_step(self, state)
        return _bake_finish(self, state, cancelled=cancelled)

