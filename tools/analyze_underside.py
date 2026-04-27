"""Analyze the underside (anti-studs and tubes) of the reference OBJ."""
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


def show_y_layer(verts, y_target, cx, cz, R, title, tol=2e-5):
    print(f"\n=== {title} (Y~{y_target:+.6f}, center=({cx:+.4f},{cz:+.4f})) ===")
    pts = []
    for i, (vx, vy, vz) in enumerate(verts):
        if abs(vy - y_target) > tol:
            continue
        d = math.hypot(vx - cx, vz - cz)
        if d > R:
            continue
        pts.append((i, vx - cx, vz - cz, d))

    pts.sort(key=lambda p: math.atan2(p[2], p[1]))
    print(f"  count={len(pts)}  R={R}")
    for i, x, z, d in pts:
        ang = math.degrees(math.atan2(z, x))
        print(f"    v#{i+1}  dx={x:+.6f}  dz={z:+.6f}  r={d:.6f}  ang={ang:+7.1f}")


def main(path):
    verts, faces = load(path)

    # 2x3 brick: studs at (X=±0.004, Z=-0.008/0/+0.008)
    # TUBES are between 4 studs: X=0, Z=-0.004 and Z=+0.004
    print("\n##### TUBES (between 4 studs) #####")
    for tube_z in (-0.004, +0.004):
        # Look at multiple Y levels to understand tube structure
        for y_target in (-0.00475, -0.00465, -0.00450, -0.00400, +0.00100, +0.00300, +0.00350, +0.00365, +0.00370):
            show_y_layer(verts, y_target, 0.0, tube_z, 0.005, f"TUBE@Z={tube_z:+.4f}")

    print("\n##### ANTI-STUDS (under each stud) #####")
    # Just one anti-stud
    cx, cz = -0.004, -0.008
    for y_target in (-0.00465, -0.00450, -0.00400, +0.00350, +0.00365, +0.00370, +0.00380, +0.00400, +0.00450):
        show_y_layer(verts, y_target, cx, cz, 0.0025, f"ANTI-STUD@({cx:+.4f},{cz:+.4f})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "c:/Users/Mike/brick2x3.obj")
