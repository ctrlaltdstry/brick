"""Run the C4D plugin's build_sds_brick() outside C4D and export to OBJ."""
import sys
import os
import math
import importlib.util

# Make sibling 'brickify' package importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub c4d module so the .pyp imports work
class _CStub:
    pass

c4d_stub = _CStub()
c4d_stub.plugins = _CStub()
c4d_stub.plugins.ObjectData = object
c4d_stub.plugins.RegisterObjectPlugin = lambda **k: None
c4d_stub.PolygonObject = lambda *a, **k: None
c4d_stub.CPolygon = lambda *a, **k: None
c4d_stub.Vector = lambda *a, **k: None
c4d_stub.OBJECT_GENERATOR = 0
c4d_stub.COPYFLAGS_NONE = 0
c4d_stub.MSG_UPDATE = 0
c4d_stub.Tpolygonselection = 0
sys.modules['c4d'] = c4d_stub
c4d_module = c4d_stub

# Don't stub c4d_symbols -- let the plugin's fallback path run.


def load_pyp_as_module(path):
    import importlib.machinery
    loader = importlib.machinery.SourceFileLoader("c4d_brick_generator", path)
    spec = importlib.util.spec_from_loader("c4d_brick_generator", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def export_obj(mesh, path):
    """Write mesh to OBJ with one polygon group (g) per brickify group."""
    with open(path, "w") as f:
        f.write("# brickify test export\n")
        for v in mesh.vertices:
            f.write(f"v {float(v[0]):.6f} {float(v[1]):.6f} {float(v[2]):.6f}\n")
        # group faces
        face_to_group = {}
        for g, indices in mesh.groups.items():
            for fi in indices:
                face_to_group[fi] = g
        last_g = None
        for fi, face in enumerate(mesh.faces):
            g = face_to_group.get(fi, "default")
            if g != last_g:
                f.write(f"g {g}\n")
                last_g = g
            f.write("f " + " ".join(str(v + 1) for v in face) + "\n")


def main():
    plugin_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "c4d_brick_generator.pyp",
    )
    mod = load_pyp_as_module(plugin_path)
    mesh = mod.build_sds_brick(2, 3, 3)
    print(mesh.stats())
    out = "test_brick_2x3x3.obj"
    export_obj(mesh, out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
