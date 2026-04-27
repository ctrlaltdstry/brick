"""Find the 6 underside indents and side support ribs in brick2x3.obj.

Strategy:
- Read all vertices.
- Cluster by (x, z) within a tolerance to find vertical "columns" of verts;
  this reveals features like ribs that are local in (x, z) but extend in y.
- Print Y-range histograms grouped by (rough x bucket, rough z bucket) to
  expose ribs (thin x/z extent, large y extent).
- Find circular vertex rings on the underside (Y near ceiling level) that are
  not the big tubes — these will be the small indents.
"""
import os
import sys
from collections import defaultdict


REF_OBJ = r"c:\Users\Mike\brick2x3.obj"


def load_obj_verts(path):
    verts = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("v "):
                continue
            parts = line.split()
            x, y, z = (float(parts[1]), float(parts[2]), float(parts[3]))
            verts.append((x * 1000.0, y * 1000.0, z * 1000.0))
    return verts


def main():
    verts = load_obj_verts(REF_OBJ)
    print(f"loaded {len(verts)} verts")
    if not verts:
        return

    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    print(
        f"X range: {min(xs):.2f} .. {max(xs):.2f}\n"
        f"Y range: {min(ys):.2f} .. {max(ys):.2f}\n"
        f"Z range: {min(zs):.2f} .. {max(zs):.2f}"
    )

    # Histogram Y values to find horizontal feature levels.
    by_y = defaultdict(int)
    for (_, y, _) in verts:
        ykey = round(y, 2)
        by_y[ykey] += 1
    sorted_y = sorted(by_y.items(), key=lambda x: x[0])
    print("\nY histogram (Y -> count). Look for spikes = horizontal rings:")
    for y, c in sorted_y:
        if c >= 12:
            print(f"  Y={y:7.2f}  count={c}")

    # Find rings on the underside cavity ceiling (Y near second-to-top-bottom).
    # We assume Y=0 is bottom of brick, Y_max is top of brick.
    y_min = min(ys)
    y_max = max(ys)
    print(f"\ny_min={y_min:.2f}  y_max={y_max:.2f}")

    # On a brick, the cavity ceiling sits at roughly y_min + (brick_height - ceiling_th).
    # For a 1-plate brick (h=3.2mm) cavity ceiling would be near y_max - 1.2.
    # For a 3-plate brick (h=9.6mm), ceiling near 9.6 - 1.2 = 8.4 ABOVE bottom.
    # In ref OBJ, brick2x3.obj is likely a regular 1-plate-tall (or 3-plate-tall)?
    # Y range will tell us.
    print("\nVerts at distinct y levels closest to ceiling (top-most "
          "underside-facing surface):")

    # Pick the underside y level: largest count of verts NOT at brick-top (which
    # is for studs only). Look for the top-third counts.
    threshold = (y_min + y_max) / 2
    print(f"\nVerts on the lower half (y < {threshold:.2f}):")
    lower_y = sorted({round(y, 2) for (_, y, _) in verts if y < threshold})
    for ylvl in lower_y:
        n = sum(1 for (_, y, _) in verts if abs(y - ylvl) < 0.01)
        if n >= 8:
            print(f"  Y={ylvl:7.2f}  count={n}")

    # For potential side ribs: look for short vertical chains of verts at the
    # same (x, z) within the inner-wall region.
    print("\n--- SIDE RIB DETECTION ---")
    print("Looking for narrow vertical bands of 3+ verts at distinct (x, z):")
    columns = defaultdict(list)
    for (x, y, z) in verts:
        key = (round(x, 1), round(z, 1))
        columns[key].append(y)
    interesting = []
    for (xz, ys_list) in columns.items():
        ys_sorted = sorted(ys_list)
        if len(ys_sorted) < 3:
            continue
        spread = ys_sorted[-1] - ys_sorted[0]
        if spread > 1.0:
            interesting.append((xz, len(ys_sorted), spread, ys_sorted))
    interesting.sort(key=lambda v: -v[1])
    print(f"top columns by vertex count:")
    for (xz, n, spread, _) in interesting[:30]:
        print(f"  (x={xz[0]:6.2f}, z={xz[1]:6.2f})  n={n}  Y-spread={spread:.2f}")


if __name__ == "__main__":
    main()
