"""Repair pass for ungrounded bricks after the buildability check.

When `Make Physically Accurate` is enabled, the existing pipeline drops
floating fragments at the voxel-island level. That leaves individual
bricks within an island that have no real stud-to-cavity support
(unsupported but still attached to the largest island via voxel
adjacency). This module attempts to fix those one at a time.

For each ungrounded brick X at grid position (x, y, z) with footprint
(w, h, d), we try (in order):

1. **Rotate 90°** in place — swap w/d. Accept if the rotated footprint
   has at least one stud-cell overlap with a brick at y - h, and the
   rotation does not intersect any other brick at y.
2. **Lateral shift** by ±1 cell in x and z (8 candidate positions).
   Accept the first shifted position that is supported with no
   intersection.
3. **Downsize** to a smaller library brick at (x, y, z). Iterate
   library footprints by total stud count ascending; accept the first
   that overlaps a stud-cell below.
4. **Drop** if none of the above can find support.

Repair runs up to `max_rounds` times to handle cascade failures
(repairing one brick may un-support another above it). After each
round we re-run check_buildability and stop if no ungrounded bricks
remain.

After repair, a final **fill pass** walks the original voxel
occupancy bottom-up and places the largest supported library brick
at each cell that was supposed to be filled but isn't covered by any
current placement. Cells that have no supported library brick at all
are left empty.
"""
from dataclasses import replace
from typing import Any, List, Optional, Tuple

import numpy as np

from .fitter import BrickPlacement
from .library import BrickLibrary, BrickType
from .connectivity import check_buildability


def _footprint_overlap_cells(
    ax: int, az: int, aw: int, ad: int,
    bx: int, bz: int, bw: int, bd: int,
) -> int:
    """Cells shared between two axis-aligned grid footprints."""
    ox = min(ax + aw, bx + bw) - max(ax, bx)
    oz = min(az + ad, bz + bd) - max(az, bz)
    if ox <= 0 or oz <= 0:
        return 0
    return int(ox * oz)


def _overlaps_3d(
    a_xyz_whd: Tuple[int, int, int, int, int, int],
    b_xyz_whd: Tuple[int, int, int, int, int, int],
) -> bool:
    """True iff two axis-aligned grid boxes share any cell."""
    ax, ay, az, aw, ah, ad = a_xyz_whd
    bx, by, bz, bw, bh, bd = b_xyz_whd
    if min(ax + aw, bx + bw) <= max(ax, bx):
        return False
    if min(ay + ah, by + bh) <= max(ay, by):
        return False
    if min(az + ad, bz + bd) <= max(az, bz):
        return False
    return True


def _box_for(p: BrickPlacement) -> Tuple[int, int, int, int, int, int]:
    return (int(p.x), int(p.y), int(p.z), int(p.w), int(p.h), int(p.d))


def _is_supported_by_anything_below(
    p: BrickPlacement,
    placements: List[BrickPlacement],
    skip_index: Optional[int] = None,
) -> bool:
    """True iff p has at least one stud-cell aligned with the top of a
    brick directly below it. Bricks at y=0 are always supported (sit on
    the build plate)."""
    if int(p.y) == 0:
        return True
    target_y = int(p.y)
    for i, q in enumerate(placements):
        if skip_index is not None and i == skip_index:
            continue
        if int(q.y) + int(q.h) != target_y:
            continue
        if _footprint_overlap_cells(
            int(p.x), int(p.z), int(p.w), int(p.d),
            int(q.x), int(q.z), int(q.w), int(q.d),
        ) > 0:
            return True
    return False


def _candidate_intersects_others(
    candidate_box: Tuple[int, int, int, int, int, int],
    placements: List[BrickPlacement],
    skip_index: int,
) -> bool:
    """True iff the candidate box overlaps any other brick's 3D box.
    The original brick at skip_index is exempt (we're replacing it)."""
    for i, q in enumerate(placements):
        if i == skip_index:
            continue
        if _overlaps_3d(candidate_box, _box_for(q)):
            return True
    return False


