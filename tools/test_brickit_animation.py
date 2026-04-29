"""Regression checks for BrickIt build-progress animation math.

Run from repo root:
    python tools/test_brickit_animation.py
"""
from __future__ import annotations

import math
import os
import sys
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "BrickGen"))

from brickit_animation import (  # noqa: E402
    BUILD_ANIMATION_DEFAULT_Y_OFFSET,
    BUILD_ANIMATION_MIN_EFFECTIVE_STAGGER,
    BUILD_MOTION_CURVE_EASE,
    BUILD_MOTION_CURVE_EASE_IN,
    BUILD_MOTION_CURVE_EASE_OUT,
    BUILD_MOTION_CURVE_QUADRATIC,
    BUILD_MOTION_CURVE_SLAM,
    BUILD_MOTION_CURVE_SPRING,
    BUILD_MOTION_CURVE_CUSTOM,
    apply_motion_curve,
    build_animation_states,
    custom_curve_signature,
    exposed_top_cap_ids,
    missing_smooth_top_cap_placements,
    ordered_placements,
    phased_build_animation_states,
    smooth_top_cap_placements_for_coverage,
)


def _p(name, x, y, z, w=1, h=1, d=1, rotation_y=0):
    return SimpleNamespace(
        name=name,
        x=x,
        y=y,
        z=z,
        w=w,
        h=h,
        d=d,
        rotation_y=rotation_y,
    )


class _FakeCurve:
    def GetPoint(self, t):
        return SimpleNamespace(y=t * 0.25)


def test_order_bottom_to_top_with_stable_ties():
    placements = [
        _p("top", 0, 2, 0),
        _p("same_layer_second_row", 0, 0, 1),
        _p("same_layer_first_column", 1, 0, 0),
        _p("bottom_first", 0, 0, 0),
        _p("middle", 0, 1, 0),
    ]

    ordered = ordered_placements(placements)

    assert [p.name for p in ordered] == [
        "bottom_first",
        "same_layer_first_column",
        "same_layer_second_row",
        "middle",
        "top",
    ]


def test_progress_states_hide_enter_drop_and_land():
    placements = [_p("a", 0, 0, 0), _p("b", 0, 1, 0)]

    at_zero = build_animation_states(
        placements,
        0.0,
        y_offset=100.0,
        stagger=0.0,
    )
    assert all(state.local_progress == 0.0 for state in at_zero)
    assert all(
        math.isclose(state.y_offset, 100.0)
        for state in at_zero
    )

    entering = build_animation_states(
        placements,
        0.25,
        y_offset=100.0,
        stagger=0.0,
    )
    assert math.isclose(entering[0].local_progress, 0.5)
    assert math.isclose(entering[0].drop_t, 0.125)
    assert math.isclose(
        entering[0].y_offset,
        87.5,
    )
    assert entering[1].local_progress == 0.0

    landed = build_animation_states(
        placements,
        1.0,
        y_offset=100.0,
        stagger=0.0,
    )
    assert all(state.local_progress == 1.0 for state in landed)
    assert all(math.isclose(state.y_offset, 0.0) for state in landed)


def test_adjustable_offset_and_stagger_window():
    placements = [_p(str(i), 0, i, 0) for i in range(5)]

    no_offset = build_animation_states(
        placements,
        0.0,
        y_offset=0.0,
        stagger=1.0,
    )
    assert all(math.isclose(state.y_offset, 0.0) for state in no_offset)

    staggered = build_animation_states(
        placements,
        0.5,
        y_offset=50.0,
        stagger=1.0,
    )
    in_motion = [
        state for state in staggered
        if 0.0 < state.local_progress < 1.0
    ]
    assert len(in_motion) > 1
    assert staggered[0].local_progress > staggered[1].local_progress
    assert all(0.0 <= state.y_offset <= 50.0 for state in staggered)

    landed = build_animation_states(
        placements,
        1.0,
        y_offset=50.0,
        stagger=1.0,
    )
    assert all(math.isclose(state.local_progress, 1.0) for state in landed)
    assert all(math.isclose(state.y_offset, 0.0) for state in landed)


def test_low_nonzero_stagger_has_minimum_visible_window():
    placements = [_p(str(i), 0, i, 0) for i in range(101)]

    strict = build_animation_states(
        placements,
        0.5,
        y_offset=50.0,
        stagger=0.0,
    )
    low = build_animation_states(
        placements,
        0.5,
        y_offset=50.0,
        stagger=0.01,
    )

    strict_in_motion = [
        state for state in strict
        if 0.0 < state.local_progress < 1.0
    ]
    low_in_motion = [
        state for state in low
        if 0.0 < state.local_progress < 1.0
    ]
    assert len(strict_in_motion) <= 1
    assert len(low_in_motion) >= int(BUILD_ANIMATION_MIN_EFFECTIVE_STAGGER * 100)


def test_motion_curves_are_selectable():
    t = 0.5

    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_SLAM), 0.125)
    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_QUADRATIC), 0.25)
    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_EASE), 0.5)
    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_EASE_IN), 0.125)
    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_EASE_OUT), 0.875)
    assert 0.0 <= apply_motion_curve(t, BUILD_MOTION_CURVE_SPRING) <= 1.0

    placements = [_p("a", 0, 0, 0), _p("b", 0, 1, 0)]
    ease_out = build_animation_states(
        placements,
        0.25,
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_EASE_OUT,
    )
    assert math.isclose(ease_out[0].drop_t, 0.875)
    assert math.isclose(ease_out[0].y_offset, 12.5)


