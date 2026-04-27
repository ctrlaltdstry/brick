"""High-resolution LEGO brick geometry with fillets modeled directly
into the mesh.

DESIGN: This is NOT a SubD-ready control cage. The fillets are real
quarter-circle curves built into the geometry. Output ships as-is, no
subdivision needed. Triangles are fine where they're useful (like
triangle fans on top caps).

Components emitted as polygon groups:
    "body"        outer shell (with filleted top edge + bottom rim)
    "studs"       cylindrical studs with filleted top edges
    "underside"   inner cavity walls + ceiling + ribs + ceiling indents
    "tubes"       connector tubes inside the cavity
    "logo"        optional, copied onto each stud

Low-res version: same outer silhouette, drastically reduced segment
counts. For rigid-body collider proxies.
"""
from typing import Optional
import numpy as np
from .mesh import Mesh


FILLET_SEGMENTS_HI = 6
FILLET_SEGMENTS_LO = 2
CYLINDER_SEGMENTS_HI = 24
CYLINDER_SEGMENTS_LO = 8
CORNER_SEGMENTS_HI = 6
CORNER_SEGMENTS_LO = 2


def make_brick_mesh(
    width_studs: int,
    depth_studs: int,
    height_plates: int,
    *,
    stud_size: float = 8.0,
    plate_size: float = 3.2,
    edge_fillet_radius: float = 0.30,
    stud_height: Optional[float] = None,
    stud_radius_ratio: float = 0.30,
    stud_top_fillet_ratio: float = 0.12,
    with_studs: bool = True,
    with_underside: bool = True,
    underside_wall: float = 1.0,
    underside_ceiling: float = 1.2,
    with_tubes: bool = True,
    tube_outer_ratio: float = 0.40,
    tube_inner_ratio: float = 0.30,
    with_stud_indents: bool = True,
    stud_indent_outer_ratio: float = 0.34,
    stud_indent_inner_ratio: float = 0.10,
    with_ribs: bool = True,
    rib_size_ratio: float = 0.06,
    rib_protrusion_ratio: float = 0.08,
    low_res: bool = False,
    logo: Optional["Mesh"] = None,
    logo_extrusion_height: Optional[float] = None,
    logo_diameter_ratio: float = 0.65,
) -> Mesh:
    if low_res:
        return _make_low_res_brick(
            width_studs, depth_studs, height_plates,
            stud_size=stud_size, plate_size=plate_size,
            edge_fillet_radius=edge_fillet_radius,
            with_studs=with_studs)

    if stud_height is None:
        stud_height = plate_size * 0.55

    W = width_studs * stud_size
    D = depth_studs * stud_size
    H = height_plates * plate_size

    fseg = FILLET_SEGMENTS_HI
    cseg = CYLINDER_SEGMENTS_HI
    cornseg = CORNER_SEGMENTS_HI

    e = float(min(edge_fillet_radius, W * 0.3, D * 0.3, H * 0.3))

    mesh = Mesh()

    # ---- BODY (outer shell + cavity, in one connected mesh) -------
    body = _build_body_shell(W, D, H, e, fseg, cornseg,
                             with_underside=with_underside,
                             wall=underside_wall, ceiling=underside_ceiling,
                             group="body")
    mesh.merge(body)

    # ---- STUDS ----------------------------------------------------
    if with_studs:
        stud_r = stud_size * stud_radius_ratio
        stud_top_fillet = max(stud_top_fillet_ratio * stud_r, 0.05)
        for sx in range(width_studs):
            for sz in range(depth_studs):
                cx = (sx + 0.5) * stud_size
                cz = (sz + 0.5) * stud_size
                stud = _build_stud(cx, H, cz,
                                   radius=stud_r,
                                   height=stud_height,
                                   top_fillet=stud_top_fillet,
                                   segments=cseg,
                                   fseg=fseg,
                                   group="studs")
                mesh.merge(stud)
                if logo is not None:
                    from .mesh import affine_translate
                    T = affine_translate(np.array(
                        [cx, H + stud_height, cz]
                    ))
                    mesh.merge(logo, transform=T)

    # ---- INTERIOR FEATURES ----------------------------------------
    if with_underside:
        ceiling_y = H - underside_ceiling

        if (with_tubes and width_studs >= 2 and depth_studs >= 2):
            tube_or = stud_size * tube_outer_ratio
            tube_ir = stud_size * tube_inner_ratio
            for sx in range(width_studs - 1):
                for sz in range(depth_studs - 1):
                    cx = (sx + 1) * stud_size
                    cz = (sz + 1) * stud_size
                    tube = _build_tube(cx, cz,
                                       top_y=ceiling_y,
                                       bottom_y=0.0,
                                       outer_r=tube_or,
                                       inner_r=tube_ir,
                                       segments=cseg,
                                       fseg=fseg,
                                       fillet=min(e, underside_ceiling * 0.3),
                                       group="tubes")
                    mesh.merge(tube)

        if with_stud_indents:
            indent_or = stud_size * stud_indent_outer_ratio
            indent_ir = stud_size * stud_indent_inner_ratio
            indent_top_y = H - underside_ceiling * 0.2
            indent_bot_y = ceiling_y
            for sx in range(width_studs):
                for sz in range(depth_studs):
                    cx = (sx + 0.5) * stud_size
                    cz = (sz + 0.5) * stud_size
                    indent = _build_indent(
                        cx, cz,
                        bottom_y=indent_bot_y,
                        top_y=indent_top_y,
                        outer_r=indent_or,
                        inner_r=indent_ir,
                        segments=cseg,
                        fseg=fseg,
                        fillet=min(e, (indent_top_y - indent_bot_y) * 0.3),
                        group="underside")
                    mesh.merge(indent)

        if with_ribs:
            rib_hw = stud_size * rib_size_ratio
            rib_pr = stud_size * rib_protrusion_ratio
            rib_top_y = ceiling_y - 0.05
            rib_bot_y = 0.05
            rib_fillet = min(e * 0.5, rib_hw * 0.3, rib_pr * 0.3)
            for i in range(depth_studs - 1):
                cz = (i + 1) * stud_size
                for (wall_pos, sgn) in [(W - underside_wall, -1),
                                        (underside_wall, +1)]:
                    rib = _build_rib(
                        along_axis="z",
                        wall_pos=wall_pos,
                        protrusion_dir=sgn,
                        center=cz,
                        top_y=rib_top_y, bot_y=rib_bot_y,
                        half_width=rib_hw,
                        protrusion=rib_pr,
                        fillet=rib_fillet,
                        fseg=fseg,
                        group="underside",
                    )
                    mesh.merge(rib)
            for i in range(width_studs - 1):
                cx = (i + 1) * stud_size
                for (wall_pos, sgn) in [(D - underside_wall, -1),
                                        (underside_wall, +1)]:
                    rib = _build_rib(
                        along_axis="x",
                        wall_pos=wall_pos,
                        protrusion_dir=sgn,
                        center=cx,
                        top_y=rib_top_y, bot_y=rib_bot_y,
                        half_width=rib_hw,
                        protrusion=rib_pr,
                        fillet=rib_fillet,
                        fseg=fseg,
                        group="underside",
                    )
                    mesh.merge(rib)

    return mesh


