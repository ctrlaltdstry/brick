"""Cinema 4D ObjectData generator: high-res LEGO brick.

Wraps brick.brick_geom_hires.make_brick_hires so the C4D plugin
shares the same baked-fillet generator that powers the standalone
exporter (tools/export_hires_brick.py). No SDS / no subdivision —
every fillet is real geometry, welded into a manifold-clean mesh.

User-exposed parameters:
  Width, Depth   - brick footprint in studs (1..32)
  Height         - height in plates (1..24)
  Quality        - draft / standard / hero
"""
import os
import sys
import site
import c4d
from c4d import plugins

try:
    from c4d_symbols import (
        IDS_BRICKGENERATOR,
        ID_BRICKGENERATOR,
        BRICKGENERATOR_WIDTH,
        BRICKGENERATOR_DEPTH,
        BRICKGENERATOR_HEIGHT,
        BRICKGENERATOR_QUALITY,
        BRICKGENERATOR_TYPE,
        BRICKGENERATOR_QUALITY_DRAFT,
        BRICKGENERATOR_QUALITY_STANDARD,
        BRICKGENERATOR_QUALITY_HERO,
        BRICKGENERATOR_TYPE_BRICK,
        BRICKGENERATOR_TYPE_PLATE,
        IDS_BRICKIFYASSEMBLY,
        ID_BRICKIFYASSEMBLY,
        IDS_BRICKLIBRARYPANEL,
        ID_BRICKLIBRARYPANEL,
        BRICKIFYASSEMBLY_SOURCE,
        BRICKIFYASSEMBLY_HIDE_SOURCE_MESH,
        BRICKIFYASSEMBLY_STUDS_ACROSS,
        BRICKIFYASSEMBLY_VOXEL_MODE,
        BRICKIFYASSEMBLY_QUALITY,
        BRICKIFYASSEMBLY_MERGE_PLATES,
        BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY,
        BRICKIFYASSEMBLY_COLOR_MODE,
        BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT,
        BRICKIFYASSEMBLY_REBUILD,
        BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS,
        BRICKIFYASSEMBLY_SHELL_THICKNESS,
        BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE,
        BRICKIFYASSEMBLY_STUD_SIZE,
        BRICKIFYASSEMBLY_DETAIL_MODE,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE,
        BRICKIFYASSEMBLY_AUTO_REBUILD,
        BRICKIFYASSEMBLY_HERO,
        BRICKIFYASSEMBLY_VOXEL_RESOLUTION,
        BRICKIFYASSEMBLY_LIB_PRESET_ALL,
        BRICKIFYASSEMBLY_LIB_PRESET_NONE,
        BRICKIFYASSEMBLY_LIB_PRESET_BRICKS,
        BRICKIFYASSEMBLY_LIB_PRESET_PLATES,
        BRICKIFYASSEMBLY_LIB_PRESET_1X1,
        BRICKIFYASSEMBLY_LIB_PRESET_INVERT,
        BRICKIFYASSEMBLY_OPEN_LIBRARY_PICKER,
        BRICKIFYASSEMBLY_THUMB_BASE,
        BRICKIFYASSEMBLY_HEIGHT_PRESET_FINE,
        BRICKIFYASSEMBLY_HEIGHT_PRESET_BALANCED,
        BRICKIFYASSEMBLY_HEIGHT_PRESET_BLOCKY,
        BRICKIFYASSEMBLY_HEIGHT_VARIATION,
        BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED,
        BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT,
        BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS,
        BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES,
        BRICKIFYASSEMBLY_ENABLE_PLATES,
        BRICKIFYASSEMBLY_LIBRARY_COUNT,
        BRICKIFYASSEMBLY_LIBRARY_MASK,
        BRICKIFYASSEMBLY_GROUP_ACTIONS,
        BRICKIFYASSEMBLY_BRICK_BASE,
        BRICKIFYASSEMBLY_VOXEL_MODE_SOLID,
        BRICKIFYASSEMBLY_VOXEL_MODE_SHELL,
        BRICKIFYASSEMBLY_DETAIL_MODE_OFF,
        BRICKIFYASSEMBLY_DETAIL_MODE_BALANCED,
        BRICKIFYASSEMBLY_DETAIL_MODE_PRESERVE,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_BRICK_SIZE,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_DEPTH,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME,
        BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG,
        BRICKIFYASSEMBLY_COLOR_MODE_NONE,
        BRICKIFYASSEMBLY_COLOR_MODE_MATERIAL,
        ICON_BRICKIFY_HERO,
        ICON_BRICKIFY_BRICK_BASE,
    )
except ModuleNotFoundError:
    IDS_BRICKGENERATOR = "BrickGen"
    ID_BRICKGENERATOR = 1069999
    BRICKGENERATOR_WIDTH = 1001
    BRICKGENERATOR_DEPTH = 1002
    BRICKGENERATOR_HEIGHT = 1003
    BRICKGENERATOR_QUALITY = 1004
    BRICKGENERATOR_TYPE = 1005
    BRICKGENERATOR_QUALITY_DRAFT = 0
    BRICKGENERATOR_QUALITY_STANDARD = 1
    BRICKGENERATOR_QUALITY_HERO = 2
    BRICKGENERATOR_TYPE_BRICK = 0
    BRICKGENERATOR_TYPE_PLATE = 1
    IDS_BRICKIFYASSEMBLY = "BrickIt"
    ID_BRICKIFYASSEMBLY = 1069998
    IDS_BRICKLIBRARYPANEL = "Brick Panel"
    ID_BRICKLIBRARYPANEL = 1069997
    BRICKIFYASSEMBLY_SOURCE = 2001
    BRICKIFYASSEMBLY_HIDE_SOURCE_MESH = 2032
    BRICKIFYASSEMBLY_STUDS_ACROSS = 2002
    BRICKIFYASSEMBLY_VOXEL_MODE = 2003
    BRICKIFYASSEMBLY_QUALITY = 2004
    BRICKIFYASSEMBLY_MERGE_PLATES = 2005
    BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY = 2006
    BRICKIFYASSEMBLY_COLOR_MODE = 2007
    BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT = 2008
    BRICKIFYASSEMBLY_REBUILD = 2009
    BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS = 2010
    BRICKIFYASSEMBLY_SHELL_THICKNESS = 2011
    BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE = 2012
    BRICKIFYASSEMBLY_STUD_SIZE = 2013
    BRICKIFYASSEMBLY_DETAIL_MODE = 2014
    BRICKIFYASSEMBLY_VISUALIZATION_MODE = 2015
    BRICKIFYASSEMBLY_AUTO_REBUILD = 2016
    BRICKIFYASSEMBLY_HERO = 2017
    BRICKIFYASSEMBLY_VOXEL_RESOLUTION = 2018
    BRICKIFYASSEMBLY_LIB_PRESET_ALL = 2019
    BRICKIFYASSEMBLY_LIB_PRESET_NONE = 2020
    BRICKIFYASSEMBLY_LIB_PRESET_BRICKS = 2021
    BRICKIFYASSEMBLY_LIB_PRESET_PLATES = 2022
    BRICKIFYASSEMBLY_LIB_PRESET_1X1 = 2023
    BRICKIFYASSEMBLY_LIB_PRESET_INVERT = 2024
    BRICKIFYASSEMBLY_OPEN_LIBRARY_PICKER = 2033
    BRICKIFYASSEMBLY_THUMB_BASE = 2200
    BRICKIFYASSEMBLY_LIBRARY_COUNT = 2025
    BRICKIFYASSEMBLY_HEIGHT_PRESET_FINE = 2026
    BRICKIFYASSEMBLY_HEIGHT_PRESET_BALANCED = 2027
    BRICKIFYASSEMBLY_HEIGHT_PRESET_BLOCKY = 2028
    BRICKIFYASSEMBLY_HEIGHT_VARIATION = 2029
    BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED = 2030
    BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT = 2031
    BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS = 2035
    BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES = 2036
    BRICKIFYASSEMBLY_ENABLE_PLATES = 2037
    BRICKIFYASSEMBLY_GROUP_ACTIONS = 2059
    BRICKIFYASSEMBLY_LIBRARY_MASK = 2034
    BRICKIFYASSEMBLY_BRICK_BASE = 2100
    BRICKIFYASSEMBLY_VOXEL_MODE_SOLID = 0
    BRICKIFYASSEMBLY_VOXEL_MODE_SHELL = 1
    BRICKIFYASSEMBLY_DETAIL_MODE_OFF = 0
    BRICKIFYASSEMBLY_DETAIL_MODE_BALANCED = 1
    BRICKIFYASSEMBLY_DETAIL_MODE_PRESERVE = 2
    BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE = 0
    BRICKIFYASSEMBLY_VISUALIZATION_MODE_BRICK_SIZE = 1
    BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_DEPTH = 2
    BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME = 3
    BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG = 4
    BRICKIFYASSEMBLY_COLOR_MODE_NONE = 0
    BRICKIFYASSEMBLY_COLOR_MODE_MATERIAL = 1
    ICON_BRICKIFY_HERO = 1090000
    ICON_BRICKIFY_BRICK_BASE = 1090100


# ---------------------------------------------------------------------
# Brick library mapping (DEFAULT_LIBRARY order). Each entry is the index
# into brick.library.DEFAULT_LIBRARY. The toggle parameter ID is
# BRICKIFYASSEMBLY_BRICK_BASE + index, and the icon ID is
# ICON_BRICKIFY_BRICK_BASE + index. Order is canonical and must match
# the .h file and the DEFAULT_LIBRARY ordering.
# ---------------------------------------------------------------------
BRICK_TOGGLE_NAMES = [
    "brick_1x1", "brick_1x2", "brick_1x3", "brick_1x4",
    "brick_1x6", "brick_1x8",
    "brick_2x2", "brick_2x3", "brick_2x4", "brick_2x6", "brick_2x8",
    "brick_3x3", "brick_3x4", "brick_3x6", "brick_3x8",
]
BRICK_LIBRARY_ALL_MASK = (1 << len(BRICK_TOGGLE_NAMES)) - 1
PLATE_LIBRARY_NAMES = (
    "plate_1x1", "plate_1x2", "plate_1x3", "plate_1x4",
    "plate_1x6", "plate_1x8",
    "plate_2x2", "plate_2x3", "plate_2x4", "plate_2x6", "plate_2x8",
    "plate_3x3", "plate_3x4", "plate_3x6", "plate_3x8",
)


def _toggle_id(idx):
    return BRICKIFYASSEMBLY_BRICK_BASE + idx


def _read_library_mask(op):
    """Read library bitmask from op; derive from toggles for legacy scenes."""
    try:
        raw_mask = int(op[BRICKIFYASSEMBLY_LIBRARY_MASK] or 0)
        mask = raw_mask & BRICK_LIBRARY_ALL_MASK
        # Back-compat: older scenes stored 22 bits (bricks + plates). If those
        # upper "plate" bits are present, fold them onto the first 11 brick
        # footprints so legacy files retain a useful brick selection.
        # Layout then was:
        #   bits 0..10  = bricks
        #   bits 11..21 = plates
        LEGACY_BASE_COUNT = 11
        has_legacy_upper_bits = bool(raw_mask >> len(BRICK_TOGGLE_NAMES))
        if has_legacy_upper_bits:
            legacy_plate_bits = (raw_mask >> LEGACY_BASE_COUNT) & ((1 << LEGACY_BASE_COUNT) - 1)
            mask |= legacy_plate_bits
        return mask & BRICK_LIBRARY_ALL_MASK
    except Exception:
        mask = 0
        for i in range(len(BRICK_TOGGLE_NAMES)):
            try:
                if bool(op[_toggle_id(i)]):
                    mask |= (1 << i)
            except Exception:
                mask |= (1 << i)
        return mask & BRICK_LIBRARY_ALL_MASK


