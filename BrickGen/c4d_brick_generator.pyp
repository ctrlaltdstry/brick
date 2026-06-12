"""Cinema 4D plugin entry point for Brick and BrickIt."""
import os
import sys

import c4d
from c4d import plugins

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)


def _register_log_enabled():
    return os.environ.get("BRICKIT_LOG_REGISTER", "").strip().lower() not in ("", "0", "false", "no")


def _register_log(message):
    if _register_log_enabled():
        print(message)

from c4d_symbols import *  # noqa: F401,F403 - re-exported for headless tools.
from brickgen_object import BrickGen
from brickit.brickit_object import BrickAssembly
from library_panel import BRICK_TOGGLE_NAMES
from mesh_bridge import build_brick, mesh_to_polygon_object  # noqa: F401 - compatibility API.


# =====================================================================
# Icon registration helpers
# =====================================================================

def _load_bitmap(path):
    """Return a BaseBitmap from `path`, or None if it can't be loaded."""
    if not path or not os.path.isfile(path):
        return None
    bmp = c4d.bitmaps.BaseBitmap()
    bmp.InitWith(path)
    if bmp.GetBw() <= 0 or bmp.GetBh() <= 0:
        return None
    return bmp


def _register_brick_icons():
    """Register the hero banner icon and brick thumbnails so the
    description's BITMAPBUTTONs can resolve their ICONIDs."""
    here = os.path.dirname(os.path.abspath(__file__))
    res_dir = os.path.join(here, "res")
    icons_dir = os.path.join(res_dir, "icons", "bricks")

    # Hero banner — used by the BITMAPBUTTON at the top of the AM.
    hero_path = os.path.join(res_dir, "brickify_hero.png")
    hero_bmp = _load_bitmap(hero_path)
    if hero_bmp is not None:
        try:
            c4d.gui.RegisterIcon(ICON_BRICKIFY_HERO, hero_bmp)
        except Exception as exc:
            _register_log("[brick] hero icon register failed: {0}".format(exc))
    else:
        _register_log("[brick] hero banner not found at {0}".format(hero_path))

    # Brick thumbnails. Use the @64 variants for crisper rendering on
    # high-DPI displays — C4D scales down to the AM's row height.
    for i, name in enumerate(BRICK_TOGGLE_NAMES):
        for suffix in ("@64", "@2x", ""):
            candidate = os.path.join(icons_dir, "{0}{1}.png".format(name, suffix))
            if os.path.isfile(candidate):
                bmp = _load_bitmap(candidate)
                if bmp is not None:
                    try:
                        c4d.gui.RegisterIcon(ICON_BRICKIFY_BRICK_BASE + i, bmp)
                    except Exception as exc:
                        _register_log(
                            "[brick] icon {0} register failed: {1}".format(name, exc)
                        )
                break
        else:
            _register_log("[brick] brick thumbnail missing: {0}".format(name))


