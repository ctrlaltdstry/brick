"""High-level mesh -> BrickPlacements pipeline.

Wraps voxelize -> fit -> (optional merge_plates) -> (optional prune to
largest connected component) into a single call. Pure-numpy in/out so the
C4D plugin layer can drive it without touching c4d-only types.

Usage
-----
    from brick.pipeline import brick_mesh
    placements, info = brick_mesh(
        vertices, faces,
        studs_across=24,
        voxel_mode="solid",
        merge_plates=True,
        prune_connectivity=True,
    )

The returned placements are in grid coordinates: a placement at
(x, y, z) sits at world (x*stud_size, y*plate_size, z*stud_size). The
caller is responsible for placing the assembly back into the source
mesh's frame (the origin is reported in `info["origin"]`).
"""
from typing import List, Optional, Tuple, Dict, Any
import numpy as np
from scipy import ndimage

from .library import BrickLibrary, DEFAULT_LIBRARY
from .palette import LegoPalette
from .fitter import (
    BrickFitter, BrickPlacement,
    merge_plates_to_bricks, merge_plates_horizontal,
)
from .voxelize import voxelize_mesh, STUD_MM, PLATE_RATIO
from .connectivity import prune_to_largest_component, check_connectivity


DETAIL_FIT_SETTINGS = {
    "off": (0, 0),
    # (band width from horizontal silhouette, max footprint in that band)
    "balanced": (1, 6),
    "preserve": (2, 4),
}


def auto_stud_size(vertices: np.ndarray, studs_across: int) -> float:
    """Choose stud_size so the longest horizontal axis spans `studs_across` studs.

    Y is height (vertical), X and Z are the stud axes — only the larger of
    those two determines the brick footprint resolution.
    """
    bbox = vertices.max(axis=0) - vertices.min(axis=0)
    longest_xz = max(float(bbox[0]), float(bbox[2]))
    if longest_xz <= 0.0:
        return 1.0
    return longest_xz / max(1, int(studs_across))


def _detail_mask_from_occupancy(
    occupancy: np.ndarray,
    *,
    band_width: int,
) -> np.ndarray:
    """Mark voxels near per-layer silhouette/groove detail.

    This is intentionally horizontal (X/Z) rather than full 3D surface
    distance: LEGO bricks are placed in horizontal footprints, so the fitter
    needs to know where a large footprint would smear across edges, grooves,
    setbacks, and thin features.
    """
    if band_width <= 0:
        return np.zeros_like(occupancy, dtype=bool)

    Nx, Ny, Nz = occupancy.shape
    mask = np.zeros_like(occupancy, dtype=bool)
    for y in range(Ny):
        layer = occupancy[:, y, :]
        if not layer.any():
            continue
        dist = ndimage.distance_transform_cdt(layer, metric="chessboard")
        mask[:, y, :] = layer & (dist <= band_width)
    return mask


def _placement_shell_depths(
    placements: List[BrickPlacement],
    occupancy: np.ndarray,
) -> List[int]:
    """Return a shell-depth value per placement.

    Depth 1 means the placement touches exterior air; larger values mean it
    sits deeper into a thick shell/solid volume. The depth is computed per
    horizontal layer from flood-filled exterior air, so the inner side of a
    hollow shell does not reset to depth 1 just because it borders the void.
    We use the minimum occupied-cell depth covered by a brick so a brick
    spanning multiple shell layers is colored by its most exterior layer.
    """
    depth_grid = np.zeros(occupancy.shape, dtype=np.int32)
    structure = np.ones((3, 3), dtype=bool)
    for y in range(occupancy.shape[1]):
        layer = occupancy[:, y, :]
        if not layer.any():
            continue
        background = ~layer
        seed = np.zeros_like(layer, dtype=bool)
        seed[0, :] = background[0, :]
        seed[-1, :] = background[-1, :]
        seed[:, 0] |= background[:, 0]
        seed[:, -1] |= background[:, -1]
        exterior_air = ndimage.binary_propagation(
            seed,
            structure=structure,
            mask=background,
        )
        depth_grid[:, y, :] = ndimage.distance_transform_cdt(
            ~exterior_air,
            metric="chessboard",
        )
    depths: List[int] = []
    for p in placements:
        sub = depth_grid[p.x:p.x + p.w, p.y:p.y + p.h, p.z:p.z + p.d]
        vals = sub[sub > 0]
        depths.append(int(vals.min()) if vals.size else 0)
    return depths