def _apply_library_mask_to_toggles(op, mask):
    """Mirror bitmask state into legacy per-brick bool toggles."""
    m = int(mask) & BRICK_LIBRARY_ALL_MASK
    for i in range(len(BRICK_TOGGLE_NAMES)):
        op[_toggle_id(i)] = bool(m & (1 << i))


def _sync_library_mask_from_toggles(op):
    """Write BRICKIFYASSEMBLY_LIBRARY_MASK from the bool toggles."""
    mask = 0
    for i in range(len(BRICK_TOGGLE_NAMES)):
        try:
            if bool(op[_toggle_id(i)]):
                mask |= (1 << i)
        except Exception:
            mask |= (1 << i)
    op[BRICKIFYASSEMBLY_LIBRARY_MASK] = int(mask & BRICK_LIBRARY_ALL_MASK)


def _apply_library_preset_to_object(op, preset_id):
    if op is None:
        return
    if preset_id == BRICKIFYASSEMBLY_LIB_PRESET_ALL:
        for i in range(len(BRICK_TOGGLE_NAMES)):
            op[_toggle_id(i)] = True
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_NONE:
        for i in range(len(BRICK_TOGGLE_NAMES)):
            op[_toggle_id(i)] = False
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_BRICKS:
        for i, n in enumerate(BRICK_TOGGLE_NAMES):
            op[_toggle_id(i)] = n.startswith("brick_")
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_PLATES:
        # Legacy compatibility (button removed): treat as "enable plates"
        # while keeping current brick footprint selection.
        try:
            op[BRICKIFYASSEMBLY_ENABLE_PLATES] = True
        except Exception:
            pass
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_1X1:
        for i, n in enumerate(BRICK_TOGGLE_NAMES):
            op[_toggle_id(i)] = (n == "brick_1x1")
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_INVERT:
        for i in range(len(BRICK_TOGGLE_NAMES)):
            op[_toggle_id(i)] = not bool(op[_toggle_id(i)])
    _sync_library_mask_from_toggles(op)
    op.SetDirty(c4d.DIRTYFLAGS_DATA)
    c4d.EventAdd()


def _active_brick_object():
    try:
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return None
        op = doc.GetActiveObject()
        if op is not None and op.GetType() == ID_BRICKIFYASSEMBLY:
            return op
    except Exception:
        pass
    return None


# Voxel-resolution slider mapping. The UI is 0..1 normalized; internally
# we drive studs_across through an exponential/detail curve. This makes the
# middle of the slider useful instead of bunching common low-res values near
# zero: 1.0=8 (chunky), 0.55~25, 0.46~32, 0.37~40, 0.1=80 (detailed).
VOXEL_RES_MIN_STUDS = 8
VOXEL_RES_MAX_STUDS = 80
VOXEL_RES_DEFAULT = 0.8
PRUNE_AUTO_DISABLE_MIX_THRESHOLD = 0.55
PRUNE_AUTO_REENABLE_MIX_THRESHOLD = 0.30


def _voxel_resolution_to_studs(value):
    v = max(0.1, min(1.0, float(value)))
    # UI direction is intentionally inverted for artist ergonomics:
    # larger numeric slider value -> chunkier (fewer studs across).
    t = (v - 0.1) / 0.9
    detail_t = 1.0 - t
    ratio = float(VOXEL_RES_MAX_STUDS) / float(VOXEL_RES_MIN_STUDS)
    return int(round(float(VOXEL_RES_MIN_STUDS) * (ratio ** detail_t)))


# ---------------------------------------------------------------------
# Quality presets (mirror tools/export_hires_brick.py).
# ---------------------------------------------------------------------
QUALITY_PRESETS = {
    BRICKGENERATOR_QUALITY_DRAFT: dict(
        body_corner_segments=2,
        stud_segments=12, stud_fillet_segments=1,
        tube_segments=12, tube_fillet_segments=1,
        rib_segments=1,
    ),
    BRICKGENERATOR_QUALITY_STANDARD: dict(
        body_corner_segments=8,
        stud_segments=32, stud_fillet_segments=4,
        tube_segments=32, tube_fillet_segments=4,
        rib_segments=4,
    ),
    BRICKGENERATOR_QUALITY_HERO: dict(
        body_corner_segments=16,
        stud_segments=64, stud_fillet_segments=8,
        tube_segments=64, tube_fillet_segments=8,
        rib_segments=8,
        body_fillet_radius=0.4,
        stud_fillet_radius=0.18,
        tube_fillet_radius=0.18,
        rib_fillet_radius=0.10,
    ),
}


# =====================================================================
# brick import bootstrap
# =====================================================================

def _ensure_brick_on_path():
    """Make sure the brick package is importable.

    Search order:
      1. $BRICK_ROOT / $BRICKIFY_ROOT (manual override)
      2. Sibling 'brick'/'brickify' directory next to this .pyp file
      3. Cinema 4D / user site-packages
    """
    here = os.path.dirname(os.path.abspath(__file__))

    candidates = []
    env_root = os.environ.get("BRICK_ROOT") or os.environ.get("BRICKIFY_ROOT")
    if env_root:
        candidates.append(env_root)

    # Hardcoded fallback to the dev repo. C4D loads the .pyp from a
    # deployed copy under %APPDATA%/Maxon/.../plugins/BrickGen,
    # so walking up from <here> can't find the package — we need to point
    # at the directory CONTAINING both `brick` and `brickify`.
    candidates.append(r"Z:\02_MKE\2026\BRICK\brick")
    candidates.append(r"Z:\02_MKE\2026\BRICK\brickify")

    walk = here
    for _ in range(6):
        pkg_init = os.path.join(walk, "brick", "__init__.py")
        if os.path.isfile(pkg_init):
            candidates.append(walk)
        legacy_pkg_init = os.path.join(walk, "brickify", "__init__.py")
        if os.path.isfile(legacy_pkg_init):
            candidates.append(walk)
        nested = os.path.join(walk, "brickify", "brickify", "__init__.py")
        if os.path.isfile(nested):
            candidates.append(os.path.join(walk, "brickify"))
        parent = os.path.dirname(walk)
        if parent == walk:
            break
        walk = parent
    candidates.append(here)

    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        candidates.append(site.getusersitepackages())
    except Exception:
        pass
    appdata = os.environ.get("APPDATA")
    if appdata:
        py_tag = "Python{0}{1}".format(
            sys.version_info.major, sys.version_info.minor
        )
        candidates.append(os.path.join(appdata, "Python", py_tag, "site-packages"))

    # Preserve candidate priority order: first candidate should be first in
    # sys.path. Using insert(0) in forward order inverts priority and can make
    # stale site-packages copies win over the live repo.
    ordered = []
    seen = set()
    for p in candidates:
        if not p:
            continue
        p_norm = os.path.normcase(os.path.normpath(p))
        if p_norm in seen:
            continue
        if not os.path.isdir(p):
            continue
        seen.add(p_norm)
        ordered.append(p)

    for p in reversed(ordered):
        if p not in sys.path:
            sys.path.insert(0, p)


def _reload_brick_modules():
    """Hot-reload every loaded brick/brickify module.

    Use case: the user edits brick/voxelize.py (or fitter.py, etc.)
    on disk and clicks Rebuild. Without this, Python's import cache
    keeps the stale module objects bound and the rebuild has no effect
    until C4D is restarted.
    """
    import importlib
    _ensure_brick_on_path()
    names = [n for n in list(sys.modules.keys())
             if n == "brick" or n.startswith("brick.") or n == "brickify" or n.startswith("brickify.")]
    names.sort(key=lambda n: -n.count("."))
    for n in names:
        mod = sys.modules.get(n)
        if mod is None:
            continue
        try:
            importlib.reload(mod)
        except Exception as exc:
            print("[brick] reload failed for {0}: {1}".format(n, exc))
            sys.modules.pop(n, None)


# =====================================================================
# Mesh -> C4D conversion
# =====================================================================

def mesh_to_polygon_object(mesh, name="brick"):
    """Convert a brick Mesh to a c4d.PolygonObject.

    n-gons are converted to a triangle fan from the polygon centroid so
    that round caps stay centered. Quads and tris pass through unchanged.
    Polygon-selection tags are emitted for each named group on the mesh
    so users can apply per-group materials.
    """
    converted_vertices = [
        (float(v[0]), float(v[1]), float(v[2])) for v in mesh.vertices
    ]
    converted_faces = []
    face_index_map = {}
    for orig_fi, face in enumerate(mesh.faces):
        verts = tuple(int(v) for v in face)
        if len(verts) < 3:
            continue
        if len(verts) in (3, 4):
            face_index_map[orig_fi] = [len(converted_faces)]
            converted_faces.append(verts)
        else:
            new_ids = []
            cx = cy = cz = 0.0
            for vi in verts:
                vx, vy, vz = converted_vertices[vi]
                cx += vx
                cy += vy
                cz += vz
            inv = 1.0 / float(len(verts))
            center_idx = len(converted_vertices)
            converted_vertices.append((cx * inv, cy * inv, cz * inv))
            for i in range(len(verts)):
                tri = (center_idx, verts[i], verts[(i + 1) % len(verts)])
                new_ids.append(len(converted_faces))
                converted_faces.append(tri)
            face_index_map[orig_fi] = new_ids

    obj = c4d.PolygonObject(len(converted_vertices), len(converted_faces))
    obj.SetName(name)

    for i, v in enumerate(converted_vertices):
        obj.SetPoint(i, c4d.Vector(float(v[0]), float(v[1]), float(v[2])))

    for i, face in enumerate(converted_faces):
        if len(face) == 3:
            obj.SetPolygon(i, c4d.CPolygon(face[0], face[1], face[2], face[2]))
        elif len(face) == 4:
            obj.SetPolygon(i, c4d.CPolygon(face[0], face[1], face[2], face[3]))

    obj.Message(c4d.MSG_UPDATE)

    groups = getattr(mesh, "groups", {}) or {}
    for group_name, face_indices in groups.items():
        sel_tag = obj.MakeTag(c4d.Tpolygonselection)
        sel_tag.SetName(str(group_name))
        sel = sel_tag.GetBaseSelect()
        for fi in face_indices:
            for converted_fi in face_index_map.get(int(fi), []):
                sel.Select(int(converted_fi))

    phong = obj.MakeTag(c4d.Tphong)
    phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
    phong[c4d.PHONGTAG_PHONG_ANGLE] = c4d.utils.DegToRad(40.0)

    return obj


