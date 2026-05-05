"""BrickIt brick and logo template helpers."""
import c4d

from logo_helpers import (
    BRICKGEN_LOGO_FILL_MIN_RATIO,
    normalized_logo_mesh_object as _normalized_logo_mesh_object,
)
from quality_presets import ASSEMBLY_QUALITY_PRESETS, QUALITY_PROXY


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
):
    from brick.brick_geom_hires import make_proxy_collider
    is_smooth_visual = int(bool(force_smooth_top))
    key = (
        "proxy",
        brick_type.width,
        brick_type.depth,
        brick_type.height,
        round(stud_size, 6),
        round(plate_size, 6),
        round(float(inset), 6),
        is_smooth_visual,
    )
    if key in self._mesh_cache:
        return self._mesh_cache[key]
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

