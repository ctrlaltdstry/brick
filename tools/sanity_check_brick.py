"""Sanity-check BrickGen headless mesh manifoldness and orientation."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.plugin_headless import load_plugin_module, build_brick_mesh

mod = load_plugin_module()


def check(width, depth, height, *, quality="hero", piece_type="brick"):
    print(f"\n=== Brick {width}x{depth}x{height} ({piece_type}, {quality}) ===")
    mesh = build_brick_mesh(
        mod, width, depth, height, quality=quality, piece_type=piece_type
    )
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--depth", type=int, default=None)
    ap.add_argument("--height", type=int, default=None, help="height in plates")
    ap.add_argument("--quality", choices=["draft", "standard", "hero"], default="hero")
    ap.add_argument("--piece-type", choices=["brick", "plate"], default="brick")
    args = ap.parse_args()

    if args.width is not None and args.depth is not None and args.height is not None:
        check(
            args.width,
            args.depth,
            args.height,
            quality=args.quality,
            piece_type=args.piece_type,
        )
    else:
        check(2, 3, 3, quality=args.quality, piece_type=args.piece_type)
        check(1, 4, 1, quality=args.quality, piece_type=args.piece_type)
        check(2, 2, 1, quality=args.quality, piece_type=args.piece_type)