def _candidate_inside_silhouette(
    candidate_box: Tuple[int, int, int, int, int, int],
    occupancy: Optional["np.ndarray"],
) -> bool:
    """True iff every cell of the candidate box is inside the source
    occupancy mask (i.e. would not place geometry where the source mesh
    said no brick should exist). When occupancy is None we skip the
    check (no silhouette information available — assume any cell ok)."""
    if occupancy is None:
        return True
    cx, cy, cz, cw, ch, cd = candidate_box
    Nx, Ny, Nz = occupancy.shape
    if cx < 0 or cy < 0 or cz < 0:
        return False
    if cx + cw > Nx or cy + ch > Ny or cz + cd > Nz:
        return False
    sub = occupancy[cx:cx + cw, cy:cy + ch, cz:cz + cd]
    return bool(sub.all())


def _candidate_supported_at(
    cx: int, cy: int, cz: int, cw: int, ch: int, cd: int,
    placements: List[BrickPlacement],
    skip_index: int,
) -> bool:
    """True iff a candidate box at (cx, cy, cz) with footprint (cw, ch, cd)
    has at least one stud-cell overlap with a brick directly below it,
    or sits on the build plate (cy == 0)."""
    if cy == 0:
        return True
    for i, q in enumerate(placements):
        if i == skip_index:
            continue
        if int(q.y) + int(q.h) != cy:
            continue
        if _footprint_overlap_cells(
            cx, cz, cw, cd,
            int(q.x), int(q.z), int(q.w), int(q.d),
        ) > 0:
            return True
    return False


def _rotate_in_place(
    p: BrickPlacement,
    placements: List[BrickPlacement],
    idx: int,
    occupancy: Optional["np.ndarray"],
) -> Optional[BrickPlacement]:
    """Try p with 90° rotation. Returns the new placement or None.

    Silhouette rule: the rotated footprint must stay entirely inside
    the source occupancy mask. We never let a repair extend the build
    outside what the source mesh said should exist.
    """
    # Square footprints don't change under rotation.
    if int(p.w) == int(p.d):
        return None
    new_rot = 0 if int(p.rotation_y) == 90 else 90
    candidate = replace(p, rotation_y=new_rot)
    cbox = _box_for(candidate)
    if not _candidate_inside_silhouette(cbox, occupancy):
        return None
    if _candidate_intersects_others(cbox, placements, idx):
        return None
    if not _candidate_supported_at(
        int(candidate.x), int(candidate.y), int(candidate.z),
        int(candidate.w), int(candidate.h), int(candidate.d),
        placements, idx,
    ):
        return None
    return candidate


_SHIFT_DELTAS = [
    (-1, 0), (1, 0), (0, -1), (0, 1),
    (-1, -1), (-1, 1), (1, -1), (1, 1),
]


def _lateral_shift(
    p: BrickPlacement,
    placements: List[BrickPlacement],
    idx: int,
    occupancy: Optional["np.ndarray"],
) -> Optional[BrickPlacement]:
    """Try shifting p ±1 cell in x/z. Returns first supported candidate.

    Silhouette rule: the shifted footprint must stay entirely inside
    the source occupancy mask. A shift that walks the brick out of
    the model breaks the silhouette and is rejected.
    """
    for dx, dz in _SHIFT_DELTAS:
        cx = int(p.x) + dx
        cz = int(p.z) + dz
        if cx < 0 or cz < 0:
            continue
        candidate = replace(p, x=cx, z=cz)
        cbox = _box_for(candidate)
        if not _candidate_inside_silhouette(cbox, occupancy):
            continue
        if _candidate_intersects_others(cbox, placements, idx):
            continue
        if not _candidate_supported_at(
            cx, int(p.y), cz,
            int(candidate.w), int(candidate.h), int(candidate.d),
            placements, idx,
        ):
            continue
        return candidate
    return None


