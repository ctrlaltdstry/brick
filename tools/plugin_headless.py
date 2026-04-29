"""Helpers for loading the C4D plugin module in headless scripts.

These tools run outside Cinema 4D, so they install lightweight `c4d`
stubs, load `BrickGen/c4d_brick_generator.pyp`, and call `build_brick`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from importlib.machinery import SourceFileLoader
from typing import Any


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def install_c4d_stubs() -> None:
    """Install minimal c4d stubs so plugin module import succeeds."""
    if "c4d" in sys.modules:
        return

    c4d = types.ModuleType("c4d")
    plugins = types.ModuleType("c4d.plugins")
    gui = types.ModuleType("c4d.gui")

    class _Stub:
        def __init__(self, *args: Any, **kwargs: Any):
            pass

        def __call__(self, *args: Any, **kwargs: Any):
            return self

        def __getattr__(self, _name: str):
            return _Stub()

    plugins.ObjectData = type(
        "ObjectData",
        (),
        {"__init__": lambda self, *args, **kwargs: None},
    )
    plugins.CommandData = type(
        "CommandData",
        (),
        {"__init__": lambda self, *args, **kwargs: None},
    )
    plugins.RegisterObjectPlugin = lambda *args, **kwargs: True
    gui.GeDialog = type(
        "GeDialog",
        (),
        {
            "__init__": lambda self, *args, **kwargs: None,
            "__getattr__": lambda self, _name: _Stub(),
        },
    )
    gui.RegisterIcon = lambda *args, **kwargs: True
    c4d.plugins = plugins
    c4d.gui = gui

    # Constants and common symbols used during module import.
    c4d.MSG_UPDATE = 0
    c4d.OBJECT_GENERATOR = 0
    c4d.COPYFLAGS_NONE = 0
    c4d.Tpolygonselection = 0
    c4d.Vector = _Stub
    c4d.PolygonObject = _Stub
    c4d.CPolygon = _Stub

    sys.modules["c4d"] = c4d
    sys.modules["c4d.plugins"] = plugins
    sys.modules["c4d.gui"] = gui


def load_plugin_module():
    """Load and return `BrickGen/c4d_brick_generator.pyp` as a module."""
    root = repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    install_c4d_stubs()

    pyp_path = os.path.join(root, "BrickGen", "c4d_brick_generator.pyp")
    loader = SourceFileLoader("c4d_brick_generator", pyp_path)
    spec = importlib.util.spec_from_loader("c4d_brick_generator", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _quality_value(mod, quality: str) -> int:
    q = str(quality).lower().strip()
    attr = {
        "draft": "BRICKGENERATOR_QUALITY_DRAFT",
        "standard": "BRICKGENERATOR_QUALITY_STANDARD",
        "hero": "BRICKGENERATOR_QUALITY_HERO",
    }.get(q)
    if attr is None:
        raise ValueError(f"Unknown quality '{quality}'. Expected draft|standard|hero.")
    return int(getattr(mod, attr))


def _piece_type_value(mod, piece_type: str) -> int:
    p = str(piece_type).lower().strip()
    attr = {
        "brick": "BRICKGENERATOR_TYPE_BRICK",
        "plate": "BRICKGENERATOR_TYPE_PLATE",
    }.get(p)
    if attr is None:
        raise ValueError(f"Unknown piece_type '{piece_type}'. Expected brick|plate.")
    return int(getattr(mod, attr))


def build_brick_mesh(
    mod,
    width: int,
    depth: int,
    height: int,
    *,
    quality: str = "hero",
    piece_type: str = "brick",
):
    """Return Mesh from plugin `build_brick` using readable string inputs."""
    return mod.build_brick(
        int(width),
        int(depth),
        int(height),
        _quality_value(mod, quality),
        _piece_type_value(mod, piece_type),
    )