# =====================================================================
# Outer body shell with rounded top edge + rounded vertical corners
# =====================================================================

def _rounded_rect_loop(W: float, D: float, r: float,
                       corner_segments: int) -> np.ndarray:
    """2D loop (X, Z) for a rounded rectangle [0..W] x [0..D] with corner
    radius r. Returns N points going CCW; same N for any (W, D, r)."""
    if r <= 0:
        # Degenerate: 4 corners + corner_segments fillers per corner
        n = 4 * (corner_segments + 1)
        pts = np.zeros((n, 2))
        # 4 corners, each repeated to keep the count
        idx = 0
        corners = [(0, 0), (W, 0), (W, D), (0, D)]
        for c in corners:
            for _ in range(corner_segments + 1):
                pts[idx] = c
                idx += 1
        return pts

    pts = []
    def arc(cx, cz, a0, a1, segs):
        for k in range(segs + 1):
            t = a0 + (a1 - a0) * k / segs
            pts.append([cx + r * np.cos(t), cz + r * np.sin(t)])

    arc(W - r, r,     -np.pi / 2,    0,             corner_segments)
    arc(W - r, D - r,  0,            np.pi / 2,     corner_segments)
    arc(r,     D - r,  np.pi / 2,    np.pi,         corner_segments)
    arc(r,     r,      np.pi,        3 * np.pi / 2, corner_segments)
    return np.array(pts)