def _downsize(
    p: BrickPlacement,
    placements: List[BrickPlacement],
    idx: int,
    library: BrickLibrary,
    occupancy: Optional["np.ndarray"],
) -> Optional[BrickPlacement]:
    """Try replacing p with a smaller library brick at the same (x,y,z).

    Iterates library bricks of matching height, footprint area smaller
    than p's, ascending — biggest-of-the-smaller first. Accepts the
    first that fits within p's original footprint AND is supported.
    """
    target_h = int(p.h)
    p_w = int(p.w)
    p_d = int(p.d)
    p_area = p_w * p_d
    candidates: List[BrickType] = [
        b for b in library.all_orientations()
        if int(b.height) == target_h
        and int(b.width * b.depth) < p_area
        and int(b.width) <= p_w
        and int(b.depth) <= p_d
    ]
    # Largest fitting smaller footprint first.
    candidates.sort(key=lambda b: -(int(b.width) * int(b.depth)))
    for bt in candidates:
        candidate = BrickPlacement(
            brick=bt,
            x=int(p.x),
            y=int(p.y),
            z=int(p.z),
            rotation_y=0,
            color_idx=int(getattr(p, "color_idx", -1)),
            rgb=tuple(getattr(p, "rgb", (180, 180, 180))),
        )
        cbox = _box_for(candidate)
        if not _candidate_inside_silhouette(cbox, occupancy):
            continue
        if _candidate_intersects_others(cbox, placements, idx):
            continue
        if not _candidate_supported_at(
            int(candidate.x), int(candidate.y), int(candidate.z),
            int(candidate.w), int(candidate.h), int(candidate.d),
            placements, idx,
        ):
            continue
        return candidate
    return None


def _placement_occupancy_mask(
    placements: List[BrickPlacement], shape: Tuple[int, int, int]
) -> np.ndarray:
    """Return a bool grid (Nx, Ny, Nz) marking cells covered by placements."""
    Nx, Ny, Nz = int(shape[0]), int(shape[1]), int(shape[2])
    mask = np.zeros((Nx, Ny, Nz), dtype=bool)
    for p in placements:
        x0, y0, z0 = int(p.x), int(p.y), int(p.z)
        x1 = min(Nx, x0 + int(p.w))
        y1 = min(Ny, y0 + int(p.h))
        z1 = min(Nz, z0 + int(p.d))
        x0 = max(0, x0)
        y0 = max(0, y0)
        z0 = max(0, z0)
        if x0 < x1 and y0 < y1 and z0 < z1:
            mask[x0:x1, y0:y1, z0:z1] = True
    return mask


