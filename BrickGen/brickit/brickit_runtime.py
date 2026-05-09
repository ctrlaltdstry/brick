"""BrickIt ObjectData runtime evaluation."""
import os
import time

import c4d

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from plugin_bootstrap import (
    brick_log as _brick_log,
    ensure_brick_on_path as _ensure_brick_on_path,
)


def _has_mograph_effectors_for_runtime(effectors):
    if effectors is None:
        return False
    try:
        return int(effectors.GetObjectCount()) > 0
    except Exception:
        pass
    return bool(effectors)


def _update_build_info_panel(op, info, placements):
    """Populate the read-only Build Info STRING fields on `op` from the
    pipeline `info` dict. Called after each successful rebuild.

    Failures are swallowed: this is purely cosmetic, and the pipeline
    must not be broken by a bad info dict or a missing UI field.
    """
    if op is None:
        return
    try:
        n_bricks = int(len(placements or []))
        # Distinct (brick_type, rotation) pairs in use.
        seen = set()
        for p in (placements or []):
            try:
                seen.add((p.brick.name, int(p.rotation_y)))
            except Exception:
                continue
        n_library_items = len(seen)

        coverage = (info or {}).get("coverage") or {}
        cov_ratio = float(coverage.get("coverage_ratio", 0.0) or 0.0)

        connectivity = (info or {}).get("final_connectivity") or {}
        n_components = int(connectivity.get("n_components", 0) or 0)

        grid_dims = (info or {}).get("grid_dims") or (0, 0, 0)
        try:
            gx, gy, gz = (int(d) for d in grid_dims)
        except Exception:
            gx = gy = gz = 0

        final_buildability = (info or {}).get("final_buildability") or {}
        is_buildable = bool(final_buildability.get("buildable", False))

        op[BRICKIFYASSEMBLY_INFO_BRICK_COUNT] = "{0:,}".format(n_bricks)
        op[BRICKIFYASSEMBLY_INFO_LIBRARY_ITEMS] = "{0}".format(n_library_items)
        op[BRICKIFYASSEMBLY_INFO_COVERAGE] = "{0:.1f}%".format(cov_ratio * 100.0)
        op[BRICKIFYASSEMBLY_INFO_COMPONENTS] = "{0}".format(n_components)
        op[BRICKIFYASSEMBLY_INFO_GRID_DIMS] = "{0} x {1} x {2}".format(gx, gy, gz)
        op[BRICKIFYASSEMBLY_INFO_BUILDABLE] = "Yes" if is_buildable else "No"
    except Exception:
        pass

    # Build animation: BUILD_STEP is the authoritative integer stepper.
    # Update its scrubable max + the read-only displays + auto-rescale
    # the step when the total brick count has changed across regenerate.
    try:
        n_bricks_total = max(0, int(len(placements or [])))
        try:
            prev_total = int(op[BRICKIFYASSEMBLY_BUILD_PREV_TOTAL] or 0)
        except Exception:
            prev_total = 0
        # Stepper is REAL — keep fractional values across rebuilds so
        # animation keyframes mid-brick aren't quantized.
        try:
            current_step = max(0.0, float(op[BRICKIFYASSEMBLY_BUILD_STEP] or 0.0))
        except Exception:
            current_step = 0.0
        # Rebuild rule for BUILD_STEP:
        #   - If step was at 100% (full build) before the rebuild, snap to
        #     the new 100% — user's mental model is "rebuild shows the
        #     full model."
        #   - If step was anywhere below 100% (user dragged it partway,
        #     OR a keyframed animation curve evaluated to a fraction),
        #     preserve the PROPORTION across the rebuild so the partial-
        #     build state survives the brick-count change.
        # The 100%-detection is computed against the previous-fit total
        # because that's what the user was looking at when they last
        # observed the slider's position.
        if prev_total == 0:
            # First-fit case snaps to 100%.
            current_step = float(n_bricks_total)
        elif current_step >= float(prev_total) - 1.0e-6:
            # Was at (or essentially at) 100% before — snap to new 100%.
            current_step = float(n_bricks_total)
        elif prev_total != n_bricks_total and prev_total > 0:
            # Was at a fraction — preserve the proportion across rebuild.
            ratio = current_step / float(prev_total)
            current_step = ratio * float(n_bricks_total)
        current_step = max(0.0, min(current_step, float(n_bricks_total)))
        # IMPORTANT: write PREV_TOTAL FIRST. The MSG_DESCRIPTION_POSTSETPARAMETER
        # handler for BUILD_STEP clamps `step` against PREV_TOTAL. If we
        # wrote BUILD_STEP first, that handler would see a STALE PREV_TOTAL
        # (from the previous fit) and clamp our just-written step down to
        # the previous fit's total — producing the "0.5 -> 0.4 leaves step
        # at 128/296" symptom. Write order matters.
        try:
            op[BRICKIFYASSEMBLY_BUILD_PREV_TOTAL] = n_bricks_total
        except Exception:
            pass
        try:
            op[BRICKIFYASSEMBLY_BUILD_STEP] = current_step
        except Exception:
            pass
        try:
            op[BRICKIFYASSEMBLY_BUILD_TOTAL_BRICKS] = "{0:,}".format(
                n_bricks_total
            )
        except Exception:
            pass
        try:
            pct = (
                100.0 * current_step / float(max(1, n_bricks_total))
            )
            op[BRICKIFYASSEMBLY_BUILD_PROGRESS_PCT] = "{0:.1f}%".format(pct)
        except Exception:
            pass
        # Re-load the description so the Build Step slider track picks up
        # the new MAX (total brick count) from GetDDescription. Without
        # this, the slider grip stays scaled to the previous total and
        # under-fills or overflows the track after a rebuild.
        try:
            op.SetDirty(c4d.DIRTYFLAGS_DESCRIPTION)
        except Exception:
            pass
    except Exception:
        pass