def _build_body_shell(W: float, D: float, H: float, e: float,
                      fseg: int, cornseg: int,
                      *, with_underside: bool,
                      wall: float, ceiling: float,
                      group: str) -> Mesh:
    """Outer body: stack of horizontal loops swept up the brick.

    Y profile:
        y=0          outer rounded-rect (corner radius e)
        y=H-e        same outer rounded-rect (top of vertical wall section)
        y in [H-e, H]  fseg quarter-arc steps that curve the loop INWARD
                       so the top edge is filleted.

    With underside enabled, also emits the inner cavity surface as part
    of the same group "underside" connected to the body's bottom rim.
    """
    mesh = Mesh()

    levels = []  # list of (y, loop_2d_array)
    levels.append((0.0,    _rounded_rect_loop(W, D, e, cornseg)))
    levels.append((H - e,  _rounded_rect_loop(W, D, e, cornseg)))
    for k in range(1, fseg + 1):
        t = (np.pi / 2) * (k / fseg)
        y = (H - e) + e * np.sin(t)
        inset = e * (1 - np.cos(t))
        new_e = max(e - inset, 0.001)
        new_W = W - 2 * inset
        new_D = D - 2 * inset
        loop = _rounded_rect_loop(new_W, new_D, new_e, cornseg)
        loop[:, 0] += inset
        loop[:, 1] += inset
        levels.append((y, loop))

    n_pts = len(levels[0][1])
    for (y, loop) in levels:
        if len(loop) != n_pts:
            raise RuntimeError(
                f"Body shell: loop sizes inconsistent ({len(loop)} vs {n_pts})")

    base = mesh.append_verts(np.array([
        [pt[0], y, pt[1]]
        for (y, loop) in levels
        for pt in loop
    ]))

    def vid(li, k): return base + li * n_pts + (k % n_pts)

    for li in range(len(levels) - 1):
        for k in range(n_pts):
            mesh.add_group_face(group, (
                vid(li,     k    ),
                vid(li,     k + 1),
                vid(li + 1, k + 1),
                vid(li + 1, k    ),
            ))

    # Top cap: triangle fan to a center vertex
    last_li = len(levels) - 1
    top_y = levels[last_li][0]
    top_loop = levels[last_li][1]
    cx = (top_loop[:, 0].min() + top_loop[:, 0].max()) / 2
    cz = (top_loop[:, 1].min() + top_loop[:, 1].max()) / 2
    top_center = mesh.append_verts(np.array([[cx, top_y, cz]]))
    for k in range(n_pts):
        mesh.add_group_face(group, (
            top_center,
            vid(last_li, k    ),
            vid(last_li, k + 1),
        ))

    if with_underside:
        _add_cavity_shell(mesh, W, D, H, e, cornseg,
                          wall=wall, ceiling=ceiling,
                          outer_bottom_base=base,
                          outer_n_pts=n_pts,
                          group="underside")
    else:
        # closed bottom (faces DOWN)
        bot_loop = levels[0][1]
        cx = (bot_loop[:, 0].min() + bot_loop[:, 0].max()) / 2
        cz = (bot_loop[:, 1].min() + bot_loop[:, 1].max()) / 2
        bot_center = mesh.append_verts(np.array([[cx, 0.0, cz]]))
        for k in range(n_pts):
            mesh.add_group_face(group, (
                bot_center,
                vid(0, k + 1),
                vid(0, k    ),
            ))

    return mesh


