"""BrickIt build-progress ordering and animation helpers."""
from dataclasses import dataclass
from collections import deque
import math
import random


CAP_STYLE_MATCH_BELOW = 0
CAP_STYLE_RANDOM_MIX = 1
CAP_STYLE_MERGED_COVER = 2


# Default plate footprints (width, depth) used when no library is supplied.
# Mirrors brick.library._PLATES_H1 footprints. Both orientations are emitted
# as separate entries so the random mix can place rectangles in either axis
# without relying on the renderer's rotation swap.
_DEFAULT_PLATE_FOOTPRINTS = (
    (1, 1),
    (1, 2), (2, 1),
    (1, 3), (3, 1),
    (1, 4), (4, 1),
    (1, 6), (6, 1),
    (1, 8), (8, 1),
    (2, 2),
    (2, 3), (3, 2),
    (2, 4), (4, 2),
    (2, 6), (6, 2),
    (2, 8), (8, 2),
    (3, 3),
    (3, 4), (4, 3),
    (3, 6), (6, 3),
    (3, 8), (8, 3),
)


BUILD_ANIMATION_DEFAULT_Y_OFFSET = 25.0
BUILD_ANIMATION_DEFAULT_STAGGER = 0.10
BUILD_ANIMATION_MIN_EFFECTIVE_STAGGER = 0.03
BUILD_ANIMATION_IN_LAYER_STAGGER = 0.35

# Brick-index scheduling: stagger maps 0..1 to in-flight brick count
# 1..BUILD_ANIMATION_IN_FLIGHT_MAX. Stagger=0 → strict one-at-a-time,
# stagger=1 → loose swarm (~20 bricks falling at once).
BUILD_ANIMATION_IN_FLIGHT_MAX = 20
BUILD_ANIMATION_VISIBLE_AHEAD_LAYERS = 2.0
BUILD_ANIMATION_Y_OFFSET_VARIATION = 0.45
BUILD_ANIMATION_MIN_HANG_EXPONENT = 0.35
BUILD_ANIMATION_SLAM_EXPONENT = 3.0
BUILD_ANIMATION_MIN_SCALE = 0.001
BUILD_ANIMATION_DEFAULT_TILT_DEGREES = 5.0
BUILD_ANIMATION_TILT_CLEARANCE_MULTIPLIER = 1.15
BUILD_ANIMATION_BLEND_TOP_START = 0.35
BUILD_ANIMATION_BLEND_TOP_DURATION = 0.08
BUILD_ANIMATION_CAP_SPEED_VARIATION = 0.50
BUILD_ANIMATION_BOUNCE_END_RESERVE = 0.35
BUILD_ANIMATION_BOUNCE_SETTLE_TIME_SCALE = 0.50
BUILD_ANIMATION_FIXED_MOTION_DURATION = 0.22
SMOOTH_TOP_FULL_COVERAGE_THRESHOLD = 0.995

BUILD_MOTION_CURVE_EASE = 0
BUILD_MOTION_CURVE_EASE_IN = 1
BUILD_MOTION_CURVE_EASE_OUT = 2
BUILD_MOTION_CURVE_SPRING = 3
BUILD_MOTION_CURVE_SLAM = 4
BUILD_MOTION_CURVE_QUADRATIC = 5
BUILD_MOTION_CURVE_CUSTOM = 6
BUILD_MOTION_CURVE_BOUNCE = 7


@dataclass(frozen=True)
class BuildAnimationState:
    placement: object
    order_index: int
    local_progress: float
    drop_t: float
    y_offset: float
    contact_progress: object = None


@dataclass(frozen=True)
class VisualCapBrickType:
    name: str = "visual_smooth_cap_1x1"
    width: int = 1
    depth: int = 1
    height: int = 1
    ldraw_code: str = "visual_smooth_cap_1x1"


@dataclass(frozen=True)
class VisualCapPlacement:
    brick: object
    x: int
    y: int
    z: int
    rotation_y: int = 0
    color_idx: int = -1
    rgb: tuple = (180, 180, 180)
    w: int = 1
    d: int = 1
    h: int = 1
    # Supporting structural placement this cap sits directly on top of. Used by
    # the renderer to anchor the cap to its support's separated position so
    # Brick Separation > 0 doesn't drift the cap up off the support.
    support: object = None


def _occupied_cells(placements):
    occupied = set()
    for p in placements:
        for x in range(int(getattr(p, "x", 0)), int(getattr(p, "x", 0) + getattr(p, "w", 1))):
            for y in range(int(getattr(p, "y", 0)), int(getattr(p, "y", 0) + getattr(p, "h", 1))):
                for z in range(int(getattr(p, "z", 0)), int(getattr(p, "z", 0) + getattr(p, "d", 1))):
                    occupied.add((x, y, z))
    return occupied


def _supporting_placements(cap, structural):
    """Return landed candidates directly under every cap footprint cell."""
    cap_y = int(getattr(cap, "y", 0))
    if cap_y <= 0:
        return []

    supports = []
    seen = set()
    for cap_x in range(int(getattr(cap, "x", 0)), int(getattr(cap, "x", 0) + getattr(cap, "w", 1))):
        for cap_z in range(int(getattr(cap, "z", 0)), int(getattr(cap, "z", 0) + getattr(cap, "d", 1))):
            support = None
            for placement in structural:
                x0 = int(getattr(placement, "x", 0))
                x1 = int(getattr(placement, "x", 0) + getattr(placement, "w", 1))
                z0 = int(getattr(placement, "z", 0))
                z1 = int(getattr(placement, "z", 0) + getattr(placement, "d", 1))
                y0 = int(getattr(placement, "y", 0))
                y1 = int(getattr(placement, "y", 0) + getattr(placement, "h", 1))
                if (
                    x0 <= cap_x < x1
                    and z0 <= cap_z < z1
                    and y0 <= (cap_y - 1) < y1
                ):
                    support = placement
                    break
            if support is None:
                return []
            if id(support) not in seen:
                supports.append(support)
                seen.add(id(support))
    return supports


def _build_support_lookup(structural):
    """Map occupied structural cells to their first owning placement."""
    support_at = {}
    for placement in structural or []:
        x0 = int(getattr(placement, "x", 0))
        x1 = int(getattr(placement, "x", 0) + getattr(placement, "w", 1))
        y0 = int(getattr(placement, "y", 0))
        y1 = int(getattr(placement, "y", 0) + getattr(placement, "h", 1))
        z0 = int(getattr(placement, "z", 0))
        z1 = int(getattr(placement, "z", 0) + getattr(placement, "d", 1))
        for x in range(x0, x1):
            for y in range(y0, y1):
                for z in range(z0, z1):
                    support_at.setdefault((x, y, z), placement)
    return support_at


def _supporting_placements_from_lookup(cap, support_at):
    cap_y = int(getattr(cap, "y", 0))
    if cap_y <= 0:
        return []

    supports = []
    seen = set()
    for cap_x in range(int(getattr(cap, "x", 0)), int(getattr(cap, "x", 0) + getattr(cap, "w", 1))):
        for cap_z in range(int(getattr(cap, "z", 0)), int(getattr(cap, "z", 0) + getattr(cap, "d", 1))):
            support = support_at.get((cap_x, cap_y - 1, cap_z))
            if support is None:
                return []
            if id(support) not in seen:
                supports.append(support)
                seen.add(id(support))
    return supports


def exterior_top_cells_from_occupancy(occupancy_cells, grid_dims):
    """Return top-air cells connected to exterior air for shell-mode capping."""
    try:
        nx, ny, nz = (int(grid_dims[0]), int(grid_dims[1]), int(grid_dims[2]))
    except Exception:
        return None
    if nx <= 0 or ny <= 0 or nz <= 0:
        return set()

    occupied = {
        (int(x), int(y), int(z))
        for x, y, z in (occupancy_cells or [])
    }
    if not occupied:
        return None

    def in_bounds(cell):
        x, y, z = cell
        return -1 <= x <= nx and -1 <= y <= ny and -1 <= z <= nz

    def is_occupied(cell):
        x, y, z = cell
        return (
            0 <= x < nx
            and 0 <= y < ny
            and 0 <= z < nz
            and cell in occupied
        )

    exterior = set()
    queue = deque([(-1, -1, -1)])
    exterior.add((-1, -1, -1))
    neighbors = (
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1),
    )
    while queue:
        x, y, z = queue.popleft()
        for dx, dy, dz in neighbors:
            nxt = (x + dx, y + dy, z + dz)
            if nxt in exterior or not in_bounds(nxt) or is_occupied(nxt):
                continue
            exterior.add(nxt)
            queue.append(nxt)

    out = set()
    for x, y, z in occupied:
        top = (x, y + 1, z)
        if top in exterior:
            out.add(top)
    return out


