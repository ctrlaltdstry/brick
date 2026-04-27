"""Sanity-check the SDS brick mesh for manifoldness and orientation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub c4d
class _S:
    pass
c4d = _S(); c4d.plugins = _S(); c4d.plugins.ObjectData = object
c4d.plugins.RegisterObjectPlugin = lambda **k: None
c4d.PolygonObject = lambda *a, **k: None
c4d.CPolygon = lambda *a, **k: None
c4d.Vector = lambda *a, **k: None
c4d.OBJECT_GENERATOR = c4d.COPYFLAGS_NONE = c4d.MSG_UPDATE = c4d.Tpolygonselection = 0
sys.modules['c4d'] = c4d

import importlib.machinery, importlib.util
plugin_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "c4d_brick_generator.pyp")
loader = importlib.machinery.SourceFileLoader("c4d_brick_generator", plugin_path)
spec = importlib.util.spec_from_loader("c4d_brick_generator", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)


def check(width, depth, height):
    print(f"\n=== Brick {width}x{depth}x{height} ===")
    mesh = mod.build_sds_brick(width, depth, height)
    print(mesh.stats())

    edges = {}  # frozenset((a,b)) -> list of (face_id, dir)  dir=+1 if a->b in face
    for fi, face in enumerate(mesh.faces):
        n = len(face)
        for i in range(n):
            a = int(face[i]); b = int(face[(i+1) % n])
            key = frozenset((a, b))
            edges.setdefault(key, []).append((fi, +1 if a < b else -1, a, b))

    face_to_group = {}
    for g, indices in mesh.groups.items():
        for fi in indices:
            face_to_group[fi] = g

    boundary = 0
    nonmanifold = 0
    flipped = 0
    flipped_groups = {}
    for key, uses in edges.items():
        if len(uses) == 1:
            boundary += 1
        elif len(uses) > 2:
            nonmanifold += 1
        elif len(uses) == 2:
            (f1, _, a1, b1), (f2, _, a2, b2) = uses
            if (a1, b1) == (a2, b2):
                flipped += 1
                pair = tuple(sorted([face_to_group.get(f1, "?"), face_to_group.get(f2, "?")]))
                flipped_groups[pair] = flipped_groups.get(pair, 0) + 1
    print(f"  {len(edges)} edges total")
    print(f"  boundary edges: {boundary}")
    print(f"  non-manifold edges (>2 faces): {nonmanifold}")
    print(f"  flipped (same-direction shared): {flipped}")
    if flipped_groups:
        print(f"  flipped by group pair:")
        for k, v in sorted(flipped_groups.items()):
            print(f"    {k}: {v}")


if __name__ == "__main__":
    check(2, 3, 3)
    check(1, 4, 1)
    check(2, 2, 1)
