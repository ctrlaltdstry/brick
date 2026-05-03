"""Brick single-brick ObjectData plugin."""
import c4d
from c4d import plugins

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.
from logo_helpers import (
    BRICKGEN_LOGO_DEFAULT_SINK,
    BRICKGEN_LOGO_FILL_UI_DEFAULT,
    apply_logo_quarter_turn,
    logo_fill_to_diameter_ratio,
    logo_link_identity_key,
    normalized_logo_mesh_object,
)
from mesh_bridge import build_brick, mesh_to_polygon_object
from plugin_bootstrap import ensure_brick_on_path, open_user_manual
from quality_presets import QUALITY_PRESETS
from source_geometry import generator_document


BRICKGEN_DEFAULT_STUD_SIZE = 8.0
BRICKGEN_DEFAULT_PLATE_SIZE = 3.2
BRICKGEN_LOGO_STUD_HEIGHT_RATIO = 0.55


class BrickGen(plugins.ObjectData):
    """C4D ObjectData generator: Width / Depth / Height / Type / Quality."""

    def __init__(self):
        super().__init__()
        self._cache_key = None
        self._cache_obj = None
        self._logo_cache = {}

    def Init(self, op, isCloneInit=False):
        op[BRICKGENERATOR_WIDTH] = 2
        op[BRICKGENERATOR_DEPTH] = 4
        op[BRICKGENERATOR_HEIGHT] = 3
        op[BRICKGENERATOR_TYPE] = BRICKGENERATOR_TYPE_BRICK
        op[BRICKGENERATOR_QUALITY] = BRICKGENERATOR_QUALITY_STANDARD
        op[BRICKGENERATOR_ENABLE_LOGO] = False
        op[BRICKGENERATOR_LOGO_SOURCE] = None
        op[BRICKGENERATOR_LOGO_DIAMETER] = BRICKGEN_LOGO_FILL_UI_DEFAULT
        op[BRICKGENERATOR_LOGO_HEIGHT] = 0.06
        op[BRICKGENERATOR_LOGO_ROTATION] = 0
        op[BRICKGENERATOR_LOGO_BLEND] = 1.0
        op[BRICKGENERATOR_LOGO_SINK] = BRICKGEN_LOGO_DEFAULT_SINK
        self._cache_key = None
        self._cache_obj = None
        return True

    def Free(self, node):
        self._logo_cache = {}

    def Message(self, op, msg_type, data):
        if msg_type == c4d.MSG_DESCRIPTION_COMMAND:
            try:
                desc_id = data["id"][0].id
            except Exception:
                desc_id = -1
            if desc_id == BRICKGENERATOR_OPEN_USER_MANUAL:
                try:
                    open_user_manual()
                except Exception:
                    pass
            return True
        if msg_type == c4d.MSG_DESCRIPTION_POSTSETPARAMETER:
            try:
                desc_id = -1
                try:
                    desc_id = data["descid"][0].id
                except Exception:
                    try:
                        desc_id = data["id"][0].id
                    except Exception:
                        desc_id = -1
                if desc_id == BRICKGENERATOR_TYPE:
                    op.SetDirty(c4d.DIRTYFLAGS_DATA)
                    c4d.EventAdd()
                elif desc_id == BRICKGENERATOR_LOGO_SOURCE:
                    try:
                        if op[BRICKGENERATOR_LOGO_SOURCE] is not None:
                            op[BRICKGENERATOR_ENABLE_LOGO] = True
                    except Exception:
                        pass
                    op.SetDirty(c4d.DIRTYFLAGS_DATA)
                    c4d.EventAdd()
            except Exception:
                pass
        return True

    def GetDEnabling(self, op, desc_id, t_data, flags, itemdesc):
        """Disable Height control while Type=Plate."""
        try:
            pid = desc_id[0].id
        except Exception:
            try:
                pid = int(desc_id)
            except Exception:
                return True
        try:
            piece_type = int(op[BRICKGENERATOR_TYPE] or BRICKGENERATOR_TYPE_BRICK)
        except Exception:
            piece_type = BRICKGENERATOR_TYPE_BRICK
        is_plate = piece_type == BRICKGENERATOR_TYPE_PLATE

        if pid == BRICKGENERATOR_HEIGHT:
            return not is_plate

        if pid == BRICKGENERATOR_ENABLE_LOGO:
            return not is_plate

        if pid in (
            BRICKGENERATOR_LOGO_SOURCE,
            BRICKGENERATOR_LOGO_ROTATION,
            BRICKGENERATOR_LOGO_DIAMETER,
            BRICKGENERATOR_LOGO_HEIGHT,
            BRICKGENERATOR_LOGO_BLEND,
            BRICKGENERATOR_LOGO_SINK,
        ):
            if is_plate:
                return False
            try:
                return bool(op[BRICKGENERATOR_ENABLE_LOGO])
            except Exception:
                return False

        return True

    def GetVirtualObjects(self, op, hh):
        ensure_brick_on_path()

        try:
            import brick.mesh  # noqa: F401
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Failed to import brick. Make sure the brick "
                "package is next to c4d_brick_generator.pyp (or set "
                "BRICK_ROOT) and that numpy/scipy are installed in "
                "Cinema 4D's Python environment."
            ) from exc

        width = max(1, int(op[BRICKGENERATOR_WIDTH]))
        depth = max(1, int(op[BRICKGENERATOR_DEPTH]))
        height = max(1, int(op[BRICKGENERATOR_HEIGHT]))
        piece_type = int(op[BRICKGENERATOR_TYPE] or BRICKGENERATOR_TYPE_BRICK)
        if piece_type not in (BRICKGENERATOR_TYPE_BRICK, BRICKGENERATOR_TYPE_PLATE):
            piece_type = BRICKGENERATOR_TYPE_BRICK
        quality = int(op[BRICKGENERATOR_QUALITY])
        if quality not in QUALITY_PRESETS:
            quality = BRICKGENERATOR_QUALITY_STANDARD

        logo_enabled = False
        logo_source = None
        logo_rotation = 0
        logo_diameter = logo_fill_to_diameter_ratio(BRICKGEN_LOGO_FILL_UI_DEFAULT)
        logo_height = 0.06
        logo_blend = 1.0
        logo_sink = BRICKGEN_LOGO_DEFAULT_SINK
        try:
            logo_enabled = bool(op[BRICKGENERATOR_ENABLE_LOGO])
            logo_source = op[BRICKGENERATOR_LOGO_SOURCE]
            logo_rotation = int(op[BRICKGENERATOR_LOGO_ROTATION] or 0) % 4
            logo_diameter = logo_fill_to_diameter_ratio(op[BRICKGENERATOR_LOGO_DIAMETER])
            logo_height = max(0.02, min(0.25, float(op[BRICKGENERATOR_LOGO_HEIGHT] or 0.06)))
            logo_blend = max(0.0, min(1.0, float(op[BRICKGENERATOR_LOGO_BLEND] or 0.0)))
            logo_sink = max(0.0, min(0.05, float(op[BRICKGENERATOR_LOGO_SINK] or 0.0)))
        except Exception:
            pass

        if piece_type == BRICKGENERATOR_TYPE_PLATE:
            logo_enabled = False

        logo_state_key = None
        if logo_enabled and logo_source is not None:
            logo_state_key = (
                logo_link_identity_key(logo_source),
                round(logo_diameter, 4),
                round(logo_height, 4),
                logo_rotation,
                round(logo_blend, 4),
                round(logo_sink, 4),
            )

        need_logo = bool(logo_enabled and logo_source is not None)
        doc = generator_document(op, hh)

        cache_key = (
            width,
            depth,
            height,
            piece_type,
            quality,
            logo_state_key,
        )
        if self._cache_key == cache_key and self._cache_obj is not None:
            return self._cache_obj.GetClone(c4d.COPYFLAGS_NONE)

        mesh = build_brick(width, depth, height, quality, piece_type)
        out_h = 1 if piece_type == BRICKGENERATOR_TYPE_PLATE else height
        prefix = "Plate" if piece_type == BRICKGENERATOR_TYPE_PLATE else "Brick"
        name = "{p}_{w}x{d}x{h}".format(p=prefix, w=width, d=depth, h=out_h)
        brick_po = mesh_to_polygon_object(mesh, name=name)

        stud_size = BRICKGEN_DEFAULT_STUD_SIZE
        plate_size = BRICKGEN_DEFAULT_PLATE_SIZE
        stud_h = plate_size * BRICKGEN_LOGO_STUD_HEIGHT_RATIO

        logo_template = None
        if logo_enabled and logo_source is not None and doc is not None:
            logo_key = (
                "src",
                logo_link_identity_key(logo_source),
                round(stud_size, 6),
                round(plate_size, 6),
                round(logo_diameter, 4),
                round(logo_height, 4),
                round(logo_blend, 4),
            )
            if logo_key not in self._logo_cache:
                self._logo_cache[logo_key] = normalized_logo_mesh_object(
                    logo_source,
                    doc,
                    stud_size,
                    plate_size,
                    diameter_ratio=logo_diameter,
                    height_ratio=logo_height,
                    blend=logo_blend,
                )
            tmpl = self._logo_cache.get(logo_key)
            if tmpl is not None:
                logo_template = tmpl.GetClone(c4d.COPYFLAGS_NONE)

        result = brick_po
        if logo_template is not None:
            root = c4d.BaseObject(c4d.Onull)
            root.SetName("Brick_{0}".format(name))

            brick_po.InsertUnder(root)

            body_top_y = float(out_h) * plate_size
            logo_surface_bias = -plate_size * logo_sink
            top_y = body_top_y + stud_h + logo_surface_bias

            logos_root = c4d.BaseObject(c4d.Onull)
            logos_root.SetName("stud_logos")
            logos_root.InsertUnder(root)
            for sx in range(width):
                for sz in range(depth):
                    m = c4d.Matrix()
                    m.off = c4d.Vector(
                        float((sx + 0.5) * stud_size),
                        float(top_y),
                        float((sz + 0.5) * stud_size),
                    )
                    apply_logo_quarter_turn(m, logo_rotation)
                    logo_obj = logo_template.GetClone(c4d.COPYFLAGS_NONE)
                    if logo_obj is None:
                        continue
                    logo_obj.SetName("stud_logo")
                    logo_obj.SetMl(m)
                    logo_obj.InsertUnder(logos_root)
            result = root

        if need_logo and logo_template is None:
            if self._cache_key == cache_key and self._cache_obj is not None:
                return self._cache_obj.GetClone(c4d.COPYFLAGS_NONE)
            self._cache_key = None
            self._cache_obj = None
            return result.GetClone(c4d.COPYFLAGS_NONE)

        self._cache_key = cache_key
        self._cache_obj = result.GetClone(c4d.COPYFLAGS_NONE)
        return result