def _fitted_grid_dims(placements, fallback_dims=None):
    """Return (nx, ny, nz) bounding the fitted placement set, padded by 1."""
    nx = ny = nz = 0
    for p in placements or []:
        nx = max(nx, int(getattr(p, "x", 0) + getattr(p, "w", 1)))
        ny = max(ny, int(getattr(p, "y", 0) + getattr(p, "h", 1)))
        nz = max(nz, int(getattr(p, "z", 0) + getattr(p, "d", 1)))
    if fallback_dims is not None:
        try:
            nx = max(nx, int(fallback_dims[0]))
            ny = max(ny, int(fallback_dims[1]))
            nz = max(nz, int(fallback_dims[2]))
        except Exception:
            pass
    return (nx, ny, nz)


def _exterior_air_mask_3d(occupied, grid_dims):
    """Return the set of air cells reachable from outside the grid (true 3D)."""
    try:
        nx, ny, nz = (int(grid_dims[0]), int(grid_dims[1]), int(grid_dims[2]))
    except Exception:
        return None, (0, 0, 0)
    if nx <= 0 or ny <= 0 or nz <= 0:
        return set(), (nx, ny, nz)

    occupied = set(occupied or ())
    if not occupied:
        return None, (nx, ny, nz)

    exterior = set()
    queue = deque([(-1, -1, -1)])
    exterior.add((-1, -1, -1))
    neighbors = (
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1),
    )
    while queue:
        x, y, z = queue.popleft()
        for dx, dy, dz in neighbors:
            nxt = (x + dx, y + dy, z + dz)
            ax, ay, az = nxt
            if nxt in exterior:
                continue
            if not (-1 <= ax <= nx and -1 <= ay <= ny and -1 <= az <= nz):
                continue
            if (
                0 <= ax < nx
                and 0 <= ay < ny
                and 0 <= az < nz
                and nxt in occupied
            ):
                continue
            exterior.add(nxt)
            queue.append(nxt)
    return exterior, (nx, ny, nz)


def shell_smooth_top_target_cells(
    placements,
    occupancy_cells,
    grid_dims,
    interior_void_cells=None,  # legacy arg, ignored
):
    """Return fitted shell cap targets using true 3D exterior-air connectivity.

    Every fitted brick whose top cell is reachable from outside the grid (or is
    outside grid bounds entirely) gets capped. Cells already occupied by another
    fitted brick are skipped. Air cells fully enclosed in a 3D pocket are
    skipped — these are the inside surfaces of a hollow shell.
    """
    placements = list(placements or [])
    occupied = _occupied_cells(placements)
    if not occupied:
        return None

    fitted_dims = _fitted_grid_dims(placements, grid_dims)
    exterior_air, (nx, ny, nz) = _exterior_air_mask_3d(occupied, fitted_dims)
    if exterior_air is None:
        return None
    sky_cache = {}

    def _has_sky_column(x, top_y, z):
        # True if cells (x, top_y..ny-1, z) are all empty (no fitted brick).
        # A brick that has an open vertical air chimney to the top of the grid
        # is exterior from above, even when laterally walled by neighbors at
        # the same y-level.
        col_key = (x, top_y, z)
        cached = sky_cache.get(col_key)
        if cached is not None:
            return cached
        cy = top_y
        while cy < ny:
            if (x, cy, z) in occupied:
                sky_cache[col_key] = False
                return False
            cy += 1
        sky_cache[col_key] = True
        return True

    out = set()
    for p in placements:
        top_y = int(getattr(p, "y", 0) + getattr(p, "h", 1))
        x0 = int(getattr(p, "x", 0))
        z0 = int(getattr(p, "z", 0))
        w = int(getattr(p, "w", 1))
        d = int(getattr(p, "d", 1))
        for x in range(x0, x0 + w):
            for z in range(z0, z0 + d):
                key = (x, top_y, z)
                if key in occupied:
                    continue
                in_grid = (
                    0 <= x < nx
                    and 0 <= top_y < ny
                    and 0 <= z < nz
                )
                if not in_grid:
                    out.add(key)
                    continue
                if key in exterior_air or _has_sky_column(x, top_y, z):
                    out.add(key)
    return out


def exposed_top_cap_ids(placements, target_top_cells=None):
    """Return ids for one-plate placements with any visible final top area."""
    placements = list(placements or [])
    occupied = _occupied_cells(placements)
    target_top_cells = None if target_top_cells is None else set(target_top_cells)

    out = set()
    for p in placements:
        if int(getattr(p, "h", 1)) != 1:
            continue
        top_y = int(getattr(p, "y", 0) + getattr(p, "h", 1))
        exposed = False
        for x in range(int(getattr(p, "x", 0)), int(getattr(p, "x", 0) + getattr(p, "w", 1))):
            for z in range(int(getattr(p, "z", 0)), int(getattr(p, "z", 0) + getattr(p, "d", 1))):
                key = (x, top_y, z)
                if target_top_cells is not None and key not in target_top_cells:
                    continue
                if key not in occupied:
                    exposed = True
                    break
            if exposed:
                break
        if exposed:
            out.add(id(p))
    return out


def _exposed_top_cells_with_source(placements, target_top_cells=None):
    placements = list(placements or [])
    occupied = _occupied_cells(placements)
    target_top_cells = None if target_top_cells is None else set(target_top_cells)
    out = {}
    for p in placements:
        top_y = int(getattr(p, "y", 0) + getattr(p, "h", 1))
        rgb = tuple(getattr(p, "rgb", (180, 180, 180)))
        color_idx = int(getattr(p, "color_idx", -1))
        for x in range(int(getattr(p, "x", 0)), int(getattr(p, "x", 0) + getattr(p, "w", 1))):
            for z in range(int(getattr(p, "z", 0)), int(getattr(p, "z", 0) + getattr(p, "d", 1))):
                key = (x, top_y, z)
                if target_top_cells is not None and key not in target_top_cells:
                    continue
                if key in occupied:
                    continue
                out.setdefault(key, (rgb, color_idx))
    return out


def _all_exposed_top_visual_caps(placements, library=None, target_top_cells=None):
    placements = list(placements or [])
    occupied = _occupied_cells(placements)
    target_top_cells = None if target_top_cells is None else set(target_top_cells)
    caps = []
    seen = set()
    for p in placements:
        x0 = int(getattr(p, "x", 0))
        z0 = int(getattr(p, "z", 0))
        w = int(getattr(p, "w", 1))
        d = int(getattr(p, "d", 1))
        top_y = int(getattr(p, "y", 0) + getattr(p, "h", 1))
        rgb = tuple(getattr(p, "rgb", (180, 180, 180)))
        color_idx = int(getattr(p, "color_idx", -1))

        exposed = set()
        for x in range(x0, x0 + w):
            for z in range(z0, z0 + d):
                key = (x, top_y, z)
                if target_top_cells is not None and key not in target_top_cells:
                    continue
                if key in occupied or key in seen:
                    continue
                exposed.add((x, z))

        if not exposed:
            continue

        if len(exposed) == w * d:
            for cx, cz in exposed:
                seen.add((cx, top_y, cz))
            _emit_cap(caps, x0, z0, top_y, w, d, rgb, color_idx, support=p)
            continue

        remaining = set(exposed)
        while remaining:
            rect = _largest_exposed_rect(remaining, x0, z0, w, d)
            if rect is None:
                break
            rx, rz, rw, rd = rect
            for ix in range(rx, rx + rw):
                for iz in range(rz, rz + rd):
                    remaining.discard((ix, iz))
                    seen.add((ix, top_y, iz))
            _emit_cap(caps, rx, rz, top_y, rw, rd, rgb, color_idx, support=p)
    return caps


