"""BrickIt brick and logo template helpers."""
import c4d

from logo_helpers import (
    BRICKGEN_LOGO_FILL_MIN_RATIO,
    normalized_logo_mesh_object as _normalized_logo_mesh_object,
)
from quality_presets import ASSEMBLY_QUALITY_PRESETS, QUALITY_PROXY


def _make_simple_cube_proxy(
    width_studs,
    depth_studs,
    height_plates,
    *,
    stud_size,
    plate_size,
):
    """Build the simplest possible cube mesh for a brick proxy: 8 verts,
    6 quads, no studs, fully welded, watertight. Tiles flush with
    adjacent simplified proxies because there's no stud sticking up.

    Coordinate system: low-corner-origin, matching the existing studded
    proxy template convention. Vertices span 0..w in X, 0..h in Y,
    0..d in Z. The proxy build pipeline calls _center_template_mesh on
    the resulting mesh to shift it to center-pivot before placement.
    """
    # Imports inside the function: numpy / brick.mesh aren't guaranteed
    # to be on sys.path at plugin-registration time. Keeping these out
    # of module load avoids a registration failure if the path setup
    # changes.
    import numpy as np
    from brick.mesh import Mesh
    w = float(width_studs) * float(stud_size)
    d = float(depth_studs) * float(stud_size)
    h = float(height_plates) * float(plate_size)
    x0, x1 = 0.0, w
    y0, y1 = 0.0, h
    z0, z1 = 0.0, d
    # 8 corners. Index layout:
    #   0:(x0,y0,z0) 1:(x1,y0,z0) 2:(x1,y0,z1) 3:(x0,y0,z1)
    #   4:(x0,y1,z0) 5:(x1,y1,z0) 6:(x1,y1,z1) 7:(x0,y1,z1)
    vertices = np.array([
        [x0, y0, z0],
        [x1, y0, z0],
        [x1, y0, z1],
        [x0, y0, z1],
        [x0, y1, z0],
        [x1, y1, z0],
        [x1, y1, z1],
        [x0, y1, z1],
    ], dtype=np.float64)
    # 6 quad faces, CCW from outside.
    faces = [
        (0, 3, 2, 1),  # bottom
        (4, 5, 6, 7),  # top
        (0, 1, 5, 4),  # front (-Z)
        (2, 3, 7, 6),  # back (+Z)
        (0, 4, 7, 3),  # left (-X)
        (1, 2, 6, 5),  # right (+X)
    ]
    return Mesh(vertices=vertices, faces=faces)


def _get_template_mesh(
    self,
    brick_type,
    quality,
    stud_size,
    plate_size,
    *,
    smooth_plate_visual=True,
    force_smooth_top=False,
):
    from brick.brick_geom_hires import make_brick_hires, make_proxy_collider
    is_smooth_visual = int(
        bool(
            force_smooth_top
            or (
                getattr(brick_type, "height", 0) == 1
                and bool(smooth_plate_visual)
            )
        )
    )
    if quality == QUALITY_PROXY:
        key = (
            "proxy",
            brick_type.width,
            brick_type.depth,
            brick_type.height,
            round(stud_size, 6),
            round(plate_size, 6),
            is_smooth_visual,
        )
        if key in self._mesh_cache:
            return self._mesh_cache[key]
        # V5 watertight OBJ-based proxy first; falls back to the
        # procedural collider when V5 doesn't cover the request.
        mesh = None
        try:
            from .brickit_obj_proxy import is_supported, synthesize_proxy
            if is_supported(brick_type, smooth=bool(is_smooth_visual)):
                mesh = synthesize_proxy(
                    brick_type,
                    smooth=bool(is_smooth_visual),
                    stud_size=float(stud_size),
                    plate_size=float(plate_size),
                )
        except Exception as _exc:
            try:
                from plugin_bootstrap import brick_log as _bl
                _bl("[brick] OBJ proxy: synth failed: {0}".format(_exc))
            except Exception:
                pass
            mesh = None
        if mesh is None:
            mesh = make_proxy_collider(
                brick_type.width,
                brick_type.depth,
                brick_type.height,
                stud_size=stud_size,
                plate_size=plate_size,
                inset=0.0,
                with_studs=not bool(is_smooth_visual),
            )
        self._mesh_cache[key] = mesh
        return mesh

    key = (brick_type.width, brick_type.depth, brick_type.height,
           quality, round(stud_size, 6), round(plate_size, 6),
           is_smooth_visual)
    if key in self._mesh_cache:
        return self._mesh_cache[key]
    kwargs = dict(ASSEMBLY_QUALITY_PRESETS[quality])
    kwargs["stud_size"] = stud_size
    kwargs["plate_size"] = plate_size
    if is_smooth_visual:
        kwargs["with_studs"] = False
    SCALE_REF = 8.0
    s = float(stud_size) / SCALE_REF
    SCALED_DEFAULTS = {
        "body_fillet_radius": 0.30,
        "stud_fillet_radius": 0.20,
        "tube_fillet_radius": 0.20,
        "rib_fillet_radius": 0.12,
        "underside_wall_thickness": 1.0,
        "underside_ceiling_thickness": 1.2,
    }
    for k, v in SCALED_DEFAULTS.items():
        base = kwargs.get(k, v)
        kwargs[k] = base * s
    mesh = make_brick_hires(
        brick_type.width, brick_type.depth, brick_type.height, **kwargs
    )
    self._mesh_cache[key] = mesh
    return mesh


