"""Diagnose the voxelization of a source OBJ at a given studs_across.

Reports mesh stats, voxel grid contents, per-column distribution,
brick fit summary, and exports a debug OBJ of the voxel mass.

Usage:
    python tools/diagnose_voxelize.py empire_state.obj 12
"""
import sys
import os
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brickify.voxelize import voxelize_mesh  # noqa: E402
from brickify.pipeline import auto_stud_size  # noqa: E402


def load_obj(path):
    verts = []
    faces = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                parts = line.split()[1:]
                idxs = [int(p.split("/")[0]) - 1 for p in parts]
                # triangulate fan
                for i in range(1, len(idxs) - 1):
                    faces.append([idxs[0], idxs[i], idxs[i + 1]])
    return np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def main():
    obj_path = sys.argv[1] if len(sys.argv) > 1 else "empire_state.obj"
    studs_across = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    verts, faces = load_obj(obj_path)
    print(f"OBJ: {obj_path}")
    print(f"  verts: {len(verts):,}  faces: {len(faces):,}")
    bbox_min = verts.min(axis=0)
    bbox_max = verts.max(axis=0)
    print(f"  bbox min: {bbox_min}")
    print(f"  bbox max: {bbox_max}")
    extent = bbox_max - bbox_min
    print(f"  extent:   {extent}")

    stud = auto_stud_size(verts, studs_across)
    plate = stud * (3.2 / 8.0)
    print(f"\nStuds across: {studs_across}")
    print(f"  stud_size:  {stud:.4f}")
    print(f"  plate_size: {plate:.4f}")

    # voxelize in solid mode
    occ_solid, _, origin = voxelize_mesh(
        verts, faces,
        mode="solid",
        stud_size=stud,
        plate_size=plate,
    )
    occ_shell, _, _ = voxelize_mesh(
        verts, faces,
        mode="shell",
        stud_size=stud,
        plate_size=plate,
    )
    print(f"\nGrid dims: {occ_solid.shape}")
    print(f"  surface (shell) voxels: {occ_shell.sum():,}")
    print(f"  solid voxels:           {occ_solid.sum():,}")
    print(f"  interior-only:          {(occ_solid & ~occ_shell).sum():,}")

    # per-column height (along Y)
    col_count = occ_solid.sum(axis=1)  # (Nx, Nz)
    col_count_nonzero = col_count[col_count > 0]
    if len(col_count_nonzero):
        print(f"\nPer-column voxel count (occupied columns only):")
        print(f"  min={col_count_nonzero.min()}  "
              f"max={col_count_nonzero.max()}  "
              f"mean={col_count_nonzero.mean():.1f}  "
              f"median={int(np.median(col_count_nonzero))}")
        # histogram
        bins = [0, 1, 2, 3, 4, 6, 10, 20, 50, 1_000_000]
        hist, _ = np.histogram(col_count_nonzero, bins=bins)
        print("  histogram:")
        for lo, hi, n in zip(bins[:-1], bins[1:], hist):
            label = f"  [{lo:>4}..{hi:>5})"
            bar = "#" * min(60, n // max(1, hist.max() // 60))
            print(f"  {label}: {n:>6,} {bar}")

    # connected component analysis on the SOLID volume
    labels, n_comp = ndimage.label(occ_solid, structure=np.ones((3, 3, 3)))
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0  # background
    print(f"\nSolid 3D connected components: {n_comp}")
    if n_comp:
        # top 10 by size
        order = np.argsort(sizes)[::-1]
        for i, idx in enumerate(order[:10]):
            if sizes[idx] == 0:
                break
            print(f"  comp {idx:>3}: {sizes[idx]:>8,} voxels")

    # Bottom layer analysis — do we have voxels right at y=0 that don't
    # connect upward? That'd be a ground-plane-style ring.
    y0 = occ_solid[:, 0, :]
    print(f"\nBottom Y=0 layer:")
    print(f"  occupied (x,z) cells at y=0: {y0.sum():,}")
    # cells at y=0 whose column has count == 1: pure ground plane voxels
    y0_pure = y0 & (col_count == 1)
    print(f"  of which only-1-voxel columns: {y0_pure.sum():,}")
    y0_short = y0 & (col_count <= 3)
    print(f"  of which <=3-voxel columns:    {y0_short.sum():,}")

    # Where are the short columns located? (might be a ring around base)
    if (col_count <= 3).any() and (col_count > 0).any():
        short_mask = (col_count > 0) & (col_count <= 3)
        ix, iz = np.where(short_mask)
        if len(ix):
            print(f"\n  short columns ({len(ix)} total):")
            for i, k in zip(ix, iz):
                ys_with_voxels = np.where(occ_solid[i, :, k])[0]
                print(f"    (x={i:>2}, z={k:>2})  count={col_count[i,k]:>3}  "
                      f"y-range=[{ys_with_voxels.min()}..{ys_with_voxels.max()}]")

    # Per-Y-slice occupied area
    print(f"\nOccupied (x,z) cells per Y slice (every 10th level):")
    Ny = occ_solid.shape[1]
    for j in range(0, Ny, max(1, Ny // 12)):
        slice_count = occ_solid[:, j, :].sum()
        bar = "#" * min(50, slice_count // 4)
        print(f"  y={j:>3}: {slice_count:>4} cells  {bar}")

    # Run the actual pipeline to see brick-type distribution
    from brickify.pipeline import brickify_mesh
    print("\nRunning full pipeline (NO prune, NO merge) ...")
    placements_raw, info_raw = brickify_mesh(
        verts, faces,
        studs_across=studs_across,
        voxel_mode="solid",
        merge_plates=False,
        prune_connectivity=False,
        min_column_voxels=3,
    )
    print(f"  raw: {len(placements_raw)} placements")

    print("\nRunning full pipeline (with prune+merge) ...")
    placements, info = brickify_mesh(
        verts, faces,
        studs_across=studs_across,
        voxel_mode="solid",
        merge_plates=True,
        prune_connectivity=True,
        min_column_voxels=3,
    )
    print(f"  {len(placements)} placements, "
          f"dropped {info['n_dropped']} by prune")
    # brick type histogram
    from collections import Counter
    type_counts = Counter(
        (p.brick.width, p.brick.depth, p.brick.height) for p in placements
    )
    print("  brick types (top 15):")
    for (w, d, h), n in type_counts.most_common(15):
        print(f"    {w}x{d}x{h}p : {n:>5}")
    # Y distribution of placements
    y_hist = Counter(p.y for p in placements)
    print("  placements per Y level (kept):")
    for y in sorted(y_hist):
        n = y_hist[y]
        bar = "#" * min(50, n)
        print(f"    y={y:>3}: {n:>4}  {bar}")

    # 1x1 plates / bricks: where are they?
    print("\n  1x1 placements (any height) by Y:")
    onex_hist = Counter(p.y for p in placements
                        if p.brick.width == 1 and p.brick.depth == 1)
    for y in sorted(onex_hist):
        n = onex_hist[y]
        bar = "#" * min(50, n)
        print(f"    y={y:>3}: {n:>4}  {bar}")


if __name__ == "__main__":
    main()
