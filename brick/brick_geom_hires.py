"""High-resolution procedural LEGO brick with real geometric fillets.

This is a from-scratch rebuild that DOES NOT rely on Catmull-Clark
subdivision. Every fillet is tessellated as actual triangle/quad
geometry following a swept arc, so the OBJ contains the rounded
corners directly -- no SubD modifier required at render time.

Topology approach: each feature is built from a "vertical profile" + a
sweep operation:

  - The body is a rounded box: 6 flat panels + 12 cylindrical edges
    (one per box edge) + 8 spherical corners. Quarter-circle fillets
    of `body_fillet_radius` at every box edge.

  - The studs are extruded cylinders with a rounded base fillet
    (body-to-stud), a straight side, and a rounded top edge
    (side-to-top-cap).

  - Tubes are hollow cylinders mounted to the cavity ceiling with a
    rounded fillet at the top (tube-to-ceiling) and a small fillet
    at the bottom rim. The inner bore has its own top fillet too
    (no sharp edges anywhere).

  - The cavity interior (open bottom + walls + ceiling) is a second
    rounded box, smaller and inverted, sharing verts with the body's
    bottom rim so the brick reads as one continuous shell with a hole
    cut in the bottom.

  - Ribs are pill-shaped vertical bumps with rounded vertical edges
    and small top/bottom fillets where they meet the wall.

  - Ceiling indents are hollow cylindrical pockets with a small fillet
    at the rim where they open into the cavity.

The output is a triangle mesh (well, a mix of quads and tris where
convenient) ready to use as-is. Default polygon count for a 2x3 brick
with all features: ~30-50k triangles, in the "heavy hero-shot" range.

A separate `make_low_res_collider()` function returns a single 6-quad
bounding box for rigid-body simulation use.
"""
import numpy as np
from typing import Optional, Tuple
from .mesh import Mesh, affine_translate


# ---------------------------------------------------------------------
# Public API


def make_brick_hires(
    width_studs: int,
    depth_studs: int,
    height_plates: int,
    *,
    stud_size: float = 8.0,
    plate_size: float = 3.2,
    # ---- body ----
    body_fillet_radius: float = 0.30,
    body_corner_segments: int = 6,
    # ---- studs ----
    with_studs: bool = True,
    stud_radius_ratio: float = 0.30,
    stud_height_ratio: float = 0.55,         # of plate_size
    stud_segments: int = 32,
    stud_fillet_radius: float = 0.20,
    stud_fillet_segments: int = 4,
    # ---- cavity ----
    with_underside: bool = True,
    underside_wall_thickness: float = 1.0,
    underside_ceiling_thickness: float = 1.2,
    # ---- tubes ----
    with_tubes: bool = True,
    tube_outer_ratio: float = 0.40,
    tube_inner_ratio: float = 0.30,
    tube_segments: int = 32,
    tube_fillet_radius: float = 0.20,
    tube_fillet_segments: int = 4,
    # ---- stud-position ceiling indents ----
    with_stud_indents: bool = True,
    stud_indent_outer_ratio: float = 0.18,
    stud_indent_depth_ratio: float = 0.7,    # of ceiling thickness
    # ---- ribs ----
    with_ribs: bool = True,
    rib_half_width_ratio: float = 0.06,
    rib_protrusion_ratio: float = 0.04,
    rib_fillet_radius: float = 0.12,
    rib_segments: int = 4,
    # ---- optional stud logo ----
    logo: Optional[Mesh] = None,
) -> Mesh:
    """Build a high-resolution LEGO brick with real fillets baked in.
    Returns a Mesh with triangles/quads and named polygon groups.
    """
    W = width_studs * stud_size
    D = depth_studs * stud_size
    H = height_plates * plate_size

    mesh = Mesh()

    # ---- BODY (rounded box) ----------------------------------------
    # The cavity will be cut into the bottom; we generate the body as
    # if it were a closed rounded box, then either keep the bottom
    # face (with_underside=False) or remove its bottom face when we
    # build the cavity (and replace it with the cavity wall geometry).
    #
    # When studs are present, we ALSO skip the body's flat top panel
    # and re-emit it with one circular hole per stud cut out (radius
    # = stud_r + stud_fillet_radius, the stud's base-fillet skirt
    # point). The disc of body-top under each stud is otherwise
    # hidden inside the merged stud+body solid -- pure waste.
    skip_body_top = with_studs and width_studs > 0 and depth_studs > 0
    _add_rounded_box_outer(
        mesh,
        x0=0, y0=0, z0=0,
        x1=W, y1=H, z1=D,
        radius=body_fillet_radius,
        corner_segs=body_corner_segments,
        skip_bottom=with_underside,
        skip_top=skip_body_top,
        group="body",
    )

    # ---- STUDS -----------------------------------------------------
    if with_studs:
        stud_r = stud_size * stud_radius_ratio
        stud_h = plate_size * stud_height_ratio
        for sx in range(width_studs):
            for sz in range(depth_studs):
                cx = (sx + 0.5) * stud_size
                cz = (sz + 0.5) * stud_size
                _add_filleted_stud(
                    mesh,
                    cx=cx, cy=H, cz=cz,
                    radius=stud_r,
                    height=stud_h,
                    base_fillet=stud_fillet_radius,
                    top_fillet=stud_fillet_radius,
                    side_segs=stud_segments,
                    fillet_segs=stud_fillet_segments,
                    group="studs",
                )
                if logo is not None:
                    T = affine_translate(np.array([cx, H + stud_h, cz]))
                    mesh.merge(logo, transform=T)

        # Body top panel with one circular hole per stud. Hole radius
        # matches the stud's first profile ring (R_outer = stud_r +
        # stud_fillet_radius) at exactly stud_segments around, so the
        # hole rim verts coincide with the stud's base ring and the
        # final weld_vertices pass seals every seam.
        if skip_body_top:
            stud_R_outer = stud_r + stud_fillet_radius
            stud_holes = []
            for sx in range(width_studs):
                for sz in range(depth_studs):
                    stud_holes.append(((sx + 0.5) * stud_size,
                                       (sz + 0.5) * stud_size,
                                       stud_R_outer))
            _emit_ceiling_with_holes(
                mesh, group="body",
                cx_lo=body_fillet_radius,
                cx_hi=W - body_fillet_radius,
                cz_lo=body_fillet_radius,
                cz_hi=D - body_fillet_radius,
                cy=H,
                holes=stud_holes,
                segs=stud_segments,
                face_up=True,
            )

    # ---- CAVITY (inner shell) --------------------------------------
    if with_underside:
        ceiling_y = H - underside_ceiling_thickness
        wall = underside_wall_thickness
        # Cavity fillet radius for both ceiling-to-wall and the new
        # wall-to-rim concave fillets. Same value so the corner torus
        # sections (major r, minor rb) get matching tessellation
        # density at every seam and weld cleanly.
        cavity_fillet_r = body_fillet_radius * 0.5
        # The flat ceiling panel of the cavity does NOT sit at
        # `ceiling_y` -- it sits at `ceiling_y - cavity_fillet_r`,
        # because the ceiling-to-wall fillet rounds the corner up
        # from the panel level (cy) to the conceptual cavity-top
        # level (y1=ceiling_y) at the wall. The flat panel is at cy.
        # Tubes and indents must attach at cy, otherwise their rim
        # ring sits cavity_fillet_r ABOVE the panel hole boundary,
        # leaving a hairline annular gap.
        ceiling_panel_y = ceiling_y - cavity_fillet_r
        # Lift rib feet so they sit on the new wall foot, not in mid-
        # air over the bottom-edge fillet (where the wall no longer
        # exists below y=cavity_fillet_r).
        rib_y_bot = cavity_fillet_r

        # Pre-compute indent positions AND tube positions for ceiling
        # hole-cutting. Each circular feature that intersects the
        # ceiling needs a corresponding hole.
        indent_holes = None
        if with_stud_indents or (with_tubes and width_studs >= 2 and depth_studs >= 2):
            indent_holes = []
            if with_stud_indents:
                indent_outer = stud_size * stud_indent_outer_ratio
                rim_fillet = tube_fillet_radius * 0.4
                hole_r = indent_outer + rim_fillet
                for sx in range(width_studs):
                    for sz in range(depth_studs):
                        cx = (sx + 0.5) * stud_size
                        cz = (sz + 0.5) * stud_size
                        indent_holes.append((cx, cz, hole_r))
            if with_tubes and width_studs >= 2 and depth_studs >= 2:
                tube_outer = stud_size * tube_outer_ratio
                # Tube outer top rim is at radius = outer_r + top_fillet
                # (where the tube's outer top fillet meets the ceiling).
                tube_hole_r = tube_outer + tube_fillet_radius
                for sx in range(width_studs - 1):
                    for sz in range(depth_studs - 1):
                        cx = (sx + 1) * stud_size
                        cz = (sz + 1) * stud_size
                        indent_holes.append((cx, cz, tube_hole_r))

        _add_inner_cavity(
            mesh,
            x0=wall, y0=0, z0=wall,
            x1=W - wall, y1=ceiling_y, z1=D - wall,
            outer_x0=body_fillet_radius, outer_z0=body_fillet_radius,
            outer_x1=W - body_fillet_radius,
            outer_z1=D - body_fillet_radius,
            outer_y0=0,
            radius=cavity_fillet_r,
            corner_segs=body_corner_segments,
            group="underside",
            indent_holes=indent_holes,
            indent_segs=tube_segments,
            bottom_fillet_radius=cavity_fillet_r,
        )

        # ---- CONNECTOR TUBES -----------------------------------------
        if with_tubes and width_studs >= 2 and depth_studs >= 2:
            tube_outer = stud_size * tube_outer_ratio
            tube_inner = stud_size * tube_inner_ratio
            for sx in range(width_studs - 1):
                for sz in range(depth_studs - 1):
                    cx = (sx + 1) * stud_size
                    cz = (sz + 1) * stud_size
                    _add_filleted_tube(
                        mesh,
                        cx=cx, cz=cz,
                        ceiling_y=ceiling_panel_y,
                        floor_y=0.0,
                        outer_r=tube_outer,
                        inner_r=tube_inner,
                        top_fillet=tube_fillet_radius,
                        bottom_fillet=tube_fillet_radius * 0.5,
                        side_segs=tube_segments,
                        fillet_segs=tube_fillet_segments,
                        group="tubes",
                    )

        # ---- CEILING INDENTS -----------------------------------------
        if with_stud_indents:
            indent_outer = stud_size * stud_indent_outer_ratio
            indent_depth = underside_ceiling_thickness * stud_indent_depth_ratio
            for sx in range(width_studs):
                for sz in range(depth_studs):
                    cx = (sx + 0.5) * stud_size
                    cz = (sz + 0.5) * stud_size
                    _add_ceiling_indent(
                        mesh,
                        cx=cx, cz=cz,
                        ceiling_y=ceiling_panel_y,
                        depth=indent_depth,
                        outer_r=indent_outer,
                        rim_fillet=tube_fillet_radius * 0.4,
                        side_segs=tube_segments,
                        fillet_segs=tube_fillet_segments,
                        group="underside",
                    )

        # ---- RIBS --------------------------------------------------
        # Per the reference: rectangular pads on inner walls, one per
        # stud's position projected onto each wall.
        #
        # Long walls (parallel to Z axis, normal is +/-X):
        #   For a brick with depth_studs studs, place depth_studs ribs
        #   at z = (i + 0.5) * stud_size for i in 0..depth_studs-1.
        #   That's one rib per stud, on each long wall.
        # Short walls (parallel to X axis, normal is +/-Z):
        #   For a brick with width_studs studs, place width_studs ribs
        #   at x = (i + 0.5) * stud_size.
        #   One rib per stud column, on each short wall.
        #
        # Ribs go from cavity floor (y=0) up to just below the cavity
        # ceiling.
        if with_ribs:
            rib_hw = stud_size * rib_half_width_ratio
            rib_prot = stud_size * rib_protrusion_ratio
            # Push the rib's top all the way up to the ceiling panel
            # level so the rib reads as flush with the wall cap (where
            # the wall meets the ceiling) instead of stopping short.
            #
            # The rib's geometry above `wall_top_y = panel_y -
            # cavity_fillet_r` (back face at s=0, back-top concave
            # fillet, top back-corner saddles) ends up inside the
            # wall's solid material -- because the ceiling-to-wall
            # cap fillet has already moved the wall's cavity-facing
            # surface to s > 0 at those y values. Those faces are
            # hidden from the cavity view by the wall + cap geometry
            # in front of them.
            #
            # Visible additions: front + side faces extend up to
            # ~panel_y - r, the 4 top convex edge fillets and 2 top
            # front-corner octants form the rounded top of the rib,
            # and the top face at y = panel_y is coincident with the
            # ceiling plane but with opposite normal -- backface-
            # culled so the ceiling renders normally.
            rib_y_top = ceiling_panel_y
            # Small uniform fillet radius. Sized so the rib reads as a
            # clear rectangular pad with a soft injection-molded kiss
            # into the wall on every perimeter edge -- not a pillow
            # blob. ~15% larger than the prior pass per user feedback.
            rib_round_r = min(rib_prot * 0.32, rib_hw * 0.32, 0.23)
            # Lift the rib's bottom by `r` so the bottom concave wall-
            # blend fillet (which flares OUTWARD by `r` past y_bot at
            # the wall plane) cannot drop below the cavity-wall's foot
            # at y = cavity_fillet_r. Without this, the back-bot fillet
            # would extend into the body's bottom-edge fillet region
            # where there is no wall to weld to.
            rib_y_bot_for_fillet = rib_y_bot + rib_round_r

            # Long walls (axis=z): one rib per stud, centered on the
            # stud's z position.
            for i in range(depth_studs):
                cz = (i + 0.5) * stud_size
                # +X wall (x = W - wall): rib protrudes in -X direction
                _add_wall_rib(mesh, axis="z",
                              wall_pos=W - wall, protrude_dir=-1,
                              center=cz,
                              y_bot=rib_y_bot_for_fillet, y_top=rib_y_top,
                              half_width=rib_hw, protrusion=rib_prot,
                              fillet_r=rib_round_r,
                              fillet_segs=rib_segments,
                              group="underside")
                # -X wall (x = wall): rib protrudes in +X direction
                _add_wall_rib(mesh, axis="z",
                              wall_pos=wall, protrude_dir=+1,
                              center=cz,
                              y_bot=rib_y_bot_for_fillet, y_top=rib_y_top,
                              half_width=rib_hw, protrusion=rib_prot,
                              fillet_r=rib_round_r,
                              fillet_segs=rib_segments,
                              group="underside")
            # Short walls (axis=x): one rib per stud column, centered
            # on the stud's x position.
            for i in range(width_studs):
                cx = (i + 0.5) * stud_size
                # +Z wall (z = D - wall): rib protrudes in -Z direction
                _add_wall_rib(mesh, axis="x",
                              wall_pos=D - wall, protrude_dir=-1,
                              center=cx,
                              y_bot=rib_y_bot_for_fillet, y_top=rib_y_top,
                              half_width=rib_hw, protrusion=rib_prot,
                              fillet_r=rib_round_r,
                              fillet_segs=rib_segments,
                              group="underside")
                # -Z wall (z = wall): rib protrudes in +Z direction
                _add_wall_rib(mesh, axis="x",
                              wall_pos=wall, protrude_dir=+1,
                              center=cx,
                              y_bot=rib_y_bot_for_fillet, y_top=rib_y_top,
                              half_width=rib_hw, protrusion=rib_prot,
                              fillet_r=rib_round_r,
                              fillet_segs=rib_segments,
                              group="underside")

    # Final pass: weld coincident verts so the mesh is water-tight at
    # surface seams (body bottom rim meets cavity rim, ceiling meets
    # tube tops, etc). Without this, two surfaces that share a boundary
    # have duplicate verts and may render with a hairline crack.
    mesh.weld_vertices(tol=1e-4)
    return mesh


