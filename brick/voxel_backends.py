"""Voxel backend dispatch for mesh -> brick assembly.

The internal numpy voxelizer remains the production backend. The C4D Volume
backend is exposed as an experimental option so the plugin UI and cache path
can be wired before native volume sampling is implemented.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from .voxelize import voxelize_mesh


VOXEL_BACKEND_INTERNAL = "internal"
VOXEL_BACKEND_C4D_VOLUME = "c4d_volume"


def normalize_voxel_backend(value: Optional[str]) -> str:
    key = str(value or VOXEL_BACKEND_INTERNAL).strip().lower()
    if key in ("c4d", "c4d_volume", "cinema4d_volume", "volume"):
        return VOXEL_BACKEND_C4D_VOLUME
    return VOXEL_BACKEND_INTERNAL


def voxelize_with_backend(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    backend: str = VOXEL_BACKEND_INTERNAL,
    vertex_colors: Optional[np.ndarray] = None,
    face_colors: Optional[np.ndarray] = None,
    default_color: Tuple[int, int, int] = (180, 180, 180),
    mode: str = "solid",
    shell_thickness: int = 1,
    stud_size: float,
    plate_size: float,
    min_column_voxels: int = 0,
    cleanup_protrusions: int = 0,
    preserve_silhouette: bool = False,
    preserve_tiny_gaps: bool = False,
):
    backend_key = normalize_voxel_backend(backend)

    # Placeholder for the next implementation step. Falling back keeps the
    # experimental UI selectable without breaking current BrickIt builds.
    if backend_key == VOXEL_BACKEND_C4D_VOLUME:
        occupancy, colors, origin = voxelize_mesh(
            vertices,
            faces,
            vertex_colors=vertex_colors,
            face_colors=face_colors,
            default_color=default_color,
            mode=mode,
            shell_thickness=shell_thickness,
            stud_size=stud_size,
            plate_size=plate_size,
            min_column_voxels=min_column_voxels,
            cleanup_protrusions=cleanup_protrusions,
            preserve_silhouette=preserve_silhouette,
            preserve_tiny_gaps=preserve_tiny_gaps,
        )
        return occupancy, colors, origin, {
            "voxel_backend": VOXEL_BACKEND_INTERNAL,
            "voxel_backend_requested": VOXEL_BACKEND_C4D_VOLUME,
            "voxel_backend_fallback": True,
            "voxel_backend_note": "C4D Volume backend is not implemented yet; using Internal.",
        }

    occupancy, colors, origin = voxelize_mesh(
        vertices,
        faces,
        vertex_colors=vertex_colors,
        face_colors=face_colors,
        default_color=default_color,
        mode=mode,
        shell_thickness=shell_thickness,
        stud_size=stud_size,
        plate_size=plate_size,
        min_column_voxels=min_column_voxels,
        cleanup_protrusions=cleanup_protrusions,
        preserve_silhouette=preserve_silhouette,
        preserve_tiny_gaps=preserve_tiny_gaps,
    )
    return occupancy, colors, origin, {
        "voxel_backend": VOXEL_BACKEND_INTERNAL,
        "voxel_backend_requested": VOXEL_BACKEND_INTERNAL,
        "voxel_backend_fallback": False,
        "voxel_backend_note": "",
    }
