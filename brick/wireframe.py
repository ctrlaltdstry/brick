"""Wireframe rendering for verifying quad topology.

Uses matplotlib to draw the edges of every face. Quads are blue,
triangles are red, n-gons are green -- so the artist can spot non-quad
faces at a glance.
"""
from typing import Optional
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
from .mesh import Mesh


COLORS = {
    3: "#cc4444",  # red for triangles
    4: "#3060a8",  # blue for quads
}
NGON = "#33aa55"  # green for n-gons


def render_wireframe(
    mesh: Mesh,
    path: str,
    *,
    title: str = "",
    elev: float = 22,
    azim: float = -55,
    show_filled: bool = False,
    highlight_groups: Optional[dict] = None,  # {group_name: rgb_color}
):
    """Render all edges of every face. Optionally fill with translucent
    color per group (highlight_groups) so the viewer can see which faces
    belong to which polygon group.
    """
    fig = plt.figure(figsize=(11, 9), dpi=120)
    ax = fig.add_subplot(111, projection="3d")
    # Use orthographic projection so circular cross-sections (stud cylinders)
    # display as actual circles instead of being distorted by matplotlib's
    # default perspective camera.
    ax.set_proj_type("ortho")
    # bbox-aware aspect
    if len(mesh.vertices):
        mn, mx = mesh.vertices.min(axis=0), mesh.vertices.max(axis=0)
        size = mx - mn
        # matplotlib axes: mpl_X = world X,  mpl_Y = world Z,  mpl_Z = world Y
        ax.set_box_aspect((size[0] + 1e-6, size[2] + 1e-6, size[1] + 1e-6))
        ax.set_xlim(mn[0], mx[0])
        ax.set_ylim(mn[2], mx[2])
        ax.set_zlim(mn[1], mx[1])

    def to_mpl(p):
        return (p[0], p[2], p[1])

    # Build edges + (optionally) fills
    if show_filled and highlight_groups:
        face_to_color = {}
        for g, color in highlight_groups.items():
            for fi in mesh.groups.get(g, []):
                face_to_color[fi] = color
        polys, polycolors = [], []
        for fi, face in enumerate(mesh.faces):
            if fi not in face_to_color:
                continue
            polys.append([to_mpl(mesh.vertices[v]) for v in face])
            polycolors.append(face_to_color[fi])
        if polys:
            pc = Poly3DCollection(polys, facecolors=polycolors,
                                  edgecolor="none", alpha=0.45)
            ax.add_collection3d(pc)

    edges_q, edges_t, edges_n = [], [], []
    for face in mesh.faces:
        n = len(face)
        verts = [to_mpl(mesh.vertices[v]) for v in face]
        edges = [[verts[i], verts[(i + 1) % n]] for i in range(n)]
        if n == 3:
            edges_t.extend(edges)
        elif n == 4:
            edges_q.extend(edges)
        else:
            edges_n.extend(edges)

    if edges_q:
        ax.add_collection3d(Line3DCollection(edges_q, colors=COLORS[4],
                                             linewidths=0.7))
    if edges_t:
        ax.add_collection3d(Line3DCollection(edges_t, colors=COLORS[3],
                                             linewidths=0.9))
    if edges_n:
        ax.add_collection3d(Line3DCollection(edges_n, colors=NGON,
                                             linewidths=0.8))

    ax.set_xlabel("X")
    ax.set_ylabel("Z")
    ax.set_zlabel("Y -- up")
    ax.set_title(title or mesh.stats())
    ax.view_init(elev=elev, azim=azim)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight")
    plt.close(fig)
