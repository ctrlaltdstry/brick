"""Serialize / deserialize the per-frame fit cache for scene persistence.

The cache is {int frame -> list[BrickPlacement]}. We pack it into a compact
binary blob (struct) + zlib + base64 so it can live in a hidden STRING
parameter on the Cubify object and be saved with the .c4d. The blob is
self-contained: each distinct BrickType is stored fully (name, w, d, h,
ldraw) in a header table, so deserialization rebuilds placements without
needing the active library to still match.

Only PLACEMENTS are persisted (the visual result). The per-frame `info`
dicts are not stored — on cache load they're treated as empty, which only
affects the read-only Build Info panel, not the rendered bricks.
"""
import base64
import struct
import zlib

import numpy as _np

from brick.fitter import BrickPlacement
from brick.library import BrickType

_MAGIC = b"CFC3"  # v3: adds precomputed per-template carrier matrices/colors

# per-placement record:
#   H  brick-type index
#   h h h  x y z
#   B  rotation (0 or 1 meaning 90)
#   b  color_idx (signed; -1 = none)
#   B B B  rgb
#   B  is_anchor
_REC = struct.Struct("<HhhhBbBBBB")

# per-frame geometry info the hierarchy builder REQUIRES to place bricks:
#   origin x/y/z (double), stud_size (double), plate_size (double),
#   grid_dims x/y/z (int32). Without these the builder returns no geometry,
#   which is why a placements-only cache showed nothing on reopen.
_INFO = struct.Struct("<dddddiii")

# Precomputed carrier data (v3), grouped by template so playback is just
# "push N matrices + N colors onto one multi-instance carrier per template".
#   _TKEY: template key (w, d, h, smooth_top flag, logo-rotation bucket deg)
#   _MAT:  a 4x3 matrix as 12 floats (v1 xyz, v2 xyz, v3 xyz, off xyz)
#   _COL:  rgb bytes (playback rebuilds the c4d.Vector, matching the live path)
_TKEY = struct.Struct("<hhhBH")
_MAT = struct.Struct("<12f")
_COL = struct.Struct("<3B")


def serialize(cache):
    """cache: {int frame -> list[BrickPlacement]} -> base64 str (or "")."""
    if not cache:
        return ""
    # Collect distinct brick types -> index, storing full geometry so the
    # blob doesn't depend on the live library.
    types = []
    type_index = {}

    def _type_idx(bt):
        key = bt.name
        i = type_index.get(key)
        if i is None:
            i = len(types)
            type_index[key] = i
            types.append(bt)
        return i

    # The cache stores {frame: (placements, info)}; only placements are
    # persisted. Accept a bare placements list too, for safety.
    def _placements(entry):
        if isinstance(entry, tuple):
            return entry[0] or []
        return entry or []

    def _info(entry):
        if isinstance(entry, tuple) and len(entry) > 1:
            return entry[1] or {}
        return {}

    def _precomp(entry):
        # entry[2] is {tkey_tuple: ([c4d.Matrix...], [(r,g,b)...])} or None.
        if isinstance(entry, tuple) and len(entry) > 2:
            return entry[2]
        return None

    # Pre-walk to build the brick-type table (types must be written before
    # the frames that index into them).
    for frame in sorted(cache):
        for p in _placements(cache[frame]):
            _type_idx(p.brick)

    buf = bytearray()
    buf += _MAGIC

    buf += struct.pack("<H", len(types))
    for bt in types:
        nb = bt.name.encode("utf-8")
        lb = (bt.ldraw_code or "").encode("utf-8")
        buf += struct.pack("<B", len(nb)) + nb
        buf += struct.pack("<hhh", int(bt.width), int(bt.depth), int(bt.height))
        buf += struct.pack("<B", len(lb)) + lb

    buf += struct.pack("<I", len(cache))
    for frame in sorted(cache):
        pls = _placements(cache[frame])
        info = _info(cache[frame])
        # Per-frame geometry info (required by the builder). Default to a
        # neutral origin/sizes if somehow absent so we never write garbage.
        origin = info.get("origin")
        try:
            ox, oy, oz = (float(origin[0]), float(origin[1]), float(origin[2]))
        except Exception:
            ox = oy = oz = 0.0
        stud = float(info.get("stud_size", 8.0) or 8.0)
        plate = float(info.get("plate_size", 3.2) or 3.2)
        gd = info.get("grid_dims") or (0, 0, 0)
        try:
            gx, gy, gz = int(gd[0]), int(gd[1]), int(gd[2])
        except Exception:
            gx = gy = gz = 0
        buf += struct.pack("<iI", int(frame), len(pls))
        buf += _INFO.pack(ox, oy, oz, stud, plate, gx, gy, gz)
        for p in pls:
            rgb = p.rgb or (180, 180, 180)
            buf += _REC.pack(
                _type_idx(p.brick),
                int(p.x), int(p.y), int(p.z),
                1 if int(p.rotation_y) == 90 else 0,
                max(-1, min(127, int(p.color_idx))),
                int(rgb[0]) & 0xFF, int(rgb[1]) & 0xFF, int(rgb[2]) & 0xFF,
                1 if bool(p.is_anchor) else 0,
            )
        # Precompute section (v3): batched-by-template matrices + colors so
        # playback just pushes arrays onto one carrier per template. Written
        # as <H n_templates> [ _TKEY <I count> count*_MAT count*_COL ]*.
        # n_templates==0 means "no precompute" (falls back to per-brick build).
        precomp = _precomp(cache[frame])
        if precomp:
            buf += struct.pack("<H", len(precomp))
            for tkey, (mats, cols) in precomp.items():
                w, d, h, st_flag, rot = tkey
                buf += _TKEY.pack(int(w), int(d), int(h),
                                  int(st_flag) & 0xFF, int(rot) & 0xFFFF)
                buf += struct.pack("<I", len(mats))
                for m in mats:
                    buf += _MAT.pack(
                        float(m.v1.x), float(m.v1.y), float(m.v1.z),
                        float(m.v2.x), float(m.v2.y), float(m.v2.z),
                        float(m.v3.x), float(m.v3.y), float(m.v3.z),
                        float(m.off.x), float(m.off.y), float(m.off.z),
                    )
                for c in cols:
                    buf += _COL.pack(int(c[0]) & 0xFF, int(c[1]) & 0xFF,
                                     int(c[2]) & 0xFF)
        else:
            buf += struct.pack("<H", 0)
    return base64.b64encode(zlib.compress(bytes(buf), 6)).decode("ascii")


