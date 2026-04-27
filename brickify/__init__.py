"""Brickify: convert 3D meshes into LEGO-buildable brick assemblies."""
from .palette import LegoPalette, DEFAULT_PALETTE
from .library import BrickType, BrickLibrary, DEFAULT_LIBRARY
from .voxelize import voxelize_mesh, load_obj, make_sphere, make_torus
from .fitter import BrickFitter, BrickPlacement, merge_plates_to_bricks
from .connectivity import check_connectivity, find_articulation_points
from .exporters import export_ldraw, export_json, render_preview
from .pipeline import brickify_mesh, auto_stud_size, placement_world_position