def _add_cavity_shell(mesh: Mesh, W: float, D: float, H: float, e: float,
                      cornseg: int, *,
                      wall: float, ceiling: float,
                      outer_bottom_base: int,
                      outer_n_pts: int,
                      group: str) -> None:
    """Cavity inside the brick. Connected to the body's bottom-outer
    perimeter via a flat rim ring, then walls go up to the ceiling."""
    inner_W = W - 2 * wall
    inner_D = D - 2 * wall
    inner_corner_r = max(e - wall, 0.05)
    inner_loop = _rounded_rect_loop(inner_W, inner_D, inner_corner_r, cornseg)
    inner_loop[:, 0] += wall
    inner_loop[:, 1] += wall

    n_pts = len(inner_loop)
    if n_pts != outer_n_pts:
        raise RuntimeError(
            f"Cavity loop count {n_pts} != outer {outer_n_pts}")

    ceiling_y = H - ceiling

    inner_bot_base = mesh.append_verts(np.array([
        [pt[0], 0.0, pt[1]] for pt in inner_loop
    ]))
    inner_top_base = mesh.append_verts(np.array([
        [pt[0], ceiling_y, pt[1]] for pt in inner_loop
    ]))

    def ob(k): return outer_bottom_base + (k % outer_n_pts)
    def ib(k): return inner_bot_base + (k % n_pts)
    def it(k): return inner_top_base + (k % n_pts)

    # Bottom rim ring (faces DOWN)
    for k in range(n_pts):
        mesh.add_group_face(group, (
            ob(k),
            ib(k),
            ib(k + 1),
            ob(k + 1),
        ))
    # Inner walls (faces inward)
    for k in range(n_pts):
        mesh.add_group_face(group, (
            ib(k    ),
            it(k    ),
            it(k + 1),
            ib(k + 1),
        ))
    # Ceiling (faces DOWN)
    cx = (inner_loop[:, 0].min() + inner_loop[:, 0].max()) / 2
    cz = (inner_loop[:, 1].min() + inner_loop[:, 1].max()) / 2
    ceil_center = mesh.append_verts(np.array([[cx, ceiling_y, cz]]))
    for k in range(n_pts):
        mesh.add_group_face(group, (
            ceil_center,
            it(k + 1),
            it(k    ),
        ))


# =====================================================================
# Studs: cylinder with filleted top edge
# =====================================================================

def _build_stud(cx: float, base_y: float, cz: float, *,
                radius: float, height: float, top_fillet: float,
                segments: int, fseg: int, group: str) -> Mesh:
    m = Mesh()
    n = segments
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    # Profile (radius, y_offset_from_base):
    # bottom of stud, straight wall, then quarter-arc curving inward
    # to flat top.
    profile = []
    profile.append((radius, 0.0))
    profile.append((radius, height - top_fillet))
    for k in range(1, fseg + 1):
        t = (np.pi / 2) * (k / fseg)
        r = radius - top_fillet * (1 - np.cos(t))
        y = (height - top_fillet) + top_fillet * np.sin(t)
        profile.append((r, y))

    rings = []
    for (r, y) in profile:
        rings.append([[cx + r * cos_t[k], base_y + y, cz + r * sin_t[k]]
                      for k in range(n)])
    base = m.append_verts(np.array([v for ring in rings for v in ring]))
    def vid(ri, k): return base + ri * n + (k % n)

    for ri in range(len(profile) - 1):
        for k in range(n):
            m.add_group_face(group, (
                vid(ri,     k    ),
                vid(ri + 1, k    ),
                vid(ri + 1, k + 1),
                vid(ri,     k + 1),
            ))

    # top cap (triangle fan)
    last_ri = len(profile) - 1
    top_y_world = base_y + profile[last_ri][1]
    cidx = m.append_verts(np.array([[cx, top_y_world, cz]]))
    for k in range(n):
        m.add_group_face(group, (
            cidx,
            vid(last_ri, k    ),
            vid(last_ri, k + 1),
        ))
    return m