def build_brick(
    width,
    depth,
    height_plates,
    quality,
    piece_type=BRICKGENERATOR_TYPE_BRICK,
):
    """Return a brick/plate Mesh built by make_brick_hires."""
    from brick.brick_geom_hires import make_brick_hires

    h = max(1, int(height_plates))
    if int(piece_type) == BRICKGENERATOR_TYPE_PLATE:
        h = 1

    kwargs = dict(QUALITY_PRESETS.get(quality, QUALITY_PRESETS[BRICKGENERATOR_QUALITY_HERO]))
    if int(piece_type) == BRICKGENERATOR_TYPE_PLATE:
        # Plate mode should be the smooth plate variant by default.
        kwargs["with_studs"] = False
    return make_brick_hires(int(width), int(depth), h, **kwargs)


# =====================================================================
# C4D plugin shell
# =====================================================================

class BrickGen(plugins.ObjectData):
    """C4D ObjectData generator: Width / Depth / Height / Type / Quality."""

    def __init__(self):
        super().__init__()
        self._cache_key = None
        self._cache_obj = None

    def Init(self, op, isCloneInit=False):
        op[BRICKGENERATOR_WIDTH] = 2
        op[BRICKGENERATOR_DEPTH] = 4
        op[BRICKGENERATOR_HEIGHT] = 3
        op[BRICKGENERATOR_TYPE] = BRICKGENERATOR_TYPE_BRICK
        op[BRICKGENERATOR_QUALITY] = BRICKGENERATOR_QUALITY_STANDARD
        self._cache_key = None
        self._cache_obj = None
        return True

    def Message(self, op, msg_type, data):
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
        if pid == BRICKGENERATOR_HEIGHT:
            try:
                piece_type = int(op[BRICKGENERATOR_TYPE] or BRICKGENERATOR_TYPE_BRICK)
            except Exception:
                piece_type = BRICKGENERATOR_TYPE_BRICK
            return piece_type != BRICKGENERATOR_TYPE_PLATE
        return True

    def GetVirtualObjects(self, op, hh):
        _ensure_brick_on_path()

        try:
            import brick.mesh  # noqa: F401
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Failed to import brick. Make sure the brick "
                "package is next to c4d_brick_generator.pyp (or set "
                "BRICK_ROOT/BRICKIFY_ROOT) and that numpy/scipy are installed in "
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

        cache_key = (width, depth, height, piece_type, quality)
        if self._cache_key == cache_key and self._cache_obj is not None:
            return self._cache_obj.GetClone(c4d.COPYFLAGS_NONE)

        mesh = build_brick(width, depth, height, quality, piece_type)
        out_h = 1 if piece_type == BRICKGENERATOR_TYPE_PLATE else height
        prefix = "Plate" if piece_type == BRICKGENERATOR_TYPE_PLATE else "Brick"
        name = "{p}_{w}x{d}x{h}".format(p=prefix, w=width, d=depth, h=out_h)
        result = mesh_to_polygon_object(mesh, name=name)
        self._cache_key = cache_key
        self._cache_obj = result.GetClone(c4d.COPYFLAGS_NONE)
        return result


# =====================================================================
# BrickAssembly: source mesh -> brick assembly
# =====================================================================

ASSEMBLY_QUALITY_PRESETS = {
    0: QUALITY_PRESETS[BRICKGENERATOR_QUALITY_DRAFT],
    1: QUALITY_PRESETS[BRICKGENERATOR_QUALITY_STANDARD],
    2: QUALITY_PRESETS[BRICKGENERATOR_QUALITY_HERO],
}


def _baked_polygon_object(source_obj, doc):
    """Return a polygon-only baked clone of `source_obj`."""
    if source_obj is None:
        return None

    def _collect_polygons(root):
        found = []

        def _walk(o):
            if o is None:
                return
            if o.GetType() == c4d.Opolygon:
                found.append(o)
            ch = o.GetDown()
            while ch is not None:
                _walk(ch)
                ch = ch.GetNext()

        if isinstance(root, list):
            for r in root:
                _walk(r)
        else:
            _walk(root)
        return found

    def _merge_polygon_objects(found):
        if not found:
            return None
        if len(found) == 1:
            try:
                return found[0].GetClone(c4d.COPYFLAGS_NONE)
            except Exception:
                return found[0]
        total_v = sum(o.GetPointCount() for o in found)
        total_f = sum(o.GetPolygonCount() for o in found)
        merged = c4d.PolygonObject(total_v, total_f)
        v_off = 0
        f_off = 0
        for o in found:
            pts = o.GetAllPoints()
            polys = o.GetAllPolygons()
            mg = o.GetMg()
            for i, p in enumerate(pts):
                merged.SetPoint(v_off + i, mg * p)
            for j, fp in enumerate(polys):
                merged.SetPolygon(
                    f_off + j,
                    c4d.CPolygon(fp.a + v_off, fp.b + v_off, fp.c + v_off, fp.d + v_off),
                )
            v_off += len(pts)
            f_off += len(polys)
        merged.Message(c4d.MSG_UPDATE)
        return merged

    # Fast path: if the source is already polygon geometry, skip Current State
    # To Object (expensive on scene open for large meshes).
    if source_obj.GetType() == c4d.Opolygon:
        try:
            return source_obj.GetClone(c4d.COPYFLAGS_NONE)
        except Exception:
            return source_obj

    # Fast path: consume existing cache/deform cache when available.
    cache_roots = []
    try:
        dc = source_obj.GetDeformCache()
        if dc is not None:
            cache_roots.append(dc)
    except Exception:
        pass
    try:
        cc = source_obj.GetCache()
        if cc is not None:
            cache_roots.append(cc)
    except Exception:
        pass
    for root in cache_roots:
        merged = _merge_polygon_objects(_collect_polygons(root))
        if merged is not None and merged.GetPointCount() > 0:
            return merged

    result = c4d.utils.SendModelingCommand(
        command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,
        list=[source_obj],
        mode=c4d.MODELINGCOMMANDMODE_ALL,
        doc=doc,
    )
    if not result:
        return None
    return _merge_polygon_objects(_collect_polygons(result))


def _polygon_object_to_arrays(poly_obj):
    """Return (vertices Nx3 float64, faces Mx3 int64, vertex_colors or None)."""
    import numpy as np

    n_pts = poly_obj.GetPointCount()
    pts = poly_obj.GetAllPoints()
    polys = poly_obj.GetAllPolygons()

    mg = poly_obj.GetMg()
    verts = np.empty((n_pts, 3), dtype=np.float64)
    for i, p in enumerate(pts):
        wp = mg * p
        verts[i, 0] = wp.x
        verts[i, 1] = wp.y
        verts[i, 2] = wp.z

    tris = []
    for fp in polys:
        a, b, c, d = fp.a, fp.b, fp.c, fp.d
        if c == d:
            tris.append((a, b, c))
        else:
            tris.append((a, b, c))
            tris.append((a, c, d))
    faces = np.array(tris, dtype=np.int64) if tris else np.zeros((0, 3), dtype=np.int64)

    return verts, faces, None


def _source_material_color(source_obj):
    if source_obj is None:
        return None
    tex = source_obj.GetTag(c4d.Ttexture)
    if tex is None:
        return None
    mat = tex[c4d.TEXTURETAG_MATERIAL]
    if mat is None:
        return None
    try:
        col = mat[c4d.MATERIAL_COLOR_COLOR]
        return (
            int(round(max(0.0, min(1.0, col.x)) * 255)),
            int(round(max(0.0, min(1.0, col.y)) * 255)),
            int(round(max(0.0, min(1.0, col.z)) * 255)),
        )
    except Exception:
        return None


class BrickLibraryPickerDialog(c4d.gui.GeDialog):
    """Safe thumbnail picker outside the .res description parser."""

    DLG_HERO = 50000
    DLG_PRESET_ALL = 50001
    DLG_PRESET_NONE = 50002
    DLG_PRESET_BRICKS = 50003
    DLG_PRESET_PLATES = 50004
    DLG_PRESET_1X1 = 50005
    DLG_PRESET_INVERT = 50006
    DLG_THUMB_BASE = 51000
    DLG_TOGGLE_BASE = 52000

    def __init__(self):
        super().__init__()
        self._target = None
        self._last_target_name = ""

    def set_target(self, op):
        self._target = op
        try:
            name = op.GetName() if op is not None else ""
        except Exception:
            name = ""
        self._last_target_name = name
        title = "Brick Library Picker"
        if name:
            title = "Brick Library Picker - {0}".format(name)
        try:
            self.SetTitle(title)
        except Exception:
            pass
        if self.IsOpen():
            self._sync_from_target()

    def _sync_from_target(self):
        op = self._target
        if op is None:
            return
        for i in range(len(BRICK_TOGGLE_NAMES)):
            try:
                on = bool(op[_toggle_id(i)])
            except Exception:
                on = True
            try:
                self.SetBool(self.DLG_TOGGLE_BASE + i, on)
            except Exception:
                pass

    def CreateLayout(self):
        self.SetTitle("Brick Library Picker")
        if not self.GroupBegin(999, c4d.BFH_SCALEFIT, cols=1):
            return True
        hero_bc = c4d.BaseContainer()
        hero_bc.SetBool(c4d.BITMAPBUTTON_BUTTON, False)
        hero_bc.SetBool(c4d.BITMAPBUTTON_BORDER, False)
        hero_bc.SetLong(c4d.BITMAPBUTTON_ICONID1, int(ICON_BRICKIFY_HERO))
        self.AddCustomGui(
            self.DLG_HERO,
            c4d.CUSTOMGUI_BITMAPBUTTON,
            "",
            c4d.BFH_CENTER,
            820,
            120,
            hero_bc,
        )
        self.GroupEnd()

        if not self.GroupBegin(1000, c4d.BFH_SCALEFIT, cols=4):
            return True
        self.AddButton(self.DLG_PRESET_ALL, c4d.BFH_SCALEFIT, name="All")
        self.AddButton(self.DLG_PRESET_NONE, c4d.BFH_SCALEFIT, name="None")
        self.AddButton(self.DLG_PRESET_INVERT, c4d.BFH_SCALEFIT, name="Invert")
        self.AddButton(self.DLG_PRESET_1X1, c4d.BFH_SCALEFIT, name="1x1")
        self.GroupEnd()

        if not self.GroupBegin(1001, c4d.BFH_SCALEFIT, cols=11):
            return True
        for i, name in enumerate(BRICK_TOGGLE_NAMES):
            cell = 53000 + i
            self.GroupBegin(cell, c4d.BFH_CENTER, cols=1)

            bc = c4d.BaseContainer()
            bc.SetBool(c4d.BITMAPBUTTON_BUTTON, True)
            bc.SetLong(c4d.BITMAPBUTTON_ICONID1, int(ICON_BRICKIFY_BRICK_BASE + i))
            bc.SetBool(c4d.BITMAPBUTTON_BORDER, False)
            self.AddCustomGui(
                self.DLG_THUMB_BASE + i,
                c4d.CUSTOMGUI_BITMAPBUTTON,
                "",
                c4d.BFH_CENTER,
                28,
                28,
                bc,
            )
            self.AddCheckbox(self.DLG_TOGGLE_BASE + i, c4d.BFH_CENTER, 0, 0, name.split("_")[-1])
            self.GroupEnd()
        self.GroupEnd()
        return True

    def InitValues(self):
        self._sync_from_target()
        return True

    def CoreMessage(self, mid, bc):
        # Modeless follow-mode: while dialog is open, track current active
        # BrickAssembly selection so artists don't need to reopen picker.
        try:
            doc = c4d.documents.GetActiveDocument()
            if doc is not None:
                op = _active_brick_object()
                if op is not None:
                    if op is not self._target:
                        self.set_target(op)
                elif self._target is not None:
                    # Keep current target while non-assembly objects are selected.
                    pass
        except Exception:
            pass
        return True

    def _apply_and_refresh(self):
        op = self._target
        if op is None:
            return
        _sync_library_mask_from_toggles(op)
        op.SetDirty(c4d.DIRTYFLAGS_DATA)
        c4d.EventAdd()
        self._sync_from_target()

    def Command(self, cid, msg):
        op = self._target
        if op is None:
            return True

        preset_map = {
            self.DLG_PRESET_ALL: BRICKIFYASSEMBLY_LIB_PRESET_ALL,
            self.DLG_PRESET_NONE: BRICKIFYASSEMBLY_LIB_PRESET_NONE,
            self.DLG_PRESET_1X1: BRICKIFYASSEMBLY_LIB_PRESET_1X1,
            self.DLG_PRESET_INVERT: BRICKIFYASSEMBLY_LIB_PRESET_INVERT,
        }
        if cid in preset_map:
            _apply_library_preset_to_object(op, preset_map[cid])
            self._apply_and_refresh()
            return True

        if self.DLG_THUMB_BASE <= cid < self.DLG_THUMB_BASE + len(BRICK_TOGGLE_NAMES):
            i = int(cid - self.DLG_THUMB_BASE)
            tid = _toggle_id(i)
            op[tid] = not bool(op[tid])
            self._apply_and_refresh()
            return True

        if self.DLG_TOGGLE_BASE <= cid < self.DLG_TOGGLE_BASE + len(BRICK_TOGGLE_NAMES):
            i = int(cid - self.DLG_TOGGLE_BASE)
            tid = _toggle_id(i)
            op[tid] = bool(self.GetBool(cid))
            self._apply_and_refresh()
            return True
        return True