def _largest_exposed_rect(remaining, x0, z0, w, d):
    """Find the largest axis-aligned (rx, rz, rw, rd) rectangle of cells in
    `remaining` that lies within the (x0, z0, w, d) brick footprint.

    Standard maximal-rectangle-in-binary-matrix scan: per-row histogram of
    consecutive exposed cells per column, then scan widths.
    """
    heights = [0] * w
    best = None
    best_area = 0
    for iz in range(d):
        z = z0 + iz
        for ix in range(w):
            x = x0 + ix
            heights[ix] = heights[ix] + 1 if (x, z) in remaining else 0
        for ix in range(w):
            if heights[ix] == 0:
                continue
            min_h = heights[ix]
            for jx in range(ix, w):
                hh = heights[jx]
                if hh == 0:
                    break
                if hh < min_h:
                    min_h = hh
                area = min_h * (jx - ix + 1)
                if area > best_area:
                    best_area = area
                    best = (x0 + ix, z - min_h + 1, jx - ix + 1, min_h)
    return best


def _plate_footprints_from_library(library):
    """Return ((w, d), ...) plate footprints from a brick library, both
    orientations included. Falls back to the default plate set if `library`
    is None / has no plates."""
    if library is None:
        return _DEFAULT_PLATE_FOOTPRINTS
    bricks = getattr(library, "bricks", None)
    if bricks is None:
        bricks = list(library) if hasattr(library, "__iter__") else None
    if not bricks:
        return _DEFAULT_PLATE_FOOTPRINTS
    fps = set()
    for b in bricks:
        if int(getattr(b, "height", 1)) != 1:
            continue
        w = int(getattr(b, "width", 1))
        d = int(getattr(b, "depth", 1))
        fps.add((w, d))
        fps.add((d, w))
    if not fps:
        return _DEFAULT_PLATE_FOOTPRINTS
    return tuple(sorted(fps, key=lambda wd: (-wd[0] * wd[1], -max(wd), wd)))


def _build_top_layer_state(placements, target_top_cells=None):
    """Group h>1 brick exposed top cells per y-layer with anchor color map.

    Returns (layers, color_at):
        layers[top_y] -> set of (x, z) cells exposed (no occupied cell above)
        color_at[top_y][(x, z)] -> (rgb, color_idx) of the source brick whose
            top contains the cell (first writer wins, mirroring placement
            iteration order — caps colored by the first brick claiming a cell).

    When `target_top_cells` is provided (set of (x, top_y, z) tuples), cells
    not in that set are skipped — used by surface-only-plate mode to restrict
    caps to the silhouette top-shell.
    """
    placements = list(placements or [])
    occupied = _occupied_cells(placements)
    target_top_cells = None if target_top_cells is None else set(target_top_cells)
    layers = {}
    color_at = {}
    # Include h=1 placements (plates) so their studded tops also get smooth
    # caps under Largest Merged Plates / Random Mix at full coverage. The
    # match-below path used _all_exposed_top_visual_caps which included
    # plates too; skipping them here was an unintentional asymmetry.
    for p in placements:
        x0 = int(getattr(p, "x", 0))
        z0 = int(getattr(p, "z", 0))
        w = int(getattr(p, "w", 1))
        d = int(getattr(p, "d", 1))
        top_y = int(getattr(p, "y", 0) + getattr(p, "h", 1))
        rgb = tuple(getattr(p, "rgb", (180, 180, 180)))
        color_idx = int(getattr(p, "color_idx", -1))
        layer_cells = layers.setdefault(top_y, set())
        layer_colors = color_at.setdefault(top_y, {})
        for x in range(x0, x0 + w):
            for z in range(z0, z0 + d):
                key = (x, top_y, z)
                if target_top_cells is not None and key not in target_top_cells:
                    continue
                if key in occupied:
                    continue
                cell = (x, z)
                if cell in layer_cells:
                    continue
                layer_cells.add(cell)
                layer_colors[cell] = (rgb, color_idx)
    return layers, color_at


def _emit_cap(caps_out, ax, az, top_y, w, d, rgb, color_idx, support=None):
    cap_brick = VisualCapBrickType(width=w, depth=d, height=1)
    caps_out.append(
        VisualCapPlacement(
            brick=cap_brick,
            x=ax,
            y=top_y,
            z=az,
            rotation_y=0,
            color_idx=color_idx,
            rgb=rgb,
            w=w,
            d=d,
            h=1,
            support=support,
        )
    )


def _merged_cover_caps(placements, library, target_top_cells=None):
    """Tile every exposed top of h>1 bricks with the largest library plates
    that fit. Cells are unioned per y-layer (so a cap may span across two
    adjacent same-height bricks). Deterministic — no seed required.

    Color of each cap is taken from the source brick under its anchor cell.
    """
    layers, color_at = _build_top_layer_state(placements, target_top_cells=target_top_cells)
    plate_pool = list(_plate_footprints_from_library(library))
    if not plate_pool:
        plate_pool = [(1, 1)]
    sorted_pool = sorted(plate_pool, key=lambda wd: (-(wd[0] * wd[1]), -max(wd), wd))

    caps = []
    for top_y in sorted(layers):
        available = layers[top_y]
        cell_color = color_at[top_y]
        while available:
            placed = False
            for w, d in sorted_pool:
                anchors = _valid_anchors(available, w, d)
                if not anchors:
                    continue
                # Deterministic anchor pick: smallest (x, z) for stable output.
                anchors.sort()
                ax, az = anchors[0]
                rgb, color_idx = cell_color[(ax, az)]
                for ix in range(w):
                    for iz in range(d):
                        available.discard((ax + ix, az + iz))
                _emit_cap(caps, ax, az, top_y, w, d, rgb, color_idx)
                placed = True
                break
            if not placed:
                ax, az = sorted(available)[0]
                rgb, color_idx = cell_color[(ax, az)]
                available.discard((ax, az))
                _emit_cap(caps, ax, az, top_y, 1, 1, rgb, color_idx)
    return caps


def _random_mix_caps(placements, library, seed, target_top_cells=None):
    """Tile every exposed top of h>1 bricks with random library plates.

    Cells are grouped by their y-layer (no plate spans heights). Within each
    layer the available cell set is the union of every h>1 brick's exposed
    top cells; a plate is only placed when its entire footprint lies within
    that available set, so caps cannot overhang the model silhouette.

    Color of each emitted cap is taken from the source brick whose top
    contains the cap's anchor (origin) cell.
    """
    layers, color_at = _build_top_layer_state(placements, target_top_cells=target_top_cells)
    plate_pool = list(_plate_footprints_from_library(library))
    if not plate_pool:
        plate_pool = [(1, 1)]

    caps = []
    base_seed = int(seed) & 0xFFFFFFFF
    for top_y in sorted(layers):
        available = layers[top_y]
        if not available:
            continue
        cell_color = color_at[top_y]
        rng = random.Random(base_seed ^ (top_y * 2654435761) & 0xFFFFFFFF)

        # Plate pool sorted large->small for the deterministic fallback.
        sorted_pool = sorted(plate_pool, key=lambda wd: -(wd[0] * wd[1]))

        max_random_attempts = 8
        while available:
            placed = False
            # Random sampling for variety, weighted implicitly by pool layout.
            for _ in range(max_random_attempts):
                w, d = rng.choice(plate_pool)
                anchors = _valid_anchors(available, w, d)
                if anchors:
                    # Sort to remove insertion-order nondeterminism, then
                    # let rng choose among them.
                    anchors.sort()
                    ax, az = rng.choice(anchors)
                    rgb, color_idx = cell_color[(ax, az)]
                    for ix in range(w):
                        for iz in range(d):
                            available.discard((ax + ix, az + iz))
                    cap_brick = VisualCapBrickType(width=w, depth=d, height=1)
                    caps.append(
                        VisualCapPlacement(
                            brick=cap_brick,
                            x=ax,
                            y=top_y,
                            z=az,
                            rotation_y=0,
                            color_idx=color_idx,
                            rgb=rgb,
                            w=w,
                            d=d,
                            h=1,
                        )
                    )
                    placed = True
                    break

            if placed:
                continue

            # Deterministic fallback: largest plate that fits anywhere.
            for w, d in sorted_pool:
                anchors = _valid_anchors(available, w, d)
                if not anchors:
                    continue
                anchors.sort()
                ax, az = rng.choice(anchors)
                rgb, color_idx = cell_color[(ax, az)]
                for ix in range(w):
                    for iz in range(d):
                        available.discard((ax + ix, az + iz))
                cap_brick = VisualCapBrickType(width=w, depth=d, height=1)
                caps.append(
                    VisualCapPlacement(
                        brick=cap_brick,
                        x=ax,
                        y=top_y,
                        z=az,
                        rotation_y=0,
                        color_idx=color_idx,
                        rgb=rgb,
                        w=w,
                        d=d,
                        h=1,
                    )
                )
                placed = True
                break

            if not placed:
                # Final safety net: force a 1x1 on any remaining cell.
                ax, az = sorted(available)[0]
                rgb, color_idx = cell_color[(ax, az)]
                available.discard((ax, az))
                cap_brick = VisualCapBrickType(width=1, depth=1, height=1)
                caps.append(
                    VisualCapPlacement(
                        brick=cap_brick,
                        x=ax,
                        y=top_y,
                        z=az,
                        rotation_y=0,
                        color_idx=color_idx,
                        rgb=rgb,
                        w=1,
                        d=1,
                        h=1,
                    )
                )
    return caps