def make_low_res_collider(
    width_studs: int,
    depth_studs: int,
    height_plates: int,
    *,
    stud_size: float = 8.0,
    plate_size: float = 3.2,
) -> Mesh:
    """Single-bbox 6-quad collider mesh for rigid-body simulation."""
    W = width_studs * stud_size
    D = depth_studs * stud_size
    # Include stud height in collision bounds so studs don't sink into
    # collisions with surrounding bricks above.
    H = height_plates * plate_size + plate_size * 0.55  # body + stud height
    return _make_collider_box(W, D, H)


def make_proxy_collider(
    width_studs: int,
    depth_studs: int,
    height_plates: int,
    *,
    stud_size: float = 8.0,
    plate_size: float = 3.2,
    inset: float = 0.0,
    with_studs: bool = True,
) -> Mesh:
    """Low-cost proxy brick for MoGraph/RBD simulation prep.

    This keeps the useful collision silhouette: hollow underside shell plus
    optional coarse studs. Tubes, underside ribs, and stud-ceiling indents are
    omitted.
    """
    mesh = make_brick_hires(
        width_studs,
        depth_studs,
        height_plates,
        stud_size=stud_size,
        plate_size=plate_size,
        body_corner_segments=1,
        stud_segments=6,
        stud_fillet_segments=1,
        tube_segments=6,
        tube_fillet_segments=1,
        rib_segments=1,
        body_fillet_radius=0.0,
        stud_fillet_radius=0.0,
        tube_fillet_radius=0.0,
        rib_fillet_radius=0.0,
        with_studs=with_studs,
        with_underside=True,
        with_tubes=False,
        with_stud_indents=False,
        with_ribs=False,
    )
    inset = max(0.0, float(inset or 0.0))
    width = float(width_studs) * float(stud_size)
    depth = float(depth_studs) * float(stud_size)
    max_inset = max(0.0, min(width, depth) * 0.49)
    inset = min(inset, max_inset)
    if inset > 0.0 and width > 0.0 and depth > 0.0 and len(mesh.vertices):
        sx = max(0.0, width - inset * 2.0) / width
        sz = max(0.0, depth - inset * 2.0) / depth
        mesh.vertices[:, 0] = inset + mesh.vertices[:, 0] * sx
        mesh.vertices[:, 2] = inset + mesh.vertices[:, 2] * sz
    return mesh


def _make_collider_box(
    width: float,
    depth: float,
    height: float,
    *,
    inset: float = 0.0,
) -> Mesh:
    x0 = inset
    z0 = inset
    x1 = width - inset
    z1 = depth - inset
    m = Mesh()
    base = m.append_verts(np.array([
        [x0, 0, z0], [x1, 0, z0], [x1, 0, z1], [x0, 0, z1],
        [x0, height, z0], [x1, height, z0], [x1, height, z1], [x0, height, z1],
    ]))
    def v(i): return base + i
    m.add_group_face("collider", (v(0), v(1), v(2), v(3)))   # bottom
    m.add_group_face("collider", (v(4), v(7), v(6), v(5)))   # top
    m.add_group_face("collider", (v(0), v(4), v(5), v(1)))   # -Z
    m.add_group_face("collider", (v(1), v(5), v(6), v(2)))   # +X
    m.add_group_face("collider", (v(2), v(6), v(7), v(3)))   # +Z
    m.add_group_face("collider", (v(3), v(7), v(4), v(0)))   # -X
    return m


# =====================================================================
# Helpers below
# =====================================================================


