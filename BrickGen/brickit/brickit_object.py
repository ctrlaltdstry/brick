"""BrickIt source-mesh-to-brick-assembly ObjectData plugin."""
import os
import threading

import c4d
from c4d import plugins


def _desc_log_enabled():
    return os.environ.get("BRICKIT_LOG_DESC", "").strip().lower() not in ("", "0", "false", "no")

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from logo_helpers import (
    BRICKGEN_LOGO_DEFAULT_SINK,
    BRICKGEN_LOGO_FILL_MIN_RATIO,
    BRICKGEN_LOGO_FILL_UI_DEFAULT,
    logo_link_identity_key as _logo_link_identity_key,
)
from library_panel import (
    BRICK_TOGGLE_NAMES,
    DEFAULT_BRICK_LIBRARY_MASK,
    toggle_id as _toggle_id,
)
from .brickit_templates import (
    _get_logo_template_obj as _template_get_logo_template_obj,
    _get_proxy_template_mesh as _template_get_proxy_template_mesh,
    _get_template_mesh as _template_get_template_mesh,
    _normalized_logo_source_object as _template_normalized_logo_source_object,
)
from .brickit_mograph import (
    _create_proxy_mograph_handoff as _build_proxy_mograph_handoff,
    _swap_proxy_to_render_handoff as _swap_proxy_mograph_handoff,
)
from .brickit_rs_material import (
    _create_rs_color_material as _build_rs_color_material,
)
from .brickit_mograph_generator import (
    _build_integrated_mograph_hierarchy as _build_integrated_mograph_hierarchy_impl,
    _apply_cap_subset_fast_path as _apply_cap_subset_fast_path_impl,
    _apply_integrated_mograph_animation_fast_path as _apply_integrated_mograph_animation_fast_path_impl,
)
from .brickit_view import _build_hierarchy as _build_view_hierarchy
from .brickit_fit import (
    _get_active_library as _fit_get_active_library,
    _get_cached_source_arrays as _fit_get_cached_source_arrays,
    _make_fit_key as _fit_make_fit_key,
    _make_voxel_key as _fit_make_voxel_key,
    _refit_if_needed as _fit_refit_if_needed,
)
from .brickit_params import (
    RESOLUTION_LIVE_DEBOUNCE_SEC,
    VOXEL_RES_DEFAULT,
    _interactive_preview_params as _params_interactive_preview_params,
    _library_ui_state as _params_library_ui_state,
    _resolution_key as _params_resolution_key,
    _resolve_params as _params_resolve_params,
    _snap_voxel_resolution,
)
from .brickit_messages import (
    Message as _messages_handle_message,
    _apply_library_preset as _messages_apply_library_preset,
    _is_interactive_preview_param as _messages_is_interactive_preview_param,
    _open_library_picker as _messages_open_library_picker,
)
from .brickit_runtime import GetVirtualObjects as _runtime_get_virtual_objects


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
        self._template_obj_cache = {}
        self._logo_cache = {}
        self._last_hierarchy_obj = None
        self._fast_cap_state = None
        self._last_resolution_key = None
        self._built_voxel_resolution = None
        self._startup_draft_pending = True
        # Defer the very first heavy GVO eval after this Python instance
        # is constructed. For loaded objects this avoids blocking the
        # Object Manager during scene-open. Init() clears it for newly
        # created objects so the user sees bricks immediately.
        self._deferred_first_build_pending = True
        self._interactive_preview_active = False
        self._interactive_preview_desc_id = -1
        self._interactive_preview_log_key = None
        self._interactive_last_edit_at = 0.0
        self._interactive_last_desc_id = -1
        self._last_prune_warning_key = None
        self._resolution_live_timer = None
        self._resolution_live_timer_op = None
        self._bind_records = None
        self._bind_cache_key = None
        self._bind_diagnostics = None
        self._bind_force_rebind = False
        self._auto_hidden_guids = set()

    def Free(self, node):
        self._cancel_resolution_live_timer()

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

    def _add_custom_curve_description(self, description):
        try:
            bc = c4d.GetCustomDataTypeDefault(c4d.CUSTOMDATATYPE_SPLINE)
            bc[c4d.DESC_NAME] = "Custom Motion Curve"
            bc[c4d.DESC_SHORT_NAME] = "Custom Motion Curve"
            bc[c4d.DESC_CUSTOMGUI] = c4d.CUSTOMGUI_SPLINE
            bc[c4d.SPLINECONTROL_GRID_H] = True
            bc[c4d.SPLINECONTROL_GRID_V] = True
            bc[c4d.SPLINECONTROL_VALUE_EDIT_H] = True
            bc[c4d.SPLINECONTROL_VALUE_EDIT_V] = True
            bc[c4d.SPLINECONTROL_X_MIN] = 0.0
            bc[c4d.SPLINECONTROL_X_MAX] = 1.0
            bc[c4d.SPLINECONTROL_X_STEPS] = 0.01
            bc[c4d.SPLINECONTROL_Y_MIN] = 0.0
            bc[c4d.SPLINECONTROL_Y_MAX] = 1.0
            bc[c4d.SPLINECONTROL_Y_STEPS] = 0.01
            bc[c4d.SPLINECONTROL_MINSIZE_H] = 160
            bc[c4d.SPLINECONTROL_MINSIZE_V] = 120
            desc_id = c4d.DescID(
                c4d.DescLevel(
                    BRICKIFYASSEMBLY_BUILD_CUSTOM_CURVE,
                    c4d.CUSTOMDATATYPE_SPLINE,
                    ID_BRICKIFYASSEMBLY,
                )
            )
            group_id = c4d.DescID(c4d.DescLevel(BRICKIFYASSEMBLY_GROUP_BUILD_ANIM))
            description.SetParameter(desc_id, bc, group_id)
        except Exception:
            pass

    def _add_mograph_effectors_description(self, description):
        try:
            bc = c4d.GetCustomDataTypeDefault(c4d.CUSTOMDATATYPE_INEXCLUDE_LIST)
            bc[c4d.DESC_NAME] = "Effectors"
            bc[c4d.DESC_SHORT_NAME] = "Effectors"
            bc[c4d.DESC_CUSTOMGUI] = c4d.CUSTOMGUI_INEXCLUDE_LIST
            try:
                accepted = c4d.BaseContainer()
                accepted.InsData(c4d.Obase, "")
                bc[c4d.DESC_ACCEPT] = accepted
            except Exception:
                pass
            desc_id = c4d.DescID(
                c4d.DescLevel(
                    BRICKIFYASSEMBLY_MOGRAPH_EFFECTORS,
                    c4d.CUSTOMDATATYPE_INEXCLUDE_LIST,
                    ID_BRICKIFYASSEMBLY,
                )
            )
            group_id = c4d.DescID(c4d.DescLevel(BRICKIFYASSEMBLY_TAB_EFFECTORS))
            description.SetParameter(desc_id, bc, group_id)
        except Exception:
            pass

    def GetDDescription(self, op, description, flags):
        """Load obrickifyassembly.res from disk.

        Cinema 4D's .res lexer is effectively ASCII / Latin-1; stray UTF-8
        (e.g. Unicode dashes in comments) can make LoadDescription fail and
        hide the entire Object tab with no error dialog.
        """
        if not description.LoadDescription(ID_BRICKIFYASSEMBLY):
            if _desc_log_enabled():
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
        self._add_custom_curve_description(description)
        self._add_mograph_effectors_description(description)
        # Dynamic MAX for the Build Step slider so the slider track spans
        # 0..total_bricks instead of the .res-static 100000. Without this,
        # the slider grip would barely move on assemblies with only a few
        # hundred bricks.
        try:
            total_bricks = max(
                1, int(op[BRICKIFYASSEMBLY_BUILD_PREV_TOTAL] or 1)
            )
            step_descid = c4d.DescID(c4d.DescLevel(
                BRICKIFYASSEMBLY_BUILD_STEP, c4d.DTYPE_REAL, 0
            ))
            step_bc = description.GetParameterI(step_descid, None)
            if step_bc is not None:
                step_bc.SetFloat(c4d.DESC_MAX, float(total_bricks))
                step_bc.SetFloat(c4d.DESC_MAXSLIDER, float(total_bricks))
                step_bc.SetFloat(c4d.DESC_MIN, 0.0)
                step_bc.SetFloat(c4d.DESC_MINSLIDER, 0.0)
        except Exception:
            pass
        return True, flags | c4d.DESCFLAGS_DESC_LOADED

    def GetDEnabling(self, op, desc_id, t_data, flags, itemdesc):
        """Keep dependent controls aligned with the effective builder state."""
        try:
            pid = desc_id[0].id
        except Exception:
            try:
                pid = int(desc_id)
            except Exception:
                return True
        try:
            library_state = _params_library_ui_state(op)
        except Exception:
            library_state = {}
        if pid == BRICKIFYASSEMBLY_REBUILD:
            try:
                return not bool(op[BRICKIFYASSEMBLY_AUTO_REBUILD])
            except Exception:
                return True
        if pid == BRICKIFYASSEMBLY_STUD_SIZE:
            # Custom Scale field is only meaningful when the user opted into
            # manual sizing — auto-derive mode greys it out.
            try:
                return bool(op[BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE])
            except Exception:
                return False
        if pid == BRICKIFYASSEMBLY_VOXEL_RESOLUTION:
            # Resolution and Custom Scale are mutually exclusive sizing
            # controls: resolution sets bricks-per-source-bounds, custom
            # scale sets absolute stud size. Grey resolution out when the
            # user has taken over absolute sizing.
            try:
                return not bool(op[BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE])
            except Exception:
                return True
        if pid == BRICKIFYASSEMBLY_SHELL_THICKNESS:
            # Wall Thickness only applies in Shell build type — it sets
            # the SDF band width for surface-only voxelization. In Solid
            # mode the parameter is ignored, so grey it out for clarity.
            try:
                return int(op[BRICKIFYASSEMBLY_VOXEL_MODE]) == int(
                    BRICKIFYASSEMBLY_VOXEL_MODE_SHELL
                )
            except Exception:
                return True
        if pid in (
            BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT,
            BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED,
        ):
            # Variation amount + seed only meaningful when Vary Brick
            # Heights is on; grey out otherwise.
            try:
                return bool(op[BRICKIFYASSEMBLY_HEIGHT_VARIATION])
            except Exception:
                return False
        if pid in (
            BRICKIFYASSEMBLY_BRICK_SEPARATION,
            BRICKIFYASSEMBLY_HUMANIZE_SEED,
            BRICKIFYASSEMBLY_HUMANIZE_POSITION,
            BRICKIFYASSEMBLY_HUMANIZE_ROTATION,
        ):
            # Per-Brick Variation sub-options are all gated on Humanize
            # Bricks per user direction — including Brick Separation,
            # which is grouped here as a "things that vary per brick"
            # option even though it's not strictly humanization.
            try:
                return bool(op[BRICKIFYASSEMBLY_HUMANIZE_BRICKS])
            except Exception:
                return False
        if pid in (
            BRICKIFYASSEMBLY_LOGO_SOURCE,
            BRICKIFYASSEMBLY_LOGO_ROTATION,
            BRICKIFYASSEMBLY_LOGO_DIAMETER,
            BRICKIFYASSEMBLY_LOGO_HEIGHT,
            BRICKIFYASSEMBLY_LOGO_BLEND,
            BRICKIFYASSEMBLY_LOGO_SINK,
            BRICKIFYASSEMBLY_LOGO_MIX_FLIP,
        ):
            try:
                return bool(op[BRICKIFYASSEMBLY_ENABLE_LOGO])
            except Exception:
                return True
        if pid in (
            BRICKIFYASSEMBLY_LOGO_MIX_AMOUNT,
            BRICKIFYASSEMBLY_LOGO_MIX_SEED,
        ):
            try:
                return (
                    bool(op[BRICKIFYASSEMBLY_ENABLE_LOGO])
                    and bool(op[BRICKIFYASSEMBLY_LOGO_MIX_FLIP])
                )
            except Exception:
                return True
        if pid == BRICKIFYASSEMBLY_BUILD_CUSTOM_CURVE:
            try:
                return int(op[BRICKIFYASSEMBLY_BUILD_MOTION_CURVE]) == BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_CUSTOM
            except Exception:
                return True
        if pid == BRICKIFYASSEMBLY_MERGE_PLATES:
            return int(library_state.get("max_brick_height", 3)) >= 3
        if pid == BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS:
            return not bool(library_state.get("only_1x1_library", False))
        if pid == BRICKIFYASSEMBLY_DETAIL_MODE:
            return not bool(library_state.get("only_2x_library", False))
        if pid == BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES:
            return bool(library_state.get("enable_plates", False))
        if pid in (
            BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE,
            BRICKIFYASSEMBLY_TOP_SURFACE_RANDOM_ORDER,
            BRICKIFYASSEMBLY_TOP_SURFACE_PHASE,
            BRICKIFYASSEMBLY_CAP_STYLE,
        ):
            try:
                return bool(library_state.get("enable_plates", False)) and bool(
                    op[BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES]
                )
            except Exception:
                return bool(library_state.get("enable_plates", False))
        if pid == BRICKIFYASSEMBLY_CAP_RANDOM_SEED:
            try:
                return (
                    bool(library_state.get("enable_plates", False))
                    and bool(op[BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES])
                    and int(op[BRICKIFYASSEMBLY_CAP_STYLE]) == BRICKIFYASSEMBLY_CAP_STYLE_RANDOM_MIX
                )
            except Exception:
                return False
        if pid in (
            BRICKIFYASSEMBLY_BIND_REFERENCE_FRAME,
            BRICKIFYASSEMBLY_BIND_ORIENTATION_MODE,
            BRICKIFYASSEMBLY_BIND_STRETCH_CULL_RATIO,
            BRICKIFYASSEMBLY_BIND_ORIENT_SMOOTHING,
            BRICKIFYASSEMBLY_REBIND_TO_CURRENT_FRAME,
        ):
            try:
                return bool(op[BRICKIFYASSEMBLY_BIND_TO_SOURCE_DEFORMATION])
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
        op[BRICKIFYASSEMBLY_QUALITY] = BRICKIFYASSEMBLY_QUALITY_PROXY
        op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT] = 3
        op[BRICKIFYASSEMBLY_HEIGHT_VARIATION] = False
        op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED] = 1
        op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT] = 0.6
        op[BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS] = False
        op[BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES] = True
        op[BRICKIFYASSEMBLY_CAP_STYLE] = BRICKIFYASSEMBLY_CAP_STYLE_MATCH_BELOW
        op[BRICKIFYASSEMBLY_CAP_RANDOM_SEED] = 0
        op[BRICKIFYASSEMBLY_ENABLE_PLATES] = False
        op[BRICKIFYASSEMBLY_MERGE_PLATES] = True
        op[BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY] = False
        op[BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS] = 1
        op[BRICKIFYASSEMBLY_VISUALIZATION_MODE] = BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE
        op[BRICKIFYASSEMBLY_AUTO_REBUILD] = True
        op[BRICKIFYASSEMBLY_ENABLE_LOGO] = False
        op[BRICKIFYASSEMBLY_LOGO_SOURCE] = None
        op[BRICKIFYASSEMBLY_LOGO_ROTATION] = 0.0
        op[BRICKIFYASSEMBLY_LOGO_DIAMETER] = BRICKGEN_LOGO_FILL_UI_DEFAULT
        op[BRICKIFYASSEMBLY_LOGO_HEIGHT] = 0.06
        op[BRICKIFYASSEMBLY_LOGO_BLEND] = 1.0
        op[BRICKIFYASSEMBLY_LOGO_SINK] = BRICKGEN_LOGO_DEFAULT_SINK
        op[BRICKIFYASSEMBLY_LOGO_MIX_FLIP] = False
        op[BRICKIFYASSEMBLY_LOGO_MIX_AMOUNT] = 50.0
        op[BRICKIFYASSEMBLY_LOGO_MIX_SEED] = 0
        op[BRICKIFYASSEMBLY_BUILD_PROGRESS] = 100.0
        op[BRICKIFYASSEMBLY_BUILD_Y_OFFSET] = 25.0
        op[BRICKIFYASSEMBLY_BUILD_STAGGER] = 10.0
        op[BRICKIFYASSEMBLY_BUILD_HANG_TIME] = 0.0
        op[BRICKIFYASSEMBLY_BUILD_DAMPING] = 50.0
        op[BRICKIFYASSEMBLY_BUILD_MOTION_CURVE] = BRICKIFYASSEMBLY_BUILD_MOTION_CURVE_SLAM
        op[BRICKIFYASSEMBLY_BUILD_SCALE_IN] = False
        op[BRICKIFYASSEMBLY_BUILD_SUBTLE_ROTATION] = False
        op[BRICKIFYASSEMBLY_BUILD_TILT_AMOUNT] = 5.0
        op[BRICKIFYASSEMBLY_TOP_SURFACE_RANDOM_ORDER] = False
        op[BRICKIFYASSEMBLY_TOP_SURFACE_BLEND] = True
        op[BRICKIFYASSEMBLY_BRICK_SEPARATION] = 0.0
        op[BRICKIFYASSEMBLY_HUMANIZE_BRICKS] = False
        op[BRICKIFYASSEMBLY_HUMANIZE_SEED] = 1
        op[BRICKIFYASSEMBLY_HUMANIZE_POSITION] = 0.0
        op[BRICKIFYASSEMBLY_HUMANIZE_ROTATION] = 0.0
        try:
            op[BRICKIFYASSEMBLY_MOGRAPH_EFFECTORS] = c4d.InExcludeData()
        except Exception:
            pass
        try:
            op[BRICKIFYASSEMBLY_SOURCES] = c4d.InExcludeData()
        except Exception:
            pass
        try:
            curve = c4d.SplineData()
            curve.MakeLinearSplineBezier(2)
            curve.SetRange(0.0, 1.0, 0.01, 0.0, 1.0, 0.01)
            op[BRICKIFYASSEMBLY_BUILD_CUSTOM_CURVE] = curve
        except Exception:
            pass
        op[BRICKIFYASSEMBLY_TOP_SURFACE_PHASE] = 15.0
        op[BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE] = 100.0
        # Default to one common brick so a fresh BrickIt gives visual feedback
        # as soon as the user links a source mesh.
        for i in range(len(BRICK_TOGGLE_NAMES)):
            op[_toggle_id(i)] = bool(DEFAULT_BRICK_LIBRARY_MASK & (1 << i))
        op[BRICKIFYASSEMBLY_LIBRARY_MASK] = int(DEFAULT_BRICK_LIBRARY_MASK)
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
        self._template_obj_cache = {}
        self._logo_cache = {}
        self._last_hierarchy_obj = None
        self._fast_cap_state = None
        self._last_resolution_key = None
        self._built_voxel_resolution = None
        self._startup_draft_pending = True
        # Newly created objects (via Init) should evaluate inline — only
        # objects deserialized from disk benefit from deferring.
        self._deferred_first_build_pending = False
        self._interactive_preview_active = False
        self._interactive_preview_desc_id = -1
        self._interactive_preview_log_key = None
        self._interactive_last_edit_at = 0.0
        self._interactive_last_desc_id = -1
        self._last_prune_warning_key = None
        self._resolution_live_timer = None
        self._resolution_live_timer_op = None
        self._bind_records = None
        self._bind_cache_key = None
        self._bind_diagnostics = None
        self._bind_force_rebind = False
        self._auto_hidden_guids = set()
        try:
            op[BRICKIFYASSEMBLY_BIND_TO_SOURCE_DEFORMATION] = False
            op[BRICKIFYASSEMBLY_BIND_REFERENCE_FRAME] = 0
            op[BRICKIFYASSEMBLY_BIND_ORIENTATION_MODE] = BRICKIFYASSEMBLY_BIND_ORIENT_WORLD_UP
            op[BRICKIFYASSEMBLY_BIND_STRETCH_CULL_RATIO] = 0.6
            op[BRICKIFYASSEMBLY_BIND_ORIENT_SMOOTHING] = 0.7
        except Exception:
            pass
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

    def _make_fit_key(self, op, params):
        return _fit_make_fit_key(self, op, params)

    def _source_state_key(self, source_obj):
        return _logo_link_identity_key(source_obj)

    def _make_voxel_key(self, op, params, stud_size, plate_size):
        return _fit_make_voxel_key(self, op, params, stud_size, plate_size)

    def _get_cached_source_arrays(self, op, doc, force_csto=False):
        return _fit_get_cached_source_arrays(self, op, doc, force_csto=force_csto)

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

    def _get_proxy_template_mesh(
        self,
        brick_type,
        stud_size,
        plate_size,
        *,
        inset=0.0,
        force_smooth_top=False,
        simplified=False,
    ):
        return _template_get_proxy_template_mesh(
            self,
            brick_type,
            stud_size,
            plate_size,
            inset=inset,
            force_smooth_top=force_smooth_top,
            simplified=simplified,
        )

    def _create_proxy_mograph_handoff(self, op):
        return _build_proxy_mograph_handoff(self, op)

    def _swap_proxy_to_render_handoff(self, op):
        return _swap_proxy_mograph_handoff(self, op)

    def _create_rs_color_material(self, op):
        return _build_rs_color_material(self, op)

    def _build_hierarchy(self, op):
        return _build_view_hierarchy(self, op)

    def _build_integrated_mograph_hierarchy(self, op, params=None):
        return _build_integrated_mograph_hierarchy_impl(self, op, params=params)

    def _apply_cap_subset_fast_path(self, op, params=None):
        return _apply_cap_subset_fast_path_impl(self, op, params=params)

    def _apply_integrated_mograph_animation_fast_path(self, op, params=None):
        return _apply_integrated_mograph_animation_fast_path_impl(self, op, params=params)

    def GetVirtualObjects(self, op, hh):
        return _runtime_get_virtual_objects(self, op, hh)
