"""BrickIt MoGraph handoff construction."""
from types import SimpleNamespace

import c4d

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from logo_helpers import (
    BRICKGEN_LOGO_DEFAULT_SINK,
    apply_logo_quarter_turn as _apply_logo_quarter_turn,
)
from mesh_bridge import mesh_to_polygon_object
from plugin_bootstrap import (
    brick_log as _brick_log,
    ensure_brick_on_path as _ensure_brick_on_path,
)


def _create_mograph_handoff(self, op):
    """Create a real scene-level MoGraph rig from the current BrickIt fit."""
    _ensure_brick_on_path()
    doc = op.GetDocument()
    source_obj = op[BRICKIFYASSEMBLY_SOURCE]
    if doc is None or source_obj is None:
        _brick_log("[brick] MoGraph handoff: no document/source object")
        return False

    params = self._resolve_params(op, source_obj)
    if not self._refit_if_needed(op, doc, params):
        _brick_log("[brick] MoGraph handoff: fit is not available")
        return False
    placements = list(self._fit_placements or [])
    info = self._fit_info or {}
    if not placements or not info:
        _brick_log("[brick] MoGraph handoff: no placements to hand off")
        return False

    fracture_type = (
        getattr(c4d, "Omgfracture", None)
        or getattr(c4d, "Omograph_fracture", None)
        or 1018791
    )
    root = c4d.BaseObject(c4d.Onull)
    src_name = source_obj.GetName() if source_obj is not None else "mesh"
    root.SetName("BrickIt_MoGraph_{0}".format(src_name))

    templates_root = c4d.BaseObject(c4d.Onull)
    templates_root.SetName("BRICK_LIBRARY")
    park_m = c4d.Matrix()
    park_m.off = c4d.Vector(0.0, 1.0e9, 0.0)
    templates_root.SetMl(park_m)
    templates_root.InsertUnder(root)

    fracture = c4d.BaseObject(fracture_type)
    if fracture is None:
        _brick_log("[brick] MoGraph handoff: could not create Fracture object")
        return False
    fracture.SetName("bricks_mograph_fracture")
    try:
        fracture[c4d.MGFRACTUREOBJECT_MODE] = c4d.MGFRACTUREOBJECT_MODE_NONE
    except Exception:
        pass
    fracture.InsertUnder(root)

    stud_size = info.get("stud_size", 8.0)
    plate_size = info.get("plate_size", 3.2)
    origin = info.get("origin")
    if origin is None:
        _brick_log("[brick] MoGraph handoff: fit origin is missing")
        return False
    quality = params["quality"]
    smooth_plate_visual = bool(params.get("surface_only_plates"))
    mi_mode = getattr(c4d, "INSTANCEOBJECT_RENDERINSTANCE_MODE_RENDERINSTANCE", 1)

    type_to_template = {}
    logo_template = self._get_logo_template_obj(params, doc, stud_size, plate_size)
    logo_rotation = int(params.get("logo_rotation", 0) or 0) % 4
    logo_sink = max(0.0, min(0.05, float(params.get("logo_sink", BRICKGEN_LOGO_DEFAULT_SINK))))
    logo_surface_bias = -float(plate_size) * logo_sink

    def _brick_has_template_logos(brick_type, smooth_top=False):
        if logo_template is None:
            return False
        if bool(smooth_top):
            return False
        if int(getattr(brick_type, "height", 0)) == 1 and smooth_plate_visual:
            return False
        return True

    def _add_template_logo_children(proto, brick_type, smooth_top=False):
        if not _brick_has_template_logos(brick_type, smooth_top=smooth_top):
            return 0
        logos_root = c4d.BaseObject(c4d.Onull)
        logos_root.SetName("stud_logos")
        logos_root.InsertUnder(proto)
        top_y = (
            float(brick_type.height) * float(plate_size)
            + float(plate_size) * 0.55
            + logo_surface_bias
        )
        count = 0
        for sx in range(int(brick_type.width)):
            for sz in range(int(brick_type.depth)):
                logo_obj = logo_template.GetClone(c4d.COPYFLAGS_NONE)
                if logo_obj is None:
                    continue
                logo_obj.SetName("stud_logo")
                m = c4d.Matrix()
                m.off = c4d.Vector(
                    float((sx + 0.5) * stud_size),
                    float(top_y),
                    float((sz + 0.5) * stud_size),
                )
                _apply_logo_quarter_turn(m, logo_rotation)
                logo_obj.SetMl(m)
                logo_obj.InsertUnder(logos_root)
                count += 1
        return count

    def _get_template_obj(brick_type, smooth_top=False):
        tkey = (
            brick_type.width,
            brick_type.depth,
            brick_type.height,
            int(bool(smooth_top)),
        )
        if tkey in type_to_template:
            return type_to_template[tkey]
        name = "brick_{0}x{1}".format(
            int(brick_type.width),
            int(brick_type.depth),
        )
        if int(brick_type.height) != 3:
            name += "_h{0}".format(int(brick_type.height))
        if bool(smooth_top):
            name += "_smooth"

        mesh = self._get_template_mesh(
            brick_type,
            quality,
            stud_size,
            plate_size,
            smooth_plate_visual=smooth_plate_visual,
            force_smooth_top=bool(smooth_top),
        )
        proto = c4d.BaseObject(c4d.Onull)
        proto.SetName(name)
        mesh_obj = mesh_to_polygon_object(
            mesh,
            name="mesh_{0}x{1}x{2}p".format(
                brick_type.width, brick_type.depth, brick_type.height
            ),
        )
        mesh_obj.InsertUnder(proto)
        _add_template_logo_children(proto, brick_type, smooth_top=smooth_top)
        proto.InsertUnder(templates_root)
        type_to_template[tkey] = proto
        return proto

    # Handoff should preserve the fitted brick types exactly. The shared
    # template generator already makes height-1 plate templates studless
    # when Smooth Top Surfaces is enabled; do not force taller bricks to use
    # studless templates here.
    smooth_top_by_obj = {}

    from types import SimpleNamespace

    doc.StartUndo()
    try:
        try:
            root.InsertAfter(op)
        except Exception:
            doc.InsertObject(root)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, root)

        created_instances = 0
        logo_count = 0
        for p in placements:
            if p.rotation_y == 90:
                template_brick = SimpleNamespace(
                    width=p.brick.depth,
                    depth=p.brick.width,
                    height=p.brick.height,
                )
            else:
                template_brick = p.brick
            smooth_top = bool(smooth_top_by_obj.get(id(p), False))
            template = _get_template_obj(template_brick, smooth_top=smooth_top)
            if _brick_has_template_logos(template_brick, smooth_top=smooth_top):
                logo_count += int(template_brick.width) * int(template_brick.depth)

            inst = c4d.BaseObject(c4d.Oinstance)
            inst.SetName(
                "brick_{0}x{1}x{2}p_{3:04d}".format(
                    int(template_brick.width),
                    int(template_brick.depth),
                    int(template_brick.height),
                    created_instances,
                )
            )
            inst[c4d.INSTANCEOBJECT_LINK] = template
            try:
                inst[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = int(mi_mode)
            except Exception:
                pass
            m = c4d.Matrix()
            m.off = c4d.Vector(
                float(origin[0] + p.x * stud_size),
                float(origin[1] + p.y * plate_size),
                float(origin[2] + p.z * stud_size),
            )
            inst.SetMl(m)
            inst.InsertUnder(fracture)
            created_instances += 1

        doc.SetActiveObject(fracture)
        c4d.EventAdd()
        _brick_log(
            "[brick] MoGraph handoff: created Fracture rig, bricks={0}, logos={1}, library_items={2}".format(
                created_instances,
                logo_count,
                len(type_to_template),
            )
        )
    finally:
        doc.EndUndo()
    return True