def _add_rounded_box_outer(
    mesh: Mesh, *,
    x0: float, y0: float, z0: float,
    x1: float, y1: float, z1: float,
    radius: float,
    corner_segs: int,
    skip_bottom: bool,
    group: str,
    skip_top: bool = False,
):
    """Build a rounded box with quarter-circle fillets on every edge.

    Topology decomposition:
        6 flat panels (one per face, inset by `radius` on each edge)
        12 cylindrical edge fillets (one per box edge)
        8 spherical corner fillets (one per box corner)

    If skip_bottom is True, omits the -Y panel and the 4 bottom edge
    fillets and the 4 bottom corner fillets, leaving an open bottom
    that the cavity geometry will fill in.

    If skip_top is True, omits ONLY the +Y flat panel quad (top edge
    fillets and top corner spheres are still emitted). Use this when
    the caller wants to retessellate the top panel with stud holes
    cut out -- the body's top under each stud is otherwise hidden
    inside the merged stud+body solid.
    """
    r = radius
    # Inner extents (the flat panels' bounds)
    xa, xb = x0 + r, x1 - r
    ya, yb = y0 + r, y1 - r
    za, zb = z0 + r, z1 - r

    # ---- Flat panels --------------------------------------------------
    # +Y (top) panel
    if not skip_top:
        _add_quad(mesh, group,
                  [xa, yb + r, za], [xb, yb + r, za],
                  [xb, yb + r, zb], [xa, yb + r, zb])
    # -Y (bottom) panel: only emit when we're a closed solid (no cavity)
    # When skip_bottom is True, the cavity geometry will provide the
    # bottom-rim annulus connecting the inner cavity walls to the
    # outer body's bottom-edge-fillet inset.
    if not skip_bottom:
        _add_quad(mesh, group,
                  [xa, ya - r, za], [xa, ya - r, zb],
                  [xb, ya - r, zb], [xb, ya - r, za])
    # +X
    _add_quad(mesh, group,
              [xb + r, ya, za], [xb + r, ya, zb],
              [xb + r, yb, zb], [xb + r, yb, za])
    # -X
    _add_quad(mesh, group,
              [xa - r, ya, za], [xa - r, yb, za],
              [xa - r, yb, zb], [xa - r, ya, zb])
    # +Z
    _add_quad(mesh, group,
              [xa, ya, zb + r], [xb, ya, zb + r],
              [xb, yb, zb + r], [xa, yb, zb + r])
    # -Z
    _add_quad(mesh, group,
              [xa, ya, za - r], [xa, yb, za - r],
              [xb, yb, za - r], [xb, ya, za - r])

    # ---- Cylindrical edge fillets ------------------------------------
    # 12 edges. For each, the fillet is a quarter-cylinder of length =
    # the box edge minus 2*r at its ends, centered on the inner-corner
    # axis (running along the box edge), and sweeping 90 degrees.
    n = corner_segs
    angles = np.linspace(0, np.pi / 2, n + 1)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)

    # Top edges (4) - they connect the top panel to the side panels
    # +X +Y edge: axis along Z from za..zb, at (xb, yb), sweeping from +X to +Y
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xb, yb, za), axis_p1=(xb, yb, zb),
                       u_axis=(1, 0, 0), v_axis=(0, 1, 0),
                       r=r, segs=n)
    # -X +Y edge
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xa, yb, zb), axis_p1=(xa, yb, za),
                       u_axis=(-1, 0, 0), v_axis=(0, 1, 0),
                       r=r, segs=n)
    # +Z +Y edge: axis along X
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xb, yb, zb), axis_p1=(xa, yb, zb),
                       u_axis=(0, 0, 1), v_axis=(0, 1, 0),
                       r=r, segs=n)
    # -Z +Y edge
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xa, yb, za), axis_p1=(xb, yb, za),
                       u_axis=(0, 0, -1), v_axis=(0, 1, 0),
                       r=r, segs=n)

    # Bottom edges (4) - even when skip_bottom=True we still emit the 
    # bottom EDGE fillets (just not the bottom face). The skipped face
    # leaves a hole that the cavity geometry fills.
    # +X -Y edge
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xb, ya, zb), axis_p1=(xb, ya, za),
                       u_axis=(1, 0, 0), v_axis=(0, -1, 0),
                       r=r, segs=n)
    # -X -Y edge
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xa, ya, za), axis_p1=(xa, ya, zb),
                       u_axis=(-1, 0, 0), v_axis=(0, -1, 0),
                       r=r, segs=n)
    # +Z -Y edge
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xa, ya, zb), axis_p1=(xb, ya, zb),
                       u_axis=(0, 0, 1), v_axis=(0, -1, 0),
                       r=r, segs=n)
    # -Z -Y edge
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xb, ya, za), axis_p1=(xa, ya, za),
                       u_axis=(0, 0, -1), v_axis=(0, -1, 0),
                       r=r, segs=n)

    # Vertical edges (4) - axis along Y
    # +X +Z edge: axis (xb, *, zb), sweeping from +X to +Z
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xb, ya, zb), axis_p1=(xb, yb, zb),
                       u_axis=(1, 0, 0), v_axis=(0, 0, 1),
                       r=r, segs=n)
    # +X -Z edge
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xb, yb, za), axis_p1=(xb, ya, za),
                       u_axis=(1, 0, 0), v_axis=(0, 0, -1),
                       r=r, segs=n)
    # -X +Z edge
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xa, yb, zb), axis_p1=(xa, ya, zb),
                       u_axis=(-1, 0, 0), v_axis=(0, 0, 1),
                       r=r, segs=n)
    # -X -Z edge
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(xa, ya, za), axis_p1=(xa, yb, za),
                       u_axis=(-1, 0, 0), v_axis=(0, 0, -1),
                       r=r, segs=n)

    # ---- Spherical corner fillets (octants) --------------------------
    # 8 corners always (we always fillet all 12 edges, even when the
    # bottom face is skipped to make room for the cavity opening).
    corners = [
        ((xb, yb, zb), 1, 1, 1),
        ((xa, yb, zb), -1, 1, 1),
        ((xb, yb, za), 1, 1, -1),
        ((xa, yb, za), -1, 1, -1),
        ((xb, ya, zb), 1, -1, 1),
        ((xa, ya, zb), -1, -1, 1),
        ((xb, ya, za), 1, -1, -1),
        ((xa, ya, za), -1, -1, -1),
    ]
    for center, sx, sy, sz in corners:
        _add_corner_octant(mesh, group, center, sx, sy, sz, r, n)


def _sweep_edge_fillet(
    mesh, group: str,
    *,
    axis_p0, axis_p1,
    u_axis, v_axis,
    r: float, segs: int,
):
    """A quarter-cylinder fillet swept along an edge.

    axis_p0, axis_p1: endpoints of the inner axis (the spine of the
                      fillet, on the box's body, NOT on the rounded
                      surface).
    u_axis, v_axis:   unit-length perpendicular directions defining
                      the 90-degree sweep plane. The fillet sweeps
                      from u_axis to v_axis (both at distance r from
                      the spine).
    """
    p0 = np.array(axis_p0, dtype=np.float64)
    p1 = np.array(axis_p1, dtype=np.float64)
    u = np.array(u_axis, dtype=np.float64)
    v = np.array(v_axis, dtype=np.float64)
    angles = np.linspace(0, np.pi / 2, segs + 1)
    offset = r * (np.cos(angles)[:, None] * u + np.sin(angles)[:, None] * v)
    verts = np.vstack([p0 + offset, p1 + offset])
    base = mesh.append_verts(verts)
    _emit_grid_quads(mesh, group, base, 2, segs + 1, flip=True)


def _add_corner_octant(
    mesh, group: str,
    center, sx: int, sy: int, sz: int,
    r: float, segs: int,
):
    """A spherical octant at a box corner. sx/sy/sz are the outward
    direction (each ±1)."""
    cx, cy, cz = center
    # Parametrize as theta in [0, pi/2] (azimuth in XZ plane), phi in
    # [0, pi/2] (elevation toward +Y or -Y depending on sy).
    # Place verts on a (segs+1) x (segs+1) grid.
    n = segs
    theta = np.linspace(0, np.pi / 2, n + 1)
    phi = np.linspace(0, np.pi / 2, n + 1)
    theta_grid, phi_grid = np.meshgrid(theta, phi, indexing="ij")
    verts = np.stack([
        cx + sx * r * np.cos(phi_grid) * np.cos(theta_grid),
        cy + sy * r * np.sin(phi_grid),
        cz + sz * r * np.cos(phi_grid) * np.sin(theta_grid),
    ], axis=-1)
    base = mesh.append_verts(verts.reshape(-1, 3))
    # Determine winding so the normal points OUT (away from box center).
    # We just emit consistent winding and rely on the importer to
    # flip if needed. Use a winding that's consistent with a positive-
    # octant convention:
    flip = (sx * sy * sz) < 0
    _emit_grid_quads(mesh, group, base, n + 1, n + 1, flip=flip)


def _add_filleted_stud(
    mesh, *,
    cx, cy, cz, radius, height,
    base_fillet, top_fillet,
    side_segs, fillet_segs,
    group,
):
    """A cylindrical stud with rounded base and top edge.

    Built by sweeping a profile around the Y axis. The profile (in
    (r, y) coords) goes:
        (radius + base_fillet, cy)               -- on body top, just outside stud
        ... arc inward and up to (radius, cy + base_fillet)
        (radius, cy + height - top_fillet)       -- straight side
        ... arc inward and up to (0, cy + height) via top_fillet
        (0, cy + height)                         -- top center
    """
    profile = _build_stud_profile(radius, height, base_fillet, top_fillet,
                                  fillet_segs)
    _revolve_profile(mesh, profile, cx, cy, cz, side_segs, group)


def _build_stud_profile(radius, height, base_fillet, top_fillet, fillet_segs):
    """Return the 2D profile (r, y) to revolve around the Y axis.

    Layout:
        y=0                : starts at r = radius + base_fillet (on body top, outside stud)
        ARC up and inward  : center at (radius, base_fillet), r=base_fillet
                              from angle -pi/2 (down) to 0 (right) -- giving
                              a concave corner... no wait.

    Actually, the right way: the BODY TOP is at y=0, r infinite (a wide
    horizontal floor). The stud is a cylinder of radius `radius`, going
    up from y=0 to y=height. The corners we need to round:
      - Where stud SIDE meets body TOP: this is at (radius, 0). A CONCAVE
        fillet (the air on the OUTSIDE of the stud sees a concave curve).
      - Where stud SIDE meets stud TOP: this is at (radius, height). A
        CONVEX fillet (the air sees a convex curve, since the stud is
        the solid).

    For a profile we rotate around the Y axis, the profile is in (r, y)
    half-plane. The profile traces the boundary between solid and air,
    with solid on the +y side at the top and r=0 axis side. Walking
    along the profile from outside-in:

        Start at (R_outer, 0) where R_outer = radius + base_fillet
                 -- this is the body-top "skirt" right outside the fillet
        Concave fillet arc to (radius, base_fillet)
                 -- center at (R_outer, base_fillet)
        Straight up to (radius, height - top_fillet)
        Convex fillet arc to (radius - top_fillet, height)
                 -- center at (radius - top_fillet, height - top_fillet)
        Straight in to (0, height)

    The convex top-fillet's "center" is INSIDE the stud, so the arc is
    swept from angle 0 (pointing +X) to angle pi/2 (pointing +Y).

    Returns a list of (r, y) tuples.
    """
    profile = []
    R_outer = radius + base_fillet
    # 1) Skirt point on body top
    profile.append((R_outer, 0.0))
    # 2) Concave base fillet arc
    # center (R_outer, base_fillet), radius=base_fillet
    # arc goes from angle 3pi/2 (pointing -Y from center -> hits (R_outer, 0)) 
    # to angle pi (pointing -X from center -> hits (R_outer-base_fillet=radius, base_fillet))
    for i in range(1, fillet_segs + 1):
        a = 3 * np.pi / 2 - (np.pi / 2) * (i / fillet_segs)
        # a goes from 3pi/2 down to pi
        r = R_outer + base_fillet * np.cos(a)
        y = base_fillet + base_fillet * np.sin(a)
        profile.append((r, y))
    # 3) Straight up the side
    profile.append((radius, height - top_fillet))
    # 4) Convex top fillet
    # center (radius - top_fillet, height - top_fillet), radius=top_fillet
    # arc goes from angle 0 (pointing +X from center -> (radius, height-top_fillet))
    # to angle pi/2 (pointing +Y from center -> (radius-top_fillet, height))
    for i in range(1, fillet_segs + 1):
        a = (np.pi / 2) * (i / fillet_segs)
        r = (radius - top_fillet) + top_fillet * np.cos(a)
        y = (height - top_fillet) + top_fillet * np.sin(a)
        profile.append((r, y))
    # 5) Top center
    profile.append((0.0, height))
    return profile


