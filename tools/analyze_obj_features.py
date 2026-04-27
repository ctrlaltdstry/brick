"""Detailed feature-based analysis of a reference brick OBJ."""
import sys
import math
from collections import Counter, defaultdict


def load(path):
    verts = []
    faces = []
    with open(path, "r") as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idxs = [int(p.split("/")[0]) - 1 for p in line.split()[1:]]
                faces.append(idxs)
    return verts, faces


def main(path):
    verts, faces = load(path)
    print(f"verts={len(verts)} faces={len(faces)}")

    # Bounds
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    zmin, zmax = min(zs), max(zs)
    print(f"X: [{xmin:.6f}, {xmax:.6f}]")
    print(f"Y: [{ymin:.6f}, {ymax:.6f}]")
    print(f"Z: [{zmin:.6f}, {zmax:.6f}]")

    # Stud spacing for 2x3 = 8mm
    # Stud center positions (X = -4mm, +4mm; Z = -8, 0, +8mm) in real Lego scale
    # In this OBJ scale, 8mm = 0.008
    # X: -0.0078 to 0.0078, range 0.0156 = 2 * 0.008 ✓
    # Z: -0.0117 to 0.0117, range 0.0234 = 3 * 0.008 - 0.0006 (small inset)
    # Stud centers should be:
    # X: -0.004, +0.004
    # Z: -0.008, 0, +0.008

    stud_centers = []
    for cx in (-0.004, 0.004):
        for cz in (-0.008, 0.0, 0.008):
            stud_centers.append((cx, cz))
    print(f"\nStud centers: {stud_centers}")

    # For one stud (cx=-0.004, cz=-0.008), find vertices in cylinder around it
    cx, cz = -0.004, -0.008
    R = 0.0035  # search radius (typical stud radius is 0.0024)
    near_stud = []
    for i, (vx, vy, vz) in enumerate(verts):
        # Only consider Y >= 0 (top half of brick)
        if vy < 0.0 - 0.0001:
            continue
        d = math.hypot(vx - cx, vz - cz)
        if d <= R:
            near_stud.append((i, vx, vy, vz, d))

    print(f"\n=== Vertices near stud at ({cx:.4f}, {cz:.4f}) within R={R} ===")
    print(f"Count: {len(near_stud)}")

    # Group by Y level
    y_groups = defaultdict(list)
    for i, x, y, z, d in near_stud:
        y_groups[round(y, 6)].append((i, x, y, z, d))

    print(f"Y levels around this stud:")
    for y in sorted(y_groups.keys()):
        ds = [g[4] for g in y_groups[y]]
        print(f"  Y={y:+.6f}  count={len(y_groups[y])}  d_range=[{min(ds):.6f}, {max(ds):.6f}]")

    # Look at top-of-body region vs stud base in detail
    print("\n=== Distinct radii at each Y level near stud ===")
    for y in sorted(y_groups.keys()):
        ds = sorted(set(round(g[4], 6) for g in y_groups[y]))
        print(f"  Y={y:+.6f}  radii: {ds}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "c:/Users/Mike/brick2x3.obj")