def _valid_anchors(available, w, d):
    """List of (x, z) anchors where a (w, d) plate fits inside `available`."""
    if w == 1 and d == 1:
        return list(available)
    anchors = []
    for (x, z) in available:
        ok = True
        for ix in range(w):
            for iz in range(d):
                if (x + ix, z + iz) not in available:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            anchors.append((x, z))
    return anchors


def missing_smooth_top_cap_placements(
    placements,
    *,
    cap_style=CAP_STYLE_MATCH_BELOW,
    library=None,
    seed=0,
    target_top_cells=None,
):
    """Create visual smooth caps for exposed tops on taller bricks.

    Two `cap_style` modes:

    - `CAP_STYLE_MATCH_BELOW` (default): per-brick. Emit a single cap with
      the brick's full footprint when the entire top is exposed; on partial
      occlusion, decompose the exposed region into the largest axis-aligned
      rectangles. Full-footprint caps reuse the source brick's library
      `width`/`depth` and `rotation_y` so stud orientation aligns with the
      brick below.
    - `CAP_STYLE_MERGED_COVER`: union all h>1 brick exposed top cells per
      y-layer and deterministically tile them with the largest plate from
      `library` that fits at each step. Caps may span across two adjacent
      same-height bricks. No seed needed.
    - `CAP_STYLE_RANDOM_MIX`: union all h>1 brick exposed top cells per
      y-layer and tile them with random plates from `library` (or the
      default plate set if `library` is None). `seed` makes the result
      reproducible. Plates never overhang the model silhouette because
      placements are restricted to cells that exist in the available set.
    """
    style = int(cap_style)
    if target_top_cells is not None:
        # Surface-only-plates path: caps must stay inside the silhouette
        # top-shell. Honor cap_style — earlier this branch hard-coded the
        # match-below tiler regardless of user choice.
        if style == CAP_STYLE_RANDOM_MIX:
            return _random_mix_caps(placements, library, seed, target_top_cells=target_top_cells)
        if style == CAP_STYLE_MERGED_COVER:
            return _merged_cover_caps(placements, library, target_top_cells=target_top_cells)
        return _all_exposed_top_visual_caps(
            placements,
            library=library,
            target_top_cells=target_top_cells,
        )
    if style == CAP_STYLE_RANDOM_MIX:
        return _random_mix_caps(placements, library, seed)
    if style == CAP_STYLE_MERGED_COVER:
        return _merged_cover_caps(placements, library)

    placements = list(placements or [])
    occupied = _occupied_cells(placements)
    caps = []
    seen = set()
    for p in placements:
        if int(getattr(p, "h", 1)) <= 1:
            continue
        x0 = int(getattr(p, "x", 0))
        z0 = int(getattr(p, "z", 0))
        w = int(getattr(p, "w", 1))
        d = int(getattr(p, "d", 1))
        top_y = int(getattr(p, "y", 0) + getattr(p, "h", 1))
        rotation_y = int(getattr(p, "rotation_y", 0))
        rgb = tuple(getattr(p, "rgb", (180, 180, 180)))
        color_idx = int(getattr(p, "color_idx", -1))
        src_brick = getattr(p, "brick", None)

        exposed = set()
        for x in range(x0, x0 + w):
            for z in range(z0, z0 + d):
                key = (x, top_y, z)
                if key in occupied or key in seen:
                    continue
                exposed.add((x, z))

        if not exposed:
            continue

        if len(exposed) == w * d:
            # Full top exposed: emit single cap matching brick footprint AND
            # the source brick's library template orientation.
            for cx, cz in exposed:
                seen.add((cx, top_y, cz))
            cap_brick = VisualCapBrickType(
                width=int(getattr(src_brick, "width", w)),
                depth=int(getattr(src_brick, "depth", d)),
                height=1,
            )
            caps.append(
                VisualCapPlacement(
                    brick=cap_brick,
                    x=x0,
                    y=top_y,
                    z=z0,
                    rotation_y=rotation_y,
                    color_idx=color_idx,
                    rgb=rgb,
                    w=w,
                    d=d,
                    h=1,
                    support=p,
                )
            )
        else:
            # Partial occlusion: greedily carve the exposed region into the
            # largest axis-aligned rectangles. Each rectangle becomes a single
            # smooth cap plate, axis-aligned (rotation_y=0) in grid space.
            remaining = set(exposed)
            while remaining:
                rect = _largest_exposed_rect(remaining, x0, z0, w, d)
                if rect is None:
                    break
                rx, rz, rw, rd = rect
                for ix in range(rx, rx + rw):
                    for iz in range(rz, rz + rd):
                        remaining.discard((ix, iz))
                        seen.add((ix, top_y, iz))
                cap_brick = VisualCapBrickType(width=rw, depth=rd, height=1)
                caps.append(
                    VisualCapPlacement(
                        brick=cap_brick,
                        x=rx,
                        y=top_y,
                        z=rz,
                        rotation_y=0,
                        color_idx=color_idx,
                        rgb=rgb,
                        w=rw,
                        d=rd,
                        h=1,
                        support=p,
                    )
                )
    return caps


def smooth_top_cap_placements_for_coverage(
    placements,
    coverage,
    *,
    cap_style=CAP_STYLE_MATCH_BELOW,
    library=None,
    seed=0,
    target_top_cells=None,
):
    """Return generated smooth caps for the requested coverage amount."""
    caps = missing_smooth_top_cap_placements(
        placements,
        cap_style=cap_style,
        library=library,
        seed=seed,
        target_top_cells=target_top_cells,
    )
    if not caps:
        return []
    amount = _clamp01(coverage)
    n_visible = int(round(float(len(caps)) * amount))
    if n_visible <= 0:
        return []
    if n_visible >= len(caps):
        return caps
    return ordered_placements(caps)[:n_visible]


def _placement_random_key(placement, coverage_seed):
    return _stable_unit_noise(
        int(getattr(placement, "x", 0)),
        int(getattr(placement, "y", 0)),
        int(getattr(placement, "z", 0)),
        int(getattr(placement, "w", 1)),
        int(getattr(placement, "h", 1)),
        int(getattr(placement, "d", 1)),
        int(getattr(placement, "rotation_y", 0)),
        int(coverage_seed),
    )


