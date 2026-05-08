"""BrickIt ObjectData message and command handling."""
import time

import c4d

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from .brickit_params import (
    INTERACTIVE_PREVIEW_EDIT_WINDOW,
    _snap_voxel_resolution,
)
from library_panel import (
    BRICK_TOGGLE_NAMES,
    apply_library_mask_to_toggles as _apply_library_mask_to_toggles,
    apply_library_preset_to_object as _apply_library_preset_to_object,
    open_library_panel as _open_library_panel,
    read_library_mask as _read_library_mask,
    sync_library_mask_from_toggles as _sync_library_mask_from_toggles,
    toggle_id as _toggle_id,
)
from plugin_bootstrap import (
    open_user_manual as _open_user_manual,
    reload_brick_modules as _reload_brick_modules,
)


def _apply_library_preset(self, op, preset_id):
    _apply_library_preset_to_object(op, preset_id)

def _open_library_picker(self, op):
    _open_library_panel(op)


def _dirty(op):
    op.SetDirty(c4d.DIRTYFLAGS_DATA)
    c4d.EventAdd()


def _reset_build_state(self):
    self._fit_cache_key = None
    self._fit_placements = None
    self._voxel_cache_key = None
    self._voxel_cache_voxels = None
    self._preview_voxel_cache_key = None
    self._preview_voxel_cache_voxels = None
    self._source_cache_key = None
    self._source_cache_data = None
    self._hierarchy_cache_key = None
    self._force_rebuild = True
    self._mesh_cache = {}
    self._template_obj_cache = {}
    self._logo_cache = {}
    self._last_resolution_key = None
    self._interactive_preview_active = False
    self._interactive_preview_desc_id = -1
    self._interactive_preview_log_key = None
    self._interactive_last_edit_at = 0.0
    self._interactive_last_desc_id = -1
    self._bind_records = None
    self._bind_cache_key = None
    self._bind_diagnostics = None


def _set_height_preset(op, max_brick_height):
    op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT] = int(max_brick_height)
    _dirty(op)


def _is_interactive_preview_param(self, desc_id):
    if desc_id in (
        BRICKIFYASSEMBLY_VOXEL_RESOLUTION,
        BRICKIFYASSEMBLY_SOURCES,
        BRICKIFYASSEMBLY_AUTO_REBUILD,
        BRICKIFYASSEMBLY_REBUILD,
        BRICKIFYASSEMBLY_OPEN_LIBRARY_PICKER,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE,
        BRICKIFYASSEMBLY_BUILD_PROGRESS,
        BRICKIFYASSEMBLY_BUILD_STEP,
        BRICKIFYASSEMBLY_SMOOTH_TOP_PROGRESS,
        BRICKIFYASSEMBLY_BUILD_Y_OFFSET,
        BRICKIFYASSEMBLY_BUILD_STAGGER,
        BRICKIFYASSEMBLY_BUILD_HANG_TIME,
        BRICKIFYASSEMBLY_BUILD_MOTION_CURVE,
        BRICKIFYASSEMBLY_BUILD_SCALE_IN,
        BRICKIFYASSEMBLY_BUILD_SUBTLE_ROTATION,
        BRICKIFYASSEMBLY_BUILD_TILT_AMOUNT,
        BRICKIFYASSEMBLY_BUILD_CUSTOM_CURVE,
        BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE,
        BRICKIFYASSEMBLY_TOP_SURFACE_RANDOM_ORDER,
        BRICKIFYASSEMBLY_TOP_SURFACE_BLEND,
        BRICKIFYASSEMBLY_BRICK_SEPARATION,
        BRICKIFYASSEMBLY_HUMANIZE_BRICKS,
        BRICKIFYASSEMBLY_HUMANIZE_SEED,
        BRICKIFYASSEMBLY_HUMANIZE_POSITION,
        BRICKIFYASSEMBLY_HUMANIZE_ROTATION,
        BRICKIFYASSEMBLY_MOGRAPH_EFFECTORS,
        BRICKIFYASSEMBLY_BIND_TO_SOURCE_DEFORMATION,
        BRICKIFYASSEMBLY_BIND_REFERENCE_FRAME,
        BRICKIFYASSEMBLY_BIND_ORIENTATION_MODE,
        BRICKIFYASSEMBLY_BIND_STRETCH_CULL_RATIO,
        BRICKIFYASSEMBLY_BIND_ORIENT_SMOOTHING,
        BRICKIFYASSEMBLY_REBIND_TO_CURRENT_FRAME,
    ):
        return False
    return desc_id in (
        BRICKIFYASSEMBLY_VOXEL_MODE,
        BRICKIFYASSEMBLY_QUALITY,
        BRICKIFYASSEMBLY_MERGE_PLATES,
        BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY,
        BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT,
        BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS,
        BRICKIFYASSEMBLY_SHELL_THICKNESS,
        BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE,
        BRICKIFYASSEMBLY_STUD_SIZE,
        BRICKIFYASSEMBLY_DETAIL_MODE,
        BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS,
        BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES,
        BRICKIFYASSEMBLY_ENABLE_PLATES,
        BRICKIFYASSEMBLY_VOXEL_BACKEND,
        BRICKIFYASSEMBLY_MIRROR_X,
    )


