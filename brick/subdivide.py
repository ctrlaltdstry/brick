"""Catmull-Clark subdivision -- one iteration produces a smoother control
mesh; two or three iterations approach the limit surface.

This is here purely to VERIFY that brick_geom's output is SubD-ready: a
single iteration should turn the blocky control mesh into a brick with
visible fillets. In production you'd let C4D's HyperNURBS modifier do
this at render time; we never actually run subdivision in the pipeline.

Implementation note: any face count is fine (triangles, quads, n-gons).
Output is always all-quads.
"""
from collections import defaultdict
from typing import Tuple
import numpy as np
from .mesh import Mesh


def catmull_clark(mesh: Mesh, iterations: int = 1) -> Mesh:
    out = mesh
    for _ in range(iterations):
        out = _one_iter(out)
    return out


def _one_iter(mesh: Mesh) -> Mesh:
    V = mesh.vertices.copy()
    n_v = len(V)
    faces = mesh.faces

    # 1. Face points
    face_points = np.array([
        V[list(f)].mean(axis=0) for f in faces
    ])

    # 2. Edges -> list of faces sharing each edge
    edge_face = defaultdict(list)
    for fi, f in enumerate(faces):
        n = len(f)
        for i in range(n):
            a, b = f[i], f[(i + 1) % n]
            key = (min(a, b), max(a, b))
            edge_face[key].append(fi)

    # 3. Edge points: (V_a + V_b + face_pts) / total
    edge_point_of = {}
    for (a, b), fids in edge_face.items():
        if len(fids) == 2:
            ep = (V[a] + V[b] + face_points[fids[0]] + face_points[fids[1]]) / 4.0
        else:  # boundary edge
            ep = (V[a] + V[b]) / 2.0
        edge_point_of[(a, b)] = ep

    # 4. Updated original vertex positions
    # For each original vertex:
    #   F = average of face points of faces touching V
    #   R = average of edge midpoints (NOT edge points) of edges touching V
    #   n = number of faces touching V
    #   V' = (F + 2R + (n - 3)V) / n
    vert_faces = defaultdict(list)
    vert_edges = defaultdict(set)
    for fi, f in enumerate(faces):
        n = len(f)
        for i in range(n):
            v = f[i]
            vert_faces[v].append(fi)
            a, b = f[i], f[(i + 1) % n]
            vert_edges[v].add((min(a, b), max(a, b)))

    new_V = V.copy()
    for v in range(n_v):
        fids = vert_faces.get(v, [])
        eids = vert_edges.get(v, set())
        if not fids:
            continue
        F = face_points[fids].mean(axis=0)
        edge_mids = np.array([(V[a] + V[b]) / 2.0 for (a, b) in eids])
        R = edge_mids.mean(axis=0)
        n = len(fids)
        new_V[v] = (F + 2 * R + (n - 3) * V[v]) / n

    # 5. Build new faces. Indices: original verts use 0..n_v-1,
    #    face points use n_v..n_v+n_f-1, edge points use n_v+n_f...
    n_f = len(faces)
    edge_index = {}
    edge_points = []
    for ek, ep in edge_point_of.items():
        edge_index[ek] = n_v + n_f + len(edge_points)
        edge_points.append(ep)

    new_verts = np.vstack([new_V, face_points,
                           np.array(edge_points) if edge_points else np.zeros((0, 3))])
    new_faces = []
    new_groups = {g: [] for g in mesh.groups.keys()}
    face_to_group = {}
    for g, indices in mesh.groups.items():
        for i in indices:
            face_to_group[i] = g

    next_face_idx = 0
    for fi, f in enumerate(faces):
        n = len(f)
        fp_idx = n_v + fi
        for i in range(n):
            v_curr = f[i]
            v_prev = f[(i - 1) % n]
            v_next = f[(i + 1) % n]
            ep_prev = edge_index[(min(v_prev, v_curr), max(v_prev, v_curr))]
            ep_next = edge_index[(min(v_curr, v_next), max(v_curr, v_next))]
            quad = (v_curr, ep_next, fp_idx, ep_prev)
            new_faces.append(quad)
            if fi in face_to_group:
                new_groups[face_to_group[fi]].append(next_face_idx)
            next_face_idx += 1

    out = Mesh(vertices=new_verts, faces=new_faces, groups=new_groups)
    return out