def _interior_void_cells(occupancy: np.ndarray) -> List[Tuple[int, int, int]]:
    """Return empty voxels enclosed by the occupied shell per horizontal layer.

    This is for visualization only: it gives C4D a shaded fill for hollow
    interior space, distinct from the shell bricks themselves.
    """
    cells: List[Tuple[int, int, int]] = []
    structure = np.ones((3, 3), dtype=bool)
    for y in range(occupancy.shape[1]):
        layer = occupancy[:, y, :]
        if not layer.any():
            continue
        background = ~layer
        seed = np.zeros_like(layer, dtype=bool)
        seed[0, :] = background[0, :]
        seed[-1, :] = background[-1, :]
        seed[:, 0] |= background[:, 0]
        seed[:, -1] |= background[:, -1]
        exterior_air = ndimage.binary_propagation(
            seed,
            structure=structure,
            mask=background,
        )
        void = background & ~exterior_air
        ix, iz = np.where(void)
        cells.extend((int(x), int(y), int(z)) for x, z in zip(ix, iz))
    return cells


def _prune_voxel_largest_component(
    occupancy: np.ndarray,
) -> Tuple[np.ndarray, int, int]:
    """Keep only the largest 3D-connected occupied voxel component.

    This removes small detached voxel islands early, before fitting/merging,
    which helps avoid stray out-of-bounds brick clusters.
    Returns (pruned_occupancy, n_components, n_voxels_dropped).
    """
    if not occupancy.any():
        return occupancy, 0, 0

    # Use 26-neighborhood so diagonally touching shell voxels stay connected.
    # 6-neighborhood can over-split thin stepped facades into faux islands.
    structure = np.ones((3, 3, 3), dtype=bool)
    labels, n_components = ndimage.label(occupancy, structure=structure)
    if n_components <= 1:
        return occupancy, int(n_components), 0

    counts = np.bincount(labels.ravel())
    if counts.size <= 1:
        return occupancy, int(n_components), 0
    counts[0] = 0  # background
    keep_label = int(np.argmax(counts))
    keep = labels == keep_label
    dropped = int(occupancy.sum() - keep.sum())
    return keep, int(n_components), dropped