def Message(self, op, msg_type, data):
    if msg_type == c4d.MSG_DESCRIPTION_COMMAND:
        try:
            desc_id = data["id"][0].id
        except Exception:
            desc_id = -1
        if desc_id == BRICKIFYASSEMBLY_REBUILD:
            self._cancel_resolution_live_timer()
            _reload_brick_modules()
            _reset_build_state(self)
            # Force immediate reevaluation after the button press instead
            # of waiting for viewport/object-manager interaction.
            _dirty(op)
        elif desc_id == BRICKIFYASSEMBLY_CREATE_PROXY_MOGRAPH:
            self._create_proxy_mograph_handoff(op)
        elif desc_id == BRICKIFYASSEMBLY_SWAP_PROXY_RENDER:
            self._swap_proxy_to_render_handoff(op)
        elif desc_id == BRICKIFYASSEMBLY_CREATE_RS_COLOR_MATERIAL:
            self._create_rs_color_material(op)
        elif desc_id == BRICKIFYASSEMBLY_OPEN_USER_MANUAL:
            try:
                _open_user_manual()
            except Exception:
                pass
        elif desc_id == BRICKIFYASSEMBLY_REBIND_TO_CURRENT_FRAME:
            # Invalidate everything so the next GVO bypasses the hierarchy
            # cache, runs a full refit (which forces CSTO at fit-time when
            # binding is on), and re-authors the bind against the current-
            # frame deformed mesh.
            self._source_cache_key = None
            self._source_cache_data = None
            self._fit_cache_key = None
            self._bind_cache_key = None
            self._bind_records = None
            self._bind_force_rebind = True
            self._hierarchy_cache_key = None
            self._fast_cap_state = None
            self._force_rebuild = True
            _dirty(op)
        elif desc_id == BRICKIFYASSEMBLY_OPEN_LIBRARY_PICKER:
            self._open_library_picker(op)
        elif desc_id in (
            BRICKIFYASSEMBLY_LIB_PRESET_ALL,
            BRICKIFYASSEMBLY_LIB_PRESET_NONE,
            BRICKIFYASSEMBLY_LIB_PRESET_BRICKS,
            BRICKIFYASSEMBLY_LIB_PRESET_PLATES,
            BRICKIFYASSEMBLY_LIB_PRESET_1X1,
            BRICKIFYASSEMBLY_LIB_PRESET_INVERT,
        ):
            self._apply_library_preset(op, desc_id)
        elif (
            BRICKIFYASSEMBLY_THUMB_BASE
            <= desc_id
            < BRICKIFYASSEMBLY_THUMB_BASE + len(BRICK_TOGGLE_NAMES)
        ):
            i = int(desc_id - BRICKIFYASSEMBLY_THUMB_BASE)
            tid = _toggle_id(i)
            try:
                op[tid] = not bool(op[tid])
            except Exception:
                op[tid] = True
            _sync_library_mask_from_toggles(op)
            _dirty(op)
        elif desc_id == BRICKIFYASSEMBLY_HEIGHT_PRESET_FINE:
            _set_height_preset(op, 2)
        elif desc_id == BRICKIFYASSEMBLY_HEIGHT_PRESET_BALANCED:
            _set_height_preset(op, 3)
        elif desc_id == BRICKIFYASSEMBLY_HEIGHT_PRESET_BLOCKY:
            _set_height_preset(op, 6)
    elif msg_type == c4d.MSG_DESCRIPTION_POSTSETPARAMETER:
        # Force immediate reevaluation while editing controls when
        # auto-rebuild is enabled (avoids waiting for viewport interaction).
        try:
            desc_id = -1
            try:
                desc_id = data["descid"][0].id
            except Exception:
                try:
                    desc_id = data["id"][0].id
                except Exception:
                    desc_id = -1
            if desc_id == BRICKIFYASSEMBLY_VOXEL_RESOLUTION:
                try:
                    snapped = _snap_voxel_resolution(
                        op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION]
                    )
                    op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION] = snapped
                except Exception:
                    pass
            try:
                set_flags = int(data["flags"])
            except Exception:
                try:
                    set_flags = int(data.get("flags", 0))
                except Exception:
                    set_flags = 0
            in_drag = bool(set_flags & c4d.DESCFLAGS_SET_INDRAG)
            now = time.perf_counter()
            if self._is_interactive_preview_param(desc_id):
                rapid_edit = (
                    desc_id == self._interactive_last_desc_id
                    and (now - float(self._interactive_last_edit_at or 0.0))
                    <= INTERACTIVE_PREVIEW_EDIT_WINDOW
                )
                self._interactive_preview_active = bool(in_drag or rapid_edit)
                self._interactive_preview_desc_id = int(desc_id)
                self._interactive_last_edit_at = now
                self._interactive_last_desc_id = int(desc_id)
                if not self._interactive_preview_active:
                    self._interactive_preview_log_key = None
            elif not in_drag:
                self._interactive_preview_active = False
                self._interactive_preview_log_key = None
            # Resolution + Live Update: debounce rebuilds while scrubbing.
            if desc_id == BRICKIFYASSEMBLY_VOXEL_RESOLUTION:
                if bool(op[BRICKIFYASSEMBLY_AUTO_REBUILD]):
                    if in_drag:
                        self._cancel_resolution_live_timer()
                    else:
                        self._schedule_resolution_live_rebuild(op)
            elif desc_id == BRICKIFYASSEMBLY_AUTO_REBUILD:
                if not bool(op[BRICKIFYASSEMBLY_AUTO_REBUILD]):
                    self._cancel_resolution_live_timer()
                _dirty(op)
            else:
                _dirty(op)
            if desc_id == BRICKIFYASSEMBLY_BUILD_STEP:
                # The .res declares MAX 100000 as a static placeholder
                # (per-instance dynamic MAX would require GetDDescription
                # overrides). Clamp the value here on commit so the
                # stepper effectively caps at total_bricks even though
                # the visual range allows scrubbing past it. The clamp
                # also updates the read-only Progress display.
                # Stepper is REAL — fractional values scrub bricks
                # mid-fall, so we don't round to int here.
                try:
                    step = max(0.0, float(op[BRICKIFYASSEMBLY_BUILD_STEP] or 0.0))
                    total = max(1, int(
                        op[BRICKIFYASSEMBLY_BUILD_PREV_TOTAL] or 1
                    ))
                    if step > float(total):
                        step = float(total)
                        try:
                            op[BRICKIFYASSEMBLY_BUILD_STEP] = step
                        except Exception:
                            pass
                    pct = 100.0 * step / float(total)
                    op[BRICKIFYASSEMBLY_BUILD_PROGRESS_PCT] = (
                        "{0:.1f}%".format(pct)
                    )
                except Exception:
                    pass
            if desc_id == BRICKIFYASSEMBLY_LIBRARY_MASK:
                _apply_library_mask_to_toggles(op, _read_library_mask(op))
                _dirty(op)
            elif (
                BRICKIFYASSEMBLY_BRICK_BASE
                <= desc_id
                < BRICKIFYASSEMBLY_BRICK_BASE + len(BRICK_TOGGLE_NAMES)
            ):
                _sync_library_mask_from_toggles(op)
            # Live Update OFF means the user has explicitly opted into
            # manual rebuild control — they want to make several edits
            # (mode changes, parameter tweaks, source moves) and then
            # click Rebuild once. Don't sneak in forced rebuilds for
            # specific param edits in that mode; only the Rebuild button
            # itself bypasses Live Update.
            try:
                _live_update_on = bool(op[BRICKIFYASSEMBLY_AUTO_REBUILD])
            except Exception:
                _live_update_on = True
            if desc_id in (
                BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS,
                BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES,
                BRICKIFYASSEMBLY_MIRROR_X,
            ):
                # This toggle is commonly A/B tested while dialing a model;
                # force immediate reevaluation so users can see the effect
                # without requiring manual "Rebuild Now". Skipped when
                # Live Update is off — the user gets the rebuild on their
                # next manual Rebuild click.
                self._fit_cache_key = None
                self._hierarchy_cache_key = None
                if _live_update_on:
                    self._force_rebuild = True
                    _dirty(op)
            if desc_id == BRICKIFYASSEMBLY_SOURCES:
                # Sources list edited: invalidate caches and rebuild.
                # Same Live Update rule — without that gate, mode-cycling
                # in the sources list would force a rebuild even though
                # the user explicitly turned Live Update off.
                self._fit_cache_key = None
                self._hierarchy_cache_key = None
                if _live_update_on:
                    self._force_rebuild = True
                    c4d.EventAdd()
        except Exception:
            pass
    return True

