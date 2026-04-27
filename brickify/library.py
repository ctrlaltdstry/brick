"""Brick type definitions and the default starter library.

We work in a non-uniform voxel grid where one voxel = one stud (8mm) wide and
deep, and 1/3 of a brick (3.2mm = one PLATE) tall. So a standard brick is
3 voxels tall and a plate is 1 voxel tall. Bricks/plates have a footprint
in studs (width x depth).

The voxel grid axes:
    X = width  (stud direction)
    Y = height (plate units, 3 plates = 1 brick)
    Z = depth  (stud direction)

LEGO Y axis points UP in our internal grid. (We flip to LDraw convention
during export, where +Y is down.)
"""
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class BrickType:
    name: str
    width: int      # X studs
    depth: int      # Z studs
    height: int     # Y, in plate-units (1 plate = 1, 1 brick = 3)
    ldraw_code: str # e.g. "3001" for a 2x4 brick

    @property
    def footprint(self) -> int:
        return self.width * self.depth

    @property
    def volume(self) -> int:
        return self.width * self.depth * self.height

    def rotated(self) -> "BrickType":
        """90deg rotation around Y -> swap width/depth."""
        if self.width == self.depth:
            return self
        return BrickType(
            name=self.name + "_r",
            width=self.depth,
            depth=self.width,
            height=self.height,
            ldraw_code=self.ldraw_code,
        )


_FOOTPRINTS = [
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 6), (1, 8),
    (2, 2), (2, 3), (2, 4), (2, 6), (2, 8),
]

# Standard LDraw part numbers for common bricks/plates.
# https://library.ldraw.org/parts
_PLATES_H1 = [
    BrickType("plate_1x1", 1, 1, 1, "3024"),
    BrickType("plate_1x2", 1, 2, 1, "3023"),
    BrickType("plate_1x3", 1, 3, 1, "3623"),
    BrickType("plate_1x4", 1, 4, 1, "3710"),
    BrickType("plate_1x6", 1, 6, 1, "3666"),
    BrickType("plate_1x8", 1, 8, 1, "3460"),
    BrickType("plate_2x2", 2, 2, 1, "3022"),
    BrickType("plate_2x3", 2, 3, 1, "3021"),
    BrickType("plate_2x4", 2, 4, 1, "3020"),
    BrickType("plate_2x6", 2, 6, 1, "3795"),
    BrickType("plate_2x8", 2, 8, 1, "3034"),
]

_BRICKS_H3 = [
    BrickType("brick_1x1", 1, 1, 3, "3005"),
    BrickType("brick_1x2", 1, 2, 3, "3004"),
    BrickType("brick_1x3", 1, 3, 3, "3622"),
    BrickType("brick_1x4", 1, 4, 3, "3010"),
    BrickType("brick_1x6", 1, 6, 3, "3009"),
    BrickType("brick_1x8", 1, 8, 3, "3008"),
    BrickType("brick_2x2", 2, 2, 3, "3003"),
    BrickType("brick_2x3", 2, 3, 3, "3002"),
    BrickType("brick_2x4", 2, 4, 3, "3001"),
    BrickType("brick_2x6", 2, 6, 3, "2456"),
    BrickType("brick_2x8", 2, 8, 3, "3007"),
]

_TALLER_VARIANTS = []
for h in (2, 4, 5, 6):
    for w, d in _FOOTPRINTS:
        # Synthetic part family for fitting control: these are geometry-valid
        # in brickify/C4D, but not official LDraw stock part IDs.
        _TALLER_VARIANTS.append(
            BrickType(
                "brick_h{0}_{1}x{2}".format(h, w, d),
                w, d, h,
                "custom_h{0}_{1}x{2}".format(h, w, d),
            )
        )

DEFAULT_LIBRARY: List[BrickType] = _BRICKS_H3 + _PLATES_H1 + _TALLER_VARIANTS


@dataclass
class BrickLibrary:
    """A user-configurable list of available brick types.

    Sorted by volume descending so the greedy fitter prefers larger pieces.
    """
    bricks: List[BrickType] = field(default_factory=lambda: list(DEFAULT_LIBRARY))

    def __post_init__(self):
        self.bricks = sorted(self.bricks, key=lambda b: -b.volume)

    def all_orientations(self) -> List[BrickType]:
        """Each brick + its 90deg-rotated variant (when distinct)."""
        out = []
        seen = set()
        for b in self.bricks:
            for v in (b, b.rotated()):
                key = (v.width, v.depth, v.height)
                if key not in seen:
                    seen.add(key)
                    out.append(v)
        return sorted(out, key=lambda b: -b.volume)

    def by_height(self, h: int) -> List[BrickType]:
        return [b for b in self.all_orientations() if b.height == h]

    def find(self, name: str) -> BrickType:
        for b in self.bricks:
            if b.name == name:
                return b
        raise KeyError(name)
