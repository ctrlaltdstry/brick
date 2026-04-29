"""High-level mesh -> BrickPlacements pipeline.

Wraps voxelize -> fit -> (optional merge_plates) -> (optional connectivity
cleanup) into a single call. Pure-numpy in/out so the C4D plugin layer can
drive it without touching c4d-only types.

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
import time
import numpy as np
from scipy import ndimage

from .library import BrickLibrary, DEFAULT_LIBRARY
from .palette import LegoPalette
from .fitter import (
    BrickFitter, BrickPlacement,
    merge_plates_to_bricks, merge_plates_horizontal,
)
from .voxelize import STUD_MM, PLATE_RATIO
from .voxel_backends import voxelize_with_backend, normalize_voxel_backend
from .connectivity import check_buildability, check_connectivity


DETAIL_FIT_SETTINGS = {
    "off": (0, 0),
    # (band width from horizontal silhouette, max footprint in that band)
    "balanced": (1, 6),
    "preserve": (2, 4),
}
MAX_SAFE_CONNECTIVITY_PRUNE_DROP_RATIO = 0.35
MIN_SIGNIFICANT_FRAGMENT_PLACEMENTS = 24
MIN_SIGNIFICANT_FRAGMENT_RATIO = 0.02


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


def _label_voxel_components(
    occupancy: np.ndarray,
) -> Tuple[np.ndarray, int, List[int]]:
    """Label 3D-connected occupied voxel islands.

    Separate source islands are preserved as separate buildable subassemblies,
    so this labels them rather than pruning them to a single largest island.
    Returns (labels, n_components, component_sizes), where background is 0.
    """
    if not occupancy.any():
        return np.zeros_like(occupancy, dtype=np.int32), 0, []

    # Use 26-neighborhood so diagonally touching shell voxels stay connected.
    # 6-neighborhood can over-split thin stepped facades into faux islands.
    structure = np.ones((3, 3, 3), dtype=bool)
    labels, n_components = ndimage.label(occupancy, structure=structure)
    if n_components <= 0:
        return labels.astype(np.int32, copy=False), 0, []
    counts = np.bincount(labels.ravel(), minlength=int(n_components) + 1)
    counts[0] = 0  # background
    sizes = [int(counts[i]) for i in range(1, int(n_components) + 1)]
    return labels.astype(np.int32, copy=False), int(n_components), sizes


def _placement_voxel_component_ids(
    placements: List[BrickPlacement],
    voxel_labels: np.ndarray,
) -> List[int]:
    """Map each placement to the voxel island it covers most."""
    out: List[int] = []
    for p in placements:
        sub = voxel_labels[p.x:p.x + p.w, p.y:p.y + p.h, p.z:p.z + p.d]
        vals = sub[sub > 0]
        if vals.size == 0:
            out.append(0)
            continue
        counts = np.bincount(vals.astype(np.int32, copy=False).ravel())
        out.append(int(np.argmax(counts)))
    return out


def _component_fragments_for_indices(
    graph: Dict[int, Any],
    indices: List[int],
) -> List[List[int]]:
    """Connected placement fragments inside a voxel island."""
    allowed = set(indices)
    seen = set()
    fragments: List[List[int]] = []
    for start in indices:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        frag: List[int] = []
        while stack:
            i = stack.pop()
            frag.append(i)
            for nb in graph.get(i, ()):
                if nb in allowed and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        fragments.append(frag)
    return sorted(fragments, key=lambda f: -len(f))


def _prune_floating_fragments_by_voxel_island(
    placements: List[BrickPlacement],
    voxel_labels: np.ndarray,
    connectivity_report: Dict[str, Any],
    *,
    max_drop_ratio_per_island: Optional[float] = None,
    min_significant_fragment_size: int = MIN_SIGNIFICANT_FRAGMENT_PLACEMENTS,
    min_significant_fragment_ratio: float = MIN_SIGNIFICANT_FRAGMENT_RATIO,
) -> Tuple[List[BrickPlacement], List[BrickPlacement], List[Dict[str, Any]]]:
    """Drop only small floating placement fragments per voxel island.

    C4D Volume shell fits can legitimately split a building into many coupling
    fragments even when those fragments are visually meaningful. Keep substantial
    fragments and prune only small debris.
    """
    if not placements:
        return [], [], []

    component_ids = _placement_voxel_component_ids(placements, voxel_labels)
    by_voxel_component: Dict[int, List[int]] = {}
    for i, cid in enumerate(component_ids):
        by_voxel_component.setdefault(int(cid), []).append(i)

    graph = connectivity_report.get("graph", {})
    keep_ids = set()
    summary: List[Dict[str, Any]] = []
    for cid, ids in sorted(by_voxel_component.items()):
        fragments = _component_fragments_for_indices(graph, ids)
        if not fragments:
            continue
        significant_size = max(
            int(min_significant_fragment_size),
            int(round(float(len(ids)) * float(min_significant_fragment_ratio))),
        )
        keep_fragments = [fragments[0]]
        drop_fragments: List[List[int]] = []
        for frag in fragments[1:]:
            if len(frag) >= significant_size:
                keep_fragments.append(frag)
            else:
                drop_fragments.append(frag)
        candidate_dropped_count = sum(len(frag) for frag in drop_fragments)
        drop_ratio = (
            float(candidate_dropped_count) / float(max(1, len(ids)))
        )
        skip_prune = (
            max_drop_ratio_per_island is not None
            and drop_ratio > float(max_drop_ratio_per_island)
        )
        keep = set(ids if skip_prune else [i for frag in keep_fragments for i in frag])
        keep_ids.update(keep)
        dropped_count = 0 if skip_prune else candidate_dropped_count
        summary.append({
            "voxel_component": int(cid),
            "placement_fragments": int(len(fragments)),
            "significant_fragment_size": int(significant_size),
            "kept_fragments": int(len(fragments) if skip_prune else len(keep_fragments)),
            "kept": int(len(keep)),
            "dropped": int(dropped_count),
            "drop_candidate": int(candidate_dropped_count),
            "drop_ratio": float(drop_ratio),
            "prune_skipped": bool(skip_prune),
        })

    kept = [p for i, p in enumerate(placements) if i in keep_ids]
    dropped = [p for i, p in enumerate(placements) if i not in keep_ids]
    return kept, dropped, summary


def _physical_repair_summary(buildability_report: Dict[str, Any]) -> Dict[str, Any]:
    """Explain what kind of repair would be needed without changing geometry."""
    if not buildability_report.get("checked", True):
        return {
            "needed": False,
            "status": "not_checked",
            "reason": "artist_friendly_mode",
        }
    if bool(buildability_report.get("buildable", False)):
        return {
            "needed": False,
            "status": "buildable",
            "reason": "",
        }

    n_floating = int(buildability_report.get("n_floating_components", 0) or 0)
    n_grounded = int(buildability_report.get("n_grounded_components", 0) or 0)
    n_unsupported = int(buildability_report.get("n_unsupported", 0) or 0)
    same_layer = buildability_report.get("same_layer_islands") or []
    if n_grounded > 1:
        status = "needs_bridge"
        reason = (
            "multiple grounded subassemblies need a top piece or refit that "
            "overlaps both footprints"
        )
    elif n_floating > 0 or n_unsupported > 0:
        status = "needs_support"
        reason = "floating bricks need a vertical support path to the base"
    else:
        status = "needs_refit"
        reason = "assembly is not a single clutch-connected component"
    return {
        "needed": True,
        "status": status,
        "reason": reason,
        "candidate_bridge_islands": int(len(same_layer)),
        "floating_components": n_floating,
        "grounded_components": n_grounded,
        "unsupported_placements": n_unsupported,
    }


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
    voxel_backend: str = "internal",
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
    relaxed_boundary_fit: bool = False,
    precomputed_voxels: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]] = None,
    include_debug_info: bool = True,
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

    timings: Dict[str, float] = {}
    t_pipeline0 = time.perf_counter()
    voxel_backend_key = normalize_voxel_backend(voxel_backend)
    connectivity_required = False
    effective_prune_connectivity = bool(prune_connectivity)
    t0 = time.perf_counter()
    if precomputed_voxels is not None:
        occupancy, colors, origin, backend_info = precomputed_voxels
        backend_info = dict(backend_info or {})
    else:
        occupancy, colors, origin, backend_info = voxelize_with_backend(
            vertices, faces,
            backend=voxel_backend_key,
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
    timings["voxel_input_seconds"] = float(time.perf_counter() - t0)

    # Preserve detached voxel islands as separate source subassemblies. The
    # placement-level pass below removes only floating fragments within each
    # island, not whole secondary islands.
    t0 = time.perf_counter()
    voxel_labels, voxel_components, voxel_component_sizes = _label_voxel_components(
        occupancy
    )
    voxel_dropped = 0
    timings["voxel_label_seconds"] = float(time.perf_counter() - t0)
    timings["voxel_prune_seconds"] = timings["voxel_label_seconds"]

    detail_key = str(detail_mode).lower()
    detail_band, max_detail_footprint = DETAIL_FIT_SETTINGS.get(
        detail_key, DETAIL_FIT_SETTINGS["off"]
    )
    detail_mask = None
    t0 = time.perf_counter()
    if detail_band > 0 and max_detail_footprint > 0:
        detail_mask = _detail_mask_from_occupancy(
            occupancy,
            band_width=detail_band,
        )
    timings["detail_mask_seconds"] = float(time.perf_counter() - t0)

    fitter = BrickFitter(
        library, palette=palette,
        max_brick_height=max_brick_height,
        randomize_heights=randomize_heights,
        height_mix_seed=height_mix_seed,
        height_mix_amount=height_mix_amount,
    )
    t0 = time.perf_counter()
    placements = fitter.fit(
        occupancy,
        colors,
        detail_mask=detail_mask,
        max_detail_footprint=max_detail_footprint,
        surface_only_plates=surface_only_plates,
        relaxed_boundary_fit=relaxed_boundary_fit,
    )
    timings["fit_seconds"] = float(time.perf_counter() - t0)

    # Surface-only plate policy relies on plate-height "cap" pieces. Do not
    # promote 3-stacks into full bricks in this mode, or studded tops reappear
    # in selected regions after fitting.
    t0 = time.perf_counter()
    if merge_plates and (not surface_only_plates):
        placements = merge_plates_to_bricks(placements, library)
    timings["merge_vertical_seconds"] = float(time.perf_counter() - t0)

    t0 = time.perf_counter()
    if merge_horizontal:
        # Run after the vertical merge so 3-tall bricks formed from plate
        # stacks get combined too (this is what cleans up shoulder rings
        # of 1xN bricks at low resolutions).
        placements = merge_plates_horizontal(placements, library)
    timings["merge_horizontal_seconds"] = float(time.perf_counter() - t0)

    t0 = time.perf_counter()
    pre_prune_report = check_connectivity(placements)
    timings["connectivity_seconds"] = float(time.perf_counter() - t0)

    n_dropped = 0
    prune_skipped = False
    prune_drop_ratio = 0.0
    subassembly_report: List[Dict[str, Any]] = []
    pre_prune_buildability_report: Dict[str, Any] = {"checked": False}
    final_buildability_report: Dict[str, Any] = {"checked": False}
    physical_repair_report: Dict[str, Any] = _physical_repair_summary(
        final_buildability_report
    )
    connectivity_relaxed = bool(effective_prune_connectivity)
    shell_connectivity_relaxed = (
        str(voxel_mode).lower() == "shell" and connectivity_relaxed
    )
    t0 = time.perf_counter()
    if effective_prune_connectivity:
        pre_prune_buildability_report = check_buildability(placements)
        pre_prune_buildability_report["checked"] = True
        # Physically accurate mode should remove floating fragments, but not
        # amputate major architectural sections when the coupling graph misses
        # valid contact. If a prune would remove too much of a voxel island,
        # leave that island intact and report the skipped prune.
        kept, dropped, subassembly_report = _prune_floating_fragments_by_voxel_island(
            placements,
            voxel_labels,
            pre_prune_report,
            max_drop_ratio_per_island=MAX_SAFE_CONNECTIVITY_PRUNE_DROP_RATIO,
        )
        total_before_prune = max(1, len(placements))
        prune_drop_ratio = float(len(dropped)) / float(total_before_prune)
        placements = kept
        n_dropped = len(dropped)
        prune_skipped = any(
            bool(row.get("prune_skipped")) for row in subassembly_report
        )
    else:
        prune_skipped = True
    timings["placement_prune_seconds"] = float(time.perf_counter() - t0)

    t0 = time.perf_counter()
    if effective_prune_connectivity:
        final_connectivity_report = check_connectivity(placements)
        final_buildability_report = check_buildability(placements)
        final_buildability_report["checked"] = True
        physical_repair_report = _physical_repair_summary(final_buildability_report)
        timings["final_connectivity_seconds"] = float(time.perf_counter() - t0)
    else:
        final_connectivity_report = pre_prune_report
        final_buildability_report = {"checked": False, "buildable": False}
        physical_repair_report = _physical_repair_summary(final_buildability_report)
        timings["final_connectivity_seconds"] = 0.0

    t_info0 = time.perf_counter()
    placement_shell_depths = []
    interior_void_cells = []
    occupancy_cells = []
    if include_debug_info:
        t0 = time.perf_counter()
        placement_shell_depths = _placement_shell_depths(placements, occupancy)
        timings["placement_shell_depths_seconds"] = float(time.perf_counter() - t0)
        t0 = time.perf_counter()
        interior_void_cells = _interior_void_cells(occupancy)
        timings["interior_void_seconds"] = float(time.perf_counter() - t0)
        t0 = time.perf_counter()
        occupancy_cells = [
            (int(x), int(y), int(z))
            for x, y, z in zip(*np.where(occupancy))
        ]
        timings["occupancy_cells_seconds"] = float(time.perf_counter() - t0)
    else:
        timings["placement_shell_depths_seconds"] = 0.0
        timings["interior_void_seconds"] = 0.0
        timings["occupancy_cells_seconds"] = 0.0
    timings["info_payload_seconds"] = float(time.perf_counter() - t_info0)
    timings["pipeline_total_seconds"] = float(time.perf_counter() - t_pipeline0)

    info: Dict[str, Any] = {
        "origin": np.asarray(origin, dtype=np.float64),
        "stud_size": float(stud_size),
        "plate_size": float(plate_size),
        "voxel_backend": str(backend_info.get("voxel_backend", voxel_backend_key)),
        "voxel_backend_requested": str(
            backend_info.get("voxel_backend_requested", voxel_backend_key)
        ),
        "voxel_backend_fallback": bool(backend_info.get("voxel_backend_fallback", False)),
        "voxel_backend_note": str(backend_info.get("voxel_backend_note", "")),
        "grid_dims": tuple(int(d) for d in occupancy.shape),
        "n_placed": len(placements),
        "n_dropped": int(n_dropped),
        "connectivity": pre_prune_report,
        "detail_mode": detail_key,
        "preserve_silhouette": bool(preserve_silhouette),
        "preserve_tiny_gaps": bool(preserve_tiny_gaps),
        "surface_only_plates": bool(surface_only_plates),
        "relaxed_boundary_fit": bool(relaxed_boundary_fit),
        "randomize_heights": bool(randomize_heights),
        "height_mix_seed": int(height_mix_seed),
        "height_mix_amount": float(height_mix_amount),
        "placement_shell_depths": placement_shell_depths,
        "interior_void_cells": interior_void_cells,
        "voxel_components": int(voxel_components),
        "voxel_component_sizes": voxel_component_sizes,
        "n_voxels_dropped": int(voxel_dropped),
        "prune_skipped": bool(prune_skipped),
        "prune_connectivity_requested": bool(prune_connectivity),
        "prune_connectivity_effective": bool(effective_prune_connectivity),
        "connectivity_required": bool(connectivity_required),
        "connectivity_relaxed": bool(connectivity_relaxed),
        "max_safe_connectivity_prune_drop_ratio": float(
            MAX_SAFE_CONNECTIVITY_PRUNE_DROP_RATIO
        ),
        "shell_connectivity_relaxed": bool(shell_connectivity_relaxed),
        "shell_max_safe_prune_drop_ratio": float(MAX_SAFE_CONNECTIVITY_PRUNE_DROP_RATIO),
        "prune_drop_ratio": float(prune_drop_ratio),
        "subassemblies": subassembly_report,
        "subassembly_count": int(len(subassembly_report)),
        "final_connectivity": final_connectivity_report,
        "buildability": pre_prune_buildability_report,
        "final_buildability": final_buildability_report,
        "physical_repair": physical_repair_report,
        "occupancy_cells": occupancy_cells,
        "timings": timings,
    }
    for key, value in backend_info.items():
        if key.startswith("voxel_backend_") and key not in info:
            info[key] = value
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
