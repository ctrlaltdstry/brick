"""SVG -> extruded quad mesh, for placing logos on top of LEGO studs.

Supports a useful subset of SVG geometry:
    <path>     with M, L, H, V, C, S, Q, T, Z commands (relative + absolute)
    <polygon>  points="x,y x,y ..."
    <polyline> same
    <rect>     x, y, width, height (corners are sharp; rx/ry ignored)
    <circle>   cx, cy, r           (sampled to a polyline)
    <ellipse>  cx, cy, rx, ry      (sampled to a polyline)

What it intentionally doesn't do (for a prototype):
    - holes / sub-paths / fill-rule. Each <path> generates one polyline
      per Move command. Letters with holes (O, A, e, etc.) will fill the
      hole. Easy to add: detect winding and use a 2D triangulator with
      hole support; punted for now.
    - bezier subdivision is fixed at N=12 segments per curve; good enough
      for typical logos at small scale.
    - styling (fill, stroke, color) ignored. The artist colors logos in C4D.

Output coordinate convention: SVG y-axis points down, so we negate Y to
land in the artist's standard +Y-up frame. The logo lies in the X-Z
plane after extrusion; height goes along Y.
"""
import re
import xml.etree.ElementTree as ET
from typing import List, Tuple
import numpy as np
from .mesh import Mesh


# ---------- SVG path parsing ----------

_PATH_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")
_BEZIER_SAMPLES = 12


def _path_tokens(d: str):
    return [t for t in _PATH_TOKEN.findall(d) if t]


def _cubic(p0, p1, p2, p3, n=_BEZIER_SAMPLES):
    ts = np.linspace(0, 1, n + 1)[1:]
    pts = []
    for t in ts:
        u = 1 - t
        pts.append(u*u*u*p0 + 3*u*u*t*p1 + 3*u*t*t*p2 + t*t*t*p3)
    return pts


def _quadratic(p0, p1, p2, n=_BEZIER_SAMPLES):
    ts = np.linspace(0, 1, n + 1)[1:]
    pts = []
    for t in ts:
        u = 1 - t
        pts.append(u*u*p0 + 2*u*t*p1 + t*t*p2)
    return pts


def _parse_path(d: str) -> List[List[Tuple[float, float]]]:
    """Return a list of polylines (each a list of (x, y) tuples).
    Each Move (M/m) starts a new polyline."""
    tokens = _path_tokens(d)
    i = 0
    polylines: List[List[Tuple[float, float]]] = []
    cur: List[Tuple[float, float]] = []
    cx, cy = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    last_cmd = None
    last_ctrl = None  # for S / T continuation

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
        else:
            # implicit repeat of previous command
            cmd = last_cmd
        last_cmd = cmd
        rel = cmd.islower()
        c = cmd.upper()

        if c == "M":
            x = num(); y = num()
            if rel: x += cx; y += cy
            if cur:
                polylines.append(cur)
            cur = [(x, y)]
            cx, cy = x, y
            start_x, start_y = x, y
            last_cmd = "l" if rel else "L"  # subsequent coord pairs after M are L
            last_ctrl = None
        elif c == "L":
            x = num(); y = num()
            if rel: x += cx; y += cy
            cur.append((x, y))
            cx, cy = x, y
            last_ctrl = None
        elif c == "H":
            x = num()
            if rel: x += cx
            cur.append((x, cy))
            cx = x
            last_ctrl = None
        elif c == "V":
            y = num()
            if rel: y += cy
            cur.append((cx, y))
            cy = y
            last_ctrl = None
        elif c == "C":
            x1 = num(); y1 = num()
            x2 = num(); y2 = num()
            x = num();  y = num()
            if rel: x1 += cx; y1 += cy; x2 += cx; y2 += cy; x += cx; y += cy
            p0 = np.array([cx, cy])
            for p in _cubic(p0, np.array([x1, y1]),
                            np.array([x2, y2]), np.array([x, y])):
                cur.append((float(p[0]), float(p[1])))
            cx, cy = x, y
            last_ctrl = (x2, y2)
        elif c == "S":
            x2 = num(); y2 = num()
            x = num();  y = num()
            if rel: x2 += cx; y2 += cy; x += cx; y += cy
            if last_ctrl:
                x1 = 2*cx - last_ctrl[0]; y1 = 2*cy - last_ctrl[1]
            else:
                x1, y1 = cx, cy
            p0 = np.array([cx, cy])
            for p in _cubic(p0, np.array([x1, y1]),
                            np.array([x2, y2]), np.array([x, y])):
                cur.append((float(p[0]), float(p[1])))
            cx, cy = x, y
            last_ctrl = (x2, y2)
        elif c == "Q":
            x1 = num(); y1 = num()
            x = num();  y = num()
            if rel: x1 += cx; y1 += cy; x += cx; y += cy
            p0 = np.array([cx, cy])
            for p in _quadratic(p0, np.array([x1, y1]), np.array([x, y])):
                cur.append((float(p[0]), float(p[1])))
            cx, cy = x, y
            last_ctrl = (x1, y1)
        elif c == "T":
            x = num(); y = num()
            if rel: x += cx; y += cy
            if last_ctrl:
                x1 = 2*cx - last_ctrl[0]; y1 = 2*cy - last_ctrl[1]
            else:
                x1, y1 = cx, cy
            p0 = np.array([cx, cy])
            for p in _quadratic(p0, np.array([x1, y1]), np.array([x, y])):
                cur.append((float(p[0]), float(p[1])))
            cx, cy = x, y
            last_ctrl = (x1, y1)
        elif c == "Z":
            if cur:
                # close back to start
                if cur[-1] != (start_x, start_y):
                    cur.append((start_x, start_y))
                polylines.append(cur)
                cur = []
            cx, cy = start_x, start_y
            last_ctrl = None
            last_cmd = None
        # arcs (A/a) intentionally not supported -- log + skip if they appear

    if cur:
        polylines.append(cur)
    return polylines