# =====================================================================
# Connector tube: hollow cylinder hanging from ceiling
# =====================================================================

def _build_tube(cx: float, cz: float, *,
                top_y: float, bottom_y: float,
                outer_r: float, inner_r: float,
                segments: int, fseg: int, fillet: float,
                group: str) -> Mesh:
    """Topology: outer wall, ring at bottom (rim), inner wall, ring at top
    (where it meets the ceiling). Filleted bottom rim (visible from below).
    """
    m = Mesh()
    n = segments
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    f = max(min(fillet, (top_y - bottom_y) * 0.4,
                (outer_r - inner_r) * 0.4), 1e-4)

    # Single sweep profile (going around the outside, down, across the rim,
    # up the inside, then closing at the top with a flat ring).
    # Use (r, y) tuples; sweep around theta.

    # Outer side (top -> rim):
    profile = [(outer_r, top_y), (outer_r, bottom_y + f)]
    # bottom-outer fillet curve to rim
    for k in range(1, fseg + 1):
        t = (np.pi / 2) * (k / fseg)
        profile.append((outer_r - f * (1 - np.cos(t)),
                        bottom_y + f * (1 - np.sin(t))))
    # bottom rim flat ring (ends of fillets)
    profile.append((inner_r + f, bottom_y))
    # bottom-inner fillet curve back up
    for k in range(fseg - 1, -1, -1):
        t = (np.pi / 2) * (k / fseg)
        profile.append((inner_r + f * (1 - np.cos(t)),
                        bottom_y + f * (1 - np.sin(t))))
    # straight up inner wall to top
    profile.append((inner_r, top_y))

    rings = []
    for (r, y) in profile:
        rings.append([[cx + r * cos_t[k], y, cz + r * sin_t[k]]
                      for k in range(n)])
    base = m.append_verts(np.array([v for ring in rings for v in ring]))
    def vid(ri, k): return base + ri * n + (k % n)

    for ri in range(len(profile) - 1):
        for k in range(n):
            m.add_group_face(group, (
                vid(ri,     k    ),
                vid(ri + 1, k    ),
                vid(ri + 1, k + 1),
                vid(ri,     k + 1),
            ))
    # close the top: outer-top ring -> inner-top ring (faces UP, joining ceiling)
    last_ri = len(profile) - 1
    for k in range(n):
        m.add_group_face(group, (
            vid(0,       k    ),
            vid(0,       k + 1),
            vid(last_ri, k + 1),
            vid(last_ri, k    ),
        ))
    return m


# =====================================================================
# Ceiling indent: hollow cylinder pocket in the ceiling
# =====================================================================