def _revolve_profile(mesh, profile, cx, cy, cz, segs, group):
    """Revolve a (r, y) profile around the Y axis through (cx, cy, cz).
    Emits a tessellated surface as quads. The profile's last point
    should be on the axis (r=0) for the cap to close cleanly; any
    quads at r=0 collapse to triangles."""
    n_prof = len(profile)
    theta = np.linspace(0, 2 * np.pi, segs, endpoint=False)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    # Build verts: (n_prof) rings of (segs) verts each
    verts = np.zeros((n_prof, segs, 3))
    for i, (r, y_off) in enumerate(profile):
        verts[i, :, 0] = cx + r * cos_t
        verts[i, :, 1] = cy + y_off
        verts[i, :, 2] = cz + r * sin_t
    base = mesh.append_verts(verts.reshape(-1, 3))

    grid = np.arange(base, base + n_prof * segs, dtype=np.int64).reshape(n_prof, segs)
    k = np.arange(segs)
    kp = (k + 1) % segs

    for i in range(n_prof - 1):
        r0 = profile[i][0]
        r1 = profile[i + 1][0]
        # If a ring has r==0, all its verts coincide; emit tris.
        if r0 == 0:
            faces = np.stack([grid[i, k], grid[i + 1, kp], grid[i + 1, k]], axis=1)
        elif r1 == 0:
            faces = np.stack([grid[i, k], grid[i, kp], grid[i + 1, k]], axis=1)
        else:
            faces = np.stack([grid[i, k], grid[i, kp], grid[i + 1, kp], grid[i + 1, k]], axis=1)
        mesh.add_group_faces(group, faces)




# =====================================================================
# CAVITY -- inner shell of the brick, opening through the bottom.
#
# Layout (looking up at the underside):
#
#   Outer body bottom panel boundary: rectangle with rounded corners,
#   inset from outside by body_fillet_radius. The body's bottom edge
#   fillet rolls UNDER it.
#
#   Inside that, the cavity opening (no flat panel here -- this is the
#   hole). Cavity inner walls are at distance `wall` from the outer
#   body sides. Cavity ceiling is at `H - ceiling` from the brick top.
#
#   Bottom rim frame: connects the outer-body's bottom-panel boundary
#   to the cavity inner walls, as a flat annulus at y=0.
#
#   Cavity has 6 surfaces:
#     - 4 inner walls (rectangles, axis-aligned, facing inward)
#     - 1 ceiling (rectangle, facing DOWN -- visible looking up)
#     - The bottom rim frame
#   Plus 4 ceiling-to-wall fillet strips (one per inner wall edge).
#   Plus 4 ceiling-corner spheres.
#
# Features INSIDE the cavity:
#     - 6 ceiling indents (simple cylindrical holes in the ceiling
#       under each stud's XZ position, with rim fillet)
#     - 2 connector tubes (between adjacent studs along the long axis;
#       hollow, with concave top fillet that flares OUT to ceiling,
#       and small bottom-rim fillet)
#     - Ribs: rectangular pads on inner walls. Per the reference:
#         * 2 ribs per long wall, evenly spaced
#         * 1 rib per short wall, centered
#       All ribs are the same simple rectangular box.
# =====================================================================


