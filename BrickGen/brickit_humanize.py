"""Deterministic per-brick transform variation for BrickIt."""
import math

import c4d

from plugin_bootstrap import brick_log as _brick_log


_rotation_warning_emitted = False


def _hash32(*vals):
    h = 2166136261
    for v in vals:
        h ^= int(v) & 0xFFFFFFFF
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _signed_noise(seed, placement, channel):
    h = _hash32(
        seed,
        channel,
        placement.x,
        placement.y,
        placement.z,
        placement.w,
        placement.h,
        placement.d,
        getattr(placement, "rotation_y", 0),
    )
    return ((float(h & 0xFFFFFF) / float(0x7FFFFF)) - 1.0)


def _enabled(params):
    return bool(params.get("humanize_bricks", False)) and (
        float(params.get("humanize_position", 0.0) or 0.0) > 0.0
        or float(params.get("humanize_rotation", 0.0) or 0.0) > 0.0
    )


def _offsets(placement, params):
    if not _enabled(params):
        return c4d.Vector(0.0, 0.0, 0.0), 0.0, 0.0, 0.0

    seed = int(params.get("humanize_seed", 1) or 1)
    position_amount = max(0.0, float(params.get("humanize_position", 0.0) or 0.0))
    rotation_amount = math.radians(
        max(0.0, float(params.get("humanize_rotation", 0.0) or 0.0))
    )
    pos = c4d.Vector(
        _signed_noise(seed, placement, 1) * position_amount,
        _signed_noise(seed, placement, 2) * position_amount,
        _signed_noise(seed, placement, 3) * position_amount,
    )
    return (
        pos,
        _signed_noise(seed, placement, 4) * rotation_amount,
        _signed_noise(seed, placement, 5) * rotation_amount,
        _signed_noise(seed, placement, 6) * rotation_amount,
    )


def _rotation_matrix(rx, ry, rz):
    if not (rx or ry or rz):
        return None
    return (
        c4d.utils.MatrixRotX(rx)
        * c4d.utils.MatrixRotY(ry)
        * c4d.utils.MatrixRotZ(rz)
    )


def _local_offset(matrix, vec):
    return (
        (matrix.v1 * float(vec.x))
        + (matrix.v2 * float(vec.y))
        + (matrix.v3 * float(vec.z))
    )


def _apply_rotation(matrix, rot):
    global _rotation_warning_emitted
    try:
        return matrix * rot
    except Exception as exc:
        if not _rotation_warning_emitted:
            _rotation_warning_emitted = True
            try:
                _brick_log("[brick] Humanize rotation skipped: {0}".format(exc))
            except Exception:
                pass
        return matrix


def apply_humanize_to_center_matrix(matrix, placement, params):
    """Apply jitter to a matrix whose pivot is already at the brick center."""
    if not _enabled(params):
        return matrix
    pos, rx, ry, rz = _offsets(placement, params)
    rot = _rotation_matrix(rx, ry, rz)
    if rot is not None:
        matrix = _apply_rotation(matrix, rot)
    matrix.off += pos
    return matrix


def apply_humanize_to_low_corner_matrix(matrix, placement, params, stud_size, plate_size):
    """Apply jitter around the brick center to a low-corner-pivot matrix."""
    if not _enabled(params):
        return matrix
    base_low = c4d.Vector(matrix.off)
    half = c4d.Vector(
        float(placement.w) * float(stud_size) * 0.5,
        float(placement.h) * float(plate_size) * 0.5,
        float(placement.d) * float(stud_size) * 0.5,
    )
    pos, rx, ry, rz = _offsets(placement, params)
    rot = _rotation_matrix(rx, ry, rz)
    if rot is not None:
        matrix = _apply_rotation(matrix, rot)
    center = base_low + half + pos
    matrix.off = center - _local_offset(matrix, half)
    return matrix
