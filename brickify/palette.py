"""LEGO color palette and color-matching.

Real LEGO ABS plastic comes in a finite set of colors. When sampling colors
from an input mesh's materials/textures, we snap each sampled color to the
nearest available LEGO color. We use perceptual (Lab) distance for matching.
"""
from dataclasses import dataclass
from typing import Iterable, Tuple
import numpy as np


@dataclass(frozen=True)
class LegoColor:
    name: str
    rgb: Tuple[int, int, int]   # 0-255
    ldraw_code: int             # LDraw color id (for .ldr export)


# A reasonable subset of solid LEGO colors. Add/remove freely.
DEFAULT_PALETTE = [
    LegoColor("Black",              (27, 42, 52),    0),
    LegoColor("Blue",               (0, 85, 191),    1),
    LegoColor("Green",              (0, 133, 43),    2),
    LegoColor("Dark Turquoise",     (5, 153, 152),   3),
    LegoColor("Red",                (201, 26, 9),    4),
    LegoColor("Dark Pink",          (200, 112, 160), 5),
    LegoColor("Brown",              (88, 57, 39),    6),
    LegoColor("Light Gray",         (155, 161, 157), 7),
    LegoColor("Dark Gray",          (109, 110, 92),  8),
    LegoColor("Light Blue",         (180, 210, 228), 9),
    LegoColor("Bright Green",       (75, 159, 74),   10),
    LegoColor("Yellow",             (245, 205, 47),  14),
    LegoColor("White",              (242, 243, 242), 15),
    LegoColor("Tan",                (228, 205, 158), 19),
    LegoColor("Orange",             (218, 133, 64),  25),
    LegoColor("Magenta",            (146, 57, 120),  26),
    LegoColor("Purple",             (129, 0, 123),   22),
    LegoColor("Lime",               (187, 233, 11),  27),
    LegoColor("Dark Tan",           (144, 116, 80),  28),
    LegoColor("Pink",               (228, 173, 200), 13),
    LegoColor("Medium Stone Gray",  (163, 162, 165), 71),
    LegoColor("Dark Stone Gray",    (99, 95, 97),    72),
    LegoColor("Reddish Brown",      (105, 64, 39),   70),
    LegoColor("Sand Blue",          (95, 116, 138),  379),
    LegoColor("Sand Green",         (160, 188, 172), 378),
    LegoColor("Olive Green",        (155, 154, 90),  330),
]


def _rgb_to_lab(rgb_array: np.ndarray) -> np.ndarray:
    """Convert sRGB (0..255) -> CIELAB. Vectorized; approximate D65 white."""
    rgb = rgb_array.astype(np.float64) / 255.0
    # sRGB linearization
    a = 0.055
    linear = np.where(rgb <= 0.04045,
                      rgb / 12.92,
                      ((rgb + a) / (1 + a)) ** 2.4)
    # linear sRGB -> XYZ (D65)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = linear @ M.T
    # XYZ -> Lab
    Xn, Yn, Zn = 0.95047, 1.0, 1.08883
    xyz_n = xyz / np.array([Xn, Yn, Zn])
    delta = 6 / 29
    f = np.where(xyz_n > delta**3,
                 np.cbrt(xyz_n),
                 xyz_n / (3 * delta * delta) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a_ = 500 * (f[..., 0] - f[..., 1])
    b_ = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a_, b_], axis=-1)


class LegoPalette:
    """Snap arbitrary RGB colors to the nearest available LEGO color."""

    def __init__(self, colors: Iterable[LegoColor] = None):
        self.colors = list(colors) if colors is not None else list(DEFAULT_PALETTE)
        rgb = np.array([c.rgb for c in self.colors], dtype=np.float64)
        self._lab = _rgb_to_lab(rgb)

    def nearest(self, rgb) -> LegoColor:
        """Return the LEGO color closest to a single RGB triple (0..255)."""
        return self.colors[self.nearest_index(np.array([rgb]))[0]]

    def nearest_index(self, rgb_array: np.ndarray) -> np.ndarray:
        """Vectorized: array of RGB (..., 3) -> array of palette indices."""
        rgb_array = np.asarray(rgb_array, dtype=np.float64)
        flat = rgb_array.reshape(-1, 3)
        lab = _rgb_to_lab(flat)
        # squared distance in Lab
        d = np.sum((lab[:, None, :] - self._lab[None, :, :]) ** 2, axis=-1)
        idx = np.argmin(d, axis=-1)
        return idx.reshape(rgb_array.shape[:-1])

    def color_at(self, idx: int) -> LegoColor:
        return self.colors[idx]