def _attach_supports_by_position(generated_caps, structural_placements):
    """For any cap whose `support` is None, pick the structural placement
    whose footprint contains the cap's anchor cell at the layer below.

    Caps emitted by `_random_mix_caps` and `_merged_cover_caps` (and a
    couple of fallback paths in the per-brick tilers) don't carry a
    support reference, which breaks bind-to-source-deformation: the cap
    has nothing to inherit deformed position/orient from and stays
    axis-aligned at its source-axis-local position.  Walk those caps
    once after generation and pin each to the brick directly under its
    anchor cell.  When a cap spans multiple bricks (rare) the anchor's
    brick is chosen — slight artifact under extreme deformation but
    correct in the common case.
    """
    if not generated_caps:
        return
    structural_list = list(structural_placements or [])
    if not structural_list:
        return
    # Index structural placements by every (x, top_y, z) cell they
    # contribute as a top surface, so cap lookup is O(1) per cap.
    top_cell_to_placement = {}
    for p in structural_list:
        x0 = int(getattr(p, "x", 0))
        y0 = int(getattr(p, "y", 0))
        z0 = int(getattr(p, "z", 0))
        w = int(getattr(p, "w", 1))
        h = int(getattr(p, "h", 1))
        d = int(getattr(p, "d", 1))
        top_y = y0 + h
        for ix in range(w):
            for iz in range(d):
                top_cell_to_placement.setdefault(
                    (x0 + ix, top_y, z0 + iz), p
                )
    for cap in generated_caps:
        if getattr(cap, "support", None) is not None:
            continue
        cx = int(getattr(cap, "x", 0))
        cy = int(getattr(cap, "y", 0))
        cz = int(getattr(cap, "z", 0))
        sup = top_cell_to_placement.get((cx, cy, cz))
        if sup is not None:
            try:
                cap.support = sup
            except Exception:
                pass


def smooth_top_cap_selection_for_coverage(
    placements,
    coverage,
    random_order=False,
    *,
    cap_style=CAP_STYLE_MATCH_BELOW,
    library=None,
    seed=0,
    target_top_cells=None,
):
    """Return existing smooth ids and generated caps for total coverage."""
    placements = list(placements or [])
    target_top_cells = None if target_top_cells is None else set(target_top_cells)
    amount = _clamp01(coverage)
    if amount >= SMOOTH_TOP_FULL_COVERAGE_THRESHOLD:
        # Full coverage: cap every exposed top. For MATCH_BELOW we keep
        # _all_exposed_top_visual_caps (it also covers h=1 plate tops via
        # the per-placement loop). For Random Mix and Largest Merged
        # Plates the user-visible behavior is the style-specific tiling
        # of h>1 exposed tops — earlier versions silently fell through to
        # match-below regardless of style.
        style = int(cap_style)
        if style in (CAP_STYLE_RANDOM_MIX, CAP_STYLE_MERGED_COVER):
            generated = missing_smooth_top_cap_placements(
                placements,
                cap_style=style,
                library=library,
                seed=seed,
                target_top_cells=target_top_cells,
            )
            _attach_supports_by_position(generated, placements)
            return set(), generated
        generated = _all_exposed_top_visual_caps(
            placements,
            library=library,
            target_top_cells=target_top_cells,
        )
        _attach_supports_by_position(generated, placements)
        return set(), generated
    existing_ids = exposed_top_cap_ids(
        placements,
        target_top_cells=target_top_cells,
    )
    generated_caps = missing_smooth_top_cap_placements(
        placements,
        cap_style=cap_style,
        library=library,
        seed=seed,
        target_top_cells=target_top_cells,
    )
    _attach_supports_by_position(generated_caps, placements)
    candidates = [
        ("existing", p)
        for p in ordered_placements(placements)
        if id(p) in existing_ids
    ]
    candidates.extend(("generated", p) for p in ordered_placements(generated_caps))
    if not candidates:
        return set(), []

    n_visible = int(round(float(len(candidates)) * amount))
    if n_visible <= 0:
        return set(), []

    if random_order:
        coverage_seed = int(round(amount * 1000.0))
        candidates = sorted(
            candidates,
            key=lambda item: (
                _placement_random_key(item[1], coverage_seed),
                _placement_sort_key(0, item[1]),
            ),
        )

    selected_existing_ids = set()
    selected_generated_caps = []
    for kind, placement in candidates[:n_visible]:
        if kind == "existing":
            selected_existing_ids.add(id(placement))
        else:
            selected_generated_caps.append(placement)
    return selected_existing_ids, selected_generated_caps


def _placement_sort_key(index, placement):
    return (
        int(getattr(placement, "y", 0)),
        int(getattr(placement, "z", 0)),
        int(getattr(placement, "x", 0)),
        int(getattr(placement, "h", 1)),
        int(getattr(placement, "d", 1)),
        int(getattr(placement, "w", 1)),
        int(getattr(placement, "rotation_y", 0)),
        int(index),
    )


def ordered_placements(placements):
    """Return placements in deterministic bottom-to-top build order."""
    return [
        placement
        for _, placement in sorted(
            enumerate(placements or []),
            key=lambda item: _placement_sort_key(item[0], item[1]),
        )
    ]


def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def _effective_stagger(value):
    stagger = _clamp01(value)
    if stagger <= 0.0:
        return 0.0
    return max(BUILD_ANIMATION_MIN_EFFECTIVE_STAGGER, stagger)


def sample_custom_curve(curve_data, t):
    """Sample a C4D SplineData-like curve at normalized progress."""
    if curve_data is None or not hasattr(curve_data, "GetPoint"):
        return t
    try:
        point = curve_data.GetPoint(_clamp01(t))
        value = getattr(point, "y", None)
        if value is None:
            value = point[1]
        return _clamp01(value)
    except Exception:
        return t


def custom_curve_signature(curve_data, samples=11):
    """Return a compact sampled signature for cache invalidation."""
    if curve_data is None:
        return None
    count = max(2, int(samples))
    return tuple(
        round(sample_custom_curve(curve_data, i / float(count - 1)), 4)
        for i in range(count)
    )


def apply_motion_curve(t, curve=BUILD_MOTION_CURVE_SLAM, custom_curve=None):
    """Map local progress through the selected build motion curve."""
    t = _clamp01(t)
    curve = int(curve)
    if curve == BUILD_MOTION_CURVE_CUSTOM:
        return sample_custom_curve(custom_curve, t)
    if curve == BUILD_MOTION_CURVE_EASE:
        return t * t * (3.0 - 2.0 * t)
    if curve == BUILD_MOTION_CURVE_EASE_IN:
        return t * t * t
    if curve == BUILD_MOTION_CURVE_EASE_OUT:
        inv = 1.0 - t
        return 1.0 - (inv * inv * inv)
    if curve == BUILD_MOTION_CURVE_SPRING:
        # A damped overshoot, clamped for matrix offsets so bricks never pass
        # through their final position.
        value = 1.0 - (math.cos(t * math.pi * 4.5) * math.exp(-6.0 * t))
        return _clamp01(value)
    if curve == BUILD_MOTION_CURVE_QUADRATIC:
        return t * t
    if curve == BUILD_MOTION_CURVE_BOUNCE:
        n = 7.5625
        d = 2.75
        first_contact_t = 1.0 / d
        if t > first_contact_t:
            settle_scale = max(
                0.0001,
                min(1.0, float(BUILD_ANIMATION_BOUNCE_SETTLE_TIME_SCALE)),
            )
            t = first_contact_t + ((t - first_contact_t) / settle_scale)
            t = _clamp01(t)
        if t < (1.0 / d):
            value = n * t * t
        elif t < (2.0 / d):
            t -= 1.5 / d
            value = (n * t * t) + 0.75
        elif t < (2.5 / d):
            t -= 2.25 / d
            value = (n * t * t) + 0.9375
        else:
            t -= 2.625 / d
            value = (n * t * t) + 0.984375
        return _clamp01(value)
    return t ** BUILD_ANIMATION_SLAM_EXPONENT


def build_scale_for_progress(local_progress, enabled=False):
    if not enabled:
        return 1.0
    return BUILD_ANIMATION_MIN_SCALE + (
        (1.0 - BUILD_ANIMATION_MIN_SCALE) * _clamp01(local_progress)
    )


def _motion_curve_has_reached_landing(progress, curve, custom_curve=None):
    progress = _clamp01(progress)
    if progress <= 0.0:
        return False
    curve = int(curve)
    if curve == BUILD_MOTION_CURVE_BOUNCE:
        return progress >= (1.0 / 2.75)

    if apply_motion_curve(progress, curve, custom_curve) >= 1.0 - 1.0e-9:
        return True

    # Spring and custom curves can touch the landing point before their final
    # local progress. Keep tilt settled once the vertical curve has contacted.
    samples = 32
    for i in range(1, samples + 1):
        sample_t = progress * (float(i) / float(samples))
        if apply_motion_curve(sample_t, curve, custom_curve) >= 1.0 - 1.0e-9:
            return True
    return False


