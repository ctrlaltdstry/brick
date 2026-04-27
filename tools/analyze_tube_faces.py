"""Find all faces that touch outer-tube-perim verts at the tube TOP (Y=+0.00365)."""
import sys

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
    # Outer ring at tube TOP (Y=+0.00365), tube center (0, +0.00365, -0.004), R~0.00322
    import math
    target_y = +0.00365
    cx, cz = 0.0, -0.004
    R_outer = 0.00322
    R_inner = 0.00237
    tol_y = 5e-5
    tol_r = 5e-5

    outer_set = set()
    inner_set = set()
    for i, (vx, vy, vz) in enumerate(verts):
        if abs(vy - target_y) > tol_y:
            continue
        d = math.hypot(vx - cx, vz - cz)
        if abs(d - R_outer) < tol_r:
            outer_set.add(i)
        elif abs(d - R_inner) < tol_r:
            inner_set.add(i)

    print(f"OUTER ring verts at Y={target_y}: {len(outer_set)}")
    print(f"INNER ring verts at Y={target_y}: {len(inner_set)}")

    print("\nFaces using outer-ring verts (3+ outer verts):")
    seen = 0
    for fi, face in enumerate(faces):
        outer_in_face = sum(1 for v in face if v in outer_set)
        inner_in_face = sum(1 for v in face if v in inner_set)
        if outer_in_face >= 2 or inner_in_face >= 2:
            seen += 1
            if seen > 30:
                continue
            tags = []
            for v in face:
                if v in outer_set:
                    tags.append(f"O{v+1}")
                elif v in inner_set:
                    tags.append(f"I{v+1}")
                else:
                    vx, vy, vz = verts[v]
                    tags.append(f"v{v+1}(y={vy:+.5f})")
            print(f"  f{fi}: {' '.join(tags)}")
    print(f"\nTotal faces touching ring: {seen}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "c:/Users/Mike/brick2x3.obj")
