"""Greedy brick fitter with structural-connectivity awareness.

Algorithm:
  1. Iterate the voxel grid bottom-up (Y).
  2. For each uncovered occupied cell, try every brick in the library
     (and its 90 rotation) in order of decreasing volume.
  3. A brick "fits" when every cell it would occupy is itself occupied
     AND not already covered by another brick.
  4. Among all fitting bricks, pick the one with the best score:
        score = volume * VOL_WEIGHT
              + (#distinct bricks below it that its footprint overlaps)
                  * STAGGER_WEIGHT       <- masonry-style bonding
              - (color variance of voxels it covers) * COLOR_WEIGHT
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import numpy as np
from scipy.ndimage import binary_fill_holes
from .library import BrickLibrary, BrickType
from .palette import LegoPalette


@dataclass
class BrickPlacement:
    brick: BrickType        # natural orientation
    x: int                  # grid coords (low corner)
    y: int
    z: int
    rotation_y: int         # 0 or 90
    color_idx: int = -1     # palette index (-1 = no palette assigned)
    rgb: Tuple[int, int, int] = (180, 180, 180)   # raw averaged color
                                                  # over voxels covered.
                                                  # This is the value the
                                                  # C4D plugin pushes to
                                                  # MoGraph Color tags so
                                                  # the artist's materials
                                                  # can apply ANY palette
                                                  # via shader logic.

    @property
    def w(self) -> int:
        return self.brick.depth if self.rotation_y == 90 else self.brick.width

    @property
    def d(self) -> int:
        return self.brick.width if self.rotation_y == 90 else self.brick.depth

    @property
    def h(self) -> int:
        return self.brick.height

    @property
    def cells(self) -> Tuple[slice, slice, slice]:
        return (slice(self.x, self.x + self.w),
                slice(self.y, self.y + self.h),
                slice(self.z, self.z + self.d))


class BrickFitter:
    def __init__(
        self,
        library: BrickLibrary,
        palette: Optional[LegoPalette] = None,
        *,
        vol_weight: float = 1.0,
        stagger_weight: float = 8.0,
        color_weight: float = 0.0001,
        max_brick_height: int = 3,
        randomize_heights: bool = False,
        height_mix_seed: int = 1,
        height_mix_amount: float = 0.6,
    ):
        """The palette is OPTIONAL. If provided, every placement gets a
        color_idx (palette index) in addition to its raw rgb -- needed
        for LDraw export. If None, only raw rgb is stored, and the
        artist applies their own palette in C4D via MoGraph Color +
        material network."""
        self.library = library
        self.palette = palette
        self.vol_weight = vol_weight
        self.stagger_weight = stagger_weight
        self.color_weight = color_weight
        self.max_brick_height = max_brick_height
        self.randomize_heights = bool(randomize_heights)
        self.height_mix_seed = int(height_mix_seed)
        self.height_mix_amount = max(0.0, min(1.0, float(height_mix_amount)))

    @staticmethod
    def _hash32(*vals: int) -> int:
        """Cheap deterministic integer hash for spatial noise fields."""
        h = 2166136261
        for v in vals:
            h ^= int(v) & 0xFFFFFFFF
            h = (h * 16777619) & 0xFFFFFFFF
        return h

    def fit(
        self,
        occupancy: np.ndarray,
        colors: np.ndarray,
        *,
        detail_mask: Optional[np.ndarray] = None,
        max_detail_footprint: int = 0,
        surface_only_plates: bool = False,
    ) -> List[BrickPlacement]:
        Nx, Ny, Nz = occupancy.shape
        # placement_id[x,y,z] = index into placements list, or -1
        placement_id = -np.ones(occupancy.shape, dtype=np.int32)
        placements: List[BrickPlacement] = []

        # Fast immutable box queries for the static occupancy/detail grids.
        # The mutable "already covered" check still uses placement_id slices,
        # but most impossible candidates now fail before that slice.
        occ_i = occupancy.astype(np.int32)
        occ_prefix = np.pad(
            occ_i.cumsum(axis=0).cumsum(axis=1).cumsum(axis=2),
            ((1, 0), (1, 0), (1, 0)),
            mode="constant",
        )

        def box_sum(prefix: np.ndarray, x0: int, y0: int, z0: int,
                    x1: int, y1: int, z1: int) -> int:
            return int(
                prefix[x1, y1, z1]
                - prefix[x0, y1, z1]
                - prefix[x1, y0, z1]
                - prefix[x1, y1, z0]
                + prefix[x0, y0, z1]
                + prefix[x0, y1, z0]
                + prefix[x1, y0, z0]
                - prefix[x0, y0, z0]
            )

        detail_prefix = None
        if detail_mask is not None and max_detail_footprint > 0:
            detail_i = detail_mask.astype(np.int32)
            detail_prefix = np.pad(
                detail_i.cumsum(axis=0).cumsum(axis=1).cumsum(axis=2),
                ((1, 0), (1, 0), (1, 0)),
                mode="constant",
            )
        top_exposed = None
        side_exposed = None
        exterior_top = None
        exterior_top_prefix = None
        if surface_only_plates:
            # Top-exposed: occupied and no occupied cell directly above.
            top_exposed = occupancy.copy()
            top_exposed[:, :-1, :] &= ~occupancy[:, 1:, :]
            # Outside air excludes enclosed interior cavities.
            outside_air = ~binary_fill_holes(occupancy)
            # Side-exposed to OUTSIDE air (not just any empty interior pocket).
            side_exposed = np.zeros_like(occupancy, dtype=bool)
            side_exposed[0, :, :] |= occupancy[0, :, :]
            side_exposed[-1, :, :] |= occupancy[-1, :, :]
            side_exposed[:, :, 0] |= occupancy[:, :, 0]
            side_exposed[:, :, -1] |= occupancy[:, :, -1]
            side_exposed[1:, :, :] |= occupancy[1:, :, :] & outside_air[:-1, :, :]
            side_exposed[:-1, :, :] |= occupancy[:-1, :, :] & outside_air[1:, :, :]
            side_exposed[:, :, 1:] |= occupancy[:, :, 1:] & outside_air[:, :, :-1]
            side_exposed[:, :, :-1] |= occupancy[:, :, :-1] & outside_air[:, :, 1:]
            exterior_top = top_exposed & side_exposed
            exterior_top_i = exterior_top.astype(np.int32)
            exterior_top_prefix = np.pad(
                exterior_top_i.cumsum(axis=0).cumsum(axis=1).cumsum(axis=2),
                ((1, 0), (1, 0), (1, 0)),
                mode="constant",
            )

        # C4D currently sends one flat material/default color for the whole
        # source mesh. In that common case, color variance is always zero;
        # skip the per-candidate reshape/variance work entirely.
        occupied_colors = colors[occupancy]
        use_color_score = (
            self.color_weight > 0.0
            and occupied_colors.size > 0
            and bool(np.ptp(occupied_colors, axis=0).sum() > 0)
        )
        use_height_mix = self.randomize_heights and self.max_brick_height > 1
        height_span = max(1, int(self.max_brick_height) - 1)

        # All brick orientations, sorted by volume desc.
        orientations: List[Tuple[BrickType, int]] = []
        seen = set()
        bricks_by_vol = sorted(self.library.bricks, key=lambda b: -b.volume)
        for b in bricks_by_vol:
            if b.height > self.max_brick_height:
                continue
            for rot in (0, 90):
                w = b.depth if rot == 90 else b.width
                d = b.width if rot == 90 else b.depth
                key = (w, d, b.height, b.ldraw_code)
                if key in seen:
                    continue
                seen.add(key)
                orientations.append((b, rot))

        # Precompute a "scan order" that prefers cells with more uncovered
        # neighbors at the same level (helps pack large bricks into open
        # regions first). For prototype, just lex order: y then z then x.
        for y in range(Ny):
            for z in range(Nz):
                for x in range(Nx):
                    if not occupancy[x, y, z] or placement_id[x, y, z] != -1:
                        continue
                    target_h = 1
                    if use_height_mix:
                        target_h = 1 + (
                            self._hash32(self.height_mix_seed, x, z)
                            % int(self.max_brick_height)
                        )
                    best: Optional[Tuple[float, BrickType, int]] = None
                    for brick, rot in orientations:
                        w = brick.depth if rot == 90 else brick.width
                        d = brick.width if rot == 90 else brick.depth
                        h = brick.height
                        # bounds
                        if x + w > Nx or y + h > Ny or z + d > Nz:
                            continue
                        # all cells occupied & uncovered?
                        vol = w * d * h
                        if box_sum(occ_prefix, x, y, z, x + w, y + h, z + d) != vol:
                            continue
                        if surface_only_plates and h == 1:
                            sub_top = top_exposed[x:x + w, y:y + h, z:z + d]
                            if not bool(sub_top.all()):
                                continue
                            sub_side = side_exposed[x:x + w, y:y + h, z:z + d]
                            # Must touch true outside exposure so enclosed
                            # interior top pockets do not get plates.
                            if not bool(sub_side.any()):
                                continue
                        sub_pid = placement_id[x:x + w, y:y + h, z:z + d]
                        if (sub_pid != -1).any():
                            continue
                        # score
                        if detail_prefix is not None:
                            has_detail = box_sum(
                                detail_prefix, x, y, z,
                                x + w, y + h, z + d,
                            ) > 0
                            if has_detail and (w * d) > max_detail_footprint:
                                continue
                        # stagger: count distinct bricks directly below
                        stagger = 0
                        if y > 0:
                            below = placement_id[x:x + w, y - 1, z:z + d]
                            uniq = np.unique(below)
                            stagger = int(np.sum(uniq != -1))
                        # color variance (low = clean color)
                        if use_color_score:
                            cells_color = colors[x:x + w, y:y + h, z:z + d].reshape(-1, 3)
                            cvar = float(cells_color.astype(np.float32).var(axis=0).sum())
                        else:
                            cvar = 0.0
                        score = (
                            vol * self.vol_weight
                            + stagger * self.stagger_weight
                            - cvar * self.color_weight
                        )
                        if surface_only_plates:
                            if h == 1:
                                # Favor smooth-top plate caps on exterior top
                                # surfaces, but keep this as scoring (not a
                                # hard constraint) to avoid coverage regressions.
                                score += 1000.0
                            else:
                                # Discourage tall bricks from consuming cells
                                # that are good candidates for plate caps.
                                ext_hits = box_sum(
                                    exterior_top_prefix,
                                    x, y, z,
                                    x + w, y + h, z + d,
                                )
                                if ext_hits > 0:
                                    score -= 250.0 * float(ext_hits)
                        if use_height_mix:
                            # Encourage local target heights (seeded per X/Z),
                            # but keep it soft so structural/footprint quality
                            # still dominates where needed.
                            pref = 1.0 - (
                                abs(int(h) - int(target_h)) / float(height_span)
                            )
                            gain = (
                                self.height_mix_amount
                                * float(w * d * int(self.max_brick_height))
                            )
                            score += (
                                (pref - 0.5)
                                * 2.0
                                * gain
                            )
                        if best is None or score > best[0]:
                            best = (score, brick, rot)

                    if best is None:
                        # Should not happen if 1x1 plate is in library.
                        # Fallback: leave uncovered (will be reported).
                        continue

                    _, brick, rot = best
                    w = brick.depth if rot == 90 else brick.width
                    d = brick.width if rot == 90 else brick.depth
                    h = brick.height
                    # average color over the brick's voxels -- store raw RGB
                    # always; palette index only when palette is available
                    cells_color = colors[x:x + w, y:y + h, z:z + d].reshape(-1, 3)
                    avg = cells_color.astype(np.float32).mean(axis=0)
                    rgb = (int(np.clip(avg[0], 0, 255)),
                           int(np.clip(avg[1], 0, 255)),
                           int(np.clip(avg[2], 0, 255)))
                    if self.palette is not None:
                        color_idx = int(self.palette.nearest_index(
                            np.array([avg]))[0])
                    else:
                        color_idx = -1

                    p = BrickPlacement(brick, x, y, z, rot,
                                       color_idx=color_idx, rgb=rgb)
                    placements.append(p)
                    pid = len(placements) - 1
                    placement_id[x:x + w, y:y + h, z:z + d] = pid

        return placements


def merge_plates_to_bricks(
    placements: List[BrickPlacement],
    library: BrickLibrary,
    *,
    require_same_color: bool = False,
) -> List[BrickPlacement]:
    """Promote 3-stacks of identical-footprint plates into single bricks
    when doing so won't break inter-layer connectivity.

    A merge is "safe" if the three plates being merged were ALREADY mutually
    coupled (overlapping footprints, which they are by definition since they're
    stacked at the same x/z), AND each of them was coupled to neighbors
    OUTSIDE the stack only via their TOP and BOTTOM faces (not via mid-stack
    side neighbors -- which is automatic since plates only couple top/bottom).

    In practice this means: a stack of 3 same-footprint same-orientation plates
    can always be merged into a brick safely, because the brick has the same
    coupling surface (top of plate 3 = top of brick; bottom of plate 1 = bottom
    of brick).
    """
    from .library import DEFAULT_LIBRARY
    # Build a lookup from (w, d) -> brick BrickType (height 3) when available
    brick_by_wd = {}
    for b in library.bricks:
        if b.height == 3:
            brick_by_wd.setdefault((b.width, b.depth), b)
            brick_by_wd.setdefault((b.depth, b.width), b)
    if not brick_by_wd:
        return placements  # no bricks in library

    # Index plates by (x, y, z, w, d, rot)
    by_key = {}
    for i, p in enumerate(placements):
        if p.h == 1:
            key = (p.x, p.y, p.z, p.w, p.d, p.rotation_y)
            by_key[key] = i

    used = set()
    new_placements: List[BrickPlacement] = []
    for i, p in enumerate(placements):
        if i in used:
            continue
        if p.h != 1:
            new_placements.append(p)
            continue
        # try to find p2 = plate above, p3 = plate above that, same x/z/w/d/rot
        k2 = (p.x, p.y + 1, p.z, p.w, p.d, p.rotation_y)
        k3 = (p.x, p.y + 2, p.z, p.w, p.d, p.rotation_y)
        i2 = by_key.get(k2, -1)
        i3 = by_key.get(k3, -1)
        if i2 < 0 or i3 < 0 or i2 in used or i3 in used:
            new_placements.append(p)
            continue
        p2 = placements[i2]
        p3 = placements[i3]
        if require_same_color and not (p.color_idx == p2.color_idx == p3.color_idx):
            new_placements.append(p)
            continue
        wd = (p.w, p.d)
        if wd not in brick_by_wd:
            new_placements.append(p)
            continue
        brick_type = brick_by_wd[wd]
        # use majority color among the 3 plates (palette-index level)
        from collections import Counter
        col = Counter([p.color_idx, p2.color_idx,
                       p3.color_idx]).most_common(1)[0][0]
        # raw rgb: average the three plates' rgb (volume-weighted would be
        # equivalent here since all 3 plates have the same footprint)
        rgb_avg = (
            int(round((p.rgb[0] + p2.rgb[0] + p3.rgb[0]) / 3)),
            int(round((p.rgb[1] + p2.rgb[1] + p3.rgb[1]) / 3)),
            int(round((p.rgb[2] + p2.rgb[2] + p3.rgb[2]) / 3)),
        )
        merged = BrickPlacement(
            brick=brick_type,
            x=p.x, y=p.y, z=p.z,
            rotation_y=p.rotation_y,
            color_idx=col,
            rgb=rgb_avg,
        )
        new_placements.append(merged)
        used.add(i)
        used.add(i2)
        used.add(i3)
    return new_placements


def merge_plates_horizontal(
    placements: List[BrickPlacement],
    library: BrickLibrary,
    *,
    color_tolerance: int = 24,
    require_same_color: bool = False,
    max_passes: int = 8,
) -> List[BrickPlacement]:
    """Fuse adjacent same-layer bricks of equal height into a single larger
    brick when a matching footprint exists in the library.

    Targets the "ragged ledge" failure mode at low resolutions: where the
    voxel grid produces many 1xN single-plate bricks at building shoulders
    (plinth-to-tower transitions) the fitter can't combine. Two placements
    are mergeable when:

      - they have the same y, height, and rotation_y
      - their footprints share a full edge (so the union is a rectangle)
      - the resulting rectangle (or its 90 rotation) exists in `library`
      - their colors match within `color_tolerance` (per-channel max diff)

    Iterates until no further merges are possible (or `max_passes` reached).
    Color of the merged brick is the area-weighted average of inputs.

    Connectivity safety: a brick that swallows two children sits on the
    union of their floors and supports the union of their ceilings, so any
    couplings that existed via the children are preserved.
    """
    # All footprints in the library (independent of height; we filter by
    # height per merge).
    sizes_by_h: Dict[int, set] = {}
    for b in library.bricks:
        sizes_by_h.setdefault(b.height, set()).add((b.width, b.depth))
        sizes_by_h.setdefault(b.height, set()).add((b.depth, b.width))

    def find_brick(w: int, d: int, h: int) -> Optional[BrickType]:
        for b in library.bricks:
            if b.height != h:
                continue
            if (b.width == w and b.depth == d) or (b.width == d and b.depth == w):
                return b
        return None

    def colors_match(a: BrickPlacement, b: BrickPlacement) -> bool:
        if require_same_color:
            return a.color_idx == b.color_idx
        return all(abs(int(a.rgb[c]) - int(b.rgb[c])) <= color_tolerance
                   for c in range(3))

    def avg_rgb(a: BrickPlacement, va: int,
                b: BrickPlacement, vb: int) -> Tuple[int, int, int]:
        tot = max(1, va + vb)
        return tuple(  # type: ignore[return-value]
            int(round((a.rgb[c] * va + b.rgb[c] * vb) / tot))
            for c in range(3)
        )

    work = list(placements)
    for _pass in range(max_passes):
        # Bucket by (y, h, rotation_y) — only candidates within a bucket
        # could possibly merge.
        buckets: Dict[Tuple[int, int, int], List[int]] = {}
        for idx, p in enumerate(work):
            buckets.setdefault((p.y, p.h, p.rotation_y), []).append(idx)

        merged_any = False
        consumed: set = set()
        new_items: List[BrickPlacement] = []

        for (y, h, rot), idxs in buckets.items():
            available_sizes = sizes_by_h.get(h, set())
            if not available_sizes:
                for i in idxs:
                    if i not in consumed:
                        new_items.append(work[i])
                        consumed.add(i)
                continue
            # Try all pairs within bucket.
            for ii, i in enumerate(idxs):
                if i in consumed:
                    continue
                a = work[i]
                merged_partner = -1
                merged_brick: Optional[BrickType] = None
                merged_x = a.x
                merged_z = a.z
                merged_w = a.w
                merged_d = a.d
                for j in idxs[ii + 1:]:
                    if j in consumed:
                        continue
                    b = work[j]
                    # Adjacent along X (same z-range, same depth)?
                    if a.z == b.z and a.d == b.d:
                        if a.x + a.w == b.x:
                            new_w = a.w + b.w
                            if (new_w, a.d) in available_sizes:
                                if not colors_match(a, b):
                                    continue
                                merged_partner = j
                                merged_x, merged_z = a.x, a.z
                                merged_w, merged_d = new_w, a.d
                                break
                        elif b.x + b.w == a.x:
                            new_w = a.w + b.w
                            if (new_w, a.d) in available_sizes:
                                if not colors_match(a, b):
                                    continue
                                merged_partner = j
                                merged_x, merged_z = b.x, a.z
                                merged_w, merged_d = new_w, a.d
                                break
                    # Adjacent along Z (same x-range, same width)?
                    if a.x == b.x and a.w == b.w:
                        if a.z + a.d == b.z:
                            new_d = a.d + b.d
                            if (a.w, new_d) in available_sizes:
                                if not colors_match(a, b):
                                    continue
                                merged_partner = j
                                merged_x, merged_z = a.x, a.z
                                merged_w, merged_d = a.w, new_d
                                break
                        elif b.z + b.d == a.z:
                            new_d = a.d + b.d
                            if (a.w, new_d) in available_sizes:
                                if not colors_match(a, b):
                                    continue
                                merged_partner = j
                                merged_x, merged_z = a.x, b.z
                                merged_w, merged_d = a.w, new_d
                                break

                if merged_partner < 0:
                    new_items.append(a)
                    consumed.add(i)
                    continue

                b = work[merged_partner]
                bt = find_brick(merged_w, merged_d, h)
                if bt is None:
                    new_items.append(a)
                    consumed.add(i)
                    continue
                # Decide rotation_y so that placement bbox matches the brick's
                # natural width/depth.
                if bt.width == merged_w and bt.depth == merged_d:
                    new_rot = 0
                else:
                    new_rot = 90
                va = a.w * a.d * a.h
                vb = b.w * b.d * b.h
                from collections import Counter
                color_idx = (a.color_idx if a.color_idx == b.color_idx
                             else Counter(
                                 [a.color_idx] * va + [b.color_idx] * vb
                             ).most_common(1)[0][0])
                merged = BrickPlacement(
                    brick=bt,
                    x=merged_x, y=y, z=merged_z,
                    rotation_y=new_rot,
                    color_idx=color_idx,
                    rgb=avg_rgb(a, va, b, vb),
                )
                new_items.append(merged)
                consumed.add(i)
                consumed.add(merged_partner)
                merged_any = True

        # Append any placements outside the buckets above (none in practice).
        for idx, p in enumerate(work):
            if idx not in consumed:
                new_items.append(p)

        work = new_items
        if not merged_any:
            break
    return work