def _fill_holes_with_supported_bricks(
    placements: List[BrickPlacement],
    occupancy: np.ndarray,
    library: BrickLibrary,
    diagnostics: Optional[dict] = None,
) -> Tuple[List[BrickPlacement], int]:
    """Fill voxel cells that should be occupied (per `occupancy`) but
    aren't covered by any placement. Bottom-up greedy: at each empty
    cell visited in (y, z, x) order, try the largest library brick
    whose footprint fits within the empty region at that cell AND has
    stud-cell support from a brick directly below. Skip if no
    supported library brick exists at that cell.

    Returns (updated_placements, n_filled_cells_via_new_bricks).
    """
    if occupancy is None or not isinstance(occupancy, np.ndarray):
        return list(placements), 0

    Nx, Ny, Nz = occupancy.shape
    placement_mask = _placement_occupancy_mask(placements, (Nx, Ny, Nz))
    needs_fill = occupancy & ~placement_mask
    if not bool(needs_fill.any()):
        return list(placements), 0

    # Library candidates grouped by height. We try each candidate at
    # height 1 first because a 1-plate fill is the most flexible filler;
    # taller bricks can be added later if a column of empty cells
    # supports them.
    all_bricks = library.all_orientations()
    bricks_by_height: dict = {}
    for bt in all_bricks:
        bricks_by_height.setdefault(int(bt.height), []).append(bt)
    # Within each height, prefer larger footprints.
    for h_key in bricks_by_height:
        bricks_by_height[h_key].sort(
            key=lambda b: -(int(b.width) * int(b.depth))
        )
    available_heights = sorted(bricks_by_height.keys())

    new_placements = list(placements)
    new_cells_filled = 0

    # Diagnostic counters for the user-facing log line so we can see
    # WHY cells didn't fill. Updated only when `diagnostics` is non-None.
    if diagnostics is not None:
        diagnostics["cells_needing_fill"] = int(needs_fill.sum())
        diagnostics["cells_skipped_no_candidate"] = 0
        diagnostics["cells_skipped_no_support"] = 0
        diagnostics["cells_skipped_outside_silhouette"] = 0
        diagnostics["cells_skipped_collision"] = 0
        diagnostics["cells_skipped_outside_grid"] = 0
        diagnostics["library_heights"] = sorted(set(int(b.height) for b in all_bricks))
        diagnostics["library_has_1x1x1"] = bool(any(
            int(b.width) == 1 and int(b.depth) == 1 and int(b.height) == 1
            for b in all_bricks
        ))
        diagnostics["library_n_orientations"] = int(len(all_bricks))
        diagnostics["fail_y_no_support"] = {}
        diagnostics["fail_y_no_candidate"] = {}
        diagnostics["fail_y_collision"] = {}
        diagnostics["fail_y_outside_grid"] = {}
        diagnostics["fail_y_partial_silhouette"] = {}

        # Overhang diagnostic: for every empty silhouette cell at (x, y, z)
        # with y >= 1, is the cell directly below (x, y-1, z) also OUTSIDE
        # the silhouette? If yes, this cell is over a void in the source
        # mesh — physically unbuildable without a bridging cheat. Counts
        # are reported per Y so we can see how much of the failure budget
        # is "real overhang" vs "fill-pass blocker".
        diagnostics["overhang_by_y"] = {}
        if Ny >= 2:
            below = np.zeros_like(occupancy)
            below[:, 1:, :] = occupancy[:, :-1, :]
            overhang_mask = needs_fill & ~below
            overhang_mask[:, 0, :] = False  # y=0 has no "below"
            ohx, ohy, ohz = np.where(overhang_mask)
            for yy in ohy.tolist():
                diagnostics["overhang_by_y"][int(yy)] = (
                    diagnostics["overhang_by_y"].get(int(yy), 0) + 1
                )

    # Live filled-mask: 3D numpy bool, mutated as we place bricks. O(1)
    # cell membership check vs O(N) any(...) over placements.
    filled = placement_mask.copy()

    # Per-Y "top-of-something" mask: cells (x, z) where a placement's
    # top face lives. Built once now and updated as we add new bricks
    # so the support check stays O(1).
    top_at_y = np.zeros((Ny, Nx, Nz), dtype=bool)
    # Per-Y placement-id grid: which placement's top sits at this (y, x, z).
    # We use this to score "distinct bricks bridged below" — a fill brick
    # that sits on top of TWO different bricks scores higher than one
    # that sits on a single wide brick, because bridging is structurally
    # better. -1 means "no placement's top here." int32 supports up to
    # ~2 billion placements, plenty.
    top_id_at_y = np.full((Ny, Nx, Nz), -1, dtype=np.int32)
    for p_idx, p in enumerate(new_placements):
        top_y = int(p.y) + int(p.h)
        if 0 <= top_y < Ny:
            x0, z0 = int(p.x), int(p.z)
            x1 = min(Nx, x0 + int(p.w))
            z1 = min(Nz, z0 + int(p.d))
            x0 = max(0, x0)
            z0 = max(0, z0)
            if x0 < x1 and z0 < z1:
                top_at_y[top_y, x0:x1, z0:z1] = True
                top_id_at_y[top_y, x0:x1, z0:z1] = p_idx

    # ANCHOR PASS — plant 1x1 stud bricks BENEATH overhang cells, in the
    # column of voxels outside the source silhouette but above the build
    # plate (or above the next-lower silhouette cell). These give the
    # overhang cell a foundation to attach to. Anchors live OUTSIDE the
    # silhouette mask, so the existing collision/silhouette checks in
    # the main fill loop ignore them as candidates and they don't count
    # toward coverage. They DO count for support, because they update
    # `top_at_y`.
    bricks_1x1_by_height: dict = {
        int(bt.height): bt
        for bt in all_bricks
        if int(bt.width) == 1 and int(bt.depth) == 1
    }
    anchor_heights_desc = sorted(bricks_1x1_by_height.keys(), reverse=True)
    anchors_planted = 0
    if anchor_heights_desc and Ny >= 2:
        # Overhang root mask: needs-fill cell at (x, y>0, z) whose y-1
        # cell is OUTSIDE the silhouette. The cell directly below needs
        # an anchor stack down to either y=0 or the first silhouette cell
        # we encounter walking down.
        sil_below = np.zeros_like(occupancy)
        sil_below[:, 1:, :] = occupancy[:, :-1, :]
        overhang_root_mask = needs_fill & ~sil_below
        overhang_root_mask[:, 0, :] = False
        roots_x, roots_y, roots_z = np.where(overhang_root_mask)

        # Group root cells by (x, z) so each column gets one anchor stack
        # even if it has multiple overhang cells stacked above each other.
        # The lowest overhang root in each column is the one whose y-1
        # marks the top of the anchor stack.
        col_root_y: dict = {}
        for k in range(roots_x.shape[0]):
            cx = int(roots_x[k])
            cz = int(roots_z[k])
            cy = int(roots_y[k])
            prev = col_root_y.get((cx, cz))
            if prev is None or cy < prev:
                col_root_y[(cx, cz)] = cy

        for (cx, cz), root_y in col_root_y.items():
            # Anchor stack covers cells [stack_bottom, root_y - 1] in y.
            # Walk DOWN from root_y - 1 until we hit y=0 or a silhouette
            # cell or an already-filled cell — that's our floor.
            top_anchor_y = root_y - 1
            stack_bottom = top_anchor_y
            while stack_bottom > 0:
                next_y = stack_bottom - 1
                if bool(occupancy[cx, next_y, cz]):
                    break  # silhouette resumes below — solid foundation
                if bool(filled[cx, next_y, cz]):
                    break  # something already there
                stack_bottom = next_y

            # Plant anchor bricks bottom-up. At each step pick the
            # tallest 1x1 brick that fits remaining_h and the column
            # above the current y-cursor.
            y_cursor = stack_bottom
            while y_cursor <= top_anchor_y:
                remaining = top_anchor_y - y_cursor + 1
                placed_h = 0
                for h_try in anchor_heights_desc:
                    if h_try > remaining:
                        continue
                    if y_cursor + h_try > Ny:
                        continue
                    # Every cell the anchor would cover must be empty
                    # (not already filled and not in silhouette — silhouette
                    # cells are reserved for real fill).
                    sub_filled = filled[cx, y_cursor:y_cursor + h_try, cz]
                    sub_occ = occupancy[cx, y_cursor:y_cursor + h_try, cz]
                    if bool(sub_filled.any()) or bool(sub_occ.any()):
                        continue
                    bt_anchor = bricks_1x1_by_height[h_try]
                    new_placements.append(BrickPlacement(
                        brick=bt_anchor,
                        x=cx,
                        y=y_cursor,
                        z=cz,
                        rotation_y=0,
                        color_idx=-1,
                        rgb=(255, 0, 255),
                        is_anchor=True,
                    ))
                    filled[cx, y_cursor:y_cursor + h_try, cz] = True
                    top_y_new = y_cursor + h_try
                    if 0 <= top_y_new < Ny:
                        top_at_y[top_y_new, cx, cz] = True
                        top_id_at_y[top_y_new, cx, cz] = (
                            len(new_placements) - 1
                        )
                    anchors_planted += 1
                    placed_h = h_try
                    break
                if placed_h == 0:
                    break  # nothing fits — give up on this column
                y_cursor += placed_h

    if diagnostics is not None:
        diagnostics["anchors_planted"] = int(anchors_planted)

    # Walk in ascending y, then z, then x so newly placed bricks become
    # available as support for higher cells in the same pass. needs_fill
    # is shape (Nx, Ny, Nz); np.where returns axis-0/1/2 = x/y/z arrays.
    xs_arr, ys_arr, zs_arr = np.where(needs_fill)
    order = np.lexsort((xs_arr, zs_arr, ys_arr))
    for k in order:
        x = int(xs_arr[k])
        y = int(ys_arr[k])
        z = int(zs_arr[k])
        if filled[x, y, z]:
            continue

        # How many empty-and-needed cells are stacked directly above (x, z)?
        # Caps the height of the brick we'll try.
        empty_column_h = 1
        while (
            y + empty_column_h < Ny
            and bool(needs_fill[x, y + empty_column_h, z])
            and not bool(filled[x, y + empty_column_h, z])
        ):
            empty_column_h += 1

        # Tallest height first: prefer one tall brick over a stack of
        # plates. We iterate the full library at each cell, so if a
        # tall candidate fails (collision, no support, silhouette), we
        # fall through to shorter heights — eventually a 1-plate will
        # land if anything physically fits. The diagnostic buckets
        # record the failure modes from ALL candidates tried before
        # attributing the cell, so this order doesn't poison telemetry.
        candidate_heights = sorted(
            (h for h in available_heights if h <= empty_column_h),
            reverse=True,
        )

        placed = False
        # Per-cell rejection reason flags. A cell may have multiple
        # candidates tried; we track which failure modes were hit so the
        # diagnostic histogram can attribute the cell to the right bucket.
        cell_silhouette_failed = False
        cell_support_failed = False
        cell_collision_failed = False
        cell_outside_grid_failed = False
        cell_any_candidate_tried = False

        # First-fit: try the largest brick that satisfies silhouette +
        # collision + support and place it. We previously tried score-
        # then-pick (enumerate every viable candidate, score, pick best)
        # to handle the "1x6 vs 2x6 dangling off rim" case, but in big
        # scenes with a large library that turned the inner loop into a
        # freeze-grade hotspot. First-fit is fast; the 1x6/2x6 issue can
        # be revisited with a candidate budget later.
        for h in candidate_heights:
            for bt in bricks_by_height[h]:
                bw = int(bt.width)
                bd = int(bt.depth)
                cell_any_candidate_tried = True
                if x + bw > Nx or z + bd > Nz:
                    cell_outside_grid_failed = True
                    continue
                sub_occ = occupancy[x:x + bw, y:y + h, z:z + bd]
                sub_filled = filled[x:x + bw, y:y + h, z:z + bd]
                if not bool(sub_occ.all()):
                    cell_silhouette_failed = True
                    continue
                if bool(sub_filled.any()):
                    cell_collision_failed = True
                    continue
                if y == 0:
                    supported = True
                else:
                    supported = bool(
                        top_at_y[y, x:x + bw, z:z + bd].any()
                    )
                if not supported:
                    cell_support_failed = True
                    continue

                # Inherit color from the cell directly below if there is one.
                rgb = (180, 180, 180)
                color_idx = -1
                if y > 0:
                    for q in new_placements:
                        if int(q.y) + int(q.h) != y:
                            continue
                        if (
                            int(q.x) <= x < int(q.x) + int(q.w)
                            and int(q.z) <= z < int(q.z) + int(q.d)
                        ):
                            rgb = tuple(getattr(q, "rgb", rgb))
                            color_idx = int(getattr(q, "color_idx", -1))
                            break

                new_placements.append(BrickPlacement(
                    brick=bt,
                    x=x,
                    y=y,
                    z=z,
                    rotation_y=0,
                    color_idx=color_idx,
                    rgb=rgb,
                ))
                filled[x:x + bw, y:y + h, z:z + bd] = True
                top_y_new = y + h
                if 0 <= top_y_new < Ny:
                    top_at_y[top_y_new, x:x + bw, z:z + bd] = True
                    top_id_at_y[top_y_new, x:x + bw, z:z + bd] = (
                        len(new_placements) - 1
                    )
                new_cells_filled += int(bw * bd * h)
                placed = True
                break
            if placed:
                break
        # Attribute this empty cell to a single bucket. Order is chosen
        # so the most informative reason wins: a cell that hits both a
        # collision and a support failure is reported as collision,
        # because collision points at a different bug class (already-
        # placed bricks blocking us) than support (no foundation).
        if not placed and diagnostics is not None:
            if not cell_any_candidate_tried:
                # Library gave us nothing of any height for this cell.
                diagnostics["cells_skipped_no_candidate"] += 1
                diagnostics["fail_y_no_candidate"][y] = (
                    diagnostics["fail_y_no_candidate"].get(y, 0) + 1
                )
            elif cell_collision_failed:
                diagnostics["cells_skipped_collision"] += 1
                diagnostics["fail_y_collision"][y] = (
                    diagnostics["fail_y_collision"].get(y, 0) + 1
                )
            elif cell_support_failed and not cell_silhouette_failed:
                diagnostics["cells_skipped_no_support"] += 1
                diagnostics["fail_y_no_support"][y] = (
                    diagnostics["fail_y_no_support"].get(y, 0) + 1
                )
            elif cell_silhouette_failed and not cell_support_failed:
                diagnostics["cells_skipped_outside_silhouette"] += 1
                diagnostics["fail_y_partial_silhouette"][y] = (
                    diagnostics["fail_y_partial_silhouette"].get(y, 0) + 1
                )
            elif cell_outside_grid_failed and not (
                cell_silhouette_failed or cell_support_failed
            ):
                diagnostics["cells_skipped_outside_grid"] += 1
                diagnostics["fail_y_outside_grid"][y] = (
                    diagnostics["fail_y_outside_grid"].get(y, 0) + 1
                )
            else:
                # Mixed failures across candidates — falls back here.
                diagnostics["cells_skipped_no_candidate"] += 1
                diagnostics["fail_y_no_candidate"][y] = (
                    diagnostics["fail_y_no_candidate"].get(y, 0) + 1
                )

    return new_placements, new_cells_filled


