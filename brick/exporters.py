"""Exporters for brick assemblies: 3D preview, JSON, and LDraw."""
import json
from collections import defaultdict
from typing import List, Optional
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from .fitter import BrickPlacement
from .palette import LegoPalette
from .voxelize import STUD_MM, PLATE_MM


# ---------- JSON (MoGraph-ready manifest) ----------

def export_json(
    placements: List[BrickPlacement],
    palette: Optional[LegoPalette],
    path: str,
    *,
    stud_size: float = STUD_MM,
    plate_size: float = PLATE_MM,
):
    """Write a MoGraph-ready manifest.

    Structure:

        {
          "metadata": { stud_size, plate_size, n_placements, ... },
          "brick_types": {
            "<name>": {
              "width_studs", "depth_studs", "height_plates", "ldraw_code",
              "instances": [
                { "position": [x, y, z],   # MESH-FRAME units (ready for cloner)
                  "rotation_y_deg": 0|90,
                  "rgb": [r, g, b],        # raw averaged color
                  "lego_color_idx": int,   # optional, only if palette used
                  "lego_color_name": str,  # optional
                },
                ...
              ]
            },
            ...
          }
        }

    The C4D plugin reads this and builds:
      - one Cloner per brick type
      - a Matrix Object inside each cloner with one matrix per instance
      - a MoGraph Color tag carrying per-clone rgb
      - artist materials read MoGraph Color and apply whatever palette logic
        (direct, gradient, custom-palette lookup, etc.) they want
    """
    by_type = defaultdict(list)
    for p in placements:
        by_type[p.brick.name].append(p)

    out = {
        "metadata": {
            "stud_size": stud_size,
            "plate_size": plate_size,
            "n_placements": len(placements),
            "n_brick_types": len(by_type),
            "coordinate_frame": "mesh-units",
            "y_up": True,
            "palette_assigned": palette is not None,
        },
        "brick_types": {},
    }

    for type_name, plist in by_type.items():
        if not plist:
            continue
        b = plist[0].brick
        instances = []
        for p in plist:
            inst = {
                "position": [
                    float(p.x * stud_size),
                    float(p.y * plate_size),
                    float(p.z * stud_size),
                ],
                "rotation_y_deg": p.rotation_y,
                "rgb": list(p.rgb),
            }
            if palette is not None and p.color_idx >= 0:
                c = palette.color_at(p.color_idx)
                inst["lego_color_idx"] = p.color_idx
                inst["lego_color_name"] = c.name
                inst["lego_color_rgb"] = list(c.rgb)
                inst["ldraw_code"] = c.ldraw_code
            instances.append(inst)
        out["brick_types"][type_name] = {
            "width_studs": b.width,
            "depth_studs": b.depth,
            "height_plates": b.height,
            "ldraw_code": b.ldraw_code,
            "instance_count": len(instances),
            "instances": instances,
        }

    with open(path, "w") as f:
        json.dump(out, f, indent=2)


# ---------- LDraw ----------

# 1 stud  = 20 LDU horizontally
# 1 plate =  8 LDU vertically
# LDraw +Y points DOWN, so we negate Y on export.

def _ldraw_line(p: BrickPlacement, palette: LegoPalette) -> str:
    c = palette.color_at(p.color_idx)
    # Brick origin is the center of footprint horizontally, bottom of brick.
    cx = (p.x + p.w / 2.0) * 20.0
    cz = (p.z + p.d / 2.0) * 20.0
    cy = -p.y * 8.0
    if p.rotation_y == 90:
        a, b, c_, d, e, f, g, h, i = 0, 0, 1, 0, 1, 0, -1, 0, 0
    else:
        a, b, c_, d, e, f, g, h, i = 1, 0, 0, 0, 1, 0, 0, 0, 1
    return (f"1 {c.ldraw_code} {cx:g} {cy:g} {cz:g} "
            f"{a} {b} {c_} {d} {e} {f} {g} {h} {i} "
            f"{p.brick.ldraw_code}.dat")


def export_ldraw(placements: List[BrickPlacement], palette: LegoPalette, path: str,
                 model_name: str = "Brickified"):
    lines = [
        f"0 {model_name}",
        f"0 Name: {model_name}.ldr",
        f"0 Author: brick",
        f"0 !LICENSE Redistributable under CCAL version 2.0",
        f"0 BFC CERTIFY CCW",
        f"",
    ]
    for p in placements:
        lines.append(_ldraw_line(p, palette))
    with open(path, "w") as f:
        f.write("\n".join(lines))


# ---------- preview ----------