def register():
    def _load_first_existing(*candidates):
        """Return the first BaseBitmap that loads from `candidates`, or None.

        Used so each plugin can fall back through @2x → @64 → plain
        variants without a separate try/except per call site.
        """
        for path in candidates:
            bmp = _load_bitmap(path)
            if bmp is not None:
                return bmp
        return None

    here = os.path.dirname(os.path.abspath(__file__))
    icons_root = os.path.join(here, "res", "icons")

    def _load_brick_object_icon():
        # Object Manager icon for the legacy Brick generator (single brick,
        # ID_BRICKGENERATOR). Dedicated brick_object.png replaces the older
        # red 2x2 thumbnail-fallback chain.
        return _load_first_existing(
            os.path.join(icons_root, "brick_object@2x.png"),
            os.path.join(icons_root, "brick_object.png"),
            # Legacy fallbacks for deployments that don't have the new icon yet.
            os.path.join(here, "res", "brickify_icon.png"),
            os.path.join(icons_root, "bricks", "brick_2x2@64.png"),
            os.path.join(icons_root, "bricks", "brick_2x2@2x.png"),
            os.path.join(icons_root, "bricks", "brick_2x2.png"),
        )

    def _load_brickit_object_icon():
        # Object Manager icon for the BrickIt generator (assembly /
        # ID_BRICKIFYASSEMBLY). Distinct icon so users can tell at a
        # glance which object type they have selected.
        return _load_first_existing(
            os.path.join(icons_root, "brickit_object@2x.png"),
            os.path.join(icons_root, "brickit_object.png"),
            # Legacy fallback to the same chain as the Brick generator.
            os.path.join(here, "res", "brickify_icon.png"),
        )

    # Register brick thumbnail icons FIRST so the description widgets can
    # resolve them on first AM display.
    try:
        _register_brick_icons()
    except Exception as exc:
        _register_log("[brick] icon registration error: {0}".format(exc))

    # Pre-import the brick package + numpy/scipy chain at plugin register
    # time. Without this, the very first GetVirtualObjects evaluation after
    # opening a project pays ~1s of network-share import latency on the
    # main thread, blocking the Object Manager. Doing it here folds the
    # cost into C4D's startup splash screen instead.
    try:
        from plugin_bootstrap import ensure_brick_on_path
        ensure_brick_on_path()
        import brick.pipeline  # noqa: F401 - warm import
        import brick.fitter    # noqa: F401 - warm import
        import brick.voxelize  # noqa: F401 - warm import
    except Exception as exc:
        _register_log("[brick] preimport failed (deferring to first eval): {0}".format(exc))

    brick_icon = _load_brick_object_icon()
    brickit_icon = _load_brickit_object_icon()
    ok1 = plugins.RegisterObjectPlugin(
        id=ID_BRICKGENERATOR,
        str=IDS_BRICKGENERATOR,
        g=BrickGen,
        description="obrickgenerator",
        info=c4d.OBJECT_GENERATOR,
        icon=brick_icon,
    )
    ok2 = plugins.RegisterObjectPlugin(
        id=ID_BRICKIFYASSEMBLY,
        str=IDS_BRICKIFYASSEMBLY,
        g=BrickAssembly,
        description="obrickifyassembly",
        info=c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT,
        icon=brickit_icon,
    )
    # BrickLibraryPanelCommand is intentionally not registered as a standalone
    # command plugin. The library UI is kept embedded in BrickIt's Attribute
    # Manager instead of showing a separate "Brick Panel" plugin entry.
    try:
        from brickit.brickit_effectors_autohook import register as _register_brickit_autohook
        _register_brickit_autohook()
    except Exception as exc:
        _register_log("[brick] BrickIt effectors auto-hook register failed: {0}".format(exc))
    try:
        from plugin_bootstrap import brick_log as _bs_brick_log
    except Exception:
        _bs_brick_log = None
    try:
        from brickit.brickit_follow_surface_tag import BrickitFollowSurfaceTag
        # Register here (not in the package submodule) because
        # RegisterTagPlugin reads `__res__` from the calling module's
        # globals — only the .pyp module has it auto-injected.
        follow_surface_icon = _load_first_existing(
            os.path.join(icons_root, "brickit_follow_surface_tag@2x.png"),
            os.path.join(icons_root, "brickit_follow_surface_tag.png"),
            # Legacy fallback for older deployments.
            os.path.join(here, "res", "follow_surface_icon.png"),
        ) or brickit_icon
        result = plugins.RegisterTagPlugin(
            id=ID_BRICKIT_FOLLOW_SURFACE_TAG,
            str=IDS_BRICKIT_FOLLOW_SURFACE_TAG,
            g=BrickitFollowSurfaceTag,
            description="Tbrickitfollowsurface",
            info=c4d.TAG_VISIBLE | c4d.TAG_EXPRESSION,
            icon=follow_surface_icon,
        )
        msg = "[brick] BrickIt Follow Surface tag register returned: {0}".format(result)
        _register_log(msg)
        if _bs_brick_log is not None:
            try:
                _bs_brick_log(msg)
            except Exception:
                pass
    except Exception as exc:
        import traceback
        msg = "[brick] BrickIt Follow Surface tag register failed: {0}\n{1}".format(
            exc, traceback.format_exc()
        )
        _register_log(msg)
        if _bs_brick_log is not None:
            try:
                _bs_brick_log(msg)
            except Exception:
                pass

    # Cubify Cache tag — auto-created by Bake Fit Cache, holds the per-frame
    # cache blob. Registered TAG_VISIBLE only (no TAG_EXPRESSION = no Execute
    # = zero per-frame cost; it's a passive data store).
    try:
        from brickit.brickit_cache_tag import CubifyCacheTag
        cache_tag_icon = _load_first_existing(
            os.path.join(icons_root, "brickit_object@2x.png"),
            os.path.join(icons_root, "brickit_object.png"),
        ) or brickit_icon
        cache_result = plugins.RegisterTagPlugin(
            id=ID_CUBIFY_CACHE_TAG,
            str=IDS_CUBIFY_CACHE_TAG,
            g=CubifyCacheTag,
            description="Tcubifycache",
            info=c4d.TAG_VISIBLE,
            icon=cache_tag_icon,
        )
        _register_log(
            "[brick] Cubify Cache tag register returned: {0}".format(cache_result)
        )
    except Exception as exc:
        import traceback
        _register_log(
            "[brick] Cubify Cache tag register failed: {0}\n{1}".format(
                exc, traceback.format_exc()
            )
        )

    # Parameter help registration is disabled — both `RegisterPluginHelpDelegate`
    # and `RegisterPluginHelpCallback` crashed C4D 2026 on right-click → Show
    # Help, even with a Bool-returning delegate that opens its own dialog. The
    # registry content lives in `BrickGen/brickit_help.py` for when we figure
    # out the correct binding (likely an HTML-files-in-plugins/Brick/help/
    # path rather than a Python callback).
    return ok1 and ok2


if __name__ == "__main__":
    register()
