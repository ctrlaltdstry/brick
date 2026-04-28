"""Prepare the BRICK branding bitmaps used by the C4D plugin description.

Inputs:
    BRICK source artwork (wide PNG with transparent BG)

Outputs:
    BrickGen/res/brickify_icon.png    (square 64x64, plugin tree icon)
    BrickGen/res/brickify_hero.png    (wide 600x180, banner widget)

The hero banner is shown as a BITMAPBUTTON at the top of the AM. C4D
auto-scales bitmaps in BITMAPBUTTON widgets, but starting from a clean
crisp asset matters because the AM allocates a fixed-height row.
"""
from __future__ import annotations
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from PIL import Image  # noqa: E402


# Hero banner source (BRICK wordmark over blue with clouds).
HERO_SRC = os.path.join(
    REPO_ROOT, "..",
    ".cursor", "projects", "z-02-MKE-2026-BRICK-brickify",
    "assets",
    "c__Users_Mike_AppData_Roaming_Cursor_User_workspaceStorage_"
    "c545476e8620a5425038a13f81650ed9_images_ChatGPT_Image_Apr_27__2026"
    "__08_57_22_AM-9040e83b-146e-4356-a0bc-87a5280828a8.png",
)
# OM-tree icon source (single 2x2 red brick, transparent background).
ICON_SRC = os.path.join(
    REPO_ROOT, "..",
    ".cursor", "projects", "z-02-MKE-2026-BRICK-brickify",
    "assets",
    "c__Users_Mike_AppData_Roaming_Cursor_User_workspaceStorage_"
    "c545476e8620a5425038a13f81650ed9_images_ChatGPT_Image_Apr_27__2026"
    "__12_08_31_AM-8ea4f7f2-b256-4041-84c1-824668c4709b.png",
)
ALT_HERO = os.environ.get("BRICKIFY_HERO_PNG", "")
ALT_ICON = os.environ.get("BRICKIFY_ICON_PNG", "")
RES_DIR = os.path.join(REPO_ROOT, "BrickGen", "res")


def _scan_assets_for(needle: str) -> str:
    """Look in the user's cursor projects assets folder for a PNG whose
    filename contains `needle` and return the most-recently-modified one.
    (When the user iterates an asset, multiple files share the same
    timestamp substring; we want the latest variant.)"""
    asset_dir = os.path.expandvars(
        r"%USERPROFILE%\.cursor\projects\z-02-MKE-2026-BRICK-brickify\assets"
    )
    if not os.path.isdir(asset_dir):
        return ""
    matches = [
        os.path.join(asset_dir, fn)
        for fn in os.listdir(asset_dir)
        if needle in fn and fn.lower().endswith(".png")
    ]
    if not matches:
        return ""
    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return matches[0]


def _resolve(env_value: str, default_path: str, hint: str, needle: str) -> str:
    """Return the first source PNG that exists for `hint`."""
    if env_value and os.path.isfile(env_value):
        return env_value
    norm = os.path.normpath(default_path)
    if os.path.isfile(norm):
        return norm
    found = _scan_assets_for(needle)
    if found:
        return found
    raise FileNotFoundError(
        "{0} source PNG not found. Set BRICKIFY_{1}_PNG to its path."
        .format(hint, hint.upper())
    )


def find_hero() -> str:
    # The hero is the BRICK wordmark on blue with clouds, generated 8:57 AM.
    return _resolve(ALT_HERO, HERO_SRC, "hero", "08_57_22_AM")


def find_icon() -> str:
    # The icon is the standalone red 2x2 brick, generated 12:08 AM.
    return _resolve(ALT_ICON, ICON_SRC, "icon", "12_08_31_AM")


def _trim_transparent(img: Image.Image) -> Image.Image:
    """Crop transparent borders so the brick fills the icon square.

    The artwork has chunky transparent margins; without trimming, the
    brick becomes the centered fifth of the icon at small AM/OM sizes
    and reads as a tiny chip rather than a brick.
    """
    if img.mode != "RGBA":
        return img
    bbox = img.split()[3].getbbox()
    if bbox is None:
        return img
    return img.crop(bbox)


def make_icon(src: Image.Image, target: int = 64) -> Image.Image:
    """Square plugin icon. Trim transparent margins, then scale the brick
    to fit the canvas (preserving aspect ratio with a small breathing
    margin so neighboring entries in the OM tree don't crowd it)."""
    trimmed = _trim_transparent(src)
    pad = max(1, target // 24)
    avail = target - 2 * pad
    w, h = trimmed.size
    s = min(avail / w, avail / h)
    new_w = max(1, int(round(w * s)))
    new_h = max(1, int(round(h * s)))
    scaled = trimmed.resize((new_w, new_h), Image.LANCZOS)
    out = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    ox = (target - new_w) // 2
    oy = (target - new_h) // 2
    out.paste(scaled, (ox, oy), scaled if scaled.mode == "RGBA" else None)
    return out


def make_hero(src: Image.Image, target_w: int = 600, target_h: int = 180) -> Image.Image:
    """Hero banner. Preserve aspect, pad transparent to fixed canvas."""
    src_w, src_h = src.size
    s = min(target_w / src_w, target_h / src_h)
    new_w = max(1, int(src_w * s))
    new_h = max(1, int(src_h * s))
    scaled = src.resize((new_w, new_h), Image.LANCZOS)
    out = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    ox = (target_w - new_w) // 2
    oy = (target_h - new_h) // 2
    out.paste(scaled, (ox, oy), scaled if scaled.mode == "RGBA" else None)
    return out


def main():
    os.makedirs(RES_DIR, exist_ok=True)

    icon_src_path = find_icon()
    print("Icon source:", icon_src_path)
    icon_src = Image.open(icon_src_path).convert("RGBA")
    icon = make_icon(icon_src, 64)
    icon_path = os.path.join(RES_DIR, "brickify_icon.png")
    icon.save(icon_path)
    print("  ->", icon_path)

    hero_src_path = find_hero()
    print("Hero source:", hero_src_path)
    hero_src = Image.open(hero_src_path).convert("RGBA")
    hero = make_hero(hero_src, 600, 180)
    hero_path = os.path.join(RES_DIR, "brickify_hero.png")
    hero.save(hero_path)
    print("  ->", hero_path)


if __name__ == "__main__":
    main()