def _sweep_orphaned_auto_added(op):
    """Drop list entries flagged AUTO_ADDED whose object is no longer a
    direct child of the host BrickIt. Drag-dropped entries (AUTO_ADDED bit
    cleared) survive un-parenting — only auto-added rows track the parent
    relationship as a "live connection."

    Returns True iff the InExcludeData was rewritten so the caller can
    invalidate caches.
    """
    from .brickit_sources import (
        is_auto_added as _is_auto_added,
        BRICKIFYASSEMBLY_SOURCES as _BR_SOURCES,
    )

    try:
        data = op[_BR_SOURCES]
    except Exception:
        return False
    if data is None:
        return False
    doc = op.GetDocument()
    if doc is None:
        return False

    # Build a GUID set of the host's current direct children so we can test
    # "is this object still a child" without per-entry parent-walks.
    child_guids = set()
    ch = op.GetDown()
    while ch is not None:
        try:
            child_guids.add(int(ch.GetGUID()))
        except Exception:
            pass
        ch = ch.GetNext()

    try:
        count = int(data.GetObjectCount())
    except Exception:
        return False

    keepers = []  # (BaseObject, flags) for entries that survive the sweep
    dropped = False
    for i in range(count):
        try:
            obj = data.ObjectFromIndex(doc, i)
        except Exception:
            obj = None
        if obj is None:
            continue
        try:
            flags = int(data.GetFlags(i))
        except Exception:
            flags = 0
        if _is_auto_added(flags):
            try:
                guid = int(obj.GetGUID())
            except Exception:
                guid = None
            if guid is None or guid not in child_guids:
                # Auto-added entry whose object was un-parented from the
                # host — drop it so the visibility diff below restores it.
                dropped = True
                continue
        keepers.append((obj, flags))

    if not dropped:
        return False

    new_data = c4d.InExcludeData()
    for obj, flags in keepers:
        new_data.InsertObject(obj, int(flags))
    try:
        op[_BR_SOURCES] = new_data
    except Exception:
        return False
    return True


