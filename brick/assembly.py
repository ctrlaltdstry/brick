"""Turn a list of BrickPlacement objects into a single quad-modeled mesh.

This is the bridge between Brick's placement pipeline (palette / fitter /
connectivity, all integer grid coords) and the live baked-fillet GEOMETRY
pipeline (brick_geom_hires / svg_logo / mesh_export, all in mesh-space units).

Per the artist-friendly default we agreed on, brick positions are
multiplied by stud_size / plate_size so the assembly lives in the SAME
COORDINATE FRAME as the source mesh -- a brick that replaces voxel
(x,y,z) sits at world (x*stud, y*plate, z*stud).

Polygon-group naming: every brick's groups are prefixed with
`brick_NNNN_<color>__` so the artist can multi-select all "yellow
bodies", or all "logo islands", with C4D's selection-by-name feature.
"""
from typing import List, Optional, Iterable
import numpy as np
from .mesh import Mesh, affine_translate, affine_rotate_y
from .brick_geom_hires import make_brick_hires, make_low_res_collider
from .palette import LegoPalette
from .fitter import BrickPlacement


def build_assembly(
    placements: List[BrickPlacement],
    palette: Optional[LegoPalette] = None,
    *,
    stud_size: float = 8.0,
    plate_size: float = 3.2,
    fillet_inset: float = 0.30,    # passed to make_brick_hires as body_fillet_radius
    with_studs: bool = True,
    with_underside: bool = True,
    with_tubes: bool = True,
    with_stud_indents: bool = True,
    with_ribs: bool = True,
    low_res: bool = False,
    logo: Optional[Mesh] = None,
    progress: bool = False,
) -> Mesh:
    """Generate one merged Mesh containing every brick in `placements`.

    Each brick is built fresh from make_brick_hires -- this is a
    prototype, so we don't dedupe by brick type; for production the
    plugin would build one mesh per brick TYPE and instantiate it many
    times via C4D MoGraph or transform-list cloners. The OBJ output is
    flat (no instancing), so it will be large but it's faithful.

    Output Y-axis is up. Positions are in mesh-space units (multiply by
    stud/plate sizes already applied).
    """
    cache: dict = {}  # (W, D, H_plates) -> base Mesh in canonical orientation

    def get_brick(w_studs: int, d_studs: int, h_plates: int) -> Mesh:
        key = (w_studs, d_studs, h_plates)
        if key not in cache:
            if low_res:
                brick_mesh = make_low_res_collider(
                    w_studs,
                    d_studs,
                    h_plates,
                    stud_size=stud_size,
                    plate_size=plate_size,
                )
            else:
                brick_mesh = make_brick_hires(
                    w_studs,
                    d_studs,
                    h_plates,
                    stud_size=stud_size,
                    plate_size=plate_size,
                    body_fillet_radius=fillet_inset,
                    with_studs=with_studs,
                    with_underside=with_underside,
                    with_tubes=with_tubes,
                    with_stud_indents=with_stud_indents,
                    with_ribs=with_ribs,
                    logo=logo,
                )
            cache[key] = brick_mesh
        return cache[key]

    out = Mesh()
    n = len(placements)
    for i, p in enumerate(placements):
        if progress and i % max(1, n // 20) == 0:
            print(f"      {i}/{n} ...", flush=True)
        # The brick TYPE has its own width/depth in its NATURAL orientation.
        # When rotation_y == 90, the placement's effective w/d are swapped.
        # We build the mesh in the natural orientation (matching brick.width /
        # brick.depth) and apply a rotation transform when rotation_y == 90.
        bw, bd = p.brick.width, p.brick.depth
        bh = p.brick.height
        m = get_brick(bw, bd, bh)

        # World position: corner of the brick in mesh-space units.
        # The brick's local origin is its low corner. Placement (x, y, z)
        # is in grid units; multiply by (stud, plate, stud) to put it in
        # the artist's frame.
        T_translate = affine_translate(np.array([
            p.x * stud_size,
            p.y * plate_size,
            p.z * stud_size,
        ]))

        if p.rotation_y == 90:
            # Rotate the brick 90 degrees around its own center, then translate.
            # The natural-orientation brick spans [0..bw*stud, _, 0..bd*stud].
            # After 90-deg rotation around its center, it spans the same volume
            # but with width/depth swapped.
            center_offset = np.array([bw * stud_size * 0.5,
                                      0.0,
                                      bd * stud_size * 0.5])
            # T = T_translate * T_recenter * R * T_uncenter
            T = (T_translate
                 @ affine_translate(np.array([bd * stud_size * 0.5,
                                              0.0,
                                              bw * stud_size * 0.5]))
                 @ affine_rotate_y(90)
                 @ affine_translate(-center_offset))
        else:
            T = T_translate

        # Group prefix: prefer LEGO color name if palette was used, else
        # fall back to a hex RGB code so the artist can still identify
        # bricks by approximate color in their modeling app.
        if palette is not None and p.color_idx >= 0:
            color_tag = palette.color_at(p.color_idx).name.replace(" ", "_")
        else:
            color_tag = "{:02X}{:02X}{:02X}".format(*p.rgb)
        prefix = f"brick_{i:04d}_{color_tag}__"
        out.merge(m, transform=T, group_prefix=prefix)
    return out


def color_groups_for_assembly(assembly: Mesh,
                              palette: LegoPalette) -> dict:
    """Return {group_name: rgb} for the wireframe renderer, grouping all
    'body' subparts of bricks of the same color together. Useful for
    visualization."""
    out = {}
    for g in assembly.groups.keys():
        # group is "brick_NNNN_<colorname>__<part>"
        if "__" not in g:
            continue
        prefix, part = g.split("__", 1)
        # extract color name
        toks = prefix.split("_", 2)
        if len(toks) < 3:
            continue
        color_name = toks[2].replace("_", " ")
        # find the color in the palette
        match = next((c for c in palette.colors if c.name == color_name), None)
        if match is None:
            continue
        rgb = tuple(c / 255.0 for c in match.rgb)
        out[g] = rgb
    return out