def _contact_progress_for_motion(local_progress, motion_progress, drop_t, motion_curve, custom_curve=None):
    local_progress = _clamp01(local_progress)
    motion_progress = _clamp01(motion_progress)
    drop_t = _clamp01(drop_t)
    if _motion_curve_has_reached_landing(motion_progress, motion_curve, custom_curve):
        return 1.0
    return max(local_progress, drop_t)


def _stable_unit_noise(*values):
    h = 2166136261
    for value in values:
        n = int(value) & 0xFFFFFFFF
        for shift in (0, 8, 16, 24):
            h ^= (n >> shift) & 0xFF
            h = (h * 16777619) & 0xFFFFFFFF
    return h / float(0xFFFFFFFF)


def build_tilt_for_progress(
    placement,
    local_progress,
    *,
    enabled=False,
    amount_degrees=BUILD_ANIMATION_DEFAULT_TILT_DEGREES,
):
    """Return deterministic X/Z tilt radians that fade out at landing."""
    if not enabled:
        return (0.0, 0.0)
    amount = max(0.0, min(360.0, float(amount_degrees)))
    if amount <= 0.0:
        return (0.0, 0.0)
    fade = 1.0 - _clamp01(local_progress)
    if fade <= 0.0:
        return (0.0, 0.0)

    x = int(getattr(placement, "x", 0))
    y = int(getattr(placement, "y", 0))
    z = int(getattr(placement, "z", 0))
    w = int(getattr(placement, "w", 1))
    h = int(getattr(placement, "h", 1))
    d = int(getattr(placement, "d", 1))
    rotation_y = int(getattr(placement, "rotation_y", 0))
    x_noise = (_stable_unit_noise(x, y, z, w, h, d, rotation_y, 17) * 2.0) - 1.0
    z_noise = (_stable_unit_noise(x, y, z, w, h, d, rotation_y, 91) * 2.0) - 1.0
    amplitude = math.radians(amount) * fade
    return (x_noise * amplitude, z_noise * amplitude)


def build_tilt_clearance(
    tilt_x,
    tilt_z,
    brick_height,
    plate_size,
    *,
    enabled=False,
):
    """Approximate horizontal clearance needed by a tilted brick."""
    if not enabled:
        return 0.0
    height = max(0.0, float(brick_height) * float(plate_size))
    if height <= 0.0:
        return 0.0
    max_tilt = min((math.pi * 0.5), max(abs(float(tilt_x)), abs(float(tilt_z))))
    if max_tilt <= 0.0:
        return 0.0
    return height * math.sin(max_tilt) * BUILD_ANIMATION_TILT_CLEARANCE_MULTIPLIER


def build_animation_states(
    placements,
    progress,
    *,
    time_progress=None,
    y_offset=BUILD_ANIMATION_DEFAULT_Y_OFFSET,
    stagger=BUILD_ANIMATION_DEFAULT_STAGGER,
    hang_time=1.0,
    motion_curve=BUILD_MOTION_CURVE_SLAM,
    custom_curve=None,
    order_offset=0,
):
    """Return per-placement animation states in chronological order."""
    ordered = ordered_placements(placements)
    return _build_animation_states_for_ordered(
        ordered,
        progress,
        time_progress=time_progress,
        y_offset=y_offset,
        stagger=stagger,
        hang_time=hang_time,
        motion_curve=motion_curve,
        custom_curve=custom_curve,
        order_offset=order_offset,
    )


def _build_animation_states_for_ordered(
    ordered,
    progress,
    *,
    time_progress=None,
    y_offset,
    stagger,
    hang_time=1.0,
    motion_curve=BUILD_MOTION_CURVE_SLAM,
    custom_curve=None,
    order_offset=0,
):
    n = len(ordered)
    if n <= 0:
        return []

    return _build_fixed_motion_states_for_ordered(
        ordered,
        progress,
        time_progress=time_progress,
        y_offset=y_offset,
        stagger=stagger,
        hang_time=hang_time,
        motion_curve=motion_curve,
        custom_curve=custom_curve,
        order_offset=order_offset,
        use_y_variation=True,
    )


def _build_fixed_motion_states_for_ordered(
    ordered,
    progress,
    *,
    time_progress=None,
    y_offset,
    stagger,
    hang_time=1.0,
    motion_curve=BUILD_MOTION_CURVE_SLAM,
    custom_curve=None,
    order_offset=0,
    use_y_variation=True,
):
    """Build states with fixed per-placement curve duration.

    The progress slider schedules when each placement starts, while the selected
    motion curve gets a consistent duration for every placement. This prevents
    upper/later bricks from having their curve squeezed into the end of the
    slider range.
    """
    n = len(ordered)
    if n <= 0:
        return []

    # Brick-index scheduling with a per-layer barrier.
    #
    # Two independent timing concepts:
    #
    # - `duration` = how many cursor ticks each brick's individual drop
    #   takes. Constant per build so the fall is always visible no
    #   matter what stagger is set to.
    #
    # - `step_size` = how many cursor ticks pass between consecutive
    #   bricks starting. Driven by stagger:
    #     stagger=0  → step_size == duration   (strict sequential, no
    #                                           in-flight overlap)
    #     stagger=1  → step_size == 1          (max overlap, swarm)
    #
    # The per-layer barrier additionally jumps the cursor when the Y
    # changes so layer N+1's first brick can't start until layer N's
    # last brick has finished its drop — even at stagger=1.
    effective_stagger = _effective_stagger(stagger)
    duration = float(BUILD_ANIMATION_IN_FLIGHT_MAX)
    step_size = max(1.0, duration - effective_stagger * (duration - 1.0))

    start_ticks = [0.0] * n
    cursor_pos = 0.0
    prev_layer = None
    last_brick_in_layer_start = 0.0
    for i, placement in enumerate(ordered):
        layer = int(getattr(placement, "y", 0))
        if prev_layer is not None and layer != prev_layer:
            # New layer: wait for the previous layer's last-started
            # brick to finish its drop. That brick started at
            # last_brick_in_layer_start and lands `duration` later.
            cursor_pos = last_brick_in_layer_start + duration
        start_ticks[i] = cursor_pos
        last_brick_in_layer_start = cursor_pos
        cursor_pos += step_size
        prev_layer = layer
    total_ticks = last_brick_in_layer_start + duration
    if total_ticks <= 0.0:
        total_ticks = 1.0

    p = _clamp01(progress)
    motion_p = _clamp01(p if time_progress is None else time_progress)
    if int(motion_curve) != BUILD_MOTION_CURVE_BOUNCE:
        motion_p = p
    cursor = motion_p * total_ticks
    start_offset = max(0.0, float(y_offset))
    states = []
    for i, placement in enumerate(ordered):
        # local_progress = how far brick i is through its individual
        # drop. 0 = just started, 1 = landed.
        local_progress = _clamp01((cursor - start_ticks[i]) / duration)
        if motion_p >= 1.0 or local_progress >= 1.0 - 1.0e-9:
            local_progress = 1.0
        motion_progress = _apply_brick_hang_time(local_progress, hang_time)
        drop_t = apply_motion_curve(motion_progress, motion_curve, custom_curve)
        contact_progress = _contact_progress_for_motion(
            local_progress,
            motion_progress,
            drop_t,
            motion_curve,
            custom_curve,
        )
        y_variation = (
            _build_y_offset_variation(placement, effective_stagger, local_progress)
            if bool(use_y_variation)
            else 1.0
        )
        animated_y_offset = (1.0 - drop_t) * start_offset * y_variation
        states.append(
            BuildAnimationState(
                placement=placement,
                order_index=int(order_offset) + i,
                local_progress=local_progress,
                drop_t=drop_t,
                y_offset=animated_y_offset,
                contact_progress=contact_progress,
            )
        )
    return states