def _sync_source_visibility(self, op):
    """Hide source meshes that fed this BrickIt's bake; restore the rest.

    Runs every GVO (cheap — just walks the source list and toggles flags
    for objects whose state changed). Tracked via `self._auto_hidden_guids`
    so we only restore objects we hid ourselves — manual hides on other
    objects in the scene aren't disturbed.

    Volume Builder's convention: a mesh that's a source becomes "owned"
    by the generator and disappears from the viewport, since the bricked
    output represents it. Removing the mesh from the source list (or
    deleting it from the OM) auto-restores its default visibility.

    Auto-added entries (children that auto-appended) form a "live
    connection": un-parenting them from the host BrickIt drops the row
    here, which then triggers the restore. Drag-dropped entries survive
    un-parenting and stay as independent references.
    """
    from .brickit_sources import enumerate_brickit_sources

    if op is None:
        return
    doc = op.GetDocument()
    if doc is None:
        return

    # Phase 1: prune auto-added entries whose objects left the host's
    # subtree. This rewrites BRICKIFYASSEMBLY_SOURCES, so we have to do
    # it BEFORE enumerating sources for the visibility diff.
    if _sweep_orphaned_auto_added(op):
        # The pruned entries' objects are now eligible for restore in
        # Phase 2 because they no longer appear in enumerate_brickit_sources.
        try:
            self._fit_cache_key = None
            self._hierarchy_cache_key = None
            self._force_rebuild = True
        except Exception:
            pass

    # Phase 2: snapshot current sources by GUID so we can diff against
    # the previously-hidden set.
    pairs = enumerate_brickit_sources(op)
    current_by_guid = {}
    for child, _mode in pairs:
        if child is None:
            continue
        try:
            guid = int(child.GetGUID())
        except Exception:
            continue
        current_by_guid[guid] = child

    prev_set = getattr(self, "_auto_hidden_guids", None)
    if prev_set is None:
        prev_set = set()
        self._auto_hidden_guids = prev_set

    new_set = set(current_by_guid.keys())

    to_hide_guids = new_set - prev_set
    to_restore_guids = prev_set - new_set

    if not to_hide_guids and not to_restore_guids:
        return

    # Walk doc to resolve restore targets — they might no longer be in
    # `current_by_guid` because they were just removed from the source list.
    def _find_by_guid(guid):
        # Document scan — small docs are cheap; if this becomes a bottleneck
        # we can keep a doc-wide GUID -> BaseObject cache, but at typical
        # source counts (<20) and scene sizes (<1000 objects) it's fine.
        node = doc.GetFirstObject()
        stack = []
        while node is not None or stack:
            if node is not None:
                try:
                    if int(node.GetGUID()) == guid:
                        return node
                except Exception:
                    pass
                child = node.GetDown()
                nxt = node.GetNext()
                if nxt is not None:
                    stack.append(nxt)
                node = child
            else:
                node = stack.pop()
        return None

    try:
        doc.StartUndo()
        for guid in to_hide_guids:
            obj = current_by_guid.get(guid)
            if obj is None:
                continue
            try:
                doc.AddUndo(c4d.UNDOTYPE_BITS, obj)
                obj.SetEditorMode(c4d.MODE_OFF)
                obj.SetRenderMode(c4d.MODE_OFF)
            except Exception:
                pass
        for guid in to_restore_guids:
            obj = _find_by_guid(guid)
            if obj is None:
                continue
            try:
                doc.AddUndo(c4d.UNDOTYPE_BITS, obj)
                obj.SetEditorMode(c4d.MODE_UNDEF)
                obj.SetRenderMode(c4d.MODE_UNDEF)
            except Exception:
                pass
        doc.EndUndo()
    except Exception:
        pass

    self._auto_hidden_guids = new_set


