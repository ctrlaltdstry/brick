"""Generate a single brick via brickify.brick_geom_hires.make_brick_hires
and write it as an OBJ in the project root.

Defaults match the 'hero' preset used to produce brick_2x3_hero_4.obj
(2x3 footprint, 3 plates tall).

  python tools/export_hires_brick.py
  python tools/export_hires_brick.py --width 4 --depth 2 --height 3
  python tools/export_hires_brick.py --quality standard --tag prefix
"""
import argparse
import os
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    sys.path.insert(0, project_root)
    sys.path.insert(0, os.path.join(project_root, "BrickGen"))

    from quality_presets import QUALITY_PRESETS_BY_NAME

    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=2)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--height", type=int, default=3, help="height in plates")
    ap.add_argument("--quality", choices=list(QUALITY_PRESETS_BY_NAME), default="hero")
    ap.add_argument("--tag", default="filletfix")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from brick.brick_geom_hires import make_brick_hires
    from brick.mesh_export import write_obj

    kwargs = dict(QUALITY_PRESETS_BY_NAME[args.quality])
    mesh = make_brick_hires(args.width, args.depth, args.height, **kwargs)

    out = args.out or os.path.join(
        project_root,
        f"brick_{args.width}x{args.depth}_h{args.height}_{args.quality}_{args.tag}.obj",
    )
    write_obj(mesh, out, object_name=f"brick_{args.width}x{args.depth}")
    print(f"wrote {out}")
    print(f"  verts: {len(mesh.vertices)}  faces: {len(mesh.faces)}")


if __name__ == "__main__":
    main()
