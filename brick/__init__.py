"""Brick package namespace.

This is the canonical Python package used by the BrickGen Cinema 4D plugin
and command-line tools.
"""
from .palette import LegoPalette, DEFAULT_PALETTE
from .library import BrickType, BrickLibrary, DEFAULT_LIBRARY
from .voxelize import voxelize_mesh, load_obj, make_sphere, make_torus
from .fitter import BrickFitter, BrickPlacement, merge_plates_to_bricks
from .connectivity import check_connectivity, find_articulation_points
from .exporters import export_ldraw, export_json, render_preview
from .pipeline import brick_mesh, brickify_mesh, auto_stud_size, placement_world_position
