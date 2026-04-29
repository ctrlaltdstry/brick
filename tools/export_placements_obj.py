"""Export brick placements as a colored OBJ for inspection in C4D / Blender.

Each placement becomes a box. Colors:
  gray   = normal placement
  red    = 1x1 placements (potential filler artifacts)
  yellow = orphans dropped by connectivity prune
  cyan   = "low-Y short-coverage" suspects (placement at y < 6 with y+h < 6)

Usage:
    python tools/export_placements_obj.py empire_state.obj 12 placements.obj
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_obj(path):
    verts, faces = [], []
    with open(path) as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                verts.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idxs = [int(p.split("/")[0]) - 1 for p in line.split()[1:]]
                for i in range(1, len(idxs) - 1):
                    faces.append([idxs[0], idxs[i], idxs[i + 1]])
    return np.asarray(verts), np.asarray(faces)


def box_obj(x0, y0, z0, sx, sy, sz):
    """Return 8 verts, 12 tris for a box. Verts in CCW order per face."""
    v = [
        (x0, y0, z0), (x0 + sx, y0, z0), (x0 + sx, y0, z0 + sz), (x0, y0, z0 + sz),
        (x0, y0 + sy, z0), (x0 + sx, y0 + sy, z0),
        (x0 + sx, y0 + sy, z0 + sz), (x0, y0 + sy, z0 + sz),
    ]
    f = [
        (0, 2, 1), (0, 3, 2),  # bottom
        (4, 5, 6), (4, 6, 7),  # top
        (0, 1, 5), (0, 5, 4),  # -z
        (2, 3, 7), (2, 7, 6),  # +z
        (1, 2, 6), (1, 6, 5),  # +x
        (3, 0, 4), (3, 4, 7),  # -x
    ]
    return v, f


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "empire_state.obj"
    studs = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    out = sys.argv[3] if len(sys.argv) > 3 else "placements.obj"

    from brick.pipeline import brick_mesh, auto_stud_size
    from brick.connectivity import prune_to_largest_component

    verts, faces = load_obj(src)
    stud = auto_stud_size(verts, studs)
    plate = stud * (3.2 / 8.0)

    # Run pipeline WITHOUT prune so we can mark the orphans separately.
    placements, info = brick_mesh(
        verts, faces,
        studs_across=studs,
        voxel_mode="solid",
        merge_plates=True,
        merge_horizontal=True,
        prune_connectivity=False,
        min_column_voxels=3,
    )
    kept, dropped = prune_to_largest_component(placements)
    dropped_ids = {id(p) for p in dropped}

    origin = info["origin"]
    print(f"  {len(placements)} placements ({len(dropped)} orphans by prune)")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", out)
    with open(out_path, "w") as f:
        f.write(f"# brick placements at studs_across={studs}\n")
        f.write(f"# stud={stud:.4f} plate={plate:.4f}\n")
        f.write("mtllib placements.mtl\n")
        v_offset = 1
        groups = {
            "gray":   ([], (0.55, 0.55, 0.55)),
            "red":    ([], (0.95, 0.20, 0.20)),
            "yellow": ([], (0.95, 0.85, 0.10)),
            "cyan":   ([], (0.20, 0.80, 0.95)),
        }
        for p in placements:
            x = origin[0] + p.x * stud
            y = origin[1] + p.y * plate
            z = origin[2] + p.z * stud
            sx = p.w * stud
            sy = p.h * plate
            sz = p.d * stud
            verts_b, faces_b = box_obj(x, y, z, sx, sy, sz)
            # classify
            if id(p) in dropped_ids:
                cat = "yellow"
            elif p.brick.width == 1 and p.brick.depth == 1:
                cat = "red"
            elif p.y < 6 and (p.y + p.h) <= 6:
                cat = "cyan"
            else:
                cat = "gray"
            groups[cat][0].append((verts_b, faces_b, v_offset))
            v_offset += len(verts_b)

        # write verts in group order so usemtl groupings stay coherent
        all_v = []
        for cat, (entries, _col) in groups.items():
            for vs, fs, off in entries:
                for vx, vy, vz in vs:
                    all_v.append(f"v {vx:.4f} {vy:.4f} {vz:.4f}\n")
        f.writelines(all_v)
        running_off = 1
        for cat, (entries, _col) in groups.items():
            f.write(f"\ng {cat}\nusemtl {cat}\n")
            for vs, fs, _off in entries:
                for a, b, c in fs:
                    f.write(f"f {running_off+a} {running_off+b} {running_off+c}\n")
                running_off += len(vs)

    mtl_path = os.path.join(os.path.dirname(out_path), "placements.mtl")
    with open(mtl_path, "w") as f:
        for cat, (_e, col) in groups.items():
            f.write(f"newmtl {cat}\nKd {col[0]} {col[1]} {col[2]}\nKa 0 0 0\nKs 0 0 0\nillum 1\n\n")

    print(f"wrote {out_path}")
    counts = {cat: len(e[0]) for cat, e in groups.items()}
    print(f"  counts: {counts}")


if __name__ == "__main__":
    main()
