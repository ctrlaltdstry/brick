"""Analyze a reference OBJ file to understand brick topology."""
import sys
from collections import Counter, defaultdict


def main(path):
    verts = []
    faces = []
    with open(path, "r") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif line.startswith("f "):
                parts = line.split()[1:]
                idxs = [int(p.split("/")[0]) - 1 for p in parts]
                faces.append(idxs)

    print(f"verts: {len(verts)}")
    print(f"faces: {len(faces)}")

    # Bounds
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    print(f"bounds X: [{min(xs):.6f}, {max(xs):.6f}]  W={max(xs)-min(xs):.6f}")
    print(f"bounds Y: [{min(ys):.6f}, {max(ys):.6f}]  H={max(ys)-min(ys):.6f}")
    print(f"bounds Z: [{min(zs):.6f}, {max(zs):.6f}]  D={max(zs)-min(zs):.6f}")

    # Face counts by size
    sizes = Counter(len(f) for f in faces)
    print(f"face sizes: {sorted(sizes.items())}")

    # Histogram of Y values to find layers
    y_buckets = Counter()
    for y in ys:
        y_buckets[round(y, 6)] += 1
    print(f"\nDistinct Y levels (top 20 by count):")
    for y, c in sorted(y_buckets.items(), key=lambda x: -x[1])[:20]:
        print(f"  Y={y:+.6f}  count={c}")
    print(f"\nTotal distinct Y values: {len(y_buckets)}")

    # Sorted Y levels
    print(f"\nAll distinct Y values sorted:")
    for y in sorted(y_buckets.keys()):
        print(f"  Y={y:+.6f}  count={y_buckets[y]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "c:/Users/Mike/brick2x3.obj")