def parse_svg(path: str) -> Tuple[List[List[Tuple[float, float]]],
                                  Tuple[float, float, float, float]]:
    """Parse an SVG file into a list of closed polylines plus its viewBox.

    Returns (polylines, viewBox=(min_x, min_y, width, height)).
    """
    tree = ET.parse(path)
    root = tree.getroot()
    # strip the xmlns prefix if present
    def localname(tag):
        return tag.split("}", 1)[-1] if "}" in tag else tag

    # viewBox
    vb_attr = root.get("viewBox")
    if vb_attr:
        parts = vb_attr.replace(",", " ").split()
        vb = (float(parts[0]), float(parts[1]),
              float(parts[2]), float(parts[3]))
    else:
        w = float(root.get("width", "100").rstrip("px"))
        h = float(root.get("height", "100").rstrip("px"))
        vb = (0.0, 0.0, w, h)

    polylines: List[List[Tuple[float, float]]] = []

    def walk(node):
        for child in node:
            tag = localname(child.tag)
            if tag == "path":
                d = child.get("d", "")
                if d:
                    polylines.extend(_parse_path(d))
            elif tag == "polygon" or tag == "polyline":
                pts = child.get("points", "").replace(",", " ").split()
                pl = [(float(pts[i]), float(pts[i + 1]))
                      for i in range(0, len(pts) - 1, 2)]
                if tag == "polygon" and pl and pl[0] != pl[-1]:
                    pl.append(pl[0])
                polylines.append(pl)
            elif tag == "rect":
                x = float(child.get("x", 0))
                y = float(child.get("y", 0))
                w = float(child.get("width", 0))
                h = float(child.get("height", 0))
                polylines.append([(x, y), (x + w, y),
                                  (x + w, y + h), (x, y + h), (x, y)])
            elif tag == "circle":
                cx = float(child.get("cx", 0))
                cy = float(child.get("cy", 0))
                r = float(child.get("r", 0))
                n = 64
                pl = [(cx + r * np.cos(t), cy + r * np.sin(t))
                      for t in np.linspace(0, 2 * np.pi, n)]
                polylines.append(pl)
            elif tag == "ellipse":
                cx = float(child.get("cx", 0))
                cy = float(child.get("cy", 0))
                rx = float(child.get("rx", 0))
                ry = float(child.get("ry", 0))
                n = 64
                pl = [(cx + rx * np.cos(t), cy + ry * np.sin(t))
                      for t in np.linspace(0, 2 * np.pi, n)]
                polylines.append(pl)
            elif tag == "g":
                walk(child)

    walk(root)
    # filter out empty / open polylines that don't enclose area
    polylines = [p for p in polylines if len(p) >= 3]
    return polylines, vb


# ---------- extrusion ----------