_LIBRARY_PANEL_DIALOG = None


def _ensure_library_panel_dialog():
    global _LIBRARY_PANEL_DIALOG
    if _LIBRARY_PANEL_DIALOG is None:
        _LIBRARY_PANEL_DIALOG = BrickLibraryPickerDialog()
    return _LIBRARY_PANEL_DIALOG


def _open_library_panel(target=None):
    dlg = _ensure_library_panel_dialog()
    if target is None:
        target = _active_brick_object()
    dlg.set_target(target)
    dlg.Open(
        c4d.DLG_TYPE_ASYNC,
        pluginid=ID_BRICKLIBRARYPANEL,
        defaultw=860,
        defaulth=330,
    )
    return dlg


class BrickLibraryPanelCommand(plugins.CommandData):
    def Execute(self, doc):
        _open_library_panel(_active_brick_object())
        return True

    def RestoreLayout(self, secret):
        dlg = _ensure_library_panel_dialog()
        return dlg.Restore(pluginid=ID_BRICKLIBRARYPANEL, secret=secret)


class BrickAssembly(plugins.ObjectData):
    """Source polygon mesh -> brick-assembly hierarchy of instances."""

    def __init__(self):
        super().__init__()
        self._fit_cache_key = None
        self._fit_placements = None
        self._fit_info = None
        self._hierarchy_cache_key = None
        self._force_rebuild = False
        self._mesh_cache = {}
        self._pending_auto_key = None
        self._pending_auto_since = 0.0
        self._last_hierarchy_obj = None
        self._last_resolution_key = None
        self._startup_draft_pending = True
        self._managed_source = None
        self._last_prune_warning_key = None
        self._prune_auto_forced_off = False

    def Init(self, op, isCloneInit=False):
        op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION] = VOXEL_RES_DEFAULT
        op[BRICKIFYASSEMBLY_HERO] = 0
        op[BRICKIFYASSEMBLY_STUDS_ACROSS] = 16          # legacy fallback
        op[BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE] = False
        op[BRICKIFYASSEMBLY_STUD_SIZE] = 8.0
        op[BRICKIFYASSEMBLY_VOXEL_MODE] = BRICKIFYASSEMBLY_VOXEL_MODE_SOLID
        op[BRICKIFYASSEMBLY_SHELL_THICKNESS] = 3
        op[BRICKIFYASSEMBLY_DETAIL_MODE] = BRICKIFYASSEMBLY_DETAIL_MODE_BALANCED
        op[BRICKIFYASSEMBLY_QUALITY] = BRICKGENERATOR_QUALITY_DRAFT
        op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT] = 3
        op[BRICKIFYASSEMBLY_HEIGHT_VARIATION] = False
        op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED] = 1
        op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT] = 0.6
        op[BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS] = False
        op[BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES] = True
        op[BRICKIFYASSEMBLY_ENABLE_PLATES] = False
        op[BRICKIFYASSEMBLY_HIDE_SOURCE_MESH] = True
        op[BRICKIFYASSEMBLY_MERGE_PLATES] = True
        op[BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY] = True
        op[BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS] = 1
        op[BRICKIFYASSEMBLY_COLOR_MODE] = BRICKIFYASSEMBLY_COLOR_MODE_MATERIAL
        op[BRICKIFYASSEMBLY_VISUALIZATION_MODE] = BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE
        op[BRICKIFYASSEMBLY_AUTO_REBUILD] = True
        # Default: start with no brick types selected; artists opt-in via the
        # thumbnail library / quick select controls.
        for i in range(len(BRICK_TOGGLE_NAMES)):
            op[_toggle_id(i)] = False
        op[BRICKIFYASSEMBLY_LIBRARY_MASK] = 0
        self._fit_cache_key = None
        self._fit_placements = None
        self._fit_info = None
        self._hierarchy_cache_key = None
        self._force_rebuild = False
        self._mesh_cache = {}
        self._pending_auto_key = None
        self._pending_auto_since = 0.0
        self._last_hierarchy_obj = None
        self._last_resolution_key = None
        self._startup_draft_pending = True
        self._managed_source = None
        self._last_prune_warning_key = None
        self._prune_auto_forced_off = False
        # Ensure a fresh scene/file load triggers at least one generator
        # evaluation without requiring a manual OM interaction.
        try:
            op.SetDirty(c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_CACHE)
            op.Message(c4d.MSG_UPDATE)
        except Exception:
            pass
        return True

    def _restore_managed_source(self):
        state = self._managed_source
        if not state:
            return
        obj = state.get("obj")
        if obj is None:
            self._managed_source = None
            return
        try:
            obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = state.get("editor", c4d.OBJECT_UNDEF)
            obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = state.get("render", c4d.OBJECT_UNDEF)
        except Exception:
            pass
        self._managed_source = None

    def _sync_source_visibility(self, op):
        """Hide linked source object, restore it when unlinked/changed."""
        src = None
        try:
            src = op[BRICKIFYASSEMBLY_SOURCE]
        except Exception:
            src = None

        managed = self._managed_source
        managed_obj = managed.get("obj") if managed else None

        # Source changed or removed -> restore previous managed source.
        if managed_obj is not None and managed_obj is not src:
            self._restore_managed_source()
            managed = None
            managed_obj = None

        if src is None:
            return

        hide_source = True
        try:
            hide_source = bool(op[BRICKIFYASSEMBLY_HIDE_SOURCE_MESH])
        except Exception:
            hide_source = True

        if managed_obj is src:
            if not hide_source:
                self._restore_managed_source()
            return

        if not hide_source:
            return

        try:
            prev_editor = int(src[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR])
            prev_render = int(src[c4d.ID_BASEOBJECT_VISIBILITY_RENDER])
        except Exception:
            prev_editor = c4d.OBJECT_UNDEF
            prev_render = c4d.OBJECT_UNDEF

        self._managed_source = {
            "obj": src,
            "editor": prev_editor,
            "render": prev_render,
        }
        try:
            src[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = c4d.OBJECT_OFF
            src[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = c4d.OBJECT_OFF
        except Exception:
            pass

    def Free(self, node):
        # If the generator gets deleted, restore source-visibility state.
        self._restore_managed_source()

    def _apply_library_preset(self, op, preset_id):
        _apply_library_preset_to_object(op, preset_id)

    def _open_library_picker(self, op):
        _open_library_panel(op)

    def GetDDescription(self, op, description, flags):
        """Load obrickifyassembly.res from disk.

        Cinema 4D's .res lexer is effectively ASCII / Latin-1; stray UTF-8
        (e.g. Unicode dashes in comments) can make LoadDescription fail and
        hide the entire Object tab with no error dialog.
        """
        if not description.LoadDescription(ID_BRICKIFYASSEMBLY):
            print(
                "[brick] BrickAssembly: description.LoadDescription("
                "ID_BRICKIFYASSEMBLY) failed -- check res/description/"
                "obrickifyassembly.res for non-ASCII bytes or syntax errors."
            )
            return False
        try:
            # Migrate the temporary linear-slider default used during the UI
            # rebuild. Without this, existing test objects would keep showing
            # the unhelpful 0.111 value after the curve changed.
            v = float(op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION])
            if 0.1105 <= v <= 0.1115:
                op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION] = VOXEL_RES_DEFAULT
        except Exception:
            pass
        return True, flags | c4d.DESCFLAGS_DESC_LOADED

    def Message(self, op, msg_type, data):
        if msg_type == c4d.MSG_DESCRIPTION_COMMAND:
            try:
                desc_id = data["id"][0].id
            except Exception:
                desc_id = -1
            if desc_id == BRICKIFYASSEMBLY_REBUILD:
                _reload_brick_modules()
                self._fit_cache_key = None
                self._fit_placements = None
                self._hierarchy_cache_key = None
                self._force_rebuild = True
                self._mesh_cache = {}
                self._pending_auto_key = None
                self._pending_auto_since = 0.0
                self._last_resolution_key = None
                op.SetDirty(c4d.DIRTYFLAGS_DATA)
                # Force immediate reevaluation after the button press instead
                # of waiting for viewport/object-manager interaction.
                c4d.EventAdd()
            elif desc_id == BRICKIFYASSEMBLY_OPEN_LIBRARY_PICKER:
                self._open_library_picker(op)
            elif desc_id in (
                BRICKIFYASSEMBLY_LIB_PRESET_ALL,
                BRICKIFYASSEMBLY_LIB_PRESET_NONE,
                BRICKIFYASSEMBLY_LIB_PRESET_BRICKS,
                BRICKIFYASSEMBLY_LIB_PRESET_PLATES,
                BRICKIFYASSEMBLY_LIB_PRESET_1X1,
                BRICKIFYASSEMBLY_LIB_PRESET_INVERT,
            ):
                self._apply_library_preset(op, desc_id)
            elif (
                BRICKIFYASSEMBLY_THUMB_BASE
                <= desc_id
                < BRICKIFYASSEMBLY_THUMB_BASE + len(BRICK_TOGGLE_NAMES)
            ):
                i = int(desc_id - BRICKIFYASSEMBLY_THUMB_BASE)
                tid = _toggle_id(i)
                try:
                    op[tid] = not bool(op[tid])
                except Exception:
                    op[tid] = True
                _sync_library_mask_from_toggles(op)
                op.SetDirty(c4d.DIRTYFLAGS_DATA)
                c4d.EventAdd()
            elif desc_id == BRICKIFYASSEMBLY_HEIGHT_PRESET_FINE:
                op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT] = 2
                op.SetDirty(c4d.DIRTYFLAGS_DATA)
                c4d.EventAdd()
            elif desc_id == BRICKIFYASSEMBLY_HEIGHT_PRESET_BALANCED:
                op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT] = 3
                op.SetDirty(c4d.DIRTYFLAGS_DATA)
                c4d.EventAdd()
            elif desc_id == BRICKIFYASSEMBLY_HEIGHT_PRESET_BLOCKY:
                op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT] = 6
                op.SetDirty(c4d.DIRTYFLAGS_DATA)
                c4d.EventAdd()
        elif msg_type == c4d.MSG_DESCRIPTION_POSTSETPARAMETER:
            # Force immediate reevaluation while editing controls when
            # auto-rebuild is enabled (avoids waiting for viewport interaction).
            try:
                desc_id = -1
                try:
                    desc_id = data["descid"][0].id
                except Exception:
                    try:
                        desc_id = data["id"][0].id
                    except Exception:
                        desc_id = -1
                if (
                    bool(op[BRICKIFYASSEMBLY_AUTO_REBUILD])
                    and desc_id != BRICKIFYASSEMBLY_VOXEL_RESOLUTION
                ):
                    op.SetDirty(c4d.DIRTYFLAGS_DATA)
                    c4d.EventAdd()
                if desc_id == BRICKIFYASSEMBLY_LIBRARY_MASK:
                    _apply_library_mask_to_toggles(op, _read_library_mask(op))
                    op.SetDirty(c4d.DIRTYFLAGS_DATA)
                    c4d.EventAdd()
                elif (
                    BRICKIFYASSEMBLY_BRICK_BASE
                    <= desc_id
                    < BRICKIFYASSEMBLY_BRICK_BASE + len(BRICK_TOGGLE_NAMES)
                ):
                    _sync_library_mask_from_toggles(op)
                if desc_id in (
                    BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS,
                    BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES,
                ):
                    # This toggle is commonly A/B tested while dialing a model;
                    # force immediate reevaluation so users can see the effect
                    # without requiring manual "Rebuild Now".
                    self._fit_cache_key = None
                    self._hierarchy_cache_key = None
                    self._force_rebuild = True
                    op.SetDirty(c4d.DIRTYFLAGS_DATA)
                    c4d.EventAdd()
                if desc_id in (BRICKIFYASSEMBLY_SOURCE, BRICKIFYASSEMBLY_HIDE_SOURCE_MESH):
                    self._sync_source_visibility(op)
                    c4d.EventAdd()
            except Exception:
                pass
        return True

    def _get_active_library(self, op):
        """Return a brick.BrickLibrary filtered to enabled toggles.
        """
        from brick.library import BrickLibrary, BrickType, DEFAULT_LIBRARY

        # Keep legacy bool toggles in sync with native custom GUI bitmask.
        _apply_library_mask_to_toggles(op, _read_library_mask(op))

        enabled = []
        by_name = {b.name: b for b in DEFAULT_LIBRARY}
        toggled_names = set(BRICK_TOGGLE_NAMES)
        selected_toggle_names = set()
        try:
            enable_plates = bool(op[BRICKIFYASSEMBLY_ENABLE_PLATES])
        except Exception:
            enable_plates = False

        for i, name in enumerate(BRICK_TOGGLE_NAMES):
            try:
                on = bool(op[_toggle_id(i)])
            except Exception:
                on = True
            if on and name in by_name:
                selected_toggle_names.add(name)
                enabled.append(by_name[name])

        # If everything is off, intentionally return an empty library so users
        # can build selections tile-by-tile from a blank slate.
        if not selected_toggle_names:
            return BrickLibrary([])

        if enable_plates:
            for name in PLATE_LIBRARY_NAMES:
                bt = by_name.get(name)
                if bt is not None:
                    enabled.append(bt)

        # Add non-toggle variants (extra heights) only for footprints that are
        # currently selected by toggle controls.
        selected_footprints = {
            (b.width, b.depth) for b in enabled
        }
        for b in DEFAULT_LIBRARY:
            if b.name in toggled_names:
                # Canonical toggle-controlled members are already handled above.
                continue
            if b.name in PLATE_LIBRARY_NAMES:
                # Plate footprints are globally controlled by Enable Plates.
                continue
            if (b.width, b.depth) in selected_footprints:
                enabled.append(b)

        # Defensive expansion: guarantee meaningful max-height options 1..6
        # per enabled footprint even if a stale/default library only carries
        # plate (h=1) and brick (h=3) entries in this C4D session.
        by_key = {(b.width, b.depth, b.height): b for b in enabled}
        footprints = {(b.width, b.depth) for b in enabled}
        allowed_heights = (1, 2, 3, 4, 5, 6) if enable_plates else (2, 3, 4, 5, 6)
        for w, d in footprints:
            for h in allowed_heights:
                key = (w, d, h)
                if key in by_key:
                    continue
                bt = BrickType(
                    "brick_h{0}_{1}x{2}".format(h, w, d),
                    w,
                    d,
                    h,
                    "custom_h{0}_{1}x{2}".format(h, w, d),
                )
                enabled.append(bt)
                by_key[key] = bt
        return BrickLibrary(enabled)

    def _resolve_params(self, op, source_obj):
        # Voxel resolution — the new 0..1 slider is the source of truth.
        # If the parameter is unset (legacy scenes) fall back to the
        # studs-across integer.
        voxel_res = op[BRICKIFYASSEMBLY_VOXEL_RESOLUTION]
        if voxel_res is None:
            studs_across = max(VOXEL_RES_MIN_STUDS,
                               int(op[BRICKIFYASSEMBLY_STUDS_ACROSS] or 16))
        else:
            studs_across = _voxel_resolution_to_studs(voxel_res)
        studs_across = max(VOXEL_RES_MIN_STUDS,
                           min(VOXEL_RES_MAX_STUDS, studs_across))
        use_manual_stud_size = bool(op[BRICKIFYASSEMBLY_USE_MANUAL_STUD_SIZE])
        manual_stud_size = max(0.001, float(op[BRICKIFYASSEMBLY_STUD_SIZE] or 8.0))
        stud_size = manual_stud_size if use_manual_stud_size else None
        voxel_mode_id = int(op[BRICKIFYASSEMBLY_VOXEL_MODE])
        voxel_mode = "shell" if voxel_mode_id == BRICKIFYASSEMBLY_VOXEL_MODE_SHELL else "solid"
        shell_thickness = max(1, min(8, int(op[BRICKIFYASSEMBLY_SHELL_THICKNESS] or 3)))
        detail_mode_id = int(op[BRICKIFYASSEMBLY_DETAIL_MODE] or 0)
        detail_mode = {
            BRICKIFYASSEMBLY_DETAIL_MODE_BALANCED: "balanced",
            BRICKIFYASSEMBLY_DETAIL_MODE_PRESERVE: "preserve",
        }.get(detail_mode_id, "off")
        quality = int(op[BRICKIFYASSEMBLY_QUALITY])
        if quality not in ASSEMBLY_QUALITY_PRESETS:
            quality = 1
        # Library now exposes synthetic height variants so this cap is
        # meaningfully controllable from 1..6 plate units.
        max_bh = max(1, min(6, int(op[BRICKIFYASSEMBLY_MAX_BRICK_HEIGHT])))
        randomize_heights = bool(op[BRICKIFYASSEMBLY_HEIGHT_VARIATION])
        seed_raw = op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_SEED]
        if seed_raw is None:
            seed_raw = 1
        height_mix_seed = max(0, min(1000000, int(seed_raw)))

        mix_raw = op[BRICKIFYASSEMBLY_HEIGHT_VARIATION_AMOUNT]
        if mix_raw is None:
            mix_raw = 0.6
        # Perceptual response shaping: keep the stronger look of the original
        # mix behavior while spreading control a bit more evenly across 0..1.
        mix_linear = max(0.0, min(1.0, float(mix_raw)))
        height_mix_amount = mix_linear ** 1.3
        # When max_bh < 3, plates can't be promoted into bricks. The merge
        # step therefore must be suppressed so the fitter's plate output
        # stays plates.
        merge_plates_user = bool(op[BRICKIFYASSEMBLY_MERGE_PLATES])
        merge_plates = merge_plates_user and max_bh >= 3
        # 1x1-only libraries create many vertical "columns" that are not
        # top/bottom-coupled to each other in the structural graph. In that
        # specific mode, pruning to largest component collapses the model into
        # one center stack, so we auto-disable prune.
        lib_mask = _read_library_mask(op)
        # Keep legacy toggles synced before classifying library mode. The
        # native GUI writes a bitmask, while older scenes rely on per-toggle
        # bools; syncing here avoids stale mode detection.
        _apply_library_mask_to_toggles(op, lib_mask)
        try:
            enable_plates = bool(op[BRICKIFYASSEMBLY_ENABLE_PLATES])
        except Exception:
            enable_plates = False
        selected_toggle_names = []
        for i, name in enumerate(BRICK_TOGGLE_NAMES):
            try:
                if bool(op[_toggle_id(i)]):
                    selected_toggle_names.append(name)
            except Exception:
                # If a toggle read fails, treat it as enabled to avoid
                # accidentally entering restrictive auto-modes.
                selected_toggle_names.append(name)
        only_2x_library = (not enable_plates) and bool(selected_toggle_names) and all(
            ("_2x" in n) for n in selected_toggle_names
        )
        only_1x1_library = (not enable_plates) and bool(selected_toggle_names) and all(
            (n.endswith("_1x1") or n.endswith("1x1")) for n in selected_toggle_names
        )
        # With 2x-only libraries, detail-band restrictions can over-constrain
        # the fitter and produce carved-out facades. Force detail strategy off
        # so coverage stays stable for "2x only" workflows.
        if only_2x_library and detail_mode != "off":
            detail_mode = "off"
            try:
                op[BRICKIFYASSEMBLY_DETAIL_MODE] = BRICKIFYASSEMBLY_DETAIL_MODE_OFF
            except Exception:
                pass
        if only_2x_library and (not use_manual_stud_size):
            # 2x-only footprints tile in 2-cell quanta. At odd voxel resolution
            # widths (common around ~0.7 slider values), one-cell perimeter
            # strips become impossible to cover and look like "missing mass".
            # Snap auto resolution to an even studs-across value in this mode.
            if studs_across % 2 != 0:
                studs_across = min(VOXEL_RES_MAX_STUDS, studs_across + 1)
        prune_user = bool(op[BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY])
        # Hysteresis restore: if we auto-forced prune off at high Height Mix,
        # restore the user's original intent when mix comes back down.
        if (
            (not prune_user)
            and self._prune_auto_forced_off
            and randomize_heights
            and mix_linear <= PRUNE_AUTO_REENABLE_MIX_THRESHOLD
        ):
            try:
                op[BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY] = True
            except Exception:
                pass
            prune_user = True
            self._prune_auto_forced_off = False
        if not randomize_heights:
            self._prune_auto_forced_off = False
        prune = prune_user and (not only_1x1_library)
        prune_auto_disabled = False
        prune_auto_reason = ""
        if prune_user and only_1x1_library:
            prune_auto_disabled = True
            prune_auto_reason = "1x1-only library"
        # High height-mix intentionally introduces local structure variation.
        # In that mode, connectivity-prune can remove large valid regions.
        if (
            prune
            and randomize_heights
            and mix_linear >= PRUNE_AUTO_DISABLE_MIX_THRESHOLD
        ):
            prune = False
            prune_auto_disabled = True
            prune_auto_reason = "high Height Mix"
        # Keep UI state honest: when auto-disable triggers, flip the checkbox
        # off so users can see prune is inactive for this build.
        if prune_auto_disabled and prune_user:
            try:
                op[BRICKIFYASSEMBLY_PRUNE_CONNECTIVITY] = False
            except Exception:
                pass
            self._prune_auto_forced_off = True
        cleanup_protrusions = max(0, int(op[BRICKIFYASSEMBLY_CLEANUP_PROTRUSIONS]
                                         or 0))
        # In 1x1-only mode, protrusion cleanup tends to remove valid shelf/
        # ledge boundaries. Prioritize silhouette fidelity over cleanup.
        if only_1x1_library:
            cleanup_protrusions = 0
        # Preserve horizontal silhouette bands for 1x1 runs so stepped base
        # shelves stay intact instead of fragmenting into sparse leftovers.
        preserve_silhouette = bool(only_1x1_library or only_2x_library)
        preserve_tiny_gaps = bool(op[BRICKIFYASSEMBLY_PRESERVE_TINY_GAPS])
        # UI override for plate placement policy.
        surface_only_plates_ui = bool(op[BRICKIFYASSEMBLY_SURFACE_ONLY_PLATES])
        # Apply in both solid and shell voxel modes, but only when plate usage
        # itself is enabled.
        surface_only_plates = bool(surface_only_plates_ui and enable_plates)
        color_mode = int(op[BRICKIFYASSEMBLY_COLOR_MODE])
        visualization_mode = int(op[BRICKIFYASSEMBLY_VISUALIZATION_MODE] or 0)
        # "Brick Size" and "Shell Depth" were removed from the UI cycle.
        # Coerce legacy scene values to Source Color so old files remain valid.
        if visualization_mode in (
            BRICKIFYASSEMBLY_VISUALIZATION_MODE_BRICK_SIZE,
            BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_DEPTH,
        ):
            visualization_mode = BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE
            try:
                op[BRICKIFYASSEMBLY_VISUALIZATION_MODE] = visualization_mode
            except Exception:
                pass
        auto_rebuild = bool(op[BRICKIFYASSEMBLY_AUTO_REBUILD])

        base_rgb = (180, 180, 180)
        if color_mode == BRICKIFYASSEMBLY_COLOR_MODE_MATERIAL and source_obj is not None:
            mat_rgb = _source_material_color(source_obj)
            if mat_rgb is not None:
                base_rgb = mat_rgb

        # Library curation key — bitmask over brick toggles. Goes
        # into the fit cache key so toggling a brick reruns the fitter.
        lib_mask = _read_library_mask(op)

        return {
            "studs_across": studs_across,
            "use_manual_stud_size": use_manual_stud_size,
            "stud_size": stud_size,
            "voxel_mode": voxel_mode,
            "shell_thickness": shell_thickness,
            "detail_mode": detail_mode,
            "quality": quality,
            "max_brick_height": max_bh,
            "randomize_heights": randomize_heights,
            "height_mix_seed": height_mix_seed,
            "height_mix_amount": height_mix_amount,
            "height_mix_amount_ui": mix_linear,
            "merge_plates": merge_plates,
            "prune": prune,
            "prune_user": prune_user,
            "prune_auto_disabled": prune_auto_disabled,
            "prune_auto_reason": prune_auto_reason,
            "only_1x1_library": only_1x1_library,
            "cleanup_protrusions": cleanup_protrusions,
            "preserve_silhouette": preserve_silhouette,
            "preserve_tiny_gaps": preserve_tiny_gaps,
            "surface_only_plates": surface_only_plates,
            "enable_plates": enable_plates,
            "color_mode": color_mode,
            "visualization_mode": visualization_mode,
            "auto_rebuild": auto_rebuild,
            "base_rgb": base_rgb,
            "lib_mask": lib_mask,
        }

    def _make_fit_key(self, source_obj, params):
        src_dirty = source_obj.GetDirty(
            c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_CACHE
        )
        return (
            source_obj.GetGUID(),
            src_dirty,
            params["studs_across"],
            params["use_manual_stud_size"],
            params["stud_size"],
            params["voxel_mode"],
            params["shell_thickness"],
            params["detail_mode"],
            params["max_brick_height"],
            params["randomize_heights"],
            params["height_mix_seed"],
            params["height_mix_amount"],
            params["merge_plates"],
            params["prune"],
            params["cleanup_protrusions"],
            params["preserve_silhouette"],
            params["preserve_tiny_gaps"],
            params["surface_only_plates"],
            params["enable_plates"],
            params["lib_mask"],
        )

    def _last_hierarchy_clone(self):
        if self._last_hierarchy_obj is None:
            return None
        try:
            return self._last_hierarchy_obj.GetClone(c4d.COPYFLAGS_NONE)
        except Exception:
            return None

    def _resolution_key(self, params):
        return (
            params["studs_across"],
            bool(params["use_manual_stud_size"]),
            round(float(params["stud_size"] or -1.0), 6),
        )

    def _refit_if_needed(self, op, doc):
        from brick.pipeline import brick_mesh

        source_obj = op[BRICKIFYASSEMBLY_SOURCE]
        if source_obj is None:
            self._fit_cache_key = None
            self._fit_placements = None
            self._fit_info = None
            return False

        params = self._resolve_params(op, source_obj)
        fit_key = self._make_fit_key(source_obj, params)
        if self._fit_cache_key == fit_key and self._fit_placements is not None:
            return True

        baked = _baked_polygon_object(source_obj, doc)
        if baked is None or baked.GetPointCount() == 0:
            self._fit_cache_key = None
            self._fit_placements = None
            return False

        verts, faces, vcolors = _polygon_object_to_arrays(baked)
        if len(faces) == 0:
            self._fit_cache_key = None
            self._fit_placements = None
            return False

        active_library = self._get_active_library(op)
        try:
            has_bricks = bool(getattr(active_library, "bricks", []))
        except Exception:
            has_bricks = True
        if not has_bricks:
            self._fit_cache_key = fit_key
            self._fit_placements = []
            self._fit_info = {"note": "No brick types selected."}
            return True

        placements, info = brick_mesh(
            verts, faces,
            vertex_colors=vcolors,
            default_color=params["base_rgb"],
            studs_across=params["studs_across"],
            stud_size=params["stud_size"],
            voxel_mode=params["voxel_mode"],
            shell_thickness=params["shell_thickness"],
            detail_mode=params["detail_mode"],
            max_brick_height=params["max_brick_height"],
            randomize_heights=params["randomize_heights"],
            height_mix_seed=params["height_mix_seed"],
            height_mix_amount=params["height_mix_amount"],
            merge_plates=params["merge_plates"],
            prune_connectivity=params["prune"],
            cleanup_protrusions=params["cleanup_protrusions"],
            preserve_silhouette=params["preserve_silhouette"],
            preserve_tiny_gaps=params["preserve_tiny_gaps"],
            surface_only_plates=params["surface_only_plates"],
            library=active_library,
            min_column_voxels=0,
        )
        info["prune_auto_disabled"] = bool(params.get("prune_auto_disabled"))
        info["prune_auto_reason"] = str(params.get("prune_auto_reason") or "")
        info["prune_user"] = bool(params.get("prune_user"))
        info["height_mix_amount_ui"] = float(params.get("height_mix_amount_ui", 0.0))
        if params.get("prune_auto_disabled"):
            warn_key = (
                source_obj.GetGUID(),
                bool(params.get("prune_user")),
                bool(params.get("randomize_heights")),
                round(float(params.get("height_mix_amount_ui", 0.0)), 3),
                str(params.get("prune_auto_reason") or ""),
            )
            if warn_key != self._last_prune_warning_key:
                try:
                    c4d.GePrint(
                        "[brick] Build Cleanup: 'Prune to Largest Component' "
                        "auto-disabled ({0}). Reason: {1}. "
                        "Set Height Mix below {2:.2f} (re-enable threshold "
                        "{3:.2f}) or disable Height Mix to re-enable prune.".format(
                            "ON" if bool(params.get("prune_user")) else "OFF",
                            params.get("prune_auto_reason") or "n/a",
                            PRUNE_AUTO_DISABLE_MIX_THRESHOLD,
                            PRUNE_AUTO_REENABLE_MIX_THRESHOLD,
                        )
                    )
                except Exception:
                    pass
                self._last_prune_warning_key = warn_key
        else:
            self._last_prune_warning_key = None
        self._fit_cache_key = fit_key
        self._fit_placements = placements
        self._fit_info = info
        return True

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
        from brick.brick_geom_hires import make_brick_hires
        is_smooth_visual = int(
            bool(
                force_smooth_top
                or (
                    getattr(brick_type, "height", 0) == 1
                    and bool(smooth_plate_visual)
                )
            )
        )
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

    def _build_hierarchy(self, op):
        info = self._fit_info or {}
        params = self._resolve_params(op, op[BRICKIFYASSEMBLY_SOURCE])
        visualization_mode = params["visualization_mode"]

        # Voxel Debug must work even when there are no placements yet (e.g.
        # nothing in the brick library, or pipeline returned nothing because
        # of pruning). Otherwise the user has no way to inspect the voxel
        # grid. So defer the empty-placements early-return to non-debug modes.
        if not self._fit_placements and visualization_mode != BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG:
            return None
        if not info:
            return None

        stud_size = info.get("stud_size", 8.0)
        plate_size = info.get("plate_size", 3.2)
        origin = info.get("origin")
        if origin is None:
            return None
        quality = params["quality"]

        result = c4d.BaseObject(c4d.Onull)
        source_obj = op[BRICKIFYASSEMBLY_SOURCE]
        src_name = source_obj.GetName() if source_obj is not None else "mesh"
        result.SetName("Brickified_{0}".format(src_name))
        doc = op.GetDocument()

        templates_root = c4d.BaseObject(c4d.Onull)
        templates_root.SetName("brick_templates")
        TEMPLATES_PARK_Y = 1.0e9
        park_m = c4d.Matrix()
        park_m.off = c4d.Vector(0.0, TEMPLATES_PARK_Y, 0.0)
        templates_root.SetMl(park_m)
        templates_root.InsertUnder(result)

        instances_root = c4d.BaseObject(c4d.Onull)
        instances_root.SetName("bricks")
        instances_root.InsertUnder(result)

        type_to_template = {}

        def _get_template_obj(
            brick_type,
            variant_key=None,
            smooth_plate_visual=True,
            force_smooth_top=False,
        ):
            tkey = (
                brick_type.width,
                brick_type.depth,
                brick_type.height,
                variant_key,
                int(bool(smooth_plate_visual)),
                int(bool(force_smooth_top)),
            )
            if tkey in type_to_template:
                return type_to_template[tkey]
            mesh = self._get_template_mesh(
                brick_type,
                quality,
                stud_size,
                plate_size,
                smooth_plate_visual=smooth_plate_visual,
                force_smooth_top=force_smooth_top,
            )
            t_obj = mesh_to_polygon_object(
                mesh, name="tmpl_{0}x{1}x{2}p".format(
                    brick_type.width, brick_type.depth, brick_type.height
                )
            )
            t_obj.InsertUnder(templates_root)
            type_to_template[tkey] = t_obj
            return t_obj

        mi_mode = getattr(c4d, "INSTANCEOBJECT_RENDERINSTANCE_MODE_MULTIINSTANCE", 2)

        from collections import defaultdict
        shell_depths = info.get("placement_shell_depths") or []
        depth_by_obj = {
            id(p): int(shell_depths[i])
            for i, p in enumerate(self._fit_placements)
            if i < len(shell_depths)
        }
        smooth_top_by_obj = {}
        if bool(params.get("surface_only_plates")):
            # Robust visual rule: when surface-only policy is active, render all
            # non-plate placements with studless tops. This avoids rare "rogue"
            # exposed studs that can appear with extreme height-mix solutions.
            for p in self._fit_placements:
                smooth_top_by_obj[id(p)] = bool(
                    int(getattr(p.brick, "height", 0)) > 1
                )

        smooth_plate_visual = bool(params.get("surface_only_plates"))

        by_type = defaultdict(list)
        for p in self._fit_placements:
            # Keep 90-degree placements in separate batches so we can use
            # swapped-footprint templates and avoid per-instance rotation
            # offset ambiguity in C4D matrix space.
            smooth_top_visual = int(bool(smooth_top_by_obj.get(id(p), False)))
            tkey = (
                p.brick.width,
                p.brick.depth,
                p.brick.height,
                p.rotation_y,
                smooth_top_visual,
            )
            by_type[tkey].append(p)

        def _lerp(a, b, t):
            return a + (b - a) * max(0.0, min(1.0, t))

        def _debug_color(p):
            if visualization_mode == BRICKIFYASSEMBLY_VISUALIZATION_MODE_BRICK_SIZE:
                footprint = max(1, int(p.w * p.d))
                t = min(1.0, (footprint - 1.0) / 15.0)
                return c4d.Vector(
                    _lerp(0.10, 1.0, t),
                    _lerp(0.35, 0.20, t),
                    _lerp(1.0, 0.05, t),
                )
            if visualization_mode in (
                BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_DEPTH,
                BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME,
            ):
                depth = max(1, depth_by_obj.get(id(p), 1))
                t = min(1.0, (depth - 1.0) / 5.0)
                return c4d.Vector(
                    _lerp(1.0, 0.05, t),
                    _lerp(0.35, 0.75, t),
                    _lerp(0.05, 1.0, t),
                )
            if params["color_mode"] == BRICKIFYASSEMBLY_COLOR_MODE_MATERIAL:
                r, g, b = params["base_rgb"]
                return c4d.Vector(r / 255.0, g / 255.0, b / 255.0)
            r, g, b = p.rgb
            return c4d.Vector(r / 255.0, g / 255.0, b / 255.0)

        def _color_key(v):
            return (
                int(round(max(0.0, min(1.0, v.x)) * 255.0)),
                int(round(max(0.0, min(1.0, v.y)) * 255.0)),
                int(round(max(0.0, min(1.0, v.z)) * 255.0)),
            )

        def _apply_object_color(obj, color):
            try:
                obj[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
                obj[c4d.ID_BASEOBJECT_COLOR] = color
            except Exception:
                pass

        debug_materials = {}

        def _get_debug_material(color_key, color, transparent=False):
            if color_key is None or doc is None:
                return None
            mat_key = (color_key, bool(transparent))
            if mat_key in debug_materials:
                return debug_materials[mat_key]
            suffix = "Fill" if transparent else "Line"
            name = "Brick_Debug_{0}_{1}_{2}_{3}".format(
                color_key[0], color_key[1], color_key[2], suffix
            )
            mat = None
            try:
                mat = doc.SearchMaterial(name)
            except Exception:
                mat = None
            if mat is None:
                mat = c4d.BaseMaterial(c4d.Mmaterial)
                mat.SetName(name)
                doc.InsertMaterial(mat)
            try:
                mat[c4d.MATERIAL_COLOR_COLOR] = color
                mat[c4d.MATERIAL_COLOR_BRIGHTNESS] = 1.0
                if transparent:
                    mat[c4d.MATERIAL_USE_TRANSPARENCY] = True
                    mat[c4d.MATERIAL_TRANSPARENCY_BRIGHTNESS] = 0.72
                    mat[c4d.MATERIAL_TRANSPARENCY_COLOR] = color
                else:
                    mat[c4d.MATERIAL_USE_TRANSPARENCY] = False
                mat.Message(c4d.MSG_UPDATE)
            except Exception:
                pass
            debug_materials[mat_key] = mat
            return mat

        def _apply_material(obj, mat):
            if mat is None:
                return
            try:
                tag = c4d.TextureTag()
            except AttributeError:
                tag = c4d.BaseTag(c4d.Ttexture)
            tag[c4d.TEXTURETAG_MATERIAL] = mat
            obj.InsertTag(tag)

        def _make_wire_spline(name, placements):
            edge_count = len(placements) * 12
            point_count = edge_count * 2
            spline = c4d.SplineObject(point_count, c4d.SPLINETYPE_LINEAR)
            spline.SetName(name)
            try:
                spline.ResizeObject(point_count, edge_count)
            except Exception:
                pass

            edges = (
                (0, 1), (1, 2), (2, 3), (3, 0),
                (4, 5), (5, 6), (6, 7), (7, 4),
                (0, 4), (1, 5), (2, 6), (3, 7),
            )
            point_idx = 0
            segment_idx = 0
            for p in placements:
                x0 = float(origin[0] + p.x * stud_size)
                y0 = float(origin[1] + p.y * plate_size)
                z0 = float(origin[2] + p.z * stud_size)
                x1 = x0 + float(p.w * stud_size)
                y1 = y0 + float(p.h * plate_size)
                z1 = z0 + float(p.d * stud_size)
                pts = (
                    c4d.Vector(x0, y0, z0),
                    c4d.Vector(x1, y0, z0),
                    c4d.Vector(x1, y0, z1),
                    c4d.Vector(x0, y0, z1),
                    c4d.Vector(x0, y1, z0),
                    c4d.Vector(x1, y1, z0),
                    c4d.Vector(x1, y1, z1),
                    c4d.Vector(x0, y1, z1),
                )
                for a, b in edges:
                    spline.SetPoint(point_idx, pts[a])
                    spline.SetPoint(point_idx + 1, pts[b])
                    try:
                        spline.SetSegment(segment_idx, 2, False)
                    except Exception:
                        pass
                    point_idx += 2
                    segment_idx += 1
            spline.Message(c4d.MSG_UPDATE)
            return spline

        def _make_fill_boxes(name, boxes):
            point_count = len(boxes) * 8
            poly_count = len(boxes) * 6
            obj = c4d.PolygonObject(point_count, poly_count)
            obj.SetName(name)
            pi = 0
            fi = 0
            for x, y, z, w, h, d in boxes:
                x0 = float(origin[0] + x * stud_size)
                y0 = float(origin[1] + y * plate_size)
                z0 = float(origin[2] + z * stud_size)
                x1 = x0 + float(w * stud_size)
                y1 = y0 + float(h * plate_size)
                z1 = z0 + float(d * stud_size)
                pts = (
                    c4d.Vector(x0, y0, z0),
                    c4d.Vector(x1, y0, z0),
                    c4d.Vector(x1, y0, z1),
                    c4d.Vector(x0, y0, z1),
                    c4d.Vector(x0, y1, z0),
                    c4d.Vector(x1, y1, z0),
                    c4d.Vector(x1, y1, z1),
                    c4d.Vector(x0, y1, z1),
                )
                for offset, point in enumerate(pts):
                    obj.SetPoint(pi + offset, point)
                faces = (
                    (0, 1, 2, 3),
                    (4, 7, 6, 5),
                    (0, 4, 5, 1),
                    (1, 5, 6, 2),
                    (2, 6, 7, 3),
                    (3, 7, 4, 0),
                )
                for face in faces:
                    obj.SetPolygon(
                        fi,
                        c4d.CPolygon(
                            pi + face[0],
                            pi + face[1],
                            pi + face[2],
                            pi + face[3],
                        ),
                    )
                    fi += 1
                pi += 8
            obj.Message(c4d.MSG_UPDATE)
            return obj

        if visualization_mode == BRICKIFYASSEMBLY_VISUALIZATION_MODE_VOXEL_DEBUG:
            occ_cells = info.get("occupancy_cells")
            occ_list = list(occ_cells) if occ_cells else []
            n_placements = len(self._fit_placements or [])
            try:
                c4d.GePrint(
                    "[brick] Voxel Debug: n_voxels={0}, n_placements={1}, "
                    "grid_dims={2}, voxel_components={3}, voxels_dropped={4}".format(
                        len(occ_list),
                        n_placements,
                        info.get("grid_dims"),
                        info.get("voxel_components"),
                        info.get("n_voxels_dropped"),
                    )
                )
            except Exception:
                pass

            vox_color = c4d.Vector(1.0, 0.55, 0.10)
            vox_key = _color_key(vox_color)

            try:
                if occ_list:
                    vox_boxes = [(x, y, z, 1, 1, 1) for x, y, z in occ_list]
                    vox_obj = _make_fill_boxes(
                        "voxel_debug_occupancy", vox_boxes
                    )
                    _apply_object_color(vox_obj, vox_color)
                    _apply_material(
                        vox_obj,
                        _get_debug_material(
                            vox_key, vox_color, transparent=True
                        ),
                    )
                    vox_obj.InsertUnder(instances_root)
                elif self._fit_placements:
                    # Fallback: pipeline didn't supply occupancy cells (stale
                    # module load, etc.). Render the union of placement
                    # footprints so the debug view always shows SOMETHING.
                    fb_color = c4d.Vector(1.0, 0.20, 0.20)
                    fb_key = _color_key(fb_color)
                    fb_boxes = [
                        (p.x, p.y, p.z, p.w, p.h, p.d)
                        for p in self._fit_placements
                    ]
                    fb_obj = _make_fill_boxes(
                        "voxel_debug_placements_fallback", fb_boxes
                    )
                    _apply_object_color(fb_obj, fb_color)
                    _apply_material(
                        fb_obj,
                        _get_debug_material(
                            fb_key, fb_color, transparent=True
                        ),
                    )
                    fb_obj.InsertUnder(instances_root)
                else:
                    try:
                        c4d.GePrint(
                            "[brick] Voxel Debug: no occupancy_cells "
                            "and no placements. Pipeline produced nothing."
                        )
                    except Exception:
                        pass
            except Exception as exc:
                try:
                    c4d.GePrint(
                        "[brick] Voxel Debug: error rendering "
                        "boxes: {0}".format(exc)
                    )
                except Exception:
                    pass
            return result

        if visualization_mode == BRICKIFYASSEMBLY_VISUALIZATION_MODE_SHELL_WIREFRAME:
            void_cells = info.get("interior_void_cells") or []
            if void_cells:
                void_boxes = [(x, y, z, 1, 1, 1) for x, y, z in void_cells]
                void_color = c4d.Vector(0.10, 0.55, 1.0)
                void_key = _color_key(void_color)
                fill = _make_fill_boxes("hollow_interior_fill", void_boxes)
                _apply_object_color(fill, void_color)
                _apply_material(
                    fill,
                    _get_debug_material(void_key, void_color, transparent=True),
                )
                fill.InsertUnder(instances_root)

            wire_batches = defaultdict(list)
            for p in self._fit_placements:
                wire_batches[_color_key(_debug_color(p))].append(p)
            for color_key, batch in wire_batches.items():
                color = _debug_color(batch[0])
                wire = _make_wire_spline(
                    "shell_wire_{0}_{1}_{2}".format(*color_key),
                    batch,
                )
                _apply_object_color(wire, color)
                _apply_material(
                    wire,
                    _get_debug_material(color_key, color, transparent=False),
                )
                wire.InsertUnder(instances_root)
            return result

        for tkey, plist in by_type.items():
            batches = defaultdict(list)
            if visualization_mode == BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE:
                batches[None] = plist
            else:
                for p in plist:
                    batches[_color_key(_debug_color(p))].append(p)

            for color_key, batch in batches.items():
                batch_color = _debug_color(batch[0])
                material_key = _color_key(batch_color)
                debug_mat = None
                template_variant = None
                smooth_top_visual = bool(tkey[4]) if len(tkey) > 4 else False
                if visualization_mode != BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE:
                    debug_mat = _get_debug_material(
                        material_key, batch_color, transparent=False
                    )
                    template_variant = material_key

                p0 = batch[0]
                if p0.rotation_y == 90:
                    from types import SimpleNamespace
                    template_brick = SimpleNamespace(
                        width=p0.brick.depth,
                        depth=p0.brick.width,
                        height=p0.brick.height,
                    )
                else:
                    template_brick = p0.brick
                template = _get_template_obj(
                    template_brick,
                    template_variant,
                    smooth_plate_visual=smooth_plate_visual,
                    force_smooth_top=smooth_top_visual,
                )
                _apply_object_color(template, batch_color)
                _apply_material(template, debug_mat)

                inst = c4d.BaseObject(c4d.Oinstance)
                if color_key is None:
                    inst.SetName(
                        "bricks_{0}x{1}x{2}p_r{3}".format(
                            tkey[0], tkey[1], tkey[2], tkey[3]
                        )
                    )
                else:
                    inst.SetName(
                        "bricks_{0}x{1}x{2}p_r{3}_dbg_{4}_{5}_{6}".format(
                            tkey[0], tkey[1], tkey[2],
                            tkey[3],
                            color_key[0], color_key[1], color_key[2],
                        )
                    )
                inst[c4d.INSTANCEOBJECT_LINK] = template
                _apply_object_color(inst, batch_color)
                _apply_material(inst, debug_mat)
                try:
                    inst[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = int(mi_mode)
                except Exception:
                    pass

                matrices = []
                colors = []
                for p in batch:
                    wx = float(origin[0] + p.x * stud_size)
                    wy = float(origin[1] + p.y * plate_size)
                    wz = float(origin[2] + p.z * stud_size)
                    m = c4d.Matrix()
                    m.off = c4d.Vector(wx, wy, wz)
                    matrices.append(m)
                    colors.append(_debug_color(p))

                try:
                    inst.SetInstanceMatrices(matrices)
                except AttributeError:
                    inst[c4d.INSTANCEOBJECT_MULTIPOSITIONS] = matrices
                try:
                    inst.SetInstanceColors(colors)
                except Exception:
                    pass

                inst.InsertUnder(instances_root)

        return result

    def GetVirtualObjects(self, op, hh):
        _ensure_brick_on_path()

        try:
            import brick.pipeline  # noqa: F401
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Failed to import brick.pipeline. Ensure the brick "
                "package is reachable and numpy/scipy are installed in "
                "Cinema 4D's Python environment."
            ) from exc

        if op[BRICKIFYASSEMBLY_SOURCE] is None:
            self._restore_managed_source()
            return None

        source_obj = op[BRICKIFYASSEMBLY_SOURCE]
        self._sync_source_visibility(op)
        params = self._resolve_params(op, source_obj)
        # Startup responsiveness: first scene-open evaluation runs in draft.
        if self._startup_draft_pending and not self._force_rebuild:
            params = dict(params)
            params["quality"] = BRICKGENERATOR_QUALITY_DRAFT
        res_key = self._resolution_key(params)

        if not params["auto_rebuild"] and not self._force_rebuild:
            cached = op.GetCache(hh)
            if cached is not None:
                return cached
            stale = self._last_hierarchy_clone()
            if stale is not None:
                return stale
            # First scene load has no cache yet; allow one initial build so
            # the assembly is visible immediately without requiring selection/
            # viewport interaction.

        # Resolution changes are manual-only to avoid the known C4D crash
        # path while editing this parameter in the Attribute Manager.
        if (
            params["auto_rebuild"]
            and not self._force_rebuild
            and self._last_resolution_key is not None
            and res_key != self._last_resolution_key
        ):
            cached = op.GetCache(hh)
            if cached is not None:
                return cached
            stale = self._last_hierarchy_clone()
            if stale is not None:
                return stale
            return c4d.BaseObject(c4d.Onull)

        src_dirty = source_obj.GetDirty(
            c4d.DIRTYFLAGS_DATA | c4d.DIRTYFLAGS_CACHE
        )
        hierarchy_key = (
            source_obj.GetGUID(),
            src_dirty,
            params["studs_across"],
            params["use_manual_stud_size"],
            params["stud_size"],
            params["voxel_mode"],
            params["shell_thickness"],
            params["detail_mode"],
            params["quality"],
            params["max_brick_height"],
            params["randomize_heights"],
            params["height_mix_seed"],
            params["height_mix_amount"],
            params["merge_plates"],
            params["prune"],
            params["cleanup_protrusions"],
            params["preserve_silhouette"],
            params["preserve_tiny_gaps"],
            params["surface_only_plates"],
            params["enable_plates"],
            params["color_mode"],
            params["visualization_mode"],
            params["base_rgb"],
            params["lib_mask"],
        )

        cached = op.GetCache(hh)
        if (
            not self._force_rebuild
            and cached is not None
            and self._hierarchy_cache_key == hierarchy_key
        ):
            return cached

        doc = op.GetDocument()
        if doc is None and hh is not None:
            try:
                doc = hh.GetDocument()
            except Exception:
                doc = None

        if not self._refit_if_needed(op, doc):
            return None

        result = self._build_hierarchy(op)
        self._hierarchy_cache_key = hierarchy_key
        if result is not None:
            try:
                self._last_hierarchy_obj = result.GetClone(c4d.COPYFLAGS_NONE)
            except Exception:
                self._last_hierarchy_obj = None
        else:
            self._last_hierarchy_obj = None
        self._last_resolution_key = res_key
        self._pending_auto_key = None
        self._pending_auto_since = 0.0
        self._force_rebuild = False
        self._startup_draft_pending = False
        return result


# =====================================================================
# Icon registration helpers
# =====================================================================

def _load_bitmap(path):
    """Return a BaseBitmap from `path`, or None if it can't be loaded."""
    if not path or not os.path.isfile(path):
        return None
    bmp = c4d.bitmaps.BaseBitmap()
    bmp.InitWith(path)
    if bmp.GetBw() <= 0 or bmp.GetBh() <= 0:
        return None
    return bmp


def _register_brick_icons():
    """Register the hero banner icon and brick thumbnails so the
    description's BITMAPBUTTONs can resolve their ICONIDs."""
    here = os.path.dirname(os.path.abspath(__file__))
    res_dir = os.path.join(here, "res")
    icons_dir = os.path.join(res_dir, "icons", "bricks")

    # Hero banner — used by the BITMAPBUTTON at the top of the AM.
    hero_path = os.path.join(res_dir, "brickify_hero.png")
    hero_bmp = _load_bitmap(hero_path)
    if hero_bmp is not None:
        try:
            c4d.gui.RegisterIcon(ICON_BRICKIFY_HERO, hero_bmp)
        except Exception as exc:
            print("[brick] hero icon register failed:", exc)
    else:
        print("[brick] hero banner not found at", hero_path)

    # Brick thumbnails. Use the @64 variants for crisper rendering on
    # high-DPI displays — C4D scales down to the AM's row height.
    for i, name in enumerate(BRICK_TOGGLE_NAMES):
        for suffix in ("@64", "@2x", ""):
            candidate = os.path.join(icons_dir, "{0}{1}.png".format(name, suffix))
            if os.path.isfile(candidate):
                bmp = _load_bitmap(candidate)
                if bmp is not None:
                    try:
                        c4d.gui.RegisterIcon(ICON_BRICKIFY_BRICK_BASE + i, bmp)
                    except Exception as exc:
                        print(
                            "[brick] icon {0} register failed: {1}"
                            .format(name, exc)
                        )
                break
        else:
            print("[brick] brick thumbnail missing:", name)


def register():
    def _load_plugin_icon():
        # The Object Manager tree shows this next to every BrickAssembly
        # / BrickGen entry. brickify_icon.png is the dedicated 64x64
        # red 2x2 brick render produced by tools/prepare_branding_assets.py;
        # the isometric thumbnails are the AM gallery fallback for older
        # deployments that don't have the rendered icon yet.
        here = os.path.dirname(os.path.abspath(__file__))
        for candidate in (
            os.path.join(here, "res", "brickify_icon.png"),
            os.path.join(here, "res", "icons", "bricks", "brick_2x2@64.png"),
            os.path.join(here, "res", "icons", "bricks", "brick_2x2@2x.png"),
            os.path.join(here, "res", "icons", "bricks", "brick_2x2.png"),
        ):
            bmp = _load_bitmap(candidate)
            if bmp is not None:
                return bmp
        return None

    # Register brick thumbnail icons FIRST so the description widgets can
    # resolve them on first AM display.
    try:
        _register_brick_icons()
    except Exception as exc:
        print("[brick] icon registration error:", exc)

    icon = _load_plugin_icon()
    ok1 = plugins.RegisterObjectPlugin(
        id=ID_BRICKGENERATOR,
        str=IDS_BRICKGENERATOR,
        g=BrickGen,
        description="obrickgenerator",
        info=c4d.OBJECT_GENERATOR,
        icon=icon,
    )
    ok2 = plugins.RegisterObjectPlugin(
        id=ID_BRICKIFYASSEMBLY,
        str=IDS_BRICKIFYASSEMBLY,
        g=BrickAssembly,
        description="obrickifyassembly",
        info=c4d.OBJECT_GENERATOR | c4d.OBJECT_INPUT,
        icon=icon,
    )
    # BrickLibraryPanelCommand is intentionally not registered as a standalone
    # command plugin. The library UI is kept embedded in BrickIt's Attribute
    # Manager instead of showing a separate "Brick Panel" plugin entry.
    return ok1 and ok2


if __name__ == "__main__":
    register()