def _add_inner_cavity(
    mesh, *,
    x0, y0, z0, x1, y1, z1,        # cavity inner extents
    outer_x0, outer_z0, outer_x1, outer_z1,  # outer body bottom panel boundary
    outer_y0,                       # body bottom plane (= 0 typically)
    radius, corner_segs,            # ceiling-to-wall fillet
    group,
    # NEW: parameters for cutting indent holes in the ceiling
    indent_holes=None,              # list of (cx, cz, hole_r) or None
    indent_segs=32,                 # tessellation around each hole
    # NEW: concave fillet where cavity walls meet the rim frame
    bottom_fillet_radius=0.0,       # 0 = sharp interior edge (legacy)
):
    """Build the cavity inner walls + ceiling (with corner fillets) +
    bottom rim frame.

    If indent_holes is provided, cut circular holes in the ceiling
    flat panel for each (cx, cz, hole_r) entry. The ceiling is
    partitioned into rectangular cells (one per stud) and a ribbon
    frame around the cell grid, so that each cell can have its own
    circular hole.

    If bottom_fillet_radius > 0, the wall feet are lifted by `rb` and
    a concave fillet rounds the convex material edge between cavity
    wall and rim flat. Topology in this case:
      * walls span [y0+rb, wall_top]
      * 4 horizontal bottom-edge cylindrical fillets (one per wall)
      * 4 corner torus sections (major radius r, minor radius rb)
        joining the verticals to the horizontals at each cavity corner
      * rim's inner perimeter expands outward by rb
        (corner arcs sweep at radius r+rb)
    """
    r = radius
    rb = bottom_fillet_radius
    rb_segs = corner_segs
    wall_foot_y = y0 + rb  # bottom of inner walls (raised by fillet radius)
    cx_lo = x0 + r
    cx_hi = x1 - r
    cz_lo = z0 + r
    cz_hi = z1 - r
    cy = y1 - r

    # ---- inner ceiling (faces DOWN), with optional holes -----------
    if indent_holes is None:
        # Simple flat quad
        _add_quad(mesh, group,
                  [cx_lo, cy, cz_lo],
                  [cx_hi, cy, cz_lo],
                  [cx_hi, cy, cz_hi],
                  [cx_lo, cy, cz_hi])
    else:
        _emit_ceiling_with_holes(
            mesh, group=group,
            cx_lo=cx_lo, cx_hi=cx_hi, cz_lo=cz_lo, cz_hi=cz_hi, cy=cy,
            holes=indent_holes,
            segs=indent_segs,
        )

    # +X ceiling-to-wall fillet (axis along Z from cz_lo to cz_hi)
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(cx_hi, cy - r, cz_lo),
                       axis_p1=(cx_hi, cy - r, cz_hi),
                       u_axis=(0, 1, 0),
                       v_axis=(1, 0, 0),
                       r=r, segs=corner_segs)
    # -X
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(cx_lo, cy - r, cz_hi),
                       axis_p1=(cx_lo, cy - r, cz_lo),
                       u_axis=(0, 1, 0),
                       v_axis=(-1, 0, 0),
                       r=r, segs=corner_segs)
    # +Z
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(cx_hi, cy - r, cz_hi),
                       axis_p1=(cx_lo, cy - r, cz_hi),
                       u_axis=(0, 1, 0),
                       v_axis=(0, 0, 1),
                       r=r, segs=corner_segs)
    # -Z
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(cx_lo, cy - r, cz_lo),
                       axis_p1=(cx_hi, cy - r, cz_lo),
                       u_axis=(0, 1, 0),
                       v_axis=(0, 0, -1),
                       r=r, segs=corner_segs)

    for cx_corner, cz_corner, sx, sz in [
        (cx_hi, cz_hi,  1,  1),
        (cx_lo, cz_hi, -1,  1),
        (cx_hi, cz_lo,  1, -1),
        (cx_lo, cz_lo, -1, -1),
    ]:
        _add_corner_octant(mesh, group,
                           center=(cx_corner, cy - r, cz_corner),
                           sx=sx, sy=1, sz=sz,
                           r=r, segs=corner_segs)

    # ---- inner walls (face INWARD) -------------------------------
    # Walls are RECTANGLES inset by r at the corners on BOTH top AND
    # bottom edges. The inset corners are filled by vertical inner-
    # corner cylinder fillets below, which maintain a constant fillet
    # radius all the way down to the rim flat (instead of a triangle
    # fan converging to a sharp point at the cavity bottom corners).
    wall_top = cy - r
    # +X wall (faces -X)
    _add_quad(mesh, group,
              [x1, wall_foot_y, cz_lo], [x1, wall_top, cz_lo],
              [x1, wall_top,    cz_hi], [x1, wall_foot_y, cz_hi])
    # -X wall (faces +X)
    _add_quad(mesh, group,
              [x0, wall_foot_y, cz_hi], [x0, wall_top, cz_hi],
              [x0, wall_top,    cz_lo], [x0, wall_foot_y, cz_lo])
    # +Z wall (faces -Z)
    _add_quad(mesh, group,
              [cx_hi, wall_foot_y, z1], [cx_hi, wall_top, z1],
              [cx_lo, wall_top,    z1], [cx_lo, wall_foot_y, z1])
    # -Z wall (faces +Z)
    _add_quad(mesh, group,
              [cx_lo, wall_foot_y, z0], [cx_lo, wall_top, z0],
              [cx_hi, wall_top,    z0], [cx_hi, wall_foot_y, z0])

    # ---- vertical inner-corner fillets (concave quarter-cylinders) -
    # One quarter-cylinder per cavity inner corner, sweeping vertically
    # from the rim flat at y=y0 up to wall_top. Its top arc (at
    # y=wall_top) coincides with the corner sphere octant's bottom arc
    # and gets welded by mesh.weld_vertices. Result: a continuous
    # concave fillet from the floor straight up to the ceiling fillet.
    #
    # Spine direction is reversed for sx*sz=-1 corners so the standard
    # _sweep_edge_fillet winding produces the correct cavity-facing
    # normal at every corner.
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(cx_hi, wall_foot_y, cz_hi),
                       axis_p1=(cx_hi, wall_top,    cz_hi),
                       u_axis=(1, 0, 0), v_axis=(0, 0, 1),
                       r=r, segs=corner_segs)
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(cx_lo, wall_foot_y, cz_lo),
                       axis_p1=(cx_lo, wall_top,    cz_lo),
                       u_axis=(-1, 0, 0), v_axis=(0, 0, -1),
                       r=r, segs=corner_segs)
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(cx_lo, wall_top,    cz_hi),
                       axis_p1=(cx_lo, wall_foot_y, cz_hi),
                       u_axis=(-1, 0, 0), v_axis=(0, 0, 1),
                       r=r, segs=corner_segs)
    _sweep_edge_fillet(mesh, group,
                       axis_p0=(cx_hi, wall_top,    cz_lo),
                       axis_p1=(cx_hi, wall_foot_y, cz_lo),
                       u_axis=(1, 0, 0), v_axis=(0, 0, -1),
                       r=r, segs=corner_segs)

    # ---- horizontal bottom-edge fillets (concave, one per wall) ----
    # Quarter-cylinder swept along the wall foot. The fillet rounds
    # the convex 90-deg material edge between the cavity wall (going
    # up) and the rim flat (going outward), so from inside the cavity
    # looking at the wall going down, you see a smooth concave curve
    # transitioning into the rim.
    #
    # Spine of each fillet sits OUTSIDE the cavity wall in the
    # material region, offset by rb from both surfaces. The arc
    # sweeps from u (toward wall, distance rb above rim) to v
    # (toward rim, distance rb outside wall).
    #
    # Axis directions chosen so the standard _sweep_edge_fillet
    # winding produces the correct outward-facing normal at every
    # wall (matching ceiling-fillet axis convention: +X and -Z run
    # forward in their axis, -X and +Z run reversed).
    if rb > 0:
        # +X wall foot (axis along +Z)
        _sweep_edge_fillet(mesh, group,
                           axis_p0=(x1 + rb, wall_foot_y, cz_lo),
                           axis_p1=(x1 + rb, wall_foot_y, cz_hi),
                           u_axis=(-1, 0, 0), v_axis=(0, -1, 0),
                           r=rb, segs=rb_segs)
        # -X wall foot (axis along -Z)
        _sweep_edge_fillet(mesh, group,
                           axis_p0=(x0 - rb, wall_foot_y, cz_hi),
                           axis_p1=(x0 - rb, wall_foot_y, cz_lo),
                           u_axis=(1, 0, 0), v_axis=(0, -1, 0),
                           r=rb, segs=rb_segs)
        # +Z wall foot (axis along -X)
        _sweep_edge_fillet(mesh, group,
                           axis_p0=(cx_hi, wall_foot_y, z1 + rb),
                           axis_p1=(cx_lo, wall_foot_y, z1 + rb),
                           u_axis=(0, 0, -1), v_axis=(0, -1, 0),
                           r=rb, segs=rb_segs)
        # -Z wall foot (axis along +X)
        _sweep_edge_fillet(mesh, group,
                           axis_p0=(cx_lo, wall_foot_y, z0 - rb),
                           axis_p1=(cx_hi, wall_foot_y, z0 - rb),
                           u_axis=(0, 0, 1), v_axis=(0, -1, 0),
                           r=rb, segs=rb_segs)

        # ---- 4 corner torus sections at cavity bottom corners ------
        # Each section connects the bottom of a vertical inner-corner
        # cylinder fillet (radius r, axis vertical at corner_xz) to
        # the two adjacent horizontal bottom-edge fillets (radius rb).
        # Topologically a torus: cross-section is a quarter circle of
        # radius rb (sweeping from "wall side" at y=wall_foot_y to
        # "rim side" at y=y0), swept around the corner axis along a
        # quarter circle of radius (r+rb).
        for cx_corner, cz_corner, sx, sz in [
            (cx_hi, cz_hi, +1, +1),  # +X+Z
            (cx_lo, cz_hi, -1, +1),  # -X+Z
            (cx_lo, cz_lo, -1, -1),  # -X-Z
            (cx_hi, cz_lo, +1, -1),  # +X-Z
        ]:
            n_t = corner_segs
            n_p = rb_segs
            t = np.linspace(0, np.pi / 2, n_t + 1)
            phi = np.linspace(0, np.pi / 2, n_p + 1)
            t_grid, phi_grid = np.meshgrid(t, phi, indexing="ij")
            d = r + rb * (1 - np.cos(phi_grid))
            verts = np.stack([
                cx_corner + sx * d * np.cos(t_grid),
                wall_foot_y - rb * np.sin(phi_grid),
                cz_corner + sz * d * np.sin(t_grid),
            ], axis=-1)
            base_v = mesh.append_verts(verts.reshape(-1, 3))
            flip = (sx * sz) > 0
            _emit_grid_quads(mesh, group, base_v, n_t + 1, n_p + 1, flip=flip)

    # ---- bottom rim frame ------------------------------------------
    # Flat annulus at y=outer_y0=y0. Outer perimeter is a SHARP
    # rectangle (the body's bottom panel boundary at y=0; the body
    # has no geometry along an arc at y=0, so this edge is straight).
    # Inner perimeter is a ROUNDED rectangle: straight along each
    # wall foot at offset rb from the cavity wall (so the rim's
    # inner edge meets the bottom of the new bottom-edge fillet, or
    # the cavity wall directly when rb=0). Corner arcs sweep at
    # radius (r + rb), matching the bottom of the corner torus
    # section (or the vertical inner-corner cylinder fillet's bottom
    # arc when rb=0).
    #
    # Topology: 4 trapezoidal straight quads + 4 triangle-fan corner
    # wedges (apex at the sharp outer corner, fan to the inner arc).
    arc_radius = r + rb
    inner_x_lo = x0 - rb
    inner_x_hi = x1 + rb
    inner_z_lo = z0 - rb
    inner_z_hi = z1 + rb

    # 4 straight rim quads, one per side:
    # -Z side
    _add_quad(mesh, group,
              [outer_x0,   outer_y0, outer_z0],
              [outer_x1,   outer_y0, outer_z0],
              [cx_hi,      y0,       inner_z_lo],
              [cx_lo,      y0,       inner_z_lo])
    # +X side
    _add_quad(mesh, group,
              [outer_x1,   outer_y0, outer_z0],
              [outer_x1,   outer_y0, outer_z1],
              [inner_x_hi, y0,       cz_hi],
              [inner_x_hi, y0,       cz_lo])
    # +Z side
    _add_quad(mesh, group,
              [outer_x1,   outer_y0, outer_z1],
              [outer_x0,   outer_y0, outer_z1],
              [cx_lo,      y0,       inner_z_hi],
              [cx_hi,      y0,       inner_z_hi])
    # -X side
    _add_quad(mesh, group,
              [outer_x0,   outer_y0, outer_z1],
              [outer_x0,   outer_y0, outer_z0],
              [inner_x_lo, y0,       cz_lo],
              [inner_x_lo, y0,       cz_hi])

    # 4 corner wedges. Each is a triangle fan from the sharp outer
    # corner apex to (corner_segs+1) points along the inner-corner
    # arc at y=y0. Winding is (apex, arc[i+1], arc[i]) so the face
    # normal points -Y (rim is seen from below the brick).
    def emit_rim_corner_fan(apex_xyz, arc_center_xz, start_angle, end_angle):
        cx_arc, cz_arc = arc_center_xz
        n = corner_segs
        pts = [list(apex_xyz)]
        for i in range(n + 1):
            t = i / n
            a = start_angle + (end_angle - start_angle) * t
            pts.append([cx_arc + arc_radius * np.cos(a), y0,
                        cz_arc + arc_radius * np.sin(a)])
        base_v = mesh.append_verts(np.array(pts))
        apex_idx = base_v
        for i in range(n):
            arc_a = base_v + 1 + i
            arc_b = base_v + 1 + i + 1
            mesh.add_group_face(group, (apex_idx, arc_b, arc_a))

    # -X-Z corner
    emit_rim_corner_fan((outer_x0, outer_y0, outer_z0),
                        (cx_lo, cz_lo), np.pi, 3 * np.pi / 2)
    # +X-Z corner
    emit_rim_corner_fan((outer_x1, outer_y0, outer_z0),
                        (cx_hi, cz_lo), 3 * np.pi / 2, 2 * np.pi)
    # +X+Z corner
    emit_rim_corner_fan((outer_x1, outer_y0, outer_z1),
                        (cx_hi, cz_hi), 0, np.pi / 2)
    # -X+Z corner
    emit_rim_corner_fan((outer_x0, outer_y0, outer_z1),
                        (cx_lo, cz_hi), np.pi / 2, np.pi)