def repair_unsupported(
    placements: List[BrickPlacement],
    library: BrickLibrary,
    *,
    max_rounds: int = 3,
    occupancy: Optional[np.ndarray] = None,
) -> Tuple[List[BrickPlacement], dict]:
    """Iteratively repair ungrounded bricks. Returns (kept, summary).

    Repair order per brick: rotate → lateral shift → downsize → drop.
    Up to `max_rounds` passes; stops early when buildable.

    If `occupancy` is provided, after the repair rounds we run a
    bottom-up greedy fill pass that places library bricks into cells
    the original occupancy mask says should be filled but no current
    placement covers.
    """
    summary = {
        "rounds": 0,
        "repaired_rotated": 0,
        "repaired_shifted": 0,
        "repaired_downsized": 0,
        "dropped_unrepairable": 0,
        "still_ungrounded": 0,
        "fill_added_bricks": 0,
        "fill_cells_filled": 0,
    }
    if not placements:
        summary["still_ungrounded"] = 0
        return [], summary

    current = list(placements)

    for round_idx in range(int(max_rounds)):
        summary["rounds"] = round_idx + 1
        report = check_buildability(current)
        if bool(report.get("buildable", False)):
            break

        ungrounded_idx = list(report.get("ungrounded_indices") or [])
        if not ungrounded_idx:
            break

        # Sort by Y ascending so we repair lower bricks first; fixing
        # the bottom first gives upper bricks a better chance of being
        # supported in the next round.
        ungrounded_idx.sort(key=lambda i: (int(current[i].y), int(current[i].x), int(current[i].z)))

        # Repair in-place on a working copy. We track the indices we've
        # processed so the loop sees the latest geometry as repairs land.
        # Indices are stable within a round because we only swap entries
        # in-place (no insert/delete) until the drop step at the end.
        to_drop = set()
        for idx in ungrounded_idx:
            p = current[idx]
            new_p = _rotate_in_place(p, current, idx, occupancy)
            if new_p is not None:
                current[idx] = new_p
                summary["repaired_rotated"] += 1
                continue
            new_p = _lateral_shift(p, current, idx, occupancy)
            if new_p is not None:
                current[idx] = new_p
                summary["repaired_shifted"] += 1
                continue
            new_p = _downsize(p, current, idx, library, occupancy)
            if new_p is not None:
                current[idx] = new_p
                summary["repaired_downsized"] += 1
                continue
            to_drop.add(idx)

        if to_drop:
            current = [p for i, p in enumerate(current) if i not in to_drop]
            summary["dropped_unrepairable"] += len(to_drop)

    # Fill pass: drop+repair leaves voxel cells empty where bricks used
    # to live. Walk the original occupancy mask and place the largest
    # supported library brick into each empty cell, working bottom-up.
    if occupancy is not None:
        before = len(current)
        fill_diag: dict = {}
        current, cells_filled = _fill_holes_with_supported_bricks(
            current, occupancy, library, diagnostics=fill_diag,
        )
        summary["fill_added_bricks"] = int(len(current) - before)
        summary["fill_cells_filled"] = int(cells_filled)
        summary["fill_cells_needed"] = int(fill_diag.get("cells_needing_fill", 0))
        summary["fill_skipped_no_support"] = int(
            fill_diag.get("cells_skipped_no_support", 0)
        )
        summary["fill_skipped_outside_silhouette"] = int(
            fill_diag.get("cells_skipped_outside_silhouette", 0)
        )
        summary["fill_skipped_no_candidate"] = int(
            fill_diag.get("cells_skipped_no_candidate", 0)
        )
        summary["fill_skipped_collision"] = int(
            fill_diag.get("cells_skipped_collision", 0)
        )
        summary["fill_skipped_outside_grid"] = int(
            fill_diag.get("cells_skipped_outside_grid", 0)
        )
        summary["fill_library_heights"] = list(
            fill_diag.get("library_heights", []) or []
        )
        summary["fill_library_has_1x1x1"] = bool(
            fill_diag.get("library_has_1x1x1", False)
        )
        summary["fill_library_n_orientations"] = int(
            fill_diag.get("library_n_orientations", 0) or 0
        )
        summary["fail_y_no_support"] = dict(
            fill_diag.get("fail_y_no_support", {}) or {}
        )
        summary["fail_y_no_candidate"] = dict(
            fill_diag.get("fail_y_no_candidate", {}) or {}
        )
        summary["fail_y_collision"] = dict(
            fill_diag.get("fail_y_collision", {}) or {}
        )
        summary["fail_y_partial_silhouette"] = dict(
            fill_diag.get("fail_y_partial_silhouette", {}) or {}
        )
        summary["fail_y_outside_grid"] = dict(
            fill_diag.get("fail_y_outside_grid", {}) or {}
        )
        summary["overhang_by_y"] = dict(
            fill_diag.get("overhang_by_y", {}) or {}
        )
        summary["anchors_planted"] = int(
            fill_diag.get("anchors_planted", 0) or 0
        )

    # Final state after all rounds + fill.
    final_report = check_buildability(current)
    summary["still_ungrounded"] = int(final_report.get("n_ungrounded", 0) or 0)
    return current, summary