def _maybe_rebind(self, params):
    """Run the source-deformation bind step when needed."""
    from .brickit_bind import bind_placements_to_source, make_bind_cache_key

    if not params.get("bind_to_source_deformation"):
        return
    bind_key = make_bind_cache_key(self, params)
    if (
        not getattr(self, "_bind_force_rebind", False)
        and self._bind_cache_key == bind_key
        and self._bind_records is not None
    ):
        return
    records = bind_placements_to_source(self, params)
    self._bind_records = records
    self._bind_cache_key = bind_key
    self._bind_force_rebind = False


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

    from .brickit_sources import (
        has_any_source as _has_any_source,
        primary_source_child as _primary_source_child,
        sources_state_key as _sources_state_key,
    )

    if not _has_any_source(op):
        # Even with no sources, run the visibility sync so any prior
        # auto-hidden objects (the user just emptied the list) get
        # restored to default visibility on the next eval.
        _sync_source_visibility(self, op)
        return None

    # Auto-hide source meshes (Volume Builder convention). Runs every GVO
    # so it stays in sync with whatever made the source list change —
    # drag-drop, OM reparent, list-delete, scene-delete, etc.
    _sync_source_visibility(self, op)

    # Live Update gate: when the user unchecks Live Update, skip the
    # full refit-and-rebuild on every viewport tick so they can drag
    # source meshes, tweak parameters, or scrub the timeline without
    # paying the cost. The cached output comes from C4D's generator
    # cache — no extra state to manage on our side.
    #
    # Single-source case: we update the cached root's local matrix to
    # follow the source's current transform, so the bricks rigid-
    # translate/rotate/scale with the source mesh as the user moves
    # it. The brick fit itself stays frozen (cheap), but the visible
    # output tracks the source's position. This matches the user's
    # mental model — "I moved the source, the existing bricks should
    # come with it."
    #
    # Multi-source case: bricks are a composite of all sources via
    # union/subtract/intersect, so moving one source would need a
    # full refit to reflect the new boolean result. We can't rigid-
    # follow a single source. The output stays frozen until the user
    # re-enables Live Update or clicks Rebuild.
    #
    # The user can force a full build by clicking Rebuild (which sets
    # self._force_rebuild = True before the next eval) or by re-
    # checking Live Update.
    try:
        live_update = bool(op[BRICKIFYASSEMBLY_AUTO_REBUILD])
    except Exception:
        live_update = True
    if not live_update and not self._force_rebuild:
        cached = op.GetCache(hh)
        if cached is not None:
            try:
                from .brickit_sources import enumerate_brickit_sources as _enum_sources
                pairs = _enum_sources(op)
            except Exception:
                pairs = []
            if len(pairs) == 1:
                single_source = pairs[0][0]
                if single_source is not None:
                    try:
                        from source_geometry import source_axis_local_matrix as _src_axis_local
                        cached.SetMl(_src_axis_local(op, single_source))
                    except Exception:
                        pass
            return cached
        # No cached output yet (first eval after toggling off Live Update
        # before anything was built) — fall through to a normal build so
        # the user sees something instead of an empty viewport.

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

    source_obj = _primary_source_child(op)
    params = self._resolve_params(op, source_obj)
    actual_res_key = self._resolution_key(params)
    # Startup responsiveness: first scene-open evaluation runs in proxy.
    if self._startup_draft_pending and not self._force_rebuild:
        params = dict(params)
        params["quality"] = BRICKIFYASSEMBLY_QUALITY_PROXY
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

    # Topology/template part of the hierarchy key: anything that changes the
    # fitted placement set, instance count, or template library.
    cap_subset_key = (
        round(float(params.get("top_surface_coverage", 1.0)), 5),
        bool(params.get("top_surface_random_order", False)),
        int(params.get("cap_style", 0)),
        int(params.get("cap_random_seed", 0)),
    )
    topology_hierarchy_key = (
        _sources_state_key(op),
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
        bool(params.get("logo_mix_flip", False)),
        round(float(params.get("logo_mix_amount", 0.0) or 0.0), 4),
        int(params.get("logo_mix_seed", 0) or 0),
        params["lib_mask"],
        cap_subset_key,
        bool(params.get("bind_to_source_deformation", False)),
        int(params.get("bind_orientation_mode", 0)),
    )
    bind_per_frame_key = None
    if params.get("bind_to_source_deformation"):
        src_dirty = 0
        try:
            src_dirty = int(
                source_obj.GetDirty(
                    c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_CACHE | c4d.DIRTYFLAGS_MATRIX
                )
            )
        except Exception:
            src_dirty = 0
        try:
            doc_for_frame = op.GetDocument()
            frame = (
                int(doc_for_frame.GetTime().GetFrame(doc_for_frame.GetFps()))
                if doc_for_frame is not None
                else 0
            )
        except Exception:
            frame = 0
        bind_per_frame_key = (src_dirty, frame)
    # Animation-only values can be applied by mutating the existing Source
    # hierarchy's matrices/colors/visibility instead of rebuilding objects.
    animation_hierarchy_key = (
        round(float(params.get("build_progress", 1.0)), 6),
        round(float(params.get("build_progress_time", params.get("build_progress", 1.0))), 6),
        round(float(params.get("smooth_top_progress", 1.0)), 6),
        round(float(params.get("smooth_top_progress_time", params.get("smooth_top_progress", 1.0))), 6),
        round(float(params.get("build_y_offset", 25.0)), 3),
        round(float(params.get("build_stagger", 0.10)), 5),
        round(float(params.get("build_hang_time", 0.0)), 5),
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
        round(float(params.get("bind_stretch_cull_ratio", 0.6)), 4),
        round(float(params.get("bind_orient_smoothing", 0.7)), 4),
        bind_per_frame_key,
    )
    hierarchy_key = (topology_hierarchy_key, animation_hierarchy_key)

    cached = op.GetCache(hh)
    if (
        not self._force_rebuild
        and cached is not None
        and self._hierarchy_cache_key == hierarchy_key
    ):
        return cached

    # Fast-path eligibility. When MoGraph effectors are present, the fast
    # path internally destroys + recreates `InstanceObject` carriers under
    # the existing root/templates/group-null hierarchy because mutating
    # cached carriers' matrices via `SetInstanceMatrices` does not pick up
    # the carrier hierarchy's parent transform the way a fresh build does
    # (bricks render at the raw matrix offset instead of `source_mg *
    # matrix`). The recreation path costs ~3-5× a pure mutation but is
    # still a fraction of a full rebuild because it reuses templates,
    # refit, and group-null hierarchy. Without effectors we keep the
    # cheaper pure-mutation path.
    animation_fast_path_eligible = (
        not self._force_rebuild
        and cached is not None
        and isinstance(self._hierarchy_cache_key, tuple)
        and len(self._hierarchy_cache_key) == 2
        and self._hierarchy_cache_key[0] == topology_hierarchy_key
        and self._hierarchy_cache_key[1] != animation_hierarchy_key
        and params.get("visualization_mode") == BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE
        and getattr(self, "_fast_cap_state", None) is not None
    )
    if animation_fast_path_eligible:
        try:
            t0 = time.perf_counter()
            updated = self._apply_integrated_mograph_animation_fast_path(op, params)
            fast_seconds = time.perf_counter() - t0
            if updated is not None:
                self._hierarchy_cache_key = hierarchy_key
                if os.environ.get("BRICKIT_LOG_ANIMATION_FAST_PATH", "").strip().lower() not in ("", "0", "false", "no"):
                    _brick_log(
                        "[brick] Animation fast path: {0:.3f}s, placements={1}".format(
                            float(fast_seconds), len(self._fit_placements or [])
                        )
                    )
                return updated
        except Exception as exc:
            try:
                _brick_log("[brick] Animation fast path failed, falling back: {0}".format(exc))
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
    try:
        if not self._refit_if_needed(op, doc, params):
            try:
                c4d.StatusClear()
            except Exception:
                pass
            return None
    except Exception:
        try:
            c4d.StatusClear()
        except Exception:
            pass
        raise
    refit_seconds = time.perf_counter() - t0
    _maybe_rebind(self, params)

    try:
        c4d.StatusSetText("BrickIt: building hierarchy...")
        c4d.StatusSetBar(95)
    except Exception:
        pass

    t0 = time.perf_counter()
    try:
        if params.get("visualization_mode") == BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE:
            result = self._build_integrated_mograph_hierarchy(op, params=params)
        else:
            result = self._build_hierarchy(op)
    finally:
        # Always clear the status bar — whether the build succeeded,
        # returned None, or raised. Otherwise the bar is left "stuck" and
        # the next non-BrickIt operation inherits a confusing label.
        try:
            c4d.StatusClear()
        except Exception:
            pass
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

    # Update the read-only Build Info panel from the most recent pipeline
    # info. Cosmetic only — wrapped to never affect the build result.
    _update_build_info_panel(
        op,
        getattr(self, "_fit_info", None),
        getattr(self, "_fit_placements", None),
    )
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