def extrude_polylines(
    polylines: List[List[Tuple[float, float]]],
    *,
    bbox: Tuple[float, float, float, float],
    target_diameter: float,
    extrusion_height: float,
    base_y: float = 0.0,
    flip_y: bool = True,
) -> Mesh:
    """Take 2D polylines from SVG and produce an extruded quad mesh.

    The combined logo is fit into a circle of `target_diameter` (so it
    sits nicely on top of a stud). Each polyline becomes one polygon
    island in the output ('logo' group, no per-island sub-grouping).

    Uses n-gon top + n-gon bottom + side quads. Pure quads on the sides
    (and n-gons that subdivide cleanly on top/bottom).
    """
    m = Mesh()
    if not polylines:
        return m

    min_x, min_y, w, h = bbox
    if w <= 0 or h <= 0:
        # recompute from points
        all_pts = np.array([p for pl in polylines for p in pl])
        min_x, min_y = all_pts.min(axis=0)
        max_x, max_y = all_pts.max(axis=0)
        w, h = max_x - min_x, max_y - min_y

    fit_scale = target_diameter / max(w, h)

    for pl in polylines:
        pts = np.array(pl)
        # SVG y-down -> world y-up (we use Y for up, X-Z for ground plane)
        # so the logo sits in X/Z plane; sign-flip y if asked
        # Center, scale, then place in X-Z plane.
        cx2 = min_x + w / 2.0
        cy2 = min_y + h / 2.0
        local_x = (pts[:, 0] - cx2) * fit_scale
        local_z = (pts[:, 1] - cy2) * fit_scale * (-1.0 if flip_y else 1.0)
        # Avoid duplicate closing point
        if len(local_x) > 1 and local_x[0] == local_x[-1] and local_z[0] == local_z[-1]:
            local_x = local_x[:-1]
            local_z = local_z[:-1]
        n = len(local_x)
        if n < 3:
            continue

        # bottom ring + top ring
        bottom = np.stack([local_x,
                           np.full(n, base_y),
                           local_z], axis=1)
        top = bottom.copy()
        top[:, 1] = base_y + extrusion_height

        base_idx = m.append_verts(np.vstack([bottom, top]))
        bot = lambda k: base_idx + (k % n)
        topv = lambda k: base_idx + n + (k % n)

        # bottom n-gon (faces DOWN; reverse winding)
        m.add_group_face("logo", tuple(bot(n - 1 - k) for k in range(n)))
        # top n-gon (faces UP)
        m.add_group_face("logo", tuple(topv(k) for k in range(n)))
        # side quads
        for k in range(n):
            m.add_group_face("logo", (
                bot(k), bot(k + 1), topv(k + 1), topv(k),
            ))

    return m


# ---------- a built-in test logo so the demo works without an .svg file ----------

BUILTIN_LOGOS = {
    "star": """<svg viewBox="0 0 100 100">
  <polygon points="50,5 61,38 95,38 67,58 78,90 50,70 22,90 33,58 5,38 39,38" />
</svg>""",
    "lego_text": """<svg viewBox="0 0 220 70">
  <!-- L -->
  <polygon points="10,10 25,10 25,55 50,55 50,65 10,65"/>
  <!-- E -->
  <polygon points="60,10 100,10 100,20 75,20 75,32 95,32 95,42 75,42 75,55 100,55 100,65 60,65"/>
  <!-- G -->
  <path d="M 110,10 L 150,10 L 150,30 L 138,30 L 138,20 L 122,20
           L 122,55 L 138,55 L 138,42 L 130,42 L 130,32 L 150,32
           L 150,65 L 110,65 Z"/>
  <!-- O -->
  <path d="M 160,10 L 210,10 L 210,65 L 160,65 Z
           M 172,20 L 198,20 L 198,55 L 172,55 Z" fill-rule="evenodd"/>
</svg>""",
}


def make_builtin_logo(name: str = "star",
                      target_diameter: float = 4.0,
                      extrusion_height: float = 0.4,
                      base_y: float = 0.0) -> Mesh:
    """Return a Mesh with the named built-in logo."""
    import tempfile, os
    if name not in BUILTIN_LOGOS:
        raise KeyError(f"unknown built-in logo: {name}")
    tmpf = tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False)
    tmpf.write(BUILTIN_LOGOS[name])
    tmpf.close()
    try:
        polylines, vb = parse_svg(tmpf.name)
    finally:
        os.unlink(tmpf.name)
    return extrude_polylines(polylines, bbox=vb,
                             target_diameter=target_diameter,
                             extrusion_height=extrusion_height,
                             base_y=base_y)
