"""Run c4d_brick_generator.pyp's build_sds_brick() outside of C4D.

The .pyp imports `c4d` at module load only for the plugin shell at the
bottom of the file; build_sds_brick() itself is pure Python + numpy +
brickify.mesh. We stub `c4d` so the module import succeeds, then invoke
build_sds_brick and write an OBJ via brickify.mesh_export.
"""
import argparse
import importlib.util
import os
import sys
import types


def _install_c4d_stubs():
    c4d = types.ModuleType("c4d")
    plugins = types.ModuleType("c4d.plugins")

    class _Stub:
        def __init__(self, *a, **kw):
            pass

        def __call__(self, *a, **kw):
            return self

        def __getattr__(self, name):
            return _Stub()

    plugins.ObjectData = type("ObjectData", (), {"__init__": lambda self, *a, **kw: None})
    plugins.RegisterObjectPlugin = lambda *a, **kw: True
    c4d.plugins = plugins

    for name in (
        "Vector", "PolygonObject", "CPolygon", "BaseObject",
        "Tpolygonselection", "MSG_UPDATE", "OBJECT_GENERATOR",
    ):
        setattr(c4d, name, _Stub())

    sys.modules["c4d"] = c4d
    sys.modules["c4d.plugins"] = plugins


def _load_pyp(path):
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("c4d_brick_generator", path)
    spec = importlib.util.spec_from_loader("c4d_brick_generator", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)

    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=2)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--height", type=int, default=3, help="height in plates")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    sys.path.insert(0, project_root)
    _install_c4d_stubs()

    pyp = os.path.join(project_root, "c4d_brick_generator.pyp")
    mod = _load_pyp(pyp)

    mesh = mod.build_sds_brick(args.width, args.depth, args.height)

    from brickify.mesh_export import write_obj
    out = args.out or os.path.join(
        project_root,
        f"brick_{args.width}x{args.depth}_h{args.height}_filletfix.obj",
    )
    write_obj(mesh, out, object_name=f"brick_{args.width}x{args.depth}")
    print(f"wrote {out}")
    print(f"  verts: {len(mesh.vertices)}  faces: {len(mesh.faces)}")


if __name__ == "__main__":
    main()
