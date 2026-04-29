"""BrickIt source-mesh-to-brick-assembly ObjectData plugin."""
import threading

import c4d
from c4d import plugins

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from logo_helpers import (
    BRICKGEN_LOGO_DEFAULT_SINK,
    BRICKGEN_LOGO_FILL_MIN_RATIO,
    BRICKGEN_LOGO_FILL_UI_DEFAULT,
    logo_link_identity_key as _logo_link_identity_key,
)
from library_panel import (
    BRICK_TOGGLE_NAMES,
    toggle_id as _toggle_id,
)
from brickit_templates import (
    _get_logo_template_obj as _template_get_logo_template_obj,
    _get_template_mesh as _template_get_template_mesh,
    _normalized_logo_source_object as _template_normalized_logo_source_object,
)
from brickit_mograph import _create_mograph_handoff as _build_mograph_handoff
from brickit_view import _build_hierarchy as _build_view_hierarchy
from brickit_fit import (
    _get_active_library as _fit_get_active_library,
    _get_cached_source_arrays as _fit_get_cached_source_arrays,
    _make_fit_key as _fit_make_fit_key,
    _make_voxel_key as _fit_make_voxel_key,
    _refit_if_needed as _fit_refit_if_needed,
)
from brickit_params import (
    RESOLUTION_LIVE_DEBOUNCE_SEC,
    VOXEL_RES_DEFAULT,
    _interactive_preview_params as _params_interactive_preview_params,
    _resolution_key as _params_resolution_key,
    _resolve_params as _params_resolve_params,
    _snap_voxel_resolution,
)
from brickit_messages import (
    Message as _messages_handle_message,
    _apply_library_preset as _messages_apply_library_preset,
    _is_interactive_preview_param as _messages_is_interactive_preview_param,
    _open_library_picker as _messages_open_library_picker,
)
from brickit_runtime import GetVirtualObjects as _runtime_get_virtual_objects