def _build_smooth_top_states_for_ordered(
    ordered,
    progress,
    *,
    y_offset,
    stagger,
    hang_time,
    motion_curve,
    custom_curve=None,
    order_offset=0,
    min_start_by_obj=None,
):
    ordered = list(ordered or [])
    if not ordered:
        return []

    starts = _smooth_top_start_times(
        ordered,
        stagger,
        min_start_by_obj,
    )
    p = _clamp01(progress)
    start_offset = max(0.0, float(y_offset))
    states = []
    for i, placement in enumerate(ordered):
        cap_start = starts[i]
        local_progress = _clamp01(
            (p - cap_start) / max(0.0001, float(BUILD_ANIMATION_FIXED_MOTION_DURATION))
        )
        if p >= 1.0 or local_progress >= 1.0 - 1.0e-9:
            local_progress = 1.0
        motion_progress = _apply_brick_hang_time(local_progress, hang_time)
        drop_t = apply_motion_curve(motion_progress, motion_curve, custom_curve)
        contact_progress = _contact_progress_for_motion(
            local_progress,
            motion_progress,
            drop_t,
            motion_curve,
            custom_curve,
        )
        states.append(
            BuildAnimationState(
                placement=placement,
                order_index=int(order_offset) + i,
                local_progress=local_progress,
                drop_t=drop_t,
                y_offset=(1.0 - drop_t) * start_offset,
                contact_progress=contact_progress,
            )
        )
    return states


def _smooth_top_start_times(ordered, stagger, min_start_by_obj=None):
    ordered = list(ordered or [])
    if not ordered:
        return []

    layer_indices, _, layer_ranks = _ordered_layer_timing(ordered)
    effective_stagger = _effective_stagger(stagger)
    base_starts = _fixed_motion_start_times(
        ordered,
        layer_indices,
        layer_ranks,
        effective_stagger,
    )
    min_start_by_obj = dict(min_start_by_obj or {})
    raw_starts = [
        max(base_starts[i], _clamp01(min_start_by_obj.get(id(placement), 0.0)))
        for i, placement in enumerate(ordered)
    ]
    return _spread_late_fixed_motion_starts(raw_starts)


def _spread_late_fixed_motion_starts(raw_starts):
    raw_starts = [max(0.0, float(start)) for start in (raw_starts or [])]
    if not raw_starts:
        return []

    duration = max(0.0001, float(BUILD_ANIMATION_FIXED_MOTION_DURATION))
    latest_start = max(0.0, 1.0 - duration)
    adjusted = [min(start, latest_start) for start in raw_starts]
    late = [
        (raw_starts[i], i)
        for i in range(len(raw_starts))
        if raw_starts[i] > latest_start
    ]
    if len(late) <= 1:
        return adjusted

    late.sort(key=lambda item: (item[0], item[1]))
    tail_start = max(0.0, latest_start - min(duration, latest_start))
    tail_span = max(0.0, latest_start - tail_start)
    for rank, (_, i) in enumerate(late):
        t = 0.0 if len(late) <= 1 else float(rank) / float(len(late) - 1)
        adjusted[i] = tail_start + (tail_span * t)
    return adjusted


def _fixed_motion_start_times(ordered, layer_indices, layer_ranks, effective_stagger):
    if not ordered:
        return []
    schedule_positions = []
    for i in range(len(ordered)):
        schedule_positions.append(
            float(layer_indices[i])
            + (
                float(layer_ranks[i])
                * effective_stagger
                * BUILD_ANIMATION_IN_LAYER_STAGGER
            )
        )
    schedule_range = max(schedule_positions) if schedule_positions else 0.0
    start_span = max(0.0, 1.0 - float(BUILD_ANIMATION_FIXED_MOTION_DURATION))
    if schedule_range <= 0.0:
        return [0.0 for _ in ordered]
    return [
        (pos / schedule_range) * start_span
        for pos in schedule_positions
    ]


def _apply_brick_hang_time(local_progress, hang_time):
    progress = _clamp01(local_progress)
    if progress <= 0.0 or progress >= 1.0:
        return progress
    hang = _clamp01(hang_time)
    exponent = BUILD_ANIMATION_MIN_HANG_EXPONENT + (
        (1.0 - BUILD_ANIMATION_MIN_HANG_EXPONENT) * hang
    )
    return _clamp01(progress ** exponent)


def _build_y_offset_variation(placement, effective_stagger, local_progress):
    if effective_stagger <= 0.0:
        return 1.0
    progress = _clamp01(local_progress)
    if progress <= 0.0 or progress >= 1.0:
        return 1.0
    amount = max(0.0, min(1.0, float(BUILD_ANIMATION_Y_OFFSET_VARIATION)))
    if amount <= 0.0:
        return 1.0
    noise = _stable_unit_noise(
        int(getattr(placement, "x", 0)),
        int(getattr(placement, "y", 0)),
        int(getattr(placement, "z", 0)),
        int(getattr(placement, "w", 1)),
        int(getattr(placement, "h", 1)),
        int(getattr(placement, "d", 1)),
        int(getattr(placement, "rotation_y", 0)),
        233,
    )
    return 1.0 - (noise * amount)


def _cap_speed_multiplier(placement):
    amount = max(0.0, min(1.0, float(BUILD_ANIMATION_CAP_SPEED_VARIATION)))
    if amount <= 0.0:
        return 1.0
    noise = _stable_unit_noise(
        int(getattr(placement, "x", 0)),
        int(getattr(placement, "y", 0)),
        int(getattr(placement, "z", 0)),
        int(getattr(placement, "w", 1)),
        int(getattr(placement, "h", 1)),
        int(getattr(placement, "d", 1)),
        int(getattr(placement, "rotation_y", 0)),
        311,
    )
    return 1.0 + (((noise * 2.0) - 1.0) * amount)


def _ordered_layer_timing(ordered):
    """Return per-placement base-Y layer indices and within-layer ranks."""
    layers = sorted({
        int(getattr(placement, "y", 0))
        for placement in (ordered or [])
    })
    if not layers:
        return [], 0, []
    layer_by_y = {
        y: i
        for i, y in enumerate(layers)
    }
    layer_sizes = {}
    for placement in ordered:
        y = int(getattr(placement, "y", 0))
        layer_sizes[y] = layer_sizes.get(y, 0) + 1

    layer_seen = {}
    layer_indices = []
    layer_ranks = []
    for placement in ordered:
        y = int(getattr(placement, "y", 0))
        rank = layer_seen.get(y, 0)
        layer_seen[y] = rank + 1
        layer_indices.append(layer_by_y[y])
        layer_size = layer_sizes.get(y, 1)
        layer_ranks.append(
            0.0
            if layer_size <= 1
            else float(rank) / float(layer_size - 1)
        )
    return layer_indices, len(layers), layer_ranks


def _ordered_layer_indices(ordered):
    layer_indices, layer_count, _ = _ordered_layer_timing(ordered)
    return layer_indices, layer_count


def _animation_finish_progress(index, total_count, stagger):
    n = int(total_count)
    if n <= 0:
        return 1.0
    return _clamp01(float(index + 1) / float(n))