def _emit_ceiling_with_holes(
    mesh, *, group: str,
    cx_lo: float, cx_hi: float,
    cz_lo: float, cz_hi: float,
    cy: float,
    holes,
    segs: int,
    face_up: bool = False,
):
    """Tessellate a horizontal rectangle with circular holes punched
    out, using Delaunay triangulation.

    `face_up=False` (default): face normal is -Y. Used for the cavity
    ceiling (visible looking up from inside the cavity).
    `face_up=True`: face normal is +Y. Used for the body's top panel
    (visible looking down from above the brick), with one hole per
    stud removing the now-hidden disc under each stud's footprint.

    Strategy:
        1. Generate a 2D point cloud:
           - Rectangle's 4 corners
           - Points along each rectangle edge (helps anchor the
             tessellation near the walls)
           - `segs` points around each hole's circumference
        2. Compute the Delaunay triangulation of these points.
        3. Drop any triangle whose centroid falls inside any hole.
        4. Emit the surviving triangles as faces with the requested
           normal direction (Delaunay returns CCW in (x, z), which is
           equivalent to CCW from +Y looking down).
    """
    from scipy.spatial import Delaunay

    if not holes:
        if face_up:
            _add_quad(mesh, group,
                      [cx_lo, cy, cz_lo],
                      [cx_lo, cy, cz_hi],
                      [cx_hi, cy, cz_hi],
                      [cx_hi, cy, cz_lo])
        else:
            _add_quad(mesh, group,
                      [cx_lo, cy, cz_lo],
                      [cx_hi, cy, cz_lo],
                      [cx_hi, cy, cz_hi],
                      [cx_lo, cy, cz_hi])
        return

    # Build the point set in 2D (X, Z); Y is fixed at cy.
    pts_2d = []

    # Rectangle perimeter -- corners and intermediate edge points.
    # Add edge points roughly aligned with the holes so the
    # triangulation doesn't have weird elongated triangles near walls.
    n_edge = max(4, len(holes))  # at least one edge point per hole on each side

    # Use the holes' x-coords for the top/bottom edges
    edge_xs = sorted(set([cx_lo, cx_hi]
                         + [h[0] for h in holes if cx_lo < h[0] < cx_hi]))
    edge_zs = sorted(set([cz_lo, cz_hi]
                         + [h[1] for h in holes if cz_lo < h[1] < cz_hi]))

    # Bottom edge (z = cz_lo)
    for x in edge_xs:
        pts_2d.append((x, cz_lo))
    # Top edge (z = cz_hi)
    for x in edge_xs:
        pts_2d.append((x, cz_hi))
    # Left edge (x = cx_lo) -- skip first and last to avoid duplicates
    for z in edge_zs[1:-1]:
        pts_2d.append((cx_lo, z))
    # Right edge (x = cx_hi)
    for z in edge_zs[1:-1]:
        pts_2d.append((cx_hi, z))

    # Hole rim points
    hole_rim_indices = []  # (start_idx, count) per hole, in pts_2d
    for cxh, czh, rh in holes:
        start = len(pts_2d)
        theta = np.linspace(0, 2 * np.pi, segs, endpoint=False)
        for t in theta:
            pts_2d.append((cxh + rh * np.cos(t),
                           czh + rh * np.sin(t)))
        hole_rim_indices.append((start, segs))

    pts_2d = np.array(pts_2d)
    # Deduplicate (some perimeter points might collide with rim if
    # rim_radius is large). We'll just make sure they're distinct.
    # Actually simple: use np.unique.
    pts_unique = np.unique(pts_2d.round(6), axis=0)
    if len(pts_unique) < len(pts_2d):
        pts_2d = pts_unique

    # Delaunay
    try:
        tri = Delaunay(pts_2d)
    except Exception as e:
        # Fall back to single quad if triangulation fails (loses the
        # holes, but at least the panel is closed).
        if face_up:
            _add_quad(mesh, group,
                      [cx_lo, cy, cz_lo],
                      [cx_lo, cy, cz_hi],
                      [cx_hi, cy, cz_hi],
                      [cx_hi, cy, cz_lo])
        else:
            _add_quad(mesh, group,
                      [cx_lo, cy, cz_lo],
                      [cx_hi, cy, cz_lo],
                      [cx_hi, cy, cz_hi],
                      [cx_lo, cy, cz_hi])
        return

    # Convert to 3D verts (Y = cy) and add to mesh
    verts_3d = np.column_stack([pts_2d[:, 0], np.full(len(pts_2d), cy),
                                pts_2d[:, 1]])
    base = mesh.append_verts(verts_3d)

    # For each triangle, check if its centroid lies inside any hole.
    # Vectorizing this filter avoids a Python loop over every triangle/hole pair.
    simplices = tri.simplices
    centroids = pts_2d[simplices].mean(axis=1)
    hole_arr = np.asarray(holes, dtype=np.float64)
    dx = centroids[:, 0:1] - hole_arr[None, :, 0]
    dz = centroids[:, 1:2] - hole_arr[None, :, 1]
    r2 = (hole_arr[None, :, 2] * 0.999) ** 2
    keep = ~np.any((dx * dx + dz * dz) < r2, axis=1)

    # Delaunay returns CCW in the (x, z) plane, which is CCW from
    # +Y looking down. Keep that winding for face_up=True (+Y normal);
    # reverse it for face_up=False (-Y normal, visible from the cavity).
    kept = simplices[keep]
    if face_up:
        faces = base + kept[:, [0, 1, 2]]
    else:
        faces = base + kept[:, [0, 2, 1]]
    mesh.add_group_faces(group, faces)


# =====================================================================
# CONNECTOR TUBE
# =====================================================================


def _add_filleted_tube(
    mesh, *,
    cx, cz, ceiling_y, floor_y,
    outer_r, inner_r,
    top_fillet, bottom_fillet,
    side_segs, fillet_segs,
    group,
):
    """A connector tube: hollow cylinder hanging from the ceiling.

    Profile (in (r, y), revolved around Y axis at (cx, cz)):

        -- Outer side --
        Start on ceiling at r = outer_r + top_fillet (the ceiling
        extends INWARD past the tube's outer wall by `top_fillet`).
        Concave fillet (the air sees a concave curve; the tube's
        material is to the RIGHT of the profile as we walk down).
        Center at (outer_r + top_fillet, ceiling_y - top_fillet),
        sweep angle from pi/2 (pointing +Y from center to start) to pi
        (pointing -X from center to end). End point: (outer_r,
        ceiling_y - top_fillet).

        -- Outer wall: straight down --
        From (outer_r, ceiling_y - top_fillet) to (outer_r, floor_y +
        bottom_fillet).

        -- Bottom rim, outer convex --
        From (outer_r, floor_y + bottom_fillet) curving to
        (outer_r - bottom_fillet, floor_y).
        Center at (outer_r - bottom_fillet, floor_y + bottom_fillet);
        sweep from a=0 to a=-pi/2.

        -- Bottom flat, going inward --
        From (outer_r - bottom_fillet, floor_y) to (inner_r +
        bottom_fillet, floor_y).

        -- Bottom rim, inner convex --
        From (inner_r + bottom_fillet, floor_y) curving up to (inner_r,
        floor_y + bottom_fillet).
        Center at (inner_r + bottom_fillet, floor_y + bottom_fillet);
        sweep from a=-pi to a=-pi/2.

        -- Inner wall: straight up --
        From (inner_r, floor_y + bottom_fillet) to (inner_r, ceiling_y
        - top_fillet).

        -- Inner top, concave --
        From (inner_r, ceiling_y - top_fillet) curving up and inward
        to (inner_r - top_fillet, ceiling_y).
        Center at (inner_r - top_fillet, ceiling_y - top_fillet);
        sweep from a=0 to a=pi/2.

    The KEY POINT: both outer top fillet and inner top fillet are
    CONCAVE (the air sees a concave curve, like a smooth flare from
    the cylinder wall up into the ceiling). Looking up at the
    underside, the tube reads as a hollow ring whose top edge SMOOTHLY
    flares out to the ceiling on both sides of the wall.
    """
    profile = []

    # Outer top fillet: from (outer_r + top_fillet, ceiling_y) -> (outer_r, ceiling_y - top_fillet)
    cx_arc = outer_r + top_fillet
    cy_arc = ceiling_y - top_fillet
    # angle from pi/2 (start, vec from center is (0, +tf)) to pi (end, vec is (-tf, 0))
    profile.append((cx_arc + 0, cy_arc + top_fillet))  # angle pi/2
    for i in range(1, fillet_segs + 1):
        a = np.pi / 2 + (np.pi / 2) * (i / fillet_segs)  # pi/2 -> pi
        profile.append((cx_arc + top_fillet * np.cos(a),
                        cy_arc + top_fillet * np.sin(a)))

    # Outer wall straight
    profile.append((outer_r, floor_y + bottom_fillet))

    # Outer bottom convex
    cx_arc = outer_r - bottom_fillet
    cy_arc = floor_y + bottom_fillet
    # from a=0 (start vec (+bf, 0)) to a=-pi/2 (end vec (0, -bf))
    for i in range(1, fillet_segs + 1):
        a = 0 - (np.pi / 2) * (i / fillet_segs)
        profile.append((cx_arc + bottom_fillet * np.cos(a),
                        cy_arc + bottom_fillet * np.sin(a)))

    # Bottom flat across
    profile.append((inner_r + bottom_fillet, floor_y))

    # Inner bottom convex (mirror of outer bottom)
    cx_arc = inner_r + bottom_fillet
    cy_arc = floor_y + bottom_fillet
    # from a=-pi (start vec (-bf, 0)) to a=-pi/2 (end vec (0, -bf))... no.
    # Wait, our endpoint here is (inner_r, floor_y + bottom_fillet) which
    # from center (inner_r + bottom_fillet, floor_y + bottom_fillet)
    # has vector (-bf, 0), angle = pi. Start point (inner_r + bottom_fillet,
    # floor_y) has vector (0, -bf), angle = -pi/2 = 3pi/2.
    # Sweep from 3pi/2 (= -pi/2) to pi (going via pi -- the "left" way around)
    # equivalently a=-pi/2 to a=-pi (subtracting another pi/2)
    for i in range(1, fillet_segs + 1):
        a = -np.pi / 2 - (np.pi / 2) * (i / fillet_segs)
        profile.append((cx_arc + bottom_fillet * np.cos(a),
                        cy_arc + bottom_fillet * np.sin(a)))

    # Inner wall straight
    profile.append((inner_r, ceiling_y - top_fillet))

    # Inner top fillet -- CONCAVE, flaring OUT to the ceiling
    # End point should be (inner_r - top_fillet, ceiling_y).
    # That vector from end point's CENTER is (?, ?). For a concave fillet
    # whose air is on the +Y/-X side and material is on the -Y/+X side,
    # the center should be at (inner_r - top_fillet, ceiling_y - top_fillet).
    # Start (inner_r, ceiling_y - top_fillet) from center = (+tf, 0), angle 0.
    # End   (inner_r - top_fillet, ceiling_y) from center = (0, +tf), angle pi/2.
    cx_arc = inner_r - top_fillet
    cy_arc = ceiling_y - top_fillet
    for i in range(1, fillet_segs + 1):
        a = 0 + (np.pi / 2) * (i / fillet_segs)
        profile.append((cx_arc + top_fillet * np.cos(a),
                        cy_arc + top_fillet * np.sin(a)))

    # Top cap: close the tube at the ceiling level so the brick body
    # reads as a solid lid above the tube. Without this, the inner top
    # fillet ends mid-air at (inner_r - top_fillet, ceiling_y) and the
    # mesh has an open ring there -- visible as a hairline crack
    # between the tube's inner mouth and the cavity ceiling. Real LEGO
    # tubes are blind holes; the body material caps them from above.
    profile.append((0.0, ceiling_y))

    _revolve_profile_partial(mesh, profile, cx, cz, side_segs, group)


# =====================================================================
# CEILING INDENT -- a simple cylindrical hole through the ceiling
# under each stud's XZ position.
# =====================================================================