def brickify_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    vertex_colors: Optional[np.ndarray] = None,
    face_colors: Optional[np.ndarray] = None,
    default_color: Tuple[int, int, int] = (180, 180, 180),
    studs_across: int = 16,
    stud_size: Optional[float] = None,
    plate_size: Optional[float] = None,
    voxel_mode: str = "solid",
    shell_thickness: int = 1,
    library: Optional[BrickLibrary] = None,
    palette: Optional[LegoPalette] = None,
    max_brick_height: int = 3,
    randomize_heights: bool = False,
    height_mix_seed: int = 1,
    height_mix_amount: float = 0.6,
    merge_plates: bool = True,
    merge_horizontal: bool = True,
    prune_connectivity: bool = True,
    min_column_voxels: int = 0,
    cleanup_protrusions: int = 0,
    detail_mode: str = "off",
    preserve_silhouette: bool = False,
    preserve_tiny_gaps: bool = False,
    surface_only_plates: bool = False,
) -> Tuple[List[BrickPlacement], Dict[str, Any]]:
    """Run the full mesh -> brick placements pipeline.

    Returns
    -------
    placements : list of BrickPlacement (grid coordinates)
    info : dict with
        origin           - (3,) world-space coords of voxel (0,0,0)'s low corner
        stud_size        - resolved stud size (mesh units)
        plate_size       - resolved plate height (mesh units)
        grid_dims        - (Nx, Ny, Nz) voxel-grid size
        n_placed         - number of brick placements
        n_dropped        - number dropped by connectivity pruning (if enabled)
        connectivity     - dict from check_connectivity (pre-prune)
    """
    if stud_size is None:
        stud_size = auto_stud_size(vertices, studs_across)
    if plate_size is None:
        plate_size = stud_size * PLATE_RATIO
    if library is None:
        library = BrickLibrary(list(DEFAULT_LIBRARY))

    occupancy, colors, origin = voxelize_mesh(
        vertices, faces,
        vertex_colors=vertex_colors,
        face_colors=face_colors,
        default_color=default_color,
        mode=voxel_mode,
        shell_thickness=shell_thickness,
        stud_size=stud_size,
        plate_size=plate_size,
        min_column_voxels=min_column_voxels,
        cleanup_protrusions=cleanup_protrusions,
        preserve_silhouette=preserve_silhouette,
        preserve_tiny_gaps=preserve_tiny_gaps,
    )

    # Always remove detached voxel islands before fitting. This is separate
    # from placement-level connectivity pruning (which can be disabled in
    # 1x1-only mode to avoid collapsing columns).
    occupancy, voxel_components, voxel_dropped = _prune_voxel_largest_component(occupancy)

    detail_key = str(detail_mode).lower()
    detail_band, max_detail_footprint = DETAIL_FIT_SETTINGS.get(
        detail_key, DETAIL_FIT_SETTINGS["off"]
    )
    detail_mask = None
    if detail_band > 0 and max_detail_footprint > 0:
        detail_mask = _detail_mask_from_occupancy(
            occupancy,
            band_width=detail_band,
        )

    fitter = BrickFitter(
        library, palette=palette,
        max_brick_height=max_brick_height,
        randomize_heights=randomize_heights,
        height_mix_seed=height_mix_seed,
        height_mix_amount=height_mix_amount,
    )
    placements = fitter.fit(
        occupancy,
        colors,
        detail_mask=detail_mask,
        max_detail_footprint=max_detail_footprint,
        surface_only_plates=surface_only_plates,
    )

    # Surface-only plate policy relies on plate-height "cap" pieces. Do not
    # promote 3-stacks into full bricks in this mode, or studded tops reappear
    # in selected regions after fitting.
    if merge_plates and (not surface_only_plates):
        placements = merge_plates_to_bricks(placements, library)

    if merge_horizontal:
        # Run after the vertical merge so 3-tall bricks formed from plate
        # stacks get combined too (this is what cleans up shoulder rings
        # of 1xN bricks at low resolutions).
        placements = merge_plates_horizontal(placements, library)

    pre_prune_report = check_connectivity(placements)

    n_dropped = 0
    prune_skipped = False
    prune_drop_ratio = 0.0
    if prune_connectivity:
        total_before_prune = max(1, len(placements))
        largest_size = int(pre_prune_report.get("largest_component_size", 0))
        prune_drop_ratio = max(
            0.0,
            1.0 - (float(largest_size) / float(total_before_prune)),
        )

        # Connectivity edges only model direct vertical coupling (top/bottom
        # overlap). For aggressive mixed-size fitting this can fragment an
        # otherwise visually valid shell into many graph components. Avoid
        # deleting big chunks of model geometry in that case; only prune when
        # it's a small tail of disconnected stragglers.
        MAX_SAFE_PRUNE_DROP_RATIO = 0.10
        if prune_drop_ratio <= MAX_SAFE_PRUNE_DROP_RATIO:
            kept, dropped = prune_to_largest_component(placements)
            placements = kept
            n_dropped = len(dropped)
        else:
            prune_skipped = True

    info: Dict[str, Any] = {
        "origin": np.asarray(origin, dtype=np.float64),
        "stud_size": float(stud_size),
        "plate_size": float(plate_size),
        "grid_dims": tuple(int(d) for d in occupancy.shape),
        "n_placed": len(placements),
        "n_dropped": int(n_dropped),
        "connectivity": pre_prune_report,
        "detail_mode": detail_key,
        "preserve_silhouette": bool(preserve_silhouette),
        "preserve_tiny_gaps": bool(preserve_tiny_gaps),
        "surface_only_plates": bool(surface_only_plates),
        "randomize_heights": bool(randomize_heights),
        "height_mix_seed": int(height_mix_seed),
        "height_mix_amount": float(height_mix_amount),
        "placement_shell_depths": _placement_shell_depths(placements, occupancy),
        "interior_void_cells": _interior_void_cells(occupancy),
        "voxel_components": int(voxel_components),
        "n_voxels_dropped": int(voxel_dropped),
        "prune_skipped": bool(prune_skipped),
        "prune_drop_ratio": float(prune_drop_ratio),
        "occupancy_cells": [
            (int(x), int(y), int(z))
            for x, y, z in zip(*np.where(occupancy))
        ],
    }
    return placements, info


# New primary name; keep `brickify_mesh` as compatibility alias.
def brick_mesh(*args, **kwargs):
    return brickify_mesh(*args, **kwargs)


def placement_world_position(
    p: BrickPlacement,
    *,
    stud_size: float,
    plate_size: float,
    origin: np.ndarray,
) -> np.ndarray:
    """World-space position of a placement's low corner (XYZ)."""
    return origin + np.array([
        p.x * stud_size,
        p.y * plate_size,
        p.z * stud_size,
    ], dtype=np.float64)