def deserialize(text):
    """base64 str -> {int frame -> list[BrickPlacement]} (or {} on failure)."""
    if not text:
        return {}
    try:
        raw = zlib.decompress(base64.b64decode(text))
    except Exception:
        return {}
    magic = raw[:4]
    if magic not in (b"CFC3", b"CFC2"):
        return {}
    has_precomp = (magic == b"CFC3")
    off = 4
    try:
        (n_types,) = struct.unpack_from("<H", raw, off); off += 2
        types = []
        for _ in range(n_types):
            (ln,) = struct.unpack_from("<B", raw, off); off += 1
            name = raw[off:off + ln].decode("utf-8"); off += ln
            w, d, h = struct.unpack_from("<hhh", raw, off); off += 6
            (ll,) = struct.unpack_from("<B", raw, off); off += 1
            ldraw = raw[off:off + ll].decode("utf-8"); off += ll
            types.append(BrickType(name=name, width=w, depth=d, height=h,
                                   ldraw_code=ldraw))
        (n_frames,) = struct.unpack_from("<I", raw, off); off += 4
        cache = {}
        for _ in range(n_frames):
            frame, count = struct.unpack_from("<iI", raw, off); off += 8
            (ox, oy, oz, stud, plate, gx, gy, gz) = _INFO.unpack_from(raw, off)
            off += _INFO.size
            pls = []
            for _ in range(count):
                (ti, x, y, z, rot, ci, r, g, b, anc) = _REC.unpack_from(raw, off)
                off += _REC.size
                pls.append(BrickPlacement(
                    brick=types[ti], x=x, y=y, z=z,
                    rotation_y=90 if rot else 0,
                    color_idx=ci,
                    rgb=(r, g, b),
                    is_anchor=bool(anc),
                ))
            # Rebuild the minimal info dict the hierarchy builder requires to
            # place bricks (origin + sizes; grid_dims helps smooth-top). origin
            # is numpy to match the live fit. The heavier debug fields
            # (occupancy_cells etc.) aren't persisted — they only affect the
            # smooth-top finish, which degrades gracefully without them.
            info = {
                "origin": _np.array([ox, oy, oz], dtype=_np.float64),
                "stud_size": float(stud),
                "plate_size": float(plate),
                "grid_dims": (int(gx), int(gy), int(gz)),
            }
            precomp = None
            if has_precomp:
                (n_tpl,) = struct.unpack_from("<H", raw, off); off += 2
                if n_tpl:
                    import c4d  # only available in-host; precomp is host-only
                    precomp = {}
                    for _ in range(n_tpl):
                        (w, d, h, st_flag, rot) = _TKEY.unpack_from(raw, off)
                        off += _TKEY.size
                        (mcount,) = struct.unpack_from("<I", raw, off); off += 4
                        mats = []
                        for _ in range(mcount):
                            vals = _MAT.unpack_from(raw, off); off += _MAT.size
                            m = c4d.Matrix()
                            m.v1 = c4d.Vector(vals[0], vals[1], vals[2])
                            m.v2 = c4d.Vector(vals[3], vals[4], vals[5])
                            m.v3 = c4d.Vector(vals[6], vals[7], vals[8])
                            m.off = c4d.Vector(vals[9], vals[10], vals[11])
                            mats.append(m)
                        cols = []
                        for _ in range(mcount):
                            (cr, cg, cb) = _COL.unpack_from(raw, off)
                            off += _COL.size
                            cols.append((cr, cg, cb))
                        precomp[(int(w), int(d), int(h),
                                 int(st_flag), int(rot))] = (mats, cols)
            cache[int(frame)] = (pls, info, precomp)
        return cache
    except Exception:
        return {}
