"""Headless guardrail for BrickIt source-deformation binding math.

Exercises the small geometry primitives the bind feature stands on —
closest-point-on-triangle, per-frame center reconstruction, and the
twist-stable shortest-arc rotation basis — without needing a full C4D
context. Run from the repo root:

    python tools/test_brickit_bind.py
"""
from __future__ import annotations

import math
import os
import sys
import types


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "BrickGen"))


# Stub c4d so the bind module imports cleanly outside Cinema 4D.
if "c4d" not in sys.modules:
    sys.modules["c4d"] = types.ModuleType("c4d")


import numpy as np  # noqa: E402

from brickit.brickit_bind import _closest_point_on_triangle  # noqa: E402
from brickit.brickit_bind_follower import _shortest_arc_basis  # noqa: E402


def _approx(actual, expected, tol=1e-4, label=""):
    diff = abs(float(actual) - float(expected))
    if diff > tol:
        raise AssertionError(
            "{0}: expected {1}, got {2} (diff {3})".format(
                label, expected, actual, diff
            )
        )


def test_closest_point_centroid():
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([10.0, 0.0, 0.0])
    c = np.array([0.0, 0.0, 10.0])
    p = np.array([10.0 / 3.0, 5.0, 10.0 / 3.0])
    closest, bary = _closest_point_on_triangle(p, a, b, c)
    _approx(bary[0], 1.0 / 3.0, label="bary[0]")
    _approx(bary[1], 1.0 / 3.0, label="bary[1]")
    _approx(bary[2], 1.0 / 3.0, label="bary[2]")
    _approx(closest[0], 10.0 / 3.0, label="closest.x")
    _approx(closest[1], 0.0, label="closest.y")
    _approx(closest[2], 10.0 / 3.0, label="closest.z")


def test_closest_point_at_vertex():
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([10.0, 0.0, 0.0])
    c = np.array([0.0, 0.0, 10.0])
    p = np.array([-5.0, 2.0, -5.0])  # behind vertex a
    closest, bary = _closest_point_on_triangle(p, a, b, c)
    _approx(bary[0], 1.0, label="bary at vertex")
    _approx(closest[0], 0.0, label="closest.x at vertex")


def test_per_frame_reconstruction_at_rest():
    """Bind a center to a triangle at rest, then reconstruct from the
    same bary + normal_offset and verify we recover the original."""
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([10.0, 0.0, 0.0])
    c = np.array([0.0, 0.0, 10.0])
    original_center = np.array([3.0, 4.0, 2.0])
    # Bind step
    closest, bary = _closest_point_on_triangle(original_center, a, b, c)
    cross = np.cross(b - a, c - a)
    normal = cross / np.linalg.norm(cross)
    normal_offset = float(np.dot(original_center - closest, normal))
    # Per-frame reconstruction (rest pose => identical verts)
    on_surface = a * bary[0] + b * bary[1] + c * bary[2]
    cross_p = np.cross(b - a, c - a)
    normal_p = cross_p / np.linalg.norm(cross_p)
    reconstructed = on_surface + normal_p * normal_offset
    for i, label in enumerate(("x", "y", "z")):
        _approx(
            reconstructed[i],
            original_center[i],
            tol=1e-3,
            label="reconstruct.{0}".format(label),
        )


def test_per_frame_reconstruction_after_translation():
    """Translate one triangle vertex; the reconstructed center should
    shift by the bary-weighted vertex displacement (no rotation)."""
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([10.0, 0.0, 0.0])
    c = np.array([0.0, 0.0, 10.0])
    original_center = np.array([3.0, 4.0, 2.0])
    closest, bary = _closest_point_on_triangle(original_center, a, b, c)
    cross = np.cross(b - a, c - a)
    normal = cross / np.linalg.norm(cross)
    normal_offset = float(np.dot(original_center - closest, normal))

    # Translate vertex `a` by (5, 0, 0); the reconstructed point should
    # shift by bary[0] * (5, 0, 0) along x. Since the triangle is still
    # in the y=0 plane (only x changed), the normal stays +Y so the
    # vertical normal_offset still applies the same way.
    a2 = a + np.array([5.0, 0.0, 0.0])
    on_surface = a2 * bary[0] + b * bary[1] + c * bary[2]
    cross_p = np.cross(b - a2, c - a2)
    normal_p = cross_p / np.linalg.norm(cross_p)
    reconstructed = on_surface + normal_p * normal_offset
    expected_shift_x = bary[0] * 5.0
    _approx(
        reconstructed[0] - original_center[0],
        expected_shift_x,
        tol=1e-3,
        label="bary-weighted x shift",
    )
    _approx(
        reconstructed[1],
        original_center[1],
        tol=1e-3,
        label="y unchanged when normal didn't flip",
    )


def test_shortest_arc_at_world_y():
    v1, v2, v3 = _shortest_arc_basis(0.0, 1.0, 0.0)
    _approx(v1[0], 1.0, label="v1.x at +Y")
    _approx(v2[1], 1.0, label="v2.y at +Y")
    _approx(v3[2], 1.0, label="v3.z at +Y")


def test_shortest_arc_smooth_through_x_sweep():
    """Sweep the normal through the world-X-aligned region and verify the
    tangent + bitangent vary smoothly (no 90/180° flips). The previous
    world-X-projection method failed this when the normal crossed
    ±world-X."""
    prev = None
    for t in range(0, 360, 5):
        theta = math.radians(t)
        # Normal sweeps around the XZ plane, slightly above zero so
        # ny is always small but nonzero (worst-case for tangent flips).
        n = np.array(
            [math.cos(theta), 0.1, math.sin(theta)]
        )
        n = n / np.linalg.norm(n)
        v1, v2, v3 = _shortest_arc_basis(float(n[0]), float(n[1]), float(n[2]))
        if prev is not None:
            # The basis should change continuously — adjacent samples
            # within a 5-degree step should produce v1 vectors that
            # never differ by more than ~30 degrees.
            v1_arr = np.asarray(v1)
            prev_arr = np.asarray(prev)
            cos_angle = float(
                np.dot(v1_arr, prev_arr)
                / (np.linalg.norm(v1_arr) * np.linalg.norm(prev_arr))
            )
            cos_angle = max(-1.0, min(1.0, cos_angle))
            angle_deg = math.degrees(math.acos(cos_angle))
            if angle_deg > 30.0:
                raise AssertionError(
                    "tangent flipped {0:.1f}deg between adjacent samples "
                    "near theta={1}deg (n={2})".format(angle_deg, t, n)
                )
        prev = v1


def main():
    cases = [
        ("closest_point_centroid", test_closest_point_centroid),
        ("closest_point_at_vertex", test_closest_point_at_vertex),
        (
            "per_frame_reconstruction_at_rest",
            test_per_frame_reconstruction_at_rest,
        ),
        (
            "per_frame_reconstruction_after_translation",
            test_per_frame_reconstruction_after_translation,
        ),
        ("shortest_arc_at_world_y", test_shortest_arc_at_world_y),
        (
            "shortest_arc_smooth_through_x_sweep",
            test_shortest_arc_smooth_through_x_sweep,
        ),
    ]
    failed = []
    for name, fn in cases:
        try:
            fn()
            print("[PASS] {0}".format(name))
        except Exception as exc:
            print("[FAIL] {0}: {1}".format(name, exc))
            failed.append(name)
    if failed:
        print("\n{0} test(s) failed.".format(len(failed)))
        sys.exit(1)
    print("\nAll bind guardrail tests passed.")


if __name__ == "__main__":
    main()
