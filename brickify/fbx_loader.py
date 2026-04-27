"""Minimal binary FBX parser -- enough to extract mesh geometry.

Supports FBX binary versions 7000+ (the common Autodesk binary format used
by Maya / Max / C4D / Blender exports). NOT a complete FBX implementation;
we only walk the node tree and pull out:

  - Objects > Geometry > Vertices         (doubles, xyz xyz xyz...)
  - Objects > Geometry > PolygonVertexIndex (int32, negative = polygon end)

Each Geometry node becomes one (verts, faces) pair. Polygons of any size
are fan-triangulated. Multiple meshes in a single file are returned as
a list; the caller merges/colors them.

Reference: Blockade Games's `pyfbx` plus the community-reverse-engineered
spec at https://code.blender.org/2013/08/fbx-binary-file-format-specification/
"""
import struct
import zlib
from typing import List, Tuple, Any, Optional
import numpy as np


class FBXNode:
    __slots__ = ("name", "props", "children")

    def __init__(self, name: str, props: list, children: list):
        self.name = name
        self.props = props
        self.children = children

    def find_all(self, name: str) -> List["FBXNode"]:
        out = []
        if self.name == name:
            out.append(self)
        for c in self.children:
            out += c.find_all(name)
        return out

    def find(self, name: str) -> Optional["FBXNode"]:
        if self.name == name:
            return self
        for c in self.children:
            r = c.find(name)
            if r is not None:
                return r
        return None

    def __repr__(self):
        return f"FBXNode({self.name!r}, {len(self.props)} props, {len(self.children)} children)"


def _read_property(buf: memoryview, off: int) -> Tuple[Any, int]:
    """Read one property starting at off. Returns (value, new_offset)."""
    type_code = chr(buf[off])
    off += 1
    if type_code == "Y":   # int16
        v, = struct.unpack_from("<h", buf, off); off += 2
    elif type_code == "C": # bool
        v = bool(buf[off]); off += 1
    elif type_code == "I": # int32
        v, = struct.unpack_from("<i", buf, off); off += 4
    elif type_code == "F": # float32
        v, = struct.unpack_from("<f", buf, off); off += 4
    elif type_code == "D": # float64
        v, = struct.unpack_from("<d", buf, off); off += 8
    elif type_code == "L": # int64
        v, = struct.unpack_from("<q", buf, off); off += 8
    elif type_code in ("f", "d", "l", "i", "b"):
        # Array
        array_len, encoding, comp_len = struct.unpack_from("<III", buf, off); off += 12
        raw = bytes(buf[off:off + comp_len]); off += comp_len
        if encoding == 1:
            raw = zlib.decompress(raw)
        # decode by element type
        item = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "b"}[type_code]
        item_size = struct.calcsize("<" + item)
        v = np.frombuffer(raw[:array_len * item_size],
                          dtype=np.dtype("<" + item)).copy()
    elif type_code == "S": # string
        length, = struct.unpack_from("<I", buf, off); off += 4
        v = bytes(buf[off:off + length]).decode("utf-8", errors="replace")
        off += length
    elif type_code == "R": # raw
        length, = struct.unpack_from("<I", buf, off); off += 4
        v = bytes(buf[off:off + length])
        off += length
    else:
        raise ValueError(f"Unknown FBX property type {type_code!r} at offset {off-1}")
    return v, off


def _read_node(buf: memoryview, off: int, version: int) -> Tuple[Optional[FBXNode], int]:
    """Read one node at offset. Returns (node_or_None_for_terminator, new_offset)."""
    # In v7500+, header fields are uint64; in earlier versions, uint32.
    if version >= 7500:
        end_offset, num_props, prop_list_len = struct.unpack_from("<QQQ", buf, off)
        off += 24
        null_record_len = 25
    else:
        end_offset, num_props, prop_list_len = struct.unpack_from("<III", buf, off)
        off += 12
        null_record_len = 13

    # null terminator record
    if end_offset == 0:
        return None, off + null_record_len - (24 if version >= 7500 else 12)

    name_len = buf[off]; off += 1
    name = bytes(buf[off:off + name_len]).decode("ascii", errors="replace")
    off += name_len

    props = []
    prop_end = off + prop_list_len
    for _ in range(num_props):
        v, off = _read_property(buf, off)
        props.append(v)
    assert off == prop_end, f"property block size mismatch in {name!r}"

    # children until end_offset
    children = []
    while off < end_offset:
        child, off = _read_node(buf, off, version)
        if child is None:
            break
        children.append(child)

    # advance to end_offset just in case (handles trailing null record)
    off = end_offset
    return FBXNode(name, props, children), off


