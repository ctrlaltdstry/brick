"""Brick package namespace.

This is the canonical Python package used by the BrickGen Cinema 4D plugin
and command-line tools.
"""
from .palette import LegoPalette, DEFAULT_PALETTE
from .library import BrickType, BrickLibrary, DEFAULT_LIBRARY
from .voxelize import voxelize_mesh, load_obj, make_sphere, make_torus
from .fitter import BrickFitter, BrickPlacement, merge_plates_to_bricks
from .connectivity import (
    check_buildability, check_connectivity, find_articulation_points,
)
from .pipeline import brick_mesh, brickify_mesh, auto_stud_size, placement_world_position


def __getattr__(name):
    """Lazily expose optional exporter helpers without importing matplotlib."""
    if name in {"export_ldraw", "export_json", "render_preview"}:
        from . import exporters
        return getattr(exporters, name)
    raise AttributeError("module 'brick' has no attribute {0!r}".format(name))
