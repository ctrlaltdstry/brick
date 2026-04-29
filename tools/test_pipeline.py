"""Smoke test for brick.pipeline.

Loads tools/test_inputs/monkey.obj, runs the full pipeline at low
resolution, and prints stats. No C4D.

  python tools/test_pipeline.py
  python tools/test_pipeline.py --studs 32 --no-prune
"""
import argparse
import os
import sys
import time


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    sys.path.insert(0, project_root)

    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.path.join(here, "test_inputs", "monkey.obj"))
    ap.add_argument("--studs", type=int, default=16, help="target studs across longest XZ axis")
    ap.add_argument("--mode", choices=["solid", "shell"], default="solid")
    ap.add_argument("--no-merge", action="store_true")
    ap.add_argument("--no-prune", action="store_true")
    args = ap.parse_args()

    from brick.voxelize import load_obj
    from brick.pipeline import brick_mesh

    print(f"Loading {args.input}")
    verts, faces, vcols = load_obj(args.input)
    print(f"  {len(verts)} verts, {len(faces)} faces, vertex_colors={'yes' if vcols is not None else 'no'}")

    t0 = time.time()
    placements, info = brick_mesh(
        verts, faces,
        vertex_colors=vcols,
        studs_across=args.studs,
        voxel_mode=args.mode,
        merge_plates=not args.no_merge,
        prune_connectivity=not args.no_prune,
    )
    dt = time.time() - t0

    print(f"\nPipeline complete in {dt:.2f}s")
    print(f"  stud_size:  {info['stud_size']:.3f} mesh-units")
    print(f"  plate_size: {info['plate_size']:.3f} mesh-units")
    print(f"  grid_dims:  {info['grid_dims']}")
    print(f"  origin:     {info['origin']}")
    print(f"  placements: {info['n_placed']}")
    print(f"  dropped:    {info['n_dropped']} (connectivity prune)")

    conn = info["connectivity"]
    print(f"  components: {conn['n_components']} (largest = {conn['largest_component_size']})")
    print(f"  articulation points: {conn['n_articulation_points']}")

    # brick-type histogram
    from collections import Counter
    type_counts = Counter(
        (p.brick.width, p.brick.depth, p.brick.height) for p in placements
    )
    print(f"\nTop brick types:")
    for (w, d, h), n in type_counts.most_common(10):
        print(f"  {w}x{d}x{h}p  -> {n}")


if __name__ == "__main__":
    main()
