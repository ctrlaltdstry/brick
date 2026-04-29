"""Run the C4D plugin's build_brick() outside C4D and export to OBJ."""
import os
import sys

# Make sibling package importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.plugin_headless import load_plugin_module, build_brick_mesh


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
    mod = load_plugin_module()
    mesh = build_brick_mesh(mod, 2, 3, 3, quality="hero", piece_type="brick")
    print(mesh.stats())
    out = "test_brick_2x3x3.obj"
    export_obj(mesh, out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
