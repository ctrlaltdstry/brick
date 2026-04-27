"""Visualize the X,Z positions of vertices around a stud."""
import sys
import math


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


def show_y_layer(verts, y_target, cx, cz, R, title):
    print(f"\n=== {title} (Y~{y_target:+.6f}) ===")
    pts = []
    for i, (vx, vy, vz) in enumerate(verts):
        if abs(vy - y_target) > 1e-5:
            continue
        d = math.hypot(vx - cx, vz - cz)
        if d > R:
            continue
        pts.append((i, vx - cx, vz - cz, d))

    pts.sort(key=lambda p: math.atan2(p[2], p[1]))
    print(f"  count={len(pts)}")
    for i, x, z, d in pts:
        ang = math.degrees(math.atan2(z, x))
        print(f"    v#{i+1}  dx={x:+.6f}  dz={z:+.6f}  r={d:.6f}  ang={ang:+7.1f}")


def main(path):
    verts, faces = load(path)
    cx, cz = -0.004, -0.008
    R = 0.0030

    # Top face level
    show_y_layer(verts, 0.0038, cx, cz, 0.005, "TOP FACE region near stud")
    show_y_layer(verts, 0.0048, cx, cz, R, "Stud BASE (top of body fillet rim)")
    show_y_layer(verts, 0.00495, cx, cz, R, "Stud cylinder wall (mid)")
    show_y_layer(verts, 0.00645, cx, cz, R, "Stud top edge (start of cap fillet)")
    show_y_layer(verts, 0.00658, cx, cz, R, "Stud top fillet ring 2")
    show_y_layer(verts, 0.00660, cx, cz, R, "Stud top FACE (Y=ymax)")

    # And below (top face fillet)
    show_y_layer(verts, 0.003819, cx, cz, R, "Top face fillet at stud base (Y=0.003819)")
    show_y_layer(verts, 0.003950, cx, cz, R, "Top face fillet at stud base (Y=0.003950)")
    show_y_layer(verts, 0.004500, cx, cz, R, "Top face fillet at stud base (Y=0.004500)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "c:/Users/Mike/brick2x3.obj")
