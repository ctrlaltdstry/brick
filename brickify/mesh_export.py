"""OBJ writer that preserves quads (and n-gons) and emits polygon groups.

C4D, Blender, and Maya all read 'g <name>' directives in OBJ as separate
selectable polygon islands within a single object, which is exactly what
the artist wants here ("the whole brick would be combined into one object
but the logo is selectable").

Writes nothing else -- no normals, no UVs, no materials -- so the importer
is free to recompute smoothing groups on its own. This is intentional;
auto-generated normals from a SubD-ready control cage are usually wrong
(they point outward from the SHARP control mesh, not the smooth limit
surface), so it's better to recompute after subdivision in C4D.
"""
from typing import Iterable, Optional
from .mesh import Mesh


def write_obj(mesh: Mesh, path: str, *, object_name: str = "brick") -> None:
    """Write a Mesh to an OBJ file. Preserves quads and n-gons -- no
    triangulation. Emits 'g <group>' directives so each polygon group is
    selectable on import.
    """
    with open(path, "w") as f:
        f.write(f"# brickify -- generated quad-modeled brick\n")
        f.write(f"# {mesh.stats()}\n")
        f.write(f"o {object_name}\n")
        for v in mesh.vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        # group faces by group name; faces not in any group go in default
        face_to_group = {}
        for g, indices in mesh.groups.items():
            for i in indices:
                face_to_group[i] = g
        # emit faces in group order so 'g' transitions are clean
        for g in sorted(set(face_to_group.values())):
            f.write(f"g {g}\n")
            f.write(f"s 1\n")  # smoothing group on; importer can override
            for i, face in enumerate(mesh.faces):
                if face_to_group.get(i) != g:
                    continue
                # OBJ uses 1-based indices
                f.write("f " + " ".join(str(v + 1) for v in face) + "\n")
        # Faces in no group:
        leftover = [i for i in range(len(mesh.faces)) if i not in face_to_group]
        if leftover:
            f.write("g default\n")
            for i in leftover:
                face = mesh.faces[i]
                f.write("f " + " ".join(str(v + 1) for v in face) + "\n")


def write_obj_assembly(meshes_with_transforms, path: str,
                       object_name: str = "assembly",
                       group_prefix_fn=None) -> Mesh:
    """Merge a list of (Mesh, 4x4 transform, optional group_prefix) entries
    into one Mesh and write it as a single OBJ. Returns the merged Mesh.

    group_prefix_fn(idx, mesh) -> str  : optional callback to compute a
    per-brick prefix (e.g. so groups become 'brick_007/body' etc.). If not
    provided, a numeric prefix is used.
    """
    from .mesh import Mesh as _Mesh
    out = _Mesh()
    for idx, item in enumerate(meshes_with_transforms):
        if len(item) == 3:
            m, T, prefix = item
        else:
            m, T = item
            prefix = (group_prefix_fn(idx, m) if group_prefix_fn
                      else f"brick_{idx:04d}/")
        out.merge(m, transform=T, group_prefix=prefix)
    write_obj(out, path, object_name=object_name)
    return out