class BrickAssembly(plugins.ObjectData):
    """Source polygon mesh -> brick-assembly hierarchy of instances."""

    def __init__(self):
        super().__init__()
        self._fit_cache_key = None
        self._fit_placements = None
        self._fit_info = None
        self._voxel_cache_key = None
        self._voxel_cache_voxels = None
        self._preview_voxel_cache_key = None
        self._preview_voxel_cache_voxels = None
        self._source_cache_key = None
        self._source_cache_data = None
        self._hierarchy_cache_key = None
        self._force_rebuild = False
        self._mesh_cache = {}
        self._logo_cache = {}
        self._last_hierarchy_obj = None
        self._last_resolution_key = None
        self._built_voxel_resolution = None
        self._startup_draft_pending = True
        self._interactive_preview_active = False
        self._interactive_preview_desc_id = -1
        self._interactive_preview_log_key = None
        self._interactive_last_edit_at = 0.0
        self._interactive_last_desc_id = -1
        self._managed_source = None
        self._last_prune_warning_key = None
        self._resolution_live_timer = None
        self._resolution_live_timer_op = None

    def _restore_managed_source(self):
        state = self._managed_source
        if not state:
            return
        obj = state.get("obj")
        if obj is None:
            self._managed_source = None
            return
        try:
            obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = state.get("editor", c4d.OBJECT_UNDEF)
            obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = state.get("render", c4d.OBJECT_UNDEF)
        except Exception:
            pass
        self._managed_source = None

    def _sync_source_visibility(self, op):
        """Hide linked source object, restore it when unlinked/changed."""
        src = None
        try:
            src = op[BRICKIFYASSEMBLY_SOURCE]
        except Exception:
            src = None

        managed = self._managed_source
        managed_obj = managed.get("obj") if managed else None

        # Source changed or removed -> restore previous managed source.
        if managed_obj is not None and managed_obj is not src:
            self._restore_managed_source()
            managed = None
            managed_obj = None

        if src is None:
            return

        hide_source = True
        try:
            hide_source = bool(op[BRICKIFYASSEMBLY_HIDE_SOURCE_MESH])
        except Exception:
            hide_source = True

        if managed_obj is src:
            if not hide_source:
                self._restore_managed_source()
            return

        if not hide_source:
            return

        try:
            prev_editor = int(src[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR])
            prev_render = int(src[c4d.ID_BASEOBJECT_VISIBILITY_RENDER])
        except Exception:
            prev_editor = c4d.OBJECT_UNDEF
            prev_render = c4d.OBJECT_UNDEF

        self._managed_source = {
            "obj": src,
            "editor": prev_editor,
            "render": prev_render,
        }
        try:
            src[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = c4d.OBJECT_OFF
            src[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = c4d.OBJECT_OFF
        except Exception:
            pass

    def Free(self, node):
        self._cancel_resolution_live_timer()
        # If the generator gets deleted, restore source-visibility state.
        self._restore_managed_source()

    def _cancel_resolution_live_timer(self):
        t = self._resolution_live_timer
        if t is not None:
            try:
                t.cancel()
            except Exception:
                pass
            self._resolution_live_timer = None
        self._resolution_live_timer_op = None

    def _schedule_resolution_live_rebuild(self, op):
        """Flush one rebuild after scrubbing stops (debounced)."""

        def _fire():
            self._resolution_live_timer = None
            o = self._resolution_live_timer_op
            self._resolution_live_timer_op = None
            if o is None:
                return
            try:
                if not bool(o[BRICKIFYASSEMBLY_AUTO_REBUILD]):
                    return
            except Exception:
                return
            try:
                o.SetDirty(c4d.DIRTYFLAGS_DATA)
                c4d.EventAdd()
            except Exception:
                pass

        self._cancel_resolution_live_timer()
        self._resolution_live_timer_op = op
        timer = threading.Timer(RESOLUTION_LIVE_DEBOUNCE_SEC, _fire)
        timer.daemon = True
        self._resolution_live_timer = timer
        timer.start()

    def _apply_library_preset(self, op, preset_id):
        return _messages_apply_library_preset(self, op, preset_id)

    def _open_library_picker(self, op):
        return _messages_open_library_picker(self, op)

    def _is_interactive_preview_param(self, desc_id):
        return _messages_is_interactive_preview_param(self, desc_id)

    def _interactive_preview_params(self, params):
        return _params_interactive_preview_params(self, params)

    def GetDDescription(self, op, description, flags):
        """Load obrickifyassembly.res from disk.

        Cinema 4D's .res lexer is effectively ASCII / Latin-1; stray UTF-8
        (e.g. Unicode dashes in comments) can make LoadDescription fail and
        hide the entire Object tab with no error dialog.
        """
        if not description.LoadDescription(ID_BRICKIFYASSEMBLY):
            print(
                "[brick] BrickAssembly: description.LoadDescription("
                "ID_BRICKIFYASSEMBLY) failed -- check res/description/"
                "obrickifyassembly.res for non-ASCII bytes or syntax errors."
            )
            return False
        try:
            # Migrate the temporary linear-slider default used during the UI
            # rebuild. Without this, existing test objects would keep showing
            # the unhelpful 0.111 value after the curve changed.
            v = float(op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION])
            if 0.1105 <= v <= 0.1115:
                op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION] = VOXEL_RES_DEFAULT
            snapped = _snap_voxel_resolution(op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION])
            if abs(float(op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION]) - snapped) > 1e-9:
                op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION] = snapped
        except Exception:
            pass
        return True, flags | c4d.DESCFLAGS_DESC_LOADED

    def GetDEnabling(self, op, desc_id, t_data, flags, itemdesc):
        """Gray out Rebuild Now while Live Update is on (resolution is live)."""
        try:
            pid = desc_id[0].id
        except Exception:
            try:
                pid = int(desc_id)
            except Exception:
                return True
        if pid == BRICKIFYASSEMBLY_REBUILD:
            try:
                return not bool(op[BRICKIFYASSEMBLY_AUTO_REBUILD])
            except Exception:
                return True
        if pid in (
            BRICKIFYASSEMBLY_LOGO_SOURCE,
            BRICKIFYASSEMBLY_LOGO_ROTATION,
            BRICKIFYASSEMBLY_LOGO_DIAMETER,
            BRICKIFYASSEMBLY_LOGO_HEIGHT,
            BRICKIFYASSEMBLY_LOGO_BLEND,
            BRICKIFYASSEMBLY_LOGO_SINK,
        ):
            try:
                return bool(op[BRICKIFYASSEMBLY_ENABLE_LOGO])
            except Exception:
                return True
        return True

    def Init(self, op, isCloneInit=False):
        self._cancel_resolution_live_timer()
        op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION] = VOXEL_RES_DEFAULT
        op[BRICKIFYASSEMBLY_HERO] = 0
        op[BRICKIFYASSEMBLY_STUDS_ACROSS] = 16          # legacy fallback
        op[BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE] = False
        op[BRICKIFYASSEMBLY_STUD_SIZE] = 8.0
        op[BRICKIFYASSEMBLY_VOXEL_BACKEND] = BRICKIFYASSEMBLY_VOXEL_BACKEND_C4D_VOLUME
        op[BRICKIFYASSEMBLY_VOXEL_MODE] = BRICKIFYASSEMBLY_VOXEL_MODE_SOLID
        op[BRICKIFYASSEMBLY_SHELL_THICKNESS] = 3
        op[BRICKIFYASSEMBLY_DETAIL_MODE] = BRICKIFYASSEMBLY_DETAIL_MODE_BALANCED
        op[BRICKIFYASSEMBLY_QUALITY] = BRICKIFYASSEMBLY_QUALITY_DRAFT
        op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT] = 3
        op[BRICKIFYASSEMBLY_HEIGHT_VARIATION] = False
        op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED] = 1
        op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT] = 0.6
        op[BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS] = False
        op[BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES] = True
        op[BRICKIFYASSEMBLY_ENABLE_PLATES] = False
        op[BRICKIFYASSEMBLY_HIDE_SOURCE_MESH] = True
        op[BRICKIFYASSEMBLY_MERGE_PLATES] = True
        op[BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY] = False
        op[BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS] = 1
        op[BRICKIFYASSEMBLY_VISUALIZATION_MODE] = BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE
        op[BRICKIFYASSEMBLY_AUTO_REBUILD] = True
        op[BRICKIFYASSEMBLY_ENABLE_LOGO] = False
        op[BRICKIFYASSEMBLY_LOGO_SOURCE] = None
        op[BRICKIFYASSEMBLY_LOGO_ROTATION] = BRICKIFYASSEMBLY_LOGO_ROTATION_0
        op[BRICKIFYASSEMBLY_LOGO_DIAMETER] = BRICKGEN_LOGO_FILL_UI_DEFAULT
        op[BRICKIFYASSEMBLY_LOGO_HEIGHT] = 0.06
        op[BRICKIFYASSEMBLY_LOGO_BLEND] = 1.0
        op[BRICKIFYASSEMBLY_LOGO_SINK] = BRICKGEN_LOGO_DEFAULT_SINK
        # Default: start with no brick types selected; artists opt-in via the
        # thumbnail library / quick select controls.
        for i in range(len(BRICK_TOGGLE_NAMES)):
            op[_toggle_id(i)] = False
        op[BRICKIFYASSEMBLY_LIBRARY_MASK] = 0
        self._fit_cache_key = None
        self._fit_placements = None
        self._fit_info = None
        self._voxel_cache_key = None
        self._voxel_cache_voxels = None
        self._preview_voxel_cache_key = None
        self._preview_voxel_cache_voxels = None
        self._source_cache_key = None
        self._source_cache_data = None
        self._hierarchy_cache_key = None
        self._force_rebuild = False
        self._mesh_cache = {}
        self._logo_cache = {}
        self._last_hierarchy_obj = None
        self._last_resolution_key = None
        self._built_voxel_resolution = None
        self._startup_draft_pending = True
        self._interactive_preview_active = False
        self._interactive_preview_desc_id = -1
        self._interactive_preview_log_key = None
        self._interactive_last_edit_at = 0.0
        self._interactive_last_desc_id = -1
        self._managed_source = None
        self._last_prune_warning_key = None
        self._resolution_live_timer = None
        self._resolution_live_timer_op = None
        # Ensure a fresh scene/file load triggers at least one generator
        # evaluation without requiring a manual OM interaction.
        try:
            op.SetDirty(c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_CACHE)
            op.Message(c4d.MSG_UPDATE)
        except Exception:
            pass
        return True

    def Message(self, op, msg_type, data):
        return _messages_handle_message(self, op, msg_type, data)

    def _get_active_library(self, op):
        return _fit_get_active_library(self, op)

    def _resolve_params(self, op, source_obj):
        return _params_resolve_params(self, op, source_obj)

    def _make_fit_key(self, source_obj, params):
        return _fit_make_fit_key(self, source_obj, params)

    def _source_state_key(self, source_obj):
        return _logo_link_identity_key(source_obj)

    def _make_voxel_key(self, source_obj, params, stud_size, plate_size):
        return _fit_make_voxel_key(self, source_obj, params, stud_size, plate_size)

    def _get_cached_source_arrays(self, source_obj, doc):
        return _fit_get_cached_source_arrays(self, source_obj, doc)

    def _resolution_key(self, params):
        return _params_resolution_key(self, params)

    def _refit_if_needed(self, op, doc, params=None):
        return _fit_refit_if_needed(self, op, doc, params=params)

    def _get_template_mesh(
        self,
        brick_type,
        quality,
        stud_size,
        plate_size,
        *,
        smooth_plate_visual=True,
        force_smooth_top=False,
    ):
        return _template_get_template_mesh(
            self,
            brick_type,
            quality,
            stud_size,
            plate_size,
            smooth_plate_visual=smooth_plate_visual,
            force_smooth_top=force_smooth_top,
        )

    def _normalized_logo_source_object(
        self,
        source_obj,
        doc,
        stud_size,
        plate_size,
        *,
        diameter_ratio=BRICKGEN_LOGO_FILL_MIN_RATIO,
        height_ratio=0.06,
        blend=1.0,
    ):
        return _template_normalized_logo_source_object(
            self,
            source_obj,
            doc,
            stud_size,
            plate_size,
            diameter_ratio=diameter_ratio,
            height_ratio=height_ratio,
            blend=blend,
        )

    def _get_logo_template_obj(self, params, doc, stud_size, plate_size):
        return _template_get_logo_template_obj(self, params, doc, stud_size, plate_size)

    def _create_mograph_handoff(self, op):
        return _build_mograph_handoff(self, op)

    def _build_hierarchy(self, op):
        return _build_view_hierarchy(self, op)

    def GetVirtualObjects(self, op, hh):
        return _runtime_get_virtual_objects(self, op, hh)
