"""Brick package namespace.

This package is the new canonical import path and delegates module loading
to the existing `brickify` implementation to preserve compatibility.
"""

from pathlib import Path

# Keep this package's own directory and also expose the legacy implementation
# directory so `import brick.pipeline` resolves to `brickify/pipeline.py`.
_HERE = Path(__file__).resolve().parent
_LEGACY_IMPL = _HERE.parent / "brickify"
__path__ = [str(_HERE), str(_LEGACY_IMPL)]

from .palette import LegoPalette, DEFAULT_PALETTE
from .library import BrickType, BrickLibrary, DEFAULT_LIBRARY
from .voxelize import voxelize_mesh, load_obj, make_sphere, make_torus
from .fitter import BrickFitter, BrickPlacement, merge_plates_to_bricks
from .connectivity import check_connectivity, find_articulation_points
from .exporters import export_ldraw, export_json, render_preview
from .pipeline import brick_mesh, brickify_mesh, auto_stud_size, placement_world_position