def _get_proxy_template_mesh(
    self,
    brick_type,
    stud_size,
    plate_size,
    *,
    inset=0.0,
    force_smooth_top=False,
    simplified=False,
):
    from brick.brick_geom_hires import make_proxy_collider
    is_smooth_visual = int(bool(force_smooth_top))
    is_simplified = int(bool(simplified))
    key = (
        "proxy",
        brick_type.width,
        brick_type.depth,
        brick_type.height,
        round(stud_size, 6),
        round(plate_size, 6),
        round(float(inset), 6),
        is_smooth_visual,
        is_simplified,
    )
    if key in self._mesh_cache:
        return self._mesh_cache[key]
    # Simplified proxy: a flat 6-quad cube with no studs. Skip the OBJ
    # synthesis and procedural collider paths.
    if simplified:
        mesh = _make_simple_cube_proxy(
            int(brick_type.width),
            int(brick_type.depth),
            int(brick_type.height),
            stud_size=float(stud_size),
            plate_size=float(plate_size),
        )
        self._mesh_cache[key] = mesh
        return mesh
    # V5 watertight OBJ-based proxy first (matches the path used by
    # _get_template_mesh for QUALITY_PROXY).  V5 doesn't model the
    # procedural inset offset, so skip V5 when inset is non-zero.
    mesh = None
    if abs(float(inset)) < 1e-9:
        try:
            from .brickit_obj_proxy import is_supported, synthesize_proxy
            if is_supported(brick_type, smooth=bool(is_smooth_visual)):
                mesh = synthesize_proxy(
                    brick_type,
                    smooth=bool(is_smooth_visual),
                    stud_size=float(stud_size),
                    plate_size=float(plate_size),
                )
        except Exception as _exc:
            try:
                from plugin_bootstrap import brick_log as _bl
                _bl("[brick] OBJ proxy: Create Proxies synth failed: {0}".format(_exc))
            except Exception:
                pass
            mesh = None
    if mesh is None:
        mesh = make_proxy_collider(
            brick_type.width,
            brick_type.depth,
            brick_type.height,
            stud_size=stud_size,
            plate_size=plate_size,
            inset=inset,
            with_studs=not bool(is_smooth_visual),
        )
    self._mesh_cache[key] = mesh
    return mesh


def _normalized_logo_source_object(
    self,
    source_obj,
    doc,
    stud_size,
    plate_size,
    *,
    diameter_ratio=BRICKGEN_LOGO_FILL_MIN_RATIO,
    height_ratio=0.06,
    blend=1.0,
):
    """Bake and normalize a C4D mesh logo so its origin is stud center/top."""
    return _normalized_logo_mesh_object(
        source_obj,
        doc,
        stud_size,
        plate_size,
        diameter_ratio=diameter_ratio,
        height_ratio=height_ratio,
        blend=blend,
    )

def _get_logo_template_obj(self, params, doc, stud_size, plate_size):
    from logo_helpers import _logo_log
    logo_enabled = bool(params.get("logo_enabled"))
    source_obj = params.get("logo_source")
    if not logo_enabled:
        _logo_log("BrickIt: logo_enabled=False, skipping logo template")
        return None
    if source_obj is None:
        _logo_log("BrickIt: logo_enabled=True but logo_source is None — link did not resolve")
        return None
    diameter = float(params.get("logo_diameter", BRICKGEN_LOGO_FILL_MIN_RATIO))
    height = float(params.get("logo_height", 0.06))
    blend = float(params.get("logo_blend", 1.0))
    key = (
        "source",
        self._source_state_key(source_obj),
        round(float(stud_size), 6),
        round(float(plate_size), 6),
        round(diameter, 4),
        round(height, 4),
        round(blend, 4),
    )
    if key not in self._logo_cache:
        baked = self._normalized_logo_source_object(
            source_obj,
            doc,
            stud_size,
            plate_size,
            diameter_ratio=diameter,
            height_ratio=height,
            blend=blend,
        )
        # Only store successful bakes. Caching None on a transient bake
        # failure (e.g. doc=None during a nested rebuild) would lock the
        # logo off until the user happened to land back on a previously-
        # cached parameter combination.
        if baked is not None:
            self._logo_cache[key] = baked
        _logo_log(
            "BrickIt: baked logo template ({0}) source={1!r} diameter={2:.3f} height={3:.3f}".format(
                "ok" if baked is not None else "FAILED",
                source_obj.GetName() if source_obj is not None else None,
                diameter,
                height,
            )
        )
    template = self._logo_cache.get(key)
    if template is not None:
        return template.GetClone(c4d.COPYFLAGS_NONE)
    _logo_log("BrickIt: no logo template available for current params (bake failed)")
    return None

