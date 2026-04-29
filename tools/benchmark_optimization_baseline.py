"""Collect baseline timing/memory/mesh stats for optimization work.

Usage:
  python tools/benchmark_optimization_baseline.py
  python tools/benchmark_optimization_baseline.py --out tools/baseline_latest.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tracemalloc
from typing import Dict, Any, List

import numpy as np


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mesh_boundary_edges(mesh) -> int:
    edges: Dict[tuple, int] = {}
    for face in mesh.faces:
        n = len(face)
        for i in range(n):
            a = int(face[i])
            b = int(face[(i + 1) % n])
            key = (a, b) if a < b else (b, a)
            edges[key] = edges.get(key, 0) + 1
    return sum(1 for c in edges.values() if c == 1)


def _mesh_summary(mesh) -> Dict[str, Any]:
    return {
        "verts": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "groups": {k: int(len(v)) for k, v in sorted(mesh.groups.items())},
        "boundary_edges": int(_mesh_boundary_edges(mesh)),
    }


def _profile_call(fn, *args, **kwargs):
    tracemalloc.start()
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, int(peak)


def _run_geometry_baseline() -> List[Dict[str, Any]]:
    from brick.brick_geom_hires import make_brick_hires
    from BrickGen.quality_presets import QUALITY_PRESETS_BY_NAME

    cases = [
        ("draft", 1, 1, 1, dict(QUALITY_PRESETS_BY_NAME["draft"])),
        ("standard", 2, 3, 3, dict(QUALITY_PRESETS_BY_NAME["standard"])),
        ("hero", 2, 3, 3, dict(QUALITY_PRESETS_BY_NAME["hero"])),
        ("standard", 2, 8, 3, dict(QUALITY_PRESETS_BY_NAME["standard"])),
    ]

    rows = []
    for quality, w, d, h, kwargs in cases:
        mesh, seconds, peak_mem = _profile_call(make_brick_hires, w, d, h, **kwargs)
        rows.append(
            {
                "quality": quality,
                "width": int(w),
                "depth": int(d),
                "height_plates": int(h),
                "seconds": float(seconds),
                "peak_memory_bytes": int(peak_mem),
                "mesh": _mesh_summary(mesh),
            }
        )
    return rows


def _run_plugin_baseline() -> List[Dict[str, Any]]:
    from tools.plugin_headless import load_plugin_module, build_brick_mesh

    mod = load_plugin_module()
    cases = [
        ("draft", 2, 3, 3, "brick"),
        ("standard", 2, 3, 3, "brick"),
        ("hero", 2, 3, 3, "brick"),
        ("standard", 2, 3, 1, "plate"),
    ]
    rows = []
    for quality, w, d, h, piece_type in cases:
        mesh, seconds, peak_mem = _profile_call(
            build_brick_mesh,
            mod,
            w,
            d,
            h,
            quality=quality,
            piece_type=piece_type,
        )
        rows.append(
            {
                "quality": quality,
                "piece_type": piece_type,
                "width": int(w),
                "depth": int(d),
                "height_plates": int(h),
                "seconds": float(seconds),
                "peak_memory_bytes": int(peak_mem),
                "mesh": _mesh_summary(mesh),
            }
        )
    return rows


def _run_pipeline_baseline() -> List[Dict[str, Any]]:
    from brick.voxelize import make_sphere, make_torus
    from brick.pipeline import brick_mesh

    inputs = [
        ("sphere", make_sphere(radius=24.0, subdivisions=2)),
        ("torus", make_torus(R=32.0, r=10.0, n_major=28, n_minor=16)),
    ]
    rows = []
    for name, (verts, faces) in inputs:
        verts = np.asarray(verts, dtype=np.float64)
        faces = np.asarray(faces, dtype=np.int64)
        (placements, info), seconds, peak_mem = _profile_call(
            brick_mesh,
            verts,
            faces,
            studs_across=20,
            voxel_mode="solid",
            merge_plates=True,
            merge_horizontal=True,
            prune_connectivity=True,
        )
        rows.append(
            {
                "input": name,
                "verts": int(len(verts)),
                "faces": int(len(faces)),
                "seconds": float(seconds),
                "peak_memory_bytes": int(peak_mem),
                "n_placed": int(len(placements)),
                "n_dropped": int(info.get("n_dropped", 0)),
                "grid_dims": tuple(int(v) for v in info.get("grid_dims", ())),
                "final_components": int(info.get("final_connectivity", {}).get("n_components", 0)),
            }
        )
    return rows


def main() -> None:
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(root, "tools", "baseline_optimization.json"))
    args = ap.parse_args()

    report: Dict[str, Any] = {
        "generated_at_epoch_s": time.time(),
        "geometry": _run_geometry_baseline(),
        "plugin_brickgen": _run_plugin_baseline(),
        "pipeline": _run_pipeline_baseline(),
    }

    out_path = os.path.abspath(args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"Wrote baseline report: {out_path}")
    for section in ("geometry", "plugin_brickgen", "pipeline"):
        print(f"{section}: {len(report[section])} cases")


if __name__ == "__main__":
    main()
