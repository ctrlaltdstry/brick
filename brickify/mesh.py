"""Mesh data structures shared by brick_geom, svg_logo, and mesh_export.

We use a deliberately simple in-memory representation:

  - vertices: (N, 3) numpy array
  - faces:    list of polygons, each a tuple of vertex indices (any length >= 3)
  - groups:   dict mapping a group name (e.g. "body", "studs", "logo") to
              the list of face indices belonging to that group

This lets us keep everything in one mesh with one vertex array, while still
allowing each region to be a separately selectable "polygon island" on
import (Cinema 4D, Blender, Maya all read OBJ polygon groups this way).

QUAD-FIRST: every routine in brick_geom emits 4-vertex faces wherever
practical. Caps for cylindrical features (stud tops) emit a single
n-gon rather than a triangle fan, because n-gons subdivide cleanly under
Catmull-Clark while triangle fans introduce poles.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import numpy as np


@dataclass
class Mesh:
    vertices: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    faces: List[Tuple[int, ...]] = field(default_factory=list)
    groups: Dict[str, List[int]] = field(default_factory=dict)

    @property
    def num_verts(self) -> int:
        return len(self.vertices)

    @property
    def num_faces(self) -> int:
        return len(self.faces)

    def add_group_face(self, group: str, face_verts: Tuple[int, ...]):
        if group not in self.groups:
            self.groups[group] = []
        self.groups[group].append(len(self.faces))
        self.faces.append(tuple(int(v) for v in face_verts))

    def append_verts(self, verts: np.ndarray) -> int:
        """Append vertices and return the index of the FIRST new vertex."""
        if len(self.vertices) == 0:
            base = 0
            self.vertices = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
        else:
            base = len(self.vertices)
            self.vertices = np.vstack(
                [self.vertices, np.asarray(verts, dtype=np.float64).reshape(-1, 3)]
            )
        return base

    def merge(self, other: "Mesh", transform: np.ndarray = None,
              group_prefix: str = "") -> None:
        """Merge another mesh into this one, optionally applying a 4x4 affine
        transform and prefixing all group names. The other mesh's faces are
        offset by our current vertex count."""
        offset = self.num_verts
        v = other.vertices
        if transform is not None:
            v_h = np.hstack([v, np.ones((len(v), 1))])
            v = (v_h @ transform.T)[:, :3]
        self.vertices = (np.vstack([self.vertices, v])
                         if len(self.vertices) else v.copy())
        # remap faces
        face_remap_base = self.num_faces
        for f in other.faces:
            self.faces.append(tuple(int(i) + offset for i in f))
        for g, indices in other.groups.items():
            new_g = (group_prefix + g) if group_prefix else g
            self.groups.setdefault(new_g, []).extend(
                face_remap_base + i for i in indices
            )

    def stats(self) -> str:
        quads = sum(1 for f in self.faces if len(f) == 4)
        tris = sum(1 for f in self.faces if len(f) == 3)
        ngons = sum(1 for f in self.faces if len(f) > 4)
        return (f"{self.num_verts} verts, {self.num_faces} faces "
                f"({quads} quads / {tris} tris / {ngons} ngons), "
                f"{len(self.groups)} groups")

    def weld_vertices(self, tol: float = 1e-4) -> "Mesh":
        """Merge coincident vertices (within `tol` distance) and remap
        all face indices. Removes degenerate faces (where 2+ verts of a
        face collapse to the same merged vertex).

        Returns self for chaining.
        """
        if len(self.vertices) == 0:
            return self
        # Quantize vertex positions to `tol` precision.
        scale = 1.0 / tol
        keys = np.round(self.vertices * scale).astype(np.int64)
        # Build a map from key -> first occurrence index
        key_strings = [tuple(k.tolist()) for k in keys]
        old_to_new = np.zeros(len(self.vertices), dtype=np.int64)
        seen = {}
        new_verts = []
        for old_i, k in enumerate(key_strings):
            if k in seen:
                old_to_new[old_i] = seen[k]
            else:
                new_idx = len(new_verts)
                seen[k] = new_idx
                old_to_new[old_i] = new_idx
                new_verts.append(self.vertices[old_i])
        self.vertices = np.array(new_verts)
        # Remap faces, dropping degenerates.
        new_faces = []
        new_groups: Dict[str, List[int]] = {g: [] for g in self.groups}
        old_face_to_new = {}
        for old_fi, face in enumerate(self.faces):
            new_face = tuple(int(old_to_new[v]) for v in face)
            # Drop consecutive duplicates (e.g., (a, b, b, c) -> (a, b, c))
            dedup = [new_face[0]]
            for v in new_face[1:]:
                if v != dedup[-1]:
                    dedup.append(v)
            # Drop face if first==last after dedup
            if len(dedup) >= 2 and dedup[0] == dedup[-1]:
                dedup = dedup[:-1]
            if len(dedup) < 3:
                continue
            old_face_to_new[old_fi] = len(new_faces)
            new_faces.append(tuple(dedup))
        self.faces = new_faces
        # Remap groups
        for g, indices in self.groups.items():
            new_groups[g] = [old_face_to_new[i] for i in indices
                             if i in old_face_to_new]
        self.groups = new_groups
        return self


def affine_translate(t: np.ndarray) -> np.ndarray:
    """Return a 4x4 translation matrix."""
    M = np.eye(4)
    M[:3, 3] = t
    return M


def affine_rotate_y(angle_deg: float) -> np.ndarray:
    """Return a 4x4 rotation about the Y axis."""
    a = np.deg2rad(angle_deg)
    c, s = np.cos(a), np.sin(a)
    M = np.eye(4)
    M[0, 0], M[0, 2] = c, s
    M[2, 0], M[2, 2] = -s, c
    return M


def affine_scale(sx: float, sy: float = None, sz: float = None) -> np.ndarray:
    if sy is None: sy = sx
    if sz is None: sz = sx
    M = np.eye(4)
    M[0, 0], M[1, 1], M[2, 2] = sx, sy, sz
    return M