def _build_indent(cx: float, cz: float, *,
                  bottom_y: float, top_y: float,
                  outer_r: float, inner_r: float,
                  segments: int, fseg: int, fillet: float,
                  group: str) -> Mesh:
    """Same shape as a tube but inverted: rim at the BOTTOM (visible
    looking up), closed top (hidden inside the body)."""
    m = Mesh()
    n = segments
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    f = max(min(fillet, (top_y - bottom_y) * 0.4,
                (outer_r - inner_r) * 0.4), 1e-4)

    profile = [(outer_r, top_y), (outer_r, bottom_y + f)]
    for k in range(1, fseg + 1):
        t = (np.pi / 2) * (k / fseg)
        profile.append((outer_r - f * (1 - np.cos(t)),
                        bottom_y + f * (1 - np.sin(t))))
    profile.append((inner_r + f, bottom_y))
    for k in range(fseg - 1, -1, -1):
        t = (np.pi / 2) * (k / fseg)
        profile.append((inner_r + f * (1 - np.cos(t)),
                        bottom_y + f * (1 - np.sin(t))))
    profile.append((inner_r, top_y))

    rings = []
    for (r, y) in profile:
        rings.append([[cx + r * cos_t[k], y, cz + r * sin_t[k]]
                      for k in range(n)])
    base = m.append_verts(np.array([v for ring in rings for v in ring]))
    def vid(ri, k): return base + ri * n + (k % n)

    for ri in range(len(profile) - 1):
        for k in range(n):
            m.add_group_face(group, (
                vid(ri,     k    ),
                vid(ri + 1, k    ),
                vid(ri + 1, k + 1),
                vid(ri,     k + 1),
            ))
    # top closure (annulus at top_y, hidden inside body)
    last_ri = len(profile) - 1
    for k in range(n):
        m.add_group_face(group, (
            vid(0,       k    ),
            vid(0,       k + 1),
            vid(last_ri, k + 1),
            vid(last_ri, k    ),
        ))
    return m


# =====================================================================
# Wall ribs: filleted protrusion on inside walls
# =====================================================================

def _build_rib(*, along_axis: str, wall_pos: float, protrusion_dir: int,
               center: float, top_y: float, bot_y: float,
               half_width: float, protrusion: float,
               fillet: float, fseg: int, group: str) -> Mesh:
    """A small filleted rib protruding from one of the inside walls.

    Modeled as a rounded-rectangle prism extruded outward from the wall:
    - Front face (the visible one): rounded rectangle in (along_axis, Y),
      with corner radius `fillet`.
    - Side fillet: where the rib meets the wall, a quarter-arc curves
      from the wall plane out to the front face.
    - Back is hidden against the wall (no faces emitted there).
    """
    m = Mesh()
    f = max(min(fillet, half_width * 0.5, protrusion * 0.5,
                (top_y - bot_y) * 0.3), 1e-4)

    # Local (u, v, w): u along wall, v vertical, w protrusion direction.
    if along_axis == "z":
        def world(u, v, w):
            return (wall_pos + protrusion_dir * w, v, center + u)
    else:
        def world(u, v, w):
            return (center + u, v, wall_pos + protrusion_dir * w)

    # Front-face outline (at full protrusion). Rounded rect in (u, v) with
    # corner radius f. Build CCW.
    fpts_uv = []
    n_corner = fseg
    def carc(cu, cv, a0, a1):
        for k in range(n_corner + 1):
            t = a0 + (a1 - a0) * k / n_corner
            fpts_uv.append((cu + f * np.cos(t), cv + f * np.sin(t)))

    carc(half_width - f,  bot_y + f, -np.pi / 2, 0)
    carc(half_width - f,  top_y - f,  0,         np.pi / 2)
    carc(-half_width + f, top_y - f,  np.pi / 2, np.pi)
    carc(-half_width + f, bot_y + f,  np.pi,     3 * np.pi / 2)
    n_pts = len(fpts_uv)

    # Inward-normal helper (from the rounded-rect outline)
    def outline_normal(u, v):
        # Determine which segment this point is on
        if u >= half_width - f - 1e-6:
            if v >= top_y - f - 1e-6:
                cu, cv = half_width - f, top_y - f
                nu, nv = u - cu, v - cv
            elif v <= bot_y + f + 1e-6:
                cu, cv = half_width - f, bot_y + f
                nu, nv = u - cu, v - cv
            else:
                nu, nv = 1.0, 0.0
        elif u <= -half_width + f + 1e-6:
            if v >= top_y - f - 1e-6:
                cu, cv = -half_width + f, top_y - f
                nu, nv = u - cu, v - cv
            elif v <= bot_y + f + 1e-6:
                cu, cv = -half_width + f, bot_y + f
                nu, nv = u - cu, v - cv
            else:
                nu, nv = -1.0, 0.0
        elif v >= top_y - f - 1e-6:
            nu, nv = 0.0, 1.0
        elif v <= bot_y + f + 1e-6:
            nu, nv = 0.0, -1.0
        else:
            nu, nv = 0.0, 0.0
        mag = np.sqrt(nu * nu + nv * nv)
        if mag > 1e-9:
            nu, nv = nu / mag, nv / mag
        return nu, nv

    # Build rings going from back (w=0) to front (w=protrusion):
    # ring 0 at w=0:        outline expanded outward by 0 (rectangle outline at full size)
    # ring 1 at w=protrusion - f:  same (straight side wall section)
    # rings 2..fseg+1: front fillet quarter-arc going from straight side
    #   to inset front face
    rings = []
    def make_ring(offset, w):
        out = []
        for (u, v) in fpts_uv:
            nu, nv = outline_normal(u, v)
            iu = u - offset * nu
            iv = v - offset * nv
            out.append(world(iu, iv, w))
        return out

    rings.append(make_ring(0, 0))
    rings.append(make_ring(0, protrusion - f))
    for k in range(1, fseg + 1):
        t = (np.pi / 2) * (k / fseg)
        offset = f * (1 - np.cos(t))
        w = (protrusion - f) + f * np.sin(t)
        rings.append(make_ring(offset, w))

    flat = np.array([v for ring in rings for v in ring])
    base = m.append_verts(flat)
    def vid(ri, k): return base + ri * n_pts + (k % n_pts)

    for ri in range(len(rings) - 1):
        for k in range(n_pts):
            m.add_group_face(group, (
                vid(ri,     k    ),
                vid(ri,     k + 1),
                vid(ri + 1, k + 1),
                vid(ri + 1, k    ),
            ))

    # Front cap: triangle fan
    last_ri = len(rings) - 1
    last_pts = np.array(rings[last_ri])
    cu = last_pts[:, 0].mean()
    cv = last_pts[:, 1].mean()
    cw = last_pts[:, 2].mean()
    cidx = m.append_verts(np.array([[cu, cv, cw]]))
    for k in range(n_pts):
        m.add_group_face(group, (
            cidx,
            vid(last_ri, k    ),
            vid(last_ri, k + 1),
        ))
    # Back face (against wall) is omitted -- hidden from view.

    return m