def render_preview(
    placements: List[BrickPlacement],
    palette: LegoPalette,
    grid_shape,
    path: str,
    *,
    title: str = "Brickified",
    show_studs: bool = True,
    elev: float = 22,
    azim: float = -55,
    stud_size: float = STUD_MM,
    plate_size: float = PLATE_MM,
):
    """Render a 3D preview. Internal Y is up; we map it to matplotlib's Z."""
    Nx, Ny, Nz = grid_shape
    # local aliases so the rest of the function reads naturally
    SS = stud_size
    PS = plate_size
    fig = plt.figure(figsize=(10, 10), dpi=120)
    ax = fig.add_subplot(111, projection="3d")
    # matplotlib axes:  mpl_X = world X,  mpl_Y = world Z,  mpl_Z = world Y (up)
    ax.set_box_aspect((Nx * SS, Nz * SS, Ny * PS))

    def vXYZ(x, y, z):
        """Map world (x, y, z) with Y-up to matplotlib (x, z, y)."""
        return (x, z, y)

    # Sort placements by world Y (bottom -> top) and outward, so matplotlib's
    # painter's algorithm gives a roughly correct draw order.
    order = sorted(
        range(len(placements)),
        key=lambda i: (placements[i].y,
                       -((placements[i].x + placements[i].w / 2) - Nx / 2) ** 2
                       - ((placements[i].z + placements[i].d / 2) - Nz / 2) ** 2),
    )

    for idx in order:
        p = placements[idx]
        if palette is not None and p.color_idx >= 0:
            rgb = np.array(palette.color_at(p.color_idx).rgb) / 255.0
        else:
            rgb = np.array(p.rgb) / 255.0
        x0, x1 = p.x * SS, (p.x + p.w) * SS
        y0, y1 = p.y * PS, (p.y + p.h) * PS
        z0, z1 = p.z * SS, (p.z + p.d) * SS
        inset = 0.18 * (SS / STUD_MM)  # scale inset with stud size
        x0i, x1i = x0 + inset, x1 - inset
        z0i, z1i = z0 + inset, z1 - inset
        # 6 faces of the brick body
        faces = [
            [vXYZ(x0i, y0, z0i), vXYZ(x1i, y0, z0i),
             vXYZ(x1i, y0, z1i), vXYZ(x0i, y0, z1i)],  # bottom
            [vXYZ(x0i, y1, z0i), vXYZ(x1i, y1, z0i),
             vXYZ(x1i, y1, z1i), vXYZ(x0i, y1, z1i)],  # top
            [vXYZ(x0i, y0, z0i), vXYZ(x1i, y0, z0i),
             vXYZ(x1i, y1, z0i), vXYZ(x0i, y1, z0i)],  # -Z
            [vXYZ(x0i, y0, z1i), vXYZ(x1i, y0, z1i),
             vXYZ(x1i, y1, z1i), vXYZ(x0i, y1, z1i)],  # +Z
            [vXYZ(x0i, y0, z0i), vXYZ(x0i, y0, z1i),
             vXYZ(x0i, y1, z1i), vXYZ(x0i, y1, z0i)],  # -X
            [vXYZ(x1i, y0, z0i), vXYZ(x1i, y0, z1i),
             vXYZ(x1i, y1, z1i), vXYZ(x1i, y1, z0i)],  # +X
        ]
        body = Poly3DCollection(faces,
                                facecolor=rgb,
                                edgecolor=rgb * 0.4,
                                linewidth=0.4)
        ax.add_collection3d(body)

        if show_studs:
            stud_r = SS * 0.30
            stud_h = PS * 0.85
            theta = np.linspace(0, 2 * np.pi, 14)
            for sx in range(p.w):
                for sz in range(p.d):
                    cx = (p.x + sx + 0.5) * SS
                    cz = (p.z + sz + 0.5) * SS
                    ring_x = cx + stud_r * np.cos(theta)
                    ring_z = cz + stud_r * np.sin(theta)
                    bot = [vXYZ(rx, y1, rz) for rx, rz in zip(ring_x, ring_z)]
                    top = [vXYZ(rx, y1 + stud_h, rz) for rx, rz in zip(ring_x, ring_z)]
                    side = [[bot[k], bot[k + 1], top[k + 1], top[k]]
                            for k in range(len(theta) - 1)]
                    cap = [top]
                    ax.add_collection3d(Poly3DCollection(
                        side + cap,
                        facecolor=rgb * 0.92,
                        edgecolor=rgb * 0.45,
                        linewidth=0.2,
                    ))

    # axes limits in (mpl_x, mpl_y, mpl_z) = (world_x, world_z, world_y)
    ax.set_xlim(0, Nx * SS)
    ax.set_ylim(0, Nz * SS)
    ax.set_zlim(0, Ny * PS)
    ax.set_xlabel("X")
    ax.set_ylabel("Z")
    ax.set_zlabel("Y -- up")
    ax.set_title(title)
    ax.view_init(elev=elev, azim=azim)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight")
    plt.close(fig)