def _add_ceiling_indent(
    mesh, *,
    cx, cz, ceiling_y, depth, outer_r, rim_fillet,
    side_segs, fillet_segs, group,
):
    """A small cylindrical pocket carved upward into the ceiling.

    Profile (revolved around Y axis at (cx, cz)):
        Start: (outer_r + rim_fillet, ceiling_y) -- on the ceiling
               flat, just outside the indent rim.
        Concave fillet curving DOWN and IN to (outer_r, ceiling_y +
            rim_fillet). Wait, "up" in this geometry means "into the
            body" -- ceiling_y is the BOTTOM of the ceiling layer
            (where the cavity opens up). Going UP (+Y) is INTO the
            body. So the indent goes from the ceiling SURFACE (at
            ceiling_y) UP INTO the body to reach indent_top
            (at ceiling_y + depth).

        OK so the fillet is from (outer_r + rim_fillet, ceiling_y) to
        (outer_r, ceiling_y + rim_fillet). Center at (outer_r +
        rim_fillet, ceiling_y + rim_fillet). Concave; air is on the
        BOTTOM side; material is on the TOP side.
        From start: vector (-rim_fillet, 0) -> angle pi. No that's wrong.
        Start (outer_r + rim_fillet, ceiling_y), center (outer_r +
        rim_fillet, ceiling_y + rim_fillet) -> vector (0, -rim_fillet)
        -> angle -pi/2.
        End (outer_r, ceiling_y + rim_fillet), center same -> vector
        (-rim_fillet, 0) -> angle pi.
        Sweep -pi/2 -> -pi (the short way clockwise).

        Then straight up to (outer_r, ceiling_y + depth).
        Then across the top to (0, ceiling_y + depth) -- the top cap.
    """
    profile = []
    # Rim fillet: from (outer_r + rim_fillet, ceiling_y) to (outer_r, ceiling_y + rim_fillet)
    cx_arc = outer_r + rim_fillet
    cy_arc = ceiling_y + rim_fillet
    profile.append((outer_r + rim_fillet, ceiling_y))
    for i in range(1, fillet_segs + 1):
        a = -np.pi / 2 - (np.pi / 2) * (i / fillet_segs)  # -pi/2 -> -pi
        profile.append((cx_arc + rim_fillet * np.cos(a),
                        cy_arc + rim_fillet * np.sin(a)))
    # Straight up the wall, stopping `rim_fillet` short of the cap so
    # the cap-to-wall fillet can round the inside corner of the pocket.
    profile.append((outer_r, ceiling_y + depth - rim_fillet))
    # Cap-to-wall concave fillet: from (outer_r, ceiling_y + depth -
    # rim_fillet) curving up and inward to (outer_r - rim_fillet,
    # ceiling_y + depth). Center at (outer_r - rim_fillet, ceiling_y +
    # depth - rim_fillet) -- inside the air pocket. Sweep angle 0 ->
    # pi/2: a=0 puts the arc at (outer_r, depth - rim_fillet) on the
    # wall; a=pi/2 at (outer_r - rim_fillet, depth) on the cap. The
    # arc bulges toward the original sharp corner, smoothing it.
    cap_arc_cx = outer_r - rim_fillet
    cap_arc_cy = ceiling_y + depth - rim_fillet
    for i in range(1, fillet_segs + 1):
        a = (np.pi / 2) * (i / fillet_segs)  # 0 -> pi/2
        profile.append((cap_arc_cx + rim_fillet * np.cos(a),
                        cap_arc_cy + rim_fillet * np.sin(a)))
    # Top cap apex on the axis
    profile.append((0.0, ceiling_y + depth))

    _revolve_profile_partial(mesh, profile, cx, cz, side_segs, group)


# =====================================================================
# WALL RIB -- simple rectangular box protruding from a wall.
# Per the reference: rectangular SNOT-style ribs.
# =====================================================================


