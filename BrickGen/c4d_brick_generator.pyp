"""Cinema 4D plugin entry point for Brick and BrickIt."""
import os
import sys

import c4d
from c4d import plugins

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from c4d_symbols import *  # noqa: F401,F403 - re-exported for headless tools.
from brickgen_object import BrickGen
from brickit_object import BrickAssembly
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
            print("[brick] hero icon register failed:", exc)
    else:
        print("[brick] hero banner not found at", hero_path)

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
                        print(
                            "[brick] icon {0} register failed: {1}"
                            .format(name, exc)
                        )
                break
        else:
            print("[brick] brick thumbnail missing:", name)


def register():
    def _load_plugin_icon():
        # The Object Manager tree shows this next to every BrickAssembly
        # / Brick entry. brickify_icon.png is the dedicated 64x64
        # red 2x2 brick render produced by tools/prepare_branding_assets.py;
        # the isometric thumbnails are the AM gallery fallback for older
        # deployments that don't have the rendered icon yet.
        here = os.path.dirname(os.path.abspath(__file__))
        for candidate in (
            os.path.join(here, "res", "brickify_icon.png"),
            os.path.join(here, "res", "icons", "bricks", "brick_2x2@64.png"),
            os.path.join(here, "res", "icons", "bricks", "brick_2x2@2x.png"),
            os.path.join(here, "res", "icons", "bricks", "brick_2x2.png"),
        ):
            bmp = _load_bitmap(candidate)
            if bmp is not None:
                return bmp
        return None

    # Register brick thumbnail icons FIRST so the description widgets can
    # resolve them on first AM display.
    try:
        _register_brick_icons()
    except Exception as exc:
        print("[brick] icon registration error:", exc)

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
        print("[brick] preimport failed (deferring to first eval):", exc)

    icon = _load_plugin_icon()
    ok1 = plugins.RegisterObjectPlugin(
        id=ID_BRICKGENERATOR,
        str=IDS_BRICKGENERATOR,
        g=BrickGen,
        description="obrickgenerator",
        info=c4d.OBJECT_GENERATOR,
        icon=icon,
    )
    ok2 = plugins.RegisterObjectPlugin(
        id=ID_BRICKIFYASSEMBLY,
        str=IDS_BRICKIFYASSEMBLY,
        g=BrickAssembly,
        description="obrickifyassembly",
        info=c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT,
        icon=icon,
    )
    # BrickLibraryPanelCommand is intentionally not registered as a standalone
    # command plugin. The library UI is kept embedded in BrickIt's Attribute
    # Manager instead of showing a separate "Brick Panel" plugin entry.
    try:
        from brickit_effectors_autohook import register as _register_brickit_autohook
        _register_brickit_autohook()
    except Exception as exc:
        print("[brick] BrickIt effectors auto-hook register failed:", exc)
    return ok1 and ok2


if __name__ == "__main__":
    register()
