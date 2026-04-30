"""Transform-level brick spacing helpers.

Separation changes instance origins only. It never changes the fitted layout
or the dimensions of any brick template.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

import numpy as np


def placement_assembly_center(
    placements: Iterable,
    stud_size: float,
    plate_size: float,
) -> np.ndarray:
    """Return the world-space center of a placement set, excluding scene origin."""
    low_min = None
    high_max = None
    for p in placements or []:
        low = np.array(
            [
                float(p.x) * float(stud_size),
                float(p.y) * float(plate_size),
                float(p.z) * float(stud_size),
            ],
            dtype=float,
        )
        size = np.array(
            [
                float(p.w) * float(stud_size),
                float(p.h) * float(plate_size),
                float(p.d) * float(stud_size),
            ],
            dtype=float,
        )
        high = low + size
        low_min = low if low_min is None else np.minimum(low_min, low)
        high_max = high if high_max is None else np.maximum(high_max, high)
    if low_min is None or high_max is None:
        return np.zeros(3, dtype=float)
    return (low_min + high_max) * 0.5


def separated_low_corner(
    placement,
    stud_size: float,
    plate_size: float,
    separation: float = 0.0,
    *,
    assembly_center: Optional[Sequence[float]] = None,
) -> Tuple[float, float, float]:
    """Return a placement low-corner after deterministic center expansion."""
    low = np.array(
        [
            float(placement.x) * float(stud_size),
            float(placement.y) * float(plate_size),
            float(placement.z) * float(stud_size),
        ],
        dtype=float,
    )
    size = np.array(
        [
            float(placement.w) * float(stud_size),
            float(placement.h) * float(plate_size),
            float(placement.d) * float(stud_size),
        ],
        dtype=float,
    )
    center = _separated_center_from_low(
        low,
        size,
        stud_size,
        plate_size,
        separation,
        assembly_center=assembly_center,
    )
    separated_low = center - size * 0.5
    return (
        float(separated_low[0]),
        float(separated_low[1]),
        float(separated_low[2]),
    )


def separated_center(
    placement,
    stud_size: float,
    plate_size: float,
    separation: float = 0.0,
    *,
    assembly_center: Optional[Sequence[float]] = None,
) -> Tuple[float, float, float]:
    """Return a placement center after deterministic center expansion."""
    low = np.array(
        [
            float(placement.x) * float(stud_size),
            float(placement.y) * float(plate_size),
            float(placement.z) * float(stud_size),
        ],
        dtype=float,
    )
    size = np.array(
        [
            float(placement.w) * float(stud_size),
            float(placement.h) * float(plate_size),
            float(placement.d) * float(stud_size),
        ],
        dtype=float,
    )
    center = _separated_center_from_low(
        low,
        size,
        stud_size,
        plate_size,
        separation,
        assembly_center=assembly_center,
    )
    return float(center[0]), float(center[1]), float(center[2])


def _separated_center_from_low(
    low: np.ndarray,
    size: np.ndarray,
    stud_size: float,
    plate_size: float,
    separation: float,
    *,
    assembly_center: Optional[Sequence[float]] = None,
) -> np.ndarray:
    center = low + size * 0.5
    if separation <= 0.0 or assembly_center is None:
        return center

    assembly_center = np.array(assembly_center, dtype=float)
    scale = np.array(
        [
            1.0 + float(separation) / max(float(stud_size), 1.0e-9),
            1.0 + float(separation) / max(float(plate_size), 1.0e-9),
            1.0 + float(separation) / max(float(stud_size), 1.0e-9),
        ],
        dtype=float,
    )
    return assembly_center + (center - assembly_center) * scale