def parse_fbx(path: str) -> FBXNode:
    """Parse an entire binary FBX file into a tree rooted at a synthetic node."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:21] != b"Kaydara FBX Binary  \x00":
        raise ValueError("Not a binary FBX file (or different magic).")
    version, = struct.unpack_from("<I", data, 23)
    buf = memoryview(data)
    off = 27
    children = []
    while off < len(data) - (25 if version >= 7500 else 13):
        node, off = _read_node(buf, off, version)
        if node is None:
            break
        children.append(node)
    return FBXNode("__root__", [version], children)


def extract_meshes(root: FBXNode) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Pull every Geometry node out as (vertices, triangles).

    Each Geometry has Vertices (doubles, xyzxyz...) and PolygonVertexIndex
    (int32 with negative values terminating polygons). We fan-triangulate
    n-gons into triangles.
    """
    meshes = []
    for geom in root.find_all("Geometry"):
        verts_node = None
        idx_node = None
        for c in geom.children:
            if c.name == "Vertices":
                verts_node = c
            elif c.name == "PolygonVertexIndex":
                idx_node = c
        if verts_node is None or idx_node is None:
            continue
        if not verts_node.props:
            continue
        verts_flat = verts_node.props[0]
        idx_flat = idx_node.props[0]
        verts = np.asarray(verts_flat, dtype=np.float64).reshape(-1, 3)
        idx = np.asarray(idx_flat, dtype=np.int64)

        # Fan-triangulate
        polys = []
        cur = []
        for v in idx:
            if v < 0:
                cur.append(int((-v) - 1))
                if len(cur) >= 3:
                    for i in range(1, len(cur) - 1):
                        polys.append((cur[0], cur[i], cur[i + 1]))
                cur = []
            else:
                cur.append(int(v))
        faces = np.array(polys, dtype=np.int64) if polys else np.zeros((0, 3), dtype=np.int64)
        meshes.append((verts, faces))
    return meshes


def get_axis_info(root: FBXNode) -> dict:
    """Read the GlobalSettings axis convention so the loader can rotate
    the mesh into our internal Y-up frame."""
    info = {"up_axis": 1, "up_sign": 1, "front_axis": 2, "front_sign": 1,
            "coord_axis": 0, "coord_sign": 1, "unit_scale": 1.0}
    settings = root.find("GlobalSettings")
    if settings is None:
        return info
    props70 = None
    for c in settings.children:
        if c.name == "Properties70":
            props70 = c
            break
    if props70 is None:
        return info
    for prop in props70.children:
        if prop.name != "P":
            continue
        if not prop.props or not isinstance(prop.props[0], str):
            continue
        key = prop.props[0]
        # P props: name, type, type2, flag, value...
        if len(prop.props) >= 5:
            val = prop.props[4]
            if key == "UpAxis":      info["up_axis"] = int(val)
            elif key == "UpAxisSign":  info["up_sign"] = int(val)
            elif key == "FrontAxis":   info["front_axis"] = int(val)
            elif key == "FrontAxisSign": info["front_sign"] = int(val)
            elif key == "CoordAxis":   info["coord_axis"] = int(val)
            elif key == "CoordAxisSign": info["coord_sign"] = int(val)
            elif key == "UnitScaleFactor": info["unit_scale"] = float(val)
    return info


def load_fbx(path: str) -> dict:
    """High level: parse + extract meshes + axis info.

    Returns dict with:
      'meshes':     list of (verts, faces) pairs
      'axis':       dict from get_axis_info
      'bbox':       (min, max) over all meshes
      'mesh_names': list of geometry names where available
    """
    root = parse_fbx(path)
    meshes = extract_meshes(root)
    axis = get_axis_info(root)
    names = []
    for geom in root.find_all("Geometry"):
        name = ""
        if len(geom.props) >= 2 and isinstance(geom.props[1], str):
            # In FBX, Geometry name property is often like "Geometry::CONE\0\0Geometry"
            # We just take whatever's between :: and the next null/double-colon.
            raw = geom.props[1]
            if "::" in raw:
                raw = raw.split("::", 1)[1]
            raw = raw.split("\x00", 1)[0]
            name = raw
        names.append(name)

    if meshes:
        all_v = np.vstack([m[0] for m in meshes])
        bbox = (all_v.min(axis=0), all_v.max(axis=0))
    else:
        bbox = (np.zeros(3), np.zeros(3))

    return {"meshes": meshes, "axis": axis, "bbox": bbox, "mesh_names": names}
