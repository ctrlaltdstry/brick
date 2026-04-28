"""Generate small isometric thumbnails for every brick in DEFAULT_LIBRARY.

Used by the C4D plugin's "Brick Library" UI section so each on/off toggle
shows what the user is enabling.

Why isometric line art and not real renders?
- Plate vs brick height needs to read at 32 px without lighting.
- The plugin loads these every time the AM rebuilds the description; a
  full render pipeline (matplotlib / rasterizer) would be overkill.

Output:
    BrickGen/res/icons/bricks/<brick_name>.png   (24x24, RGBA)
    BrickGen/res/icons/bricks/<brick_name>@64.png (64x64, RGBA)
"""
from __future__ import annotations
import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from PIL import Image, ImageDraw  # noqa: E402

from brick.library import DEFAULT_LIBRARY  # noqa: E402


OUT_DIR = os.path.join(REPO_ROOT, "BrickGen", "res", "icons", "bricks")


# Iso projection: 30-degree axes for X/Z, vertical for Y.
COS30 = math.cos(math.radians(30.0))
SIN30 = math.sin(math.radians(30.0))


def iso_project(x: float, y: float, z: float, scale: float, ox: float, oy: float):
    """Standard 30-degree isometric. +X goes down-right, +Z goes down-left."""
    sx = (x - z) * COS30 * scale + ox
    sy = (x + z) * SIN30 * scale - y * scale + oy
    return sx, sy


def plate_color(brick) -> tuple:
    return (215, 30, 35)


def light_color(brick) -> tuple:
    return (255, 110, 110)


def dark_color(brick) -> tuple:
    return (140, 16, 20)


def render_brick(brick, size: int) -> Image.Image:
    """Return an RGBA Image of the brick drawn isometrically."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    w = float(brick.width)
    d = float(brick.depth)
    h = float(brick.height)

    # Find a scale that fits w, d, h into the canvas with a small margin.
    # Iso bbox in screen: width = (w + d) * COS30, height = (w + d) * SIN30 + h
    margin = max(2, size // 10)
    avail = size - 2 * margin
    bbox_w = (w + d) * COS30
    bbox_h_top = (w + d) * SIN30  # to the top edge of the brick top face
    # plates use h = 1 (in plate units), bricks use h = 3.
    # Visual height inside iso bbox: top arc above origin = h, bottom arc + iso below
    bbox_h = bbox_h_top + h
    scale = min(avail / max(bbox_w, 1e-3), avail / max(bbox_h, 1e-3))

    # We want the brick centered.
    # Origin in object space: low corner at (0, 0, 0).
    # Iso projects the box. Find min/max screen coords to center.
    corners_obj = [
        (0, 0, 0), (w, 0, 0), (w, 0, d), (0, 0, d),
        (0, h, 0), (w, h, 0), (w, h, d), (0, h, d),
    ]
    raw = [iso_project(x, y, z, scale, 0.0, 0.0) for (x, y, z) in corners_obj]
    xs = [p[0] for p in raw]
    ys = [p[1] for p in raw]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    ox = size / 2.0 - cx
    oy = size / 2.0 - cy

    def pr(x, y, z):
        return iso_project(x, y, z, scale, ox, oy)

    fill_top = light_color(brick)
    fill_left = plate_color(brick)
    fill_right = dark_color(brick)
    edge = (50, 8, 12, 255)

    # Three visible faces
    top = [pr(0, h, 0), pr(w, h, 0), pr(w, h, d), pr(0, h, d)]
    front_left = [pr(0, 0, 0), pr(0, h, 0), pr(0, h, d), pr(0, 0, d)]
    front_right = [pr(0, 0, d), pr(0, h, d), pr(w, h, d), pr(w, 0, d)]
    # Wait: which two are visible from upper-right iso depends on axis convention.
    # We project +X right-down, +Z left-down. Looking from upper-right-front (-Y up,
    # camera at (+X, +Y, +Z)), the visible faces are:
    #   top (y = h), right (x = w), front (z = d)
    right = [pr(w, 0, 0), pr(w, h, 0), pr(w, h, d), pr(w, 0, d)]
    front = [pr(0, 0, d), pr(0, h, d), pr(w, h, d), pr(w, 0, d)]

    # outline thickness scales with size
    line_w = max(1, size // 32)

    draw.polygon(front, fill=fill_left, outline=edge)
    draw.polygon(right, fill=fill_right, outline=edge)
    draw.polygon(top, fill=fill_top, outline=edge)

    # Edges (re-stroke for crispness)
    edges = (
        ((0, 0, 0), (w, 0, 0)),
        ((w, 0, 0), (w, 0, d)),
        ((w, 0, d), (0, 0, d)),
        ((0, 0, d), (0, 0, 0)),
        ((0, h, 0), (w, h, 0)),
        ((w, h, 0), (w, h, d)),
        ((w, h, d), (0, h, d)),
        ((0, h, d), (0, h, 0)),
        ((0, 0, 0), (0, h, 0)),
        ((w, 0, 0), (w, h, 0)),
        ((w, 0, d), (w, h, d)),
        ((0, 0, d), (0, h, d)),
    )
    for a, b in edges:
        draw.line([pr(*a), pr(*b)], fill=edge, width=line_w)

    # Studs on top
    stud_inset = 0.20
    stud_radius_obj = 0.30
    stud_height_obj = 0.30
    for ix in range(int(w)):
        for iz in range(int(d)):
            cx_obj = ix + 0.5
            cz_obj = iz + 0.5
            # Stud cylinder approximated as an iso ellipse on top + a small skirt.
            # Top ellipse center
            top_cx, top_cy = pr(cx_obj, h + stud_height_obj, cz_obj)
            base_cx, base_cy = pr(cx_obj, h, cz_obj)
            r_screen = stud_radius_obj * scale
            # X-radius and Y-radius for iso ellipse:
            # in iso, a circle on the XZ plane projects to an ellipse with
            # major axis horizontal and ratio sin30/cos30 in y.
            ex = r_screen * COS30 * 1.05
            ey = r_screen * SIN30 * 1.05
            # Skirt (ring connecting top to base) — simple rounded rect band
            draw.ellipse(
                [base_cx - ex, base_cy - ey, base_cx + ex, base_cy + ey],
                fill=plate_color(brick), outline=edge, width=line_w,
            )
            # Filled top
            draw.ellipse(
                [top_cx - ex, top_cy - ey, top_cx + ex, top_cy + ey],
                fill=light_color(brick), outline=edge, width=line_w,
            )

    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Output dir:", OUT_DIR)
    for b in DEFAULT_LIBRARY:
        for size, suffix in ((24, ""), (48, "@2x"), (64, "@64")):
            img = render_brick(b, size)
            path = os.path.join(OUT_DIR, f"{b.name}{suffix}.png")
            img.save(path)
        print(f"  {b.name}: {b.width}x{b.depth}x{b.height}")
    print(f"Wrote {len(DEFAULT_LIBRARY)} bricks (3 sizes each).")


if __name__ == "__main__":
    main()