def phased_build_animation_states(
    placements,
    progress,
    *,
    time_progress=None,
    top_progress=None,
    top_time_progress=None,
    top_cap_ids=None,
    top_surface_start=None,
    top_surface_phase=0.0,
    blend_top_surface=False,
    y_offset=BUILD_ANIMATION_DEFAULT_Y_OFFSET,
    stagger=BUILD_ANIMATION_DEFAULT_STAGGER,
    hang_time=1.0,
    motion_curve=BUILD_MOTION_CURVE_SLAM,
    custom_curve=None,
):
    """Animate structural placements with optional overlapping top caps."""
    top_cap_ids = set(top_cap_ids or ())
    ordered = ordered_placements(placements)
    if not ordered:
        return []

    cap_phase = _clamp01(top_surface_phase)
    if not top_cap_ids or cap_phase <= 0.0:
        return _build_animation_states_for_ordered(
            ordered,
            progress,
            time_progress=time_progress,
            y_offset=y_offset,
            stagger=stagger,
            hang_time=hang_time,
            motion_curve=motion_curve,
            custom_curve=custom_curve,
        )

    if blend_top_surface:
        generated_cap_ids = {
            id(p)
            for p in ordered
            if getattr(getattr(p, "brick", None), "name", "") == "visual_smooth_cap_1x1"
        }
        if top_progress is not None:
            structural = [p for p in ordered if id(p) not in top_cap_ids]
            caps = [p for p in ordered if id(p) in top_cap_ids]
        else:
            structural = [
                p
                for p in ordered
                if id(p) not in top_cap_ids or id(p) not in generated_cap_ids
            ]
            caps = [
                p
                for p in ordered
                if id(p) in top_cap_ids and id(p) in generated_cap_ids
            ]
    else:
        structural = [p for p in ordered if id(p) not in top_cap_ids]
        caps = [p for p in ordered if id(p) in top_cap_ids]
    if not structural or not caps:
        return _build_animation_states_for_ordered(
            ordered,
            progress,
            time_progress=time_progress,
            y_offset=y_offset,
            stagger=stagger,
            hang_time=hang_time,
            motion_curve=motion_curve,
            custom_curve=custom_curve,
        )

    p = _clamp01(progress)
    clock_p = _clamp01(p if time_progress is None else time_progress)
    if int(motion_curve) != BUILD_MOTION_CURVE_BOUNCE:
        clock_p = p
    cap_p = _clamp01(p if top_progress is None else top_progress)
    cap_clock_p = _clamp01(cap_p if top_time_progress is None else top_time_progress)
    if int(motion_curve) != BUILD_MOTION_CURVE_BOUNCE:
        cap_clock_p = cap_p
    if top_progress is not None:
        structural_progress = p
        structural_time_progress = clock_p
        cap_progress = cap_p
        cap_time_progress = cap_clock_p
    elif not blend_top_surface:
        structural_phase = max(0.0001, 1.0 - cap_phase)
        structural_progress = _clamp01(p / structural_phase)
        structural_time_progress = _clamp01(clock_p / structural_phase)
        cap_progress = _clamp01((p - structural_phase) / cap_phase)
        cap_time_progress = _clamp01((clock_p - structural_phase) / cap_phase)
    else:
        structural_progress = p
        structural_time_progress = clock_p
        cap_start = _clamp01(
            BUILD_ANIMATION_BLEND_TOP_START
            if top_surface_start is None
            else top_surface_start
        )
        cap_duration = max(0.0001, cap_phase)
        cap_progress = _clamp01((p - cap_start) / cap_duration)
        cap_time_progress = _clamp01((clock_p - cap_start) / cap_duration)
    structural_states = _build_animation_states_for_ordered(
        structural,
        structural_progress,
        time_progress=structural_time_progress,
        y_offset=y_offset,
        stagger=stagger,
        hang_time=hang_time,
        motion_curve=motion_curve,
        custom_curve=custom_curve,
        order_offset=0,
    )
    cap_hang_time = (
        1.0
        if int(motion_curve) == BUILD_MOTION_CURVE_BOUNCE
        else hang_time
    )
    structural_state_by_obj = {
        id(state.placement): state
        for state in structural_states
    }
    structural_layer_indices, structural_layer_count, structural_layer_ranks = _ordered_layer_timing(structural)
    structural_layer_index = {
        id(placement): structural_layer_indices[i]
        for i, placement in enumerate(structural)
    }
    support_at = _build_support_lookup(structural) if blend_top_surface else {}
    min_cap_start_by_obj = {}
    if top_progress is not None and blend_top_surface:
        effective_stagger = _effective_stagger(stagger)
        structural_starts = _fixed_motion_start_times(
            structural,
            structural_layer_indices,
            structural_layer_ranks,
            effective_stagger,
        )
        structural_finish_by_obj = {
            id(placement): _clamp01(
                structural_starts[i] + float(BUILD_ANIMATION_FIXED_MOTION_DURATION)
            )
            for i, placement in enumerate(structural)
        }
        for cap in caps:
            supports = _supporting_placements_from_lookup(cap, support_at)
            if supports:
                min_cap_start_by_obj[id(cap)] = max(
                    structural_finish_by_obj.get(id(support), 0.0)
                    for support in supports
                )
    if top_progress is not None:
        cap_start_by_obj = {
            id(cap): start
            for cap, start in zip(
                caps,
                _smooth_top_start_times(caps, stagger, min_cap_start_by_obj),
            )
        }
        cap_states = _build_smooth_top_states_for_ordered(
            caps,
            cap_time_progress,
            y_offset=y_offset,
            stagger=stagger,
            hang_time=cap_hang_time,
            motion_curve=motion_curve,
            custom_curve=custom_curve,
            order_offset=len(structural),
            min_start_by_obj=min_cap_start_by_obj,
        )
    else:
        cap_start_by_obj = {}
        cap_states = _build_animation_states_for_ordered(
            caps,
            cap_progress,
            time_progress=cap_time_progress,
            y_offset=y_offset,
            stagger=stagger,
            hang_time=cap_hang_time,
            motion_curve=motion_curve,
            custom_curve=custom_curve,
            order_offset=len(structural),
        )
    gated_cap_states = []
    for cap_i, state in enumerate(cap_states):
        if not blend_top_surface:
            gated_cap_states.append(state)
            continue

        supports = _supporting_placements_from_lookup(state.placement, support_at)
        if not supports:
            gated_cap_states.append(
                BuildAnimationState(
                    placement=state.placement,
                    order_index=state.order_index,
                    local_progress=0.0,
                    drop_t=0.0,
                    y_offset=max(0.0, float(y_offset)),
                )
            )
            continue

        supports_landed = all(
            structural_state_by_obj.get(id(support)) is not None
            and structural_state_by_obj[id(support)].local_progress >= 1.0
            for support in supports
        )
        if top_progress is not None:
            support_gate_start = cap_start_by_obj.get(
                id(state.placement),
                min_cap_start_by_obj.get(id(state.placement), 0.0),
            )
            if supports_landed or p >= support_gate_start:
                gated_cap_states.append(state)
            else:
                gated_cap_states.append(
                    BuildAnimationState(
                        placement=state.placement,
                        order_index=state.order_index,
                        local_progress=0.0,
                        drop_t=0.0,
                        y_offset=max(0.0, float(y_offset)),
                    )
                )
            continue

        support_ready = max(
            _animation_finish_progress(
                structural_layer_index[id(support)],
                structural_layer_count,
                stagger,
            )
            for support in supports
        )
        auto_start = _clamp01(
            BUILD_ANIMATION_BLEND_TOP_START
            if top_surface_start is None
            else top_surface_start
        )
        cap_duration_target = BUILD_ANIMATION_BLEND_TOP_DURATION * _cap_speed_multiplier(state.placement)
        if int(motion_curve) == BUILD_MOTION_CURVE_BOUNCE:
            cap_start = min(max(auto_start, support_ready), max(0.0, 1.0 - cap_duration_target))
        else:
            cap_start = max(auto_start, support_ready)
        cap_duration = min(
            cap_duration_target,
            max(0.0001, 1.0 - cap_start),
        )
        cap_motion_p = clock_p if int(motion_curve) == BUILD_MOTION_CURVE_BOUNCE else p
        local_progress = _clamp01((cap_motion_p - cap_start) / cap_duration)
        if p >= 1.0 and supports_landed:
            local_progress = 1.0
        motion_progress = _apply_brick_hang_time(local_progress, cap_hang_time)
        drop_t = apply_motion_curve(motion_progress, motion_curve, custom_curve)
        contact_progress = _contact_progress_for_motion(
            local_progress,
            motion_progress,
            drop_t,
            motion_curve,
            custom_curve,
        )
        if local_progress <= 0.0:
            gated_cap_states.append(
                BuildAnimationState(
                    placement=state.placement,
                    order_index=state.order_index,
                    local_progress=0.0,
                    drop_t=0.0,
                    y_offset=max(0.0, float(y_offset)),
                )
            )
        else:
            gated_cap_states.append(
                BuildAnimationState(
                    placement=state.placement,
                    order_index=len(structural) + cap_i,
                    local_progress=local_progress,
                    drop_t=drop_t,
                    y_offset=(1.0 - drop_t) * max(0.0, float(y_offset)),
                    contact_progress=contact_progress,
                )
            )
    return structural_states + gated_cap_states