def test_custom_motion_curve_is_sampled():
    curve = _FakeCurve()

    assert math.isclose(
        apply_motion_curve(0.8, BUILD_MOTION_CURVE_CUSTOM, curve),
        0.2,
    )
    assert custom_curve_signature(curve, samples=3) == (0.0, 0.125, 0.25)

    states = build_animation_states(
        [_p("a", 0, 0, 0), _p("b", 0, 1, 0)],
        0.25,
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_CUSTOM,
        custom_curve=curve,
    )
    assert math.isclose(states[0].drop_t, 0.125)
    assert math.isclose(states[0].y_offset, 87.5)


def test_default_animation_values_are_gentler_than_original():
    states = build_animation_states([_p("a", 0, 0, 0)], 0.0)
    assert math.isclose(states[0].y_offset, BUILD_ANIMATION_DEFAULT_Y_OFFSET)


def test_exposed_top_caps_are_final_state_only():
    base = _p("base", 0, 0, 0, w=1, h=3, d=1)
    buried_plate = _p("buried_plate", 1, 0, 0, w=1, h=1, d=1)
    cover = _p("cover", 1, 1, 0, w=1, h=3, d=1)
    partial_top = _p("partial_top", 2, 0, 0, w=2, h=3, d=1)
    partial_cover = _p("partial_cover", 2, 3, 0, w=1, h=1, d=1)
    cap = _p("cap", 0, 3, 0, w=1, h=1, d=1)

    cap_ids = exposed_top_cap_ids([
        base,
        buried_plate,
        cover,
        partial_top,
        partial_cover,
        cap,
    ])

    assert id(cap) in cap_ids
    assert id(partial_cover) in cap_ids
    assert id(cover) not in cap_ids
    assert id(partial_top) not in cap_ids
    assert id(buried_plate) not in cap_ids
    assert id(base) not in cap_ids


def test_missing_smooth_caps_cover_exposed_studs_on_tall_bricks():
    tall = _p("tall", 0, 0, 0, w=2, h=3, d=1)
    blocked = _p("blocked", 0, 3, 0, w=1, h=1, d=1)
    existing_plate = _p("existing_plate", 2, 0, 0, w=1, h=1, d=1)

    caps = missing_smooth_top_cap_placements([tall, blocked, existing_plate])

    assert [(p.x, p.y, p.z, p.w, p.h, p.d) for p in caps] == [
        (1, 3, 0, 1, 1, 1),
    ]
    assert caps[0].brick.height == 1


def test_top_surface_coverage_limits_generated_caps():
    tall = _p("tall", 0, 0, 0, w=4, h=3, d=1)

    none = smooth_top_cap_placements_for_coverage([tall], 0.0)
    half = smooth_top_cap_placements_for_coverage([tall], 0.5)
    full = smooth_top_cap_placements_for_coverage([tall], 1.0)

    assert len(none) == 0
    assert [(p.x, p.y, p.z) for p in half] == [(0, 3, 0), (1, 3, 0)]
    assert len(full) == 4


def test_top_surface_phase_builds_caps_last():
    brick_a = _p("brick_a", 0, 0, 0, h=3)
    cap_a = _p("cap_a", 0, 3, 0, h=1)
    brick_b = _p("brick_b", 1, 0, 0, h=3)
    cap_b = _p("cap_b", 1, 3, 0, h=1)
    placements = [cap_b, brick_b, cap_a, brick_a]
    cap_ids = {id(cap_a), id(cap_b)}

    before_finish = phased_build_animation_states(
        placements,
        0.80,
        top_cap_ids=cap_ids,
        top_surface_phase=0.20,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in before_finish}
    assert by_name["brick_a"].local_progress == 1.0
    assert by_name["brick_b"].local_progress == 1.0
    assert by_name["cap_a"].local_progress == 0.0
    assert by_name["cap_b"].local_progress == 0.0

    mid_finish = phased_build_animation_states(
        placements,
        0.90,
        top_cap_ids=cap_ids,
        top_surface_phase=0.20,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in mid_finish}
    assert by_name["brick_a"].local_progress == 1.0
    assert math.isclose(by_name["cap_a"].local_progress, 1.0)
    assert by_name["cap_b"].local_progress == 0.0


def main():
    test_order_bottom_to_top_with_stable_ties()
    test_progress_states_hide_enter_drop_and_land()
    test_adjustable_offset_and_stagger_window()
    test_low_nonzero_stagger_has_minimum_visible_window()
    test_motion_curves_are_selectable()
    test_custom_motion_curve_is_sampled()
    test_default_animation_values_are_gentler_than_original()
    test_exposed_top_caps_are_final_state_only()
    test_missing_smooth_caps_cover_exposed_studs_on_tall_bricks()
    test_top_surface_coverage_limits_generated_caps()
    test_top_surface_phase_builds_caps_last()
    print("brickit animation regressions passed")


if __name__ == "__main__":
    main()