# =====================================================================
# Low-res collider: matches outer silhouette, far fewer polys
# =====================================================================

def _make_low_res_brick(width_studs: int, depth_studs: int,
                        height_plates: int, *,
                        stud_size: float, plate_size: float,
                        edge_fillet_radius: float,
                        with_studs: bool) -> Mesh:
    W = width_studs * stud_size
    D = depth_studs * stud_size
    H = height_plates * plate_size

    fseg = FILLET_SEGMENTS_LO
    cseg = CYLINDER_SEGMENTS_LO
    cornseg = CORNER_SEGMENTS_LO
    e = float(min(edge_fillet_radius, W * 0.3, D * 0.3, H * 0.3))

    mesh = Mesh()
    body = _build_body_shell(W, D, H, e, fseg, cornseg,
                             with_underside=False,
                             wall=0, ceiling=0,
                             group="collider")
    mesh.merge(body)

    if with_studs:
        stud_r = stud_size * 0.30
        stud_h = plate_size * 0.55
        for sx in range(width_studs):
            for sz in range(depth_studs):
                cx = (sx + 0.5) * stud_size
                cz = (sz + 0.5) * stud_size
                stud = _build_stud(cx, H, cz,
                                   radius=stud_r,
                                   height=stud_h,
                                   top_fillet=stud_r * 0.1,
                                   segments=cseg,
                                   fseg=1,
                                   group="collider")
                mesh.merge(stud)
    return mesh
