"""Run BrickGen's build_brick() outside of C4D.

The .pyp imports `c4d` at module load only for the plugin shell at the
bottom of the file; mesh generation itself is pure Python + numpy +
brick.mesh. We stub `c4d` so the module import succeeds, then invoke
build_brick and write an OBJ via brick.mesh_export.
"""
import argparse
import os
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)

    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=2)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--height", type=int, default=3, help="height in plates")
    ap.add_argument("--quality", choices=["draft", "standard", "hero"], default="hero")
    ap.add_argument("--piece-type", choices=["brick", "plate"], default="brick")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    sys.path.insert(0, project_root)
    from tools.plugin_headless import load_plugin_module, build_brick_mesh

    mod = load_plugin_module()
    mesh = build_brick_mesh(
        mod,
        args.width,
        args.depth,
        args.height,
        quality=args.quality,
        piece_type=args.piece_type,
    )

    from brick.mesh_export import write_obj
    out = args.out or os.path.join(
        project_root,
        f"brick_{args.width}x{args.depth}_h{args.height}_filletfix.obj",
    )
    write_obj(mesh, out, object_name=f"brick_{args.width}x{args.depth}")
    print(f"wrote {out}")
    print(f"  verts: {len(mesh.vertices)}  faces: {len(mesh.faces)}")


if __name__ == "__main__":
    main()