def _add_wall_rib(
    mesh, *,
    axis: str,
    wall_pos: float,
    protrude_dir: int,
    center: float,
    y_bot: float, y_top: float,
    half_width: float, protrusion: float,
    fillet_r: float, fillet_segs: int,
    group: str,
):
    """Fully filleted rectangular boss rib protruding from a wall.

    All 12 edges of the rib's bounding box are rounded. The 4 back
    edges (where the rib's perimeter meets the wall plane) get
    CONCAVE fillets so the rib appears to grow out of the wall like
    an injection-molded boss. The 4 front edges (around the front
    face) and the 4 side-to-side edges (running along the protrusion
    direction at the rib's outer perimeter corners) get CONVEX
    fillets. The 4 front corners get CONVEX sphere octants. The 4
    back corners are saddle-shaped and are left as small unfilled
    gaps -- these sit against the wall plane and are hidden from the
    cavity view by the wall geometry behind them.

    Caller responsibilities:
      - `y_bot` must satisfy `y_bot - r >= wall_foot_y`. The bottom
        concave fillet flares OUTWARD by `r` past `y_bot` at the wall
        plane; the caller must lift the rib off the wall foot so this
        flare doesn't drop below it.

    axis="z": rib's length runs along Z; wall normal is X. Wall at
              x = wall_pos; rib protrudes in sign(protrude_dir)*X.
    axis="x": rib's length runs along X; wall normal is Z.
    """
    height = y_top - y_bot
    P = max(0.0, float(protrusion))
    if P <= 0 or height <= 0 or half_width <= 0:
        return

    # Fillet radius must fit on every axis (s, y, l) so the 12 fillets
    # and 5 flat panels all stay non-degenerate.
    r = max(0.0, float(fillet_r))
    r = min(r, P * 0.45, height * 0.45, half_width * 0.45)
    if r <= 0:
        return
    n = max(2, int(fillet_segs))
    sign = protrude_dir

    # ---- Local (s, y, l) <-> world coordinate mapping ------------------
    # +s: protrusion direction (away from wall, into cavity)
    # +y: world up (always)
    # +l: along the rib's length axis
    # The (s, y, l) -> world map is RIGHT-handed only in two of four
    # (axis, sign) cases; in the other two it's left-handed. For LH
    # cases every face's vertex order needs to be reversed so its
    # outward normal points into the cavity.
    l_min = center - half_width
    l_max = center + half_width
    if axis == "z":
        # +s -> world ±X (depending on sign), +l -> world +Z
        flip = (sign < 0)
        def to3d(s_v, y_v, l_v):
            return (wall_pos + s_v * sign, y_bot + y_v, l_v)
        def vec3d(ds, dy, dl):
            return (ds * sign, dy, dl)
        # `_add_corner_octant` takes WORLD-axis (sx, sy, sz) signs.
        # World x-sign matches sign(protrude_dir); world y/z match local.
        def world_signs(ssx, ssy, ssl):
            return (ssx * sign, ssy, ssl)
    else:  # axis == "x"
        # +s -> world ±Z, +l -> world +X
        flip = (sign > 0)
        def to3d(s_v, y_v, l_v):
            return (l_v, y_bot + y_v, wall_pos + s_v * sign)
        def vec3d(ds, dy, dl):
            return (dl, dy, ds * sign)
        def world_signs(ssx, ssy, ssl):
            return (ssl, ssy, ssx * sign)

    def add_quad_local(p0, p1, p2, p3):
        """Emit a quad given local-coord corner tuples (s, y, l)."""
        if flip:
            p0, p1, p2, p3 = p3, p2, p1, p0
        _add_quad(mesh, group, to3d(*p0), to3d(*p1), to3d(*p2), to3d(*p3))

    def add_edge_fillet(p0_local, p1_local, u_local, v_local):
        """Emit a quarter-cylinder edge fillet. Spine endpoints and
        (u, v) sweep directions are given in local (s, y, l). For LH
        coord maps we swap the spine endpoints so the (u, v, spine)
        frame is right-handed in WORLD coords (which is what
        `_sweep_edge_fillet`'s winding expects)."""
        if flip:
            p0_local, p1_local = p1_local, p0_local
        _sweep_edge_fillet(
            mesh, group,
            axis_p0=to3d(*p0_local),
            axis_p1=to3d(*p1_local),
            u_axis=vec3d(*u_local),
            v_axis=vec3d(*v_local),
            r=r, segs=n,
        )

    def add_octant_local(center_local, ssx, ssy, ssl):
        """Convex sphere octant at a local-coord corner."""
        wsx, wsy, wsz = world_signs(ssx, ssy, ssl)
        _add_corner_octant(
            mesh, group, to3d(*center_local),
            wsx, wsy, wsz, r, n,
        )

    # ===================================================================
    # 5 FLAT PANELS (back face is omitted; sits against the wall)
    # ===================================================================
    # Each panel is inset by r on every boundary so the edge/corner
    # fillets bridge the gaps. Vertex order is chosen for outward
    # normal in the canonical RH coordinate system; add_quad_local
    # reverses for LH cases.
    #
    # Front (s = P), normal -> +s (into cavity)
    add_quad_local(
        (P, r,        l_min+r), (P, height-r, l_min+r),
        (P, height-r, l_max-r), (P, r,        l_max-r),
    )
    # Top (local y = height), normal -> +y
    add_quad_local(
        (r,   height, l_min+r), (r,   height, l_max-r),
        (P-r, height, l_max-r), (P-r, height, l_min+r),
    )
    # Bot (local y = 0), normal -> -y
    add_quad_local(
        (r,   0.0, l_min+r), (P-r, 0.0, l_min+r),
        (P-r, 0.0, l_max-r), (r,   0.0, l_max-r),
    )
    # +l end, normal -> +l
    add_quad_local(
        (r,   r,        l_max), (P-r, r,        l_max),
        (P-r, height-r, l_max), (r,   height-r, l_max),
    )
    # -l end, normal -> -l
    add_quad_local(
        (r,   r,        l_min), (r,   height-r, l_min),
        (P-r, height-r, l_min), (P-r, r,        l_min),
    )

    # ===================================================================
    # 12 EDGE FILLETS
    # ===================================================================
    # Local-coord notation: y_top-y_bot = height; we work with y in
    # [0, height] in local coords (since y_v is added to y_bot in to3d).
    yh = height
    yt = yh        # local "y_top"
    yb = 0.0       # local "y_bot"

    # ---- 4 CONVEX front edges (around the front face) ----
    # front-top: spine at (P-r, yt-r, l varies), sweep +s -> +y
    add_edge_fillet((P-r, yt-r, l_min+r), (P-r, yt-r, l_max-r),
                    (+1, 0, 0), (0, +1, 0))
    # front-bot: spine at (P-r, yb+r, l varies), sweep +s -> -y
    add_edge_fillet((P-r, yb+r, l_min+r), (P-r, yb+r, l_max-r),
                    (+1, 0, 0), (0, -1, 0))
    # front-+l: spine at (P-r, y varies, l_max-r), sweep +s -> +l
    add_edge_fillet((P-r, yb+r, l_max-r), (P-r, yt-r, l_max-r),
                    (+1, 0, 0), (0, 0, +1))
    # front--l: spine at (P-r, y varies, l_min+r), sweep +s -> -l
    add_edge_fillet((P-r, yb+r, l_min+r), (P-r, yt-r, l_min+r),
                    (+1, 0, 0), (0, 0, -1))

    # ---- 4 CONVEX side-to-side edges (along the protrusion) ----
    # top-+l: spine at (s varies, yt-r, l_max-r), sweep +y -> +l
    add_edge_fillet((r, yt-r, l_max-r), (P-r, yt-r, l_max-r),
                    (0, +1, 0), (0, 0, +1))
    # top--l: spine at (s varies, yt-r, l_min+r), sweep +y -> -l
    add_edge_fillet((r, yt-r, l_min+r), (P-r, yt-r, l_min+r),
                    (0, +1, 0), (0, 0, -1))
    # bot-+l: spine at (s varies, yb+r, l_max-r), sweep -y -> +l
    add_edge_fillet((r, yb+r, l_max-r), (P-r, yb+r, l_max-r),
                    (0, -1, 0), (0, 0, +1))
    # bot--l: spine at (s varies, yb+r, l_min+r), sweep -y -> -l
    add_edge_fillet((r, yb+r, l_min+r), (P-r, yb+r, l_min+r),
                    (0, -1, 0), (0, 0, -1))

    # ---- 4 CONCAVE back edges (rib meets wall) ----
    # Spines sit OUTSIDE the rib (in the air), offset from the rib's
    # box by r in two directions. The (u, v) directions point BACK
    # toward the wall and toward the side face respectively. The
    # resulting arc is concave from the cavity-side view.
    #
    # back-top: spine at (r, yt+r, l varies), sweep -s -> -y
    add_edge_fillet((r, yt+r, l_min+r), (r, yt+r, l_max-r),
                    (-1, 0, 0), (0, -1, 0))
    # back-bot: spine at (r, yb-r, l varies), sweep -s -> +y
    add_edge_fillet((r, yb-r, l_min+r), (r, yb-r, l_max-r),
                    (-1, 0, 0), (0, +1, 0))
    # back-+l: spine at (r, y varies, l_max+r), sweep -s -> -l
    add_edge_fillet((r, yb+r, l_max+r), (r, yt-r, l_max+r),
                    (-1, 0, 0), (0, 0, -1))
    # back--l: spine at (r, y varies, l_min-r), sweep -s -> +l
    add_edge_fillet((r, yb+r, l_min-r), (r, yt-r, l_min-r),
                    (-1, 0, 0), (0, 0, +1))

    # ===================================================================
    # 4 CONVEX FRONT-CORNER SPHERE OCTANTS
    # ===================================================================
    # Each octant sits at the front corner of the core box, with the
    # outward octant in the (+s, ±y, ±l) direction.
    add_octant_local((P-r, yt-r, l_max-r), +1, +1, +1)
    add_octant_local((P-r, yt-r, l_min+r), +1, +1, -1)
    add_octant_local((P-r, yb+r, l_max-r), +1, -1, +1)
    add_octant_local((P-r, yb+r, l_min+r), +1, -1, -1)

    # ===================================================================
    # 4 SADDLE PATCHES at the back corners (rib meets wall)
    # ===================================================================
    # Each back corner is where one convex side-to-side edge fillet
    # meets two concave back edge fillets. The three fillet end-rings
    # leave a roughly triangular gap on the cavity-facing side; the
    # saddle is a Coons-patch quadrilateral that fills the gap and
    # closes against the wall plane (s = 0).
    #
    # Boundary curves of each saddle (parameterized by u, v in [0, 1]):
    #   v = 1  (convex side):    convex back end-ring
    #   u = 0  (top/bot side):   top/bot-back concave end-ring at this
    #                            corner (l = lc_in)
    #   u = 1  (+/- l side):     back-+l / back--l concave end-ring at
    #                            this corner (y = yc_in)
    #   v = 0  (wall plane):     quarter-arc of radius r * sqrt(2)
    #                            on the s = 0 plane, around the rib's
    #                            true back corner (s=0, y=y_corner,
    #                            l=l_corner). Bulges OUTWARD away from
    #                            the rib body.
    #
    # The 4 corners of the parameter square coincide exactly with the
    # shared endpoints of these curves, so weld_vertices(tol=1e-4)
    # seals the joins to all three adjacent fillets at the end of the
    # build. The wall-plane edge (v = 0) is left as an open boundary
    # by design -- the wall geometry behind it hides the gap, the same
    # way studs/tubes/indents are inserted features that introduce
    # boundary edges harmlessly.
    half_pi = np.pi * 0.5
    sqrt2 = np.sqrt(2.0)

    def _saddle_C1(u, y_corner, y_dir, l_corner, l_dir):
        """Convex back end-ring (v = 1)."""
        yc_in_ = y_corner - y_dir * r
        lc_in_ = l_corner - l_dir * r
        a = u * half_pi
        return (np.full_like(a, r, dtype=np.float64),
                yc_in_ + y_dir * r * np.cos(a),
                lc_in_ + l_dir * r * np.sin(a))

    def _saddle_C2(v, y_corner, y_dir, l_corner, l_dir):
        """Top/bot-back concave end-ring at this corner (u = 0)."""
        lc_in_ = l_corner - l_dir * r
        b = v * half_pi
        return (r * (1.0 - np.cos(b)),
                y_corner + y_dir * r * (1.0 - np.sin(b)),
                np.full_like(b, lc_in_, dtype=np.float64))

    def _saddle_C3(v, y_corner, y_dir, l_corner, l_dir):
        """Back-+l / back--l concave end-ring at this corner (u = 1)."""
        yc_in_ = y_corner - y_dir * r
        b = v * half_pi
        return (r * (1.0 - np.cos(b)),
                np.full_like(b, yc_in_, dtype=np.float64),
                l_corner + l_dir * r * (1.0 - np.sin(b)))

    def _saddle_C0(u, y_corner, y_dir, l_corner, l_dir):
        """Wall-plane arc (v = 0); quarter-circle radius r*sqrt2."""
        a = u * np.pi - np.pi * 0.25
        return (np.zeros_like(a, dtype=np.float64),
                y_corner + y_dir * r * sqrt2 * np.cos(a),
                l_corner + l_dir * r * sqrt2 * np.sin(a))

    def add_saddle_local(y_corner, y_dir, l_corner, l_dir):
        P00 = np.array(_saddle_C0(0.0, y_corner, y_dir, l_corner, l_dir))
        P10 = np.array(_saddle_C0(1.0, y_corner, y_dir, l_corner, l_dir))
        P01 = np.array(_saddle_C1(0.0, y_corner, y_dir, l_corner, l_dir))
        P11 = np.array(_saddle_C1(1.0, y_corner, y_dir, l_corner, l_dir))

        u_vals = np.linspace(0.0, 1.0, n + 1)
        v_vals = np.linspace(0.0, 1.0, n + 1)
        u_grid, v_grid = np.meshgrid(u_vals, v_vals, indexing="ij")
        c0 = np.stack(_saddle_C0(u_grid, y_corner, y_dir, l_corner, l_dir), axis=-1)
        c1 = np.stack(_saddle_C1(u_grid, y_corner, y_dir, l_corner, l_dir), axis=-1)
        c2 = np.stack(_saddle_C2(v_grid, y_corner, y_dir, l_corner, l_dir), axis=-1)
        c3 = np.stack(_saddle_C3(v_grid, y_corner, y_dir, l_corner, l_dir), axis=-1)
        u3 = u_grid[..., None]
        v3 = v_grid[..., None]
        ruled_v = (1.0 - v3) * c0 + v3 * c1
        ruled_u = (1.0 - u3) * c2 + u3 * c3
        bilin = ((1.0 - u3) * (1.0 - v3) * P00
                 + u3 * (1.0 - v3) * P10
                 + (1.0 - u3) * v3 * P01
                 + u3 * v3 * P11)
        local = (ruled_v + ruled_u - bilin).reshape(-1, 3)
        if axis == "z":
            verts_world = np.column_stack([
                wall_pos + local[:, 0] * sign,
                y_bot + local[:, 1],
                local[:, 2],
            ])
        else:
            verts_world = np.column_stack([
                local[:, 2],
                y_bot + local[:, 1],
                wall_pos + local[:, 0] * sign,
            ])
        base = mesh.append_verts(verts_world)

        # The default (v0, v1, v2, v3) winding produces an OUTWARD
        # (cavity-facing) normal at corners where y_dir * l_dir < 0
        # (top--l and bot-+l). Flip for the other two (top-+l and
        # bot--l). XOR with `flip` for LH local->world coord cases.
        saddle_flip = ((y_dir * l_dir) > 0) ^ flip
        _emit_grid_quads(mesh, group, base, n + 1, n + 1, flip=saddle_flip)

    add_saddle_local(yt, +1, l_max, +1)  # top-+l
    add_saddle_local(yt, +1, l_min, -1)  # top--l
    add_saddle_local(yb, -1, l_max, +1)  # bot-+l
    add_saddle_local(yb, -1, l_min, -1)  # bot--l


# =====================================================================
# Tiny utility helpers
# =====================================================================


def _revolve_profile_partial(mesh, profile, cx, cz, segs, group):
    """Revolve a (r, y) profile (with absolute y values) around the Y
    axis through (cx, cz). Emits a tessellated surface.
    """
    n_prof = len(profile)
    theta = np.linspace(0, 2 * np.pi, segs, endpoint=False)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    verts = np.zeros((n_prof, segs, 3))
    for i, (r, y) in enumerate(profile):
        verts[i, :, 0] = cx + r * cos_t
        verts[i, :, 1] = y
        verts[i, :, 2] = cz + r * sin_t
    base = mesh.append_verts(verts.reshape(-1, 3))

    grid = np.arange(base, base + n_prof * segs, dtype=np.int64).reshape(n_prof, segs)
    k = np.arange(segs)
    kp = (k + 1) % segs
    for i in range(n_prof - 1):
        r0 = profile[i][0]
        r1 = profile[i + 1][0]
        if r0 == 0 and r1 == 0:
            continue
        if r0 == 0:
            faces = np.stack([grid[i, k], grid[i + 1, kp], grid[i + 1, k]], axis=1)
        elif r1 == 0:
            faces = np.stack([grid[i, k], grid[i, kp], grid[i + 1, k]], axis=1)
        else:
            faces = np.stack([grid[i, k], grid[i, kp], grid[i + 1, kp], grid[i + 1, k]], axis=1)
        mesh.add_group_faces(group, faces)


def _add_quad(mesh: Mesh, group: str, p0, p1, p2, p3):
    base = mesh.append_verts(np.array([p0, p1, p2, p3]))
    mesh.add_group_face(group, (base, base + 1, base + 2, base + 3))


def _emit_grid_quads(
    mesh: Mesh,
    group: str,
    base: int,
    rows: int,
    cols: int,
    *,
    flip: bool = False,
):
    """Emit quads for a row-major vertex grid, preserving local winding."""
    grid = np.arange(base, base + rows * cols, dtype=np.int64).reshape(rows, cols)
    if flip:
        faces = np.stack([
            grid[:-1, :-1],
            grid[:-1, 1:],
            grid[1:, 1:],
            grid[1:, :-1],
        ], axis=-1)
    else:
        faces = np.stack([
            grid[:-1, :-1],
            grid[1:, :-1],
            grid[1:, 1:],
            grid[:-1, 1:],
        ], axis=-1)
    mesh.add_group_faces(group, faces.reshape(-1, 4))
