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
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "BrickGen"))

from brickit.brickit_animation import (  # noqa: E402
    BUILD_ANIMATION_DEFAULT_Y_OFFSET,
    BUILD_ANIMATION_DEFAULT_TILT_DEGREES,
    BUILD_ANIMATION_FIXED_MOTION_DURATION,
    BUILD_ANIMATION_MIN_EFFECTIVE_STAGGER,
    BUILD_ANIMATION_MIN_SCALE,
    BUILD_ANIMATION_TILT_CLEARANCE_MULTIPLIER,
    BUILD_ANIMATION_VISIBLE_AHEAD_LAYERS,
    BUILD_ANIMATION_Y_OFFSET_VARIATION,
    BUILD_MOTION_CURVE_EASE,
    BUILD_MOTION_CURVE_EASE_IN,
    BUILD_MOTION_CURVE_EASE_OUT,
    BUILD_MOTION_CURVE_QUADRATIC,
    BUILD_MOTION_CURVE_SLAM,
    BUILD_MOTION_CURVE_SPRING,
    BUILD_MOTION_CURVE_CUSTOM,
    BUILD_MOTION_CURVE_BOUNCE,
    VisualCapBrickType,
    VisualCapPlacement,
    _build_support_lookup,
    _supporting_placements,
    _supporting_placements_from_lookup,
    apply_motion_curve,
    build_scale_for_progress,
    build_tilt_clearance,
    build_tilt_for_progress,
    build_animation_states,
    custom_curve_signature,
    exterior_top_cells_from_occupancy,
    exposed_top_cap_ids,
    CAP_STYLE_MATCH_BELOW,
    CAP_STYLE_MERGED_COVER,
    CAP_STYLE_RANDOM_MIX,
    missing_smooth_top_cap_placements,
    ordered_placements,
    phased_build_animation_states,
    shell_smooth_top_target_cells,
    smooth_top_cap_placements_for_coverage,
    smooth_top_cap_selection_for_coverage,
)
from brick.separation import (  # noqa: E402
    placement_assembly_center,
    separated_center,
    separated_low_corner,
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


def _cap(name, x, y, z, w=1, d=1):
    cap = VisualCapPlacement(VisualCapBrickType(), x=x, y=y, z=z)
    return SimpleNamespace(
        name=name,
        brick=cap.brick,
        x=cap.x,
        y=cap.y,
        z=cap.z,
        w=w,
        h=cap.h,
        d=d,
        rotation_y=cap.rotation_y,
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
        BUILD_ANIMATION_FIXED_MOTION_DURATION * 0.5,
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
        0.6,
        y_offset=50.0,
        stagger=1.0,
    )
    in_motion = [
        state for state in staggered
        if 0.0 < state.local_progress < 1.0
    ]
    assert len(in_motion) > 1
    assert staggered[0].local_progress == 1.0
    assert staggered[1].local_progress == 1.0
    assert staggered[2].local_progress > staggered[3].local_progress
    assert staggered[3].local_progress > staggered[4].local_progress
    assert all(0.0 <= state.y_offset <= 50.0 for state in staggered)

    landed = build_animation_states(
        placements,
        1.0,
        y_offset=50.0,
        stagger=1.0,
    )
    assert all(math.isclose(state.local_progress, 1.0) for state in landed)
    assert all(math.isclose(state.y_offset, 0.0) for state in landed)


def test_stagger_does_not_pull_landed_lower_layers_back_up():
    placements = [_p(str(i), 0, i, 0) for i in range(5)]

    strict = build_animation_states(
        placements,
        0.5,
        y_offset=50.0,
        stagger=0.0,
    )
    staggered = build_animation_states(
        placements,
        0.5,
        y_offset=50.0,
        stagger=1.0,
    )

    assert strict[0].local_progress == 1.0
    assert strict[1].local_progress == 1.0
    assert staggered[0].local_progress == 1.0
    assert staggered[1].local_progress == 1.0
    assert math.isclose(staggered[0].y_offset, 0.0)
    assert math.isclose(staggered[1].y_offset, 0.0)
    assert 0.0 < staggered[2].local_progress < 1.0
    assert staggered[3].local_progress == 0.0


def test_stagger_locks_only_nonstaggered_landed_layers():
    placements = [_p(str(i), 0, i, 0) for i in range(5)]

    states = build_animation_states(
        placements,
        0.42,
        y_offset=50.0,
        stagger=1.0,
    )

    assert states[0].local_progress == 1.0
    assert states[1].local_progress == 1.0
    assert math.isclose(states[1].y_offset, 0.0)
    assert states[2].local_progress < states[1].local_progress


def test_staggered_bricks_enter_with_smooth_drop_progress():
    placements = [_p(str(i), 0, i, 0) for i in range(5)]

    states = build_animation_states(
        placements,
        0.23,
        y_offset=50.0,
        stagger=1.0,
    )

    entering = states[1]
    assert 0.0 < entering.local_progress < 1.0
    assert 25.0 < entering.y_offset <= 50.0


def test_same_y_bricks_share_build_progress():
    placements = [
        _p("same_a", 0, 0, 0),
        _p("same_b", 1, 0, 0),
        _p("upper", 0, 1, 0),
    ]

    states = build_animation_states(
        placements,
        0.25,
        y_offset=50.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in states}

    assert math.isclose(
        by_name["same_a"].local_progress,
        by_name["same_b"].local_progress,
    )
    assert by_name["same_a"].local_progress > by_name["upper"].local_progress


def test_stagger_spreads_bricks_within_active_y_layer():
    placements = [
        _p("same_a", 0, 0, 0),
        _p("same_b", 1, 0, 0),
        _p("same_c", 2, 0, 0),
        _p("upper", 0, 1, 0),
    ]

    states = build_animation_states(
        placements,
        0.25,
        y_offset=50.0,
        stagger=1.0,
    )
    by_name = {state.placement.name: state for state in states}

    assert by_name["same_a"].local_progress > by_name["same_b"].local_progress
    assert by_name["same_b"].local_progress > by_name["same_c"].local_progress
    assert by_name["upper"].local_progress == 0.0


def test_in_layer_stagger_does_not_snap_to_landed_at_layer_boundary():
    placements = [
        _p("same_a", 0, 0, 0),
        _p("same_b", 1, 0, 0),
        _p("same_c", 2, 0, 0),
        _p("upper", 0, 1, 0),
    ]

    states = build_animation_states(
        placements,
        0.5,
        y_offset=50.0,
        stagger=1.0,
    )
    by_name = {state.placement.name: state for state in states}

    assert by_name["same_a"].local_progress == 1.0
    assert by_name["same_b"].local_progress == 1.0
    assert by_name["same_c"].local_progress == 1.0
    assert by_name["upper"].local_progress == 0.0


def test_stagger_visibility_frontier_hides_far_ahead_layers():
    placements = [_p(str(i), 0, i, 0) for i in range(20)]

    states = build_animation_states(
        placements,
        0.5,
        y_offset=50.0,
        stagger=1.0,
    )

    frontier_layer = int(0.5 * len(placements))
    near_ahead = states[frontier_layer + 1]
    far_ahead = states[
        frontier_layer + int(BUILD_ANIMATION_VISIBLE_AHEAD_LAYERS) + 3
    ]

    assert 0.0 < near_ahead.local_progress < 1.0
    assert 0.0 < near_ahead.y_offset < 50.0
    assert far_ahead.local_progress == 0.0
    assert math.isclose(far_ahead.y_offset, 50.0)


def test_incoming_staggered_bricks_get_varied_y_offsets():
    placements = [
        _p("same_{0}".format(i), i, 0, 0)
        for i in range(8)
    ]

    states = build_animation_states(
        placements,
        0.25,
        y_offset=50.0,
        stagger=1.0,
    )
    in_flight_offsets = [
        round(state.y_offset, 4)
        for state in states
        if 0.0 < state.local_progress < 1.0
    ]

    assert len(in_flight_offsets) > 1
    assert len(set(in_flight_offsets)) > 1
    assert min(in_flight_offsets) >= 0.0
    assert max(in_flight_offsets) <= 50.0


def test_landed_staggered_bricks_keep_exact_final_y_offset():
    placements = [_p(str(i), 0, i, 0) for i in range(5)]

    states = build_animation_states(
        placements,
        1.0,
        y_offset=50.0,
        stagger=1.0,
    )

    assert all(math.isclose(state.y_offset, 0.0) for state in states)


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
    assert len(strict_in_motion) > 1
    assert len(low_in_motion) == len(strict_in_motion)


def test_motion_curves_are_selectable():
    t = 0.5

    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_SLAM), 0.125)
    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_QUADRATIC), 0.25)
    assert apply_motion_curve(t, BUILD_MOTION_CURVE_SLAM) < apply_motion_curve(
        t,
        BUILD_MOTION_CURVE_QUADRATIC,
    )
    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_EASE), 0.5)
    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_EASE_IN), 0.125)
    assert math.isclose(apply_motion_curve(t, BUILD_MOTION_CURVE_EASE_OUT), 0.875)
    assert 0.0 <= apply_motion_curve(t, BUILD_MOTION_CURVE_SPRING) <= 1.0

    placements = [_p("a", 0, 0, 0), _p("b", 0, 1, 0)]
    ease_out = build_animation_states(
        placements,
        BUILD_ANIMATION_FIXED_MOTION_DURATION * 0.5,
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_EASE_OUT,
    )
    assert math.isclose(ease_out[0].drop_t, 0.875)
    assert math.isclose(ease_out[0].y_offset, 12.5)


def test_brick_hang_time_controls_initial_drop_motion():
    placement = [_p("a", 0, 0, 0)]

    no_hang = build_animation_states(
        placement,
        0.10,
        y_offset=100.0,
        stagger=0.0,
        hang_time=0.0,
    )
    full_hang = build_animation_states(
        placement,
        0.10,
        y_offset=100.0,
        stagger=0.0,
        hang_time=1.0,
    )

    assert no_hang[0].local_progress == full_hang[0].local_progress
    assert no_hang[0].drop_t > full_hang[0].drop_t
    assert no_hang[0].y_offset < full_hang[0].y_offset


def test_brick_hang_time_preserves_final_landing():
    landed = build_animation_states(
        [_p("a", 0, 0, 0)],
        1.0,
        y_offset=100.0,
        stagger=0.0,
        hang_time=0.0,
    )

    assert landed[0].local_progress == 1.0
    assert landed[0].drop_t == 1.0
    assert math.isclose(landed[0].y_offset, 0.0)


def test_bounce_motion_curve_never_overshoots_landing():
    samples = [
        apply_motion_curve(i / 100.0, BUILD_MOTION_CURVE_BOUNCE)
        for i in range(101)
    ]

    assert samples[0] == 0.0
    assert samples[-1] == 1.0
    assert all(0.0 <= value <= 1.0 for value in samples)


def test_bounce_motion_curve_contacts_then_rebounds():
    contact = apply_motion_curve(1.0 / 2.75, BUILD_MOTION_CURVE_BOUNCE)
    rebound = apply_motion_curve(0.45, BUILD_MOTION_CURVE_BOUNCE)
    second_rebound = apply_motion_curve(0.55, BUILD_MOTION_CURVE_BOUNCE)
    early_settled = apply_motion_curve(0.70, BUILD_MOTION_CURVE_BOUNCE)
    settled = apply_motion_curve(1.0, BUILD_MOTION_CURVE_BOUNCE)

    assert math.isclose(contact, 1.0)
    assert rebound < contact
    assert second_rebound < contact
    assert early_settled == 1.0
    assert settled == 1.0


def test_structural_bounce_keeps_curve_progress_visible():
    placements = [_p(str(i), 0, i, 0) for i in range(5)]

    states = build_animation_states(
        placements,
        0.42,
        y_offset=50.0,
        stagger=1.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )

    assert states[2].local_progress < 1.0
    assert states[2].y_offset > 0.0


def test_top_structural_bounce_completes_before_final_frame():
    placements = [_p(str(i), 0, i, 0) for i in range(5)]

    rebounding = build_animation_states(
        placements,
        0.85,
        y_offset=50.0,
        stagger=1.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    final_state = build_animation_states(
        placements,
        1.0,
        y_offset=50.0,
        stagger=1.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )

    assert 0.0 < rebounding[-1].local_progress < 1.0
    assert rebounding[-1].y_offset > 0.0
    assert final_state[-1].local_progress == 1.0
    assert math.isclose(final_state[-1].y_offset, 0.0)


def test_bounce_uses_linear_time_progress_when_build_progress_eases():
    placements = [_p(str(i), 0, i, 0) for i in range(5)]

    eased_slider = build_animation_states(
        placements,
        0.60,
        time_progress=0.80,
        y_offset=50.0,
        stagger=1.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    linear_slider = build_animation_states(
        placements,
        0.80,
        time_progress=0.80,
        y_offset=50.0,
        stagger=1.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )

    assert [
        round(state.local_progress, 4)
        for state in eased_slider
    ] == [
        round(state.local_progress, 4)
        for state in linear_slider
    ]
    assert [
        round(state.y_offset, 4)
        for state in eased_slider
    ] == [
        round(state.y_offset, 4)
        for state in linear_slider
    ]


def test_non_bounce_curves_ignore_linear_time_progress():
    placements = [_p(str(i), 0, i, 0) for i in range(5)]

    eased_slider = build_animation_states(
        placements,
        0.60,
        time_progress=0.80,
        y_offset=50.0,
        stagger=1.0,
        motion_curve=BUILD_MOTION_CURVE_SLAM,
    )
    linear_slider = build_animation_states(
        placements,
        0.80,
        time_progress=0.80,
        y_offset=50.0,
        stagger=1.0,
        motion_curve=BUILD_MOTION_CURVE_SLAM,
    )

    assert [
        round(state.local_progress, 4)
        for state in eased_slider
    ] != [
        round(state.local_progress, 4)
        for state in linear_slider
    ]


def test_final_blended_cap_bounce_has_pre_end_rebound_window():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    cap = _cap("cap", 0, 3, 0)

    rebounding = phased_build_animation_states(
        [support, cap],
        0.97,
        top_cap_ids={id(cap)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    final_state = phased_build_animation_states(
        [support, cap],
        1.0,
        top_cap_ids={id(cap)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    rebound_by_name = {state.placement.name: state for state in rebounding}
    final_by_name = {state.placement.name: state for state in final_state}

    assert 0.0 < rebound_by_name["cap"].local_progress < 1.0
    assert rebound_by_name["cap"].y_offset > 0.0
    assert final_by_name["cap"].local_progress == 1.0
    assert math.isclose(final_by_name["cap"].y_offset, 0.0)


def test_custom_motion_curve_is_sampled():
    curve = _FakeCurve()

    assert math.isclose(
        apply_motion_curve(0.8, BUILD_MOTION_CURVE_CUSTOM, curve),
        0.2,
    )
    assert custom_curve_signature(curve, samples=3) == (0.0, 0.125, 0.25)

    states = build_animation_states(
        [_p("a", 0, 0, 0), _p("b", 0, 1, 0)],
        BUILD_ANIMATION_FIXED_MOTION_DURATION * 0.5,
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_CUSTOM,
        custom_curve=curve,
    )
    assert math.isclose(states[0].drop_t, 0.125)
    assert math.isclose(states[0].y_offset, 87.5)


def test_scale_in_uses_small_minimum_scale():
    assert math.isclose(build_scale_for_progress(0.0, enabled=False), 1.0)
    assert math.isclose(
        build_scale_for_progress(0.0, enabled=True),
        BUILD_ANIMATION_MIN_SCALE,
    )
    assert math.isclose(build_scale_for_progress(1.0, enabled=True), 1.0)
    halfway = build_scale_for_progress(0.5, enabled=True)
    assert BUILD_ANIMATION_MIN_SCALE < halfway < 1.0


def test_scale_in_resolves_at_bounce_contact():
    placement = _p("scaled", 2, 3, 4, w=2, h=3, d=1, rotation_y=90)

    before_contact = build_animation_states(
        [placement],
        BUILD_ANIMATION_FIXED_MOTION_DURATION * 0.20,
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )[0]
    at_contact = build_animation_states(
        [placement],
        BUILD_ANIMATION_FIXED_MOTION_DURATION * (1.0 / 2.75),
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )[0]
    rebound = build_animation_states(
        [placement],
        BUILD_ANIMATION_FIXED_MOTION_DURATION * 0.45,
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )[0]

    incoming_scale = build_scale_for_progress(
        before_contact.contact_progress,
        enabled=True,
    )
    contact_scale = build_scale_for_progress(
        at_contact.contact_progress,
        enabled=True,
    )
    rebound_scale = build_scale_for_progress(
        rebound.contact_progress,
        enabled=True,
    )

    assert before_contact.local_progress < 1.0
    assert BUILD_ANIMATION_MIN_SCALE < incoming_scale < 1.0
    assert at_contact.local_progress < 1.0
    assert math.isclose(at_contact.y_offset, 0.0, abs_tol=1.0e-6)
    assert math.isclose(contact_scale, 1.0)
    assert rebound.local_progress < 1.0
    assert rebound.y_offset > 0.0
    assert math.isclose(rebound_scale, 1.0)


def test_subtle_rotation_is_stable_and_lands_flat():
    placement = _p("tilted", 2, 3, 4, w=2, h=3, d=1, rotation_y=90)

    disabled = build_tilt_for_progress(
        placement,
        0.25,
        enabled=False,
        amount_degrees=BUILD_ANIMATION_DEFAULT_TILT_DEGREES,
    )
    first = build_tilt_for_progress(
        placement,
        0.25,
        enabled=True,
        amount_degrees=10.0,
    )
    second = build_tilt_for_progress(
        placement,
        0.25,
        enabled=True,
        amount_degrees=10.0,
    )
    landed = build_tilt_for_progress(
        placement,
        1.0,
        enabled=True,
        amount_degrees=360.0,
    )

    assert disabled == (0.0, 0.0)
    assert first == second
    assert any(abs(angle) > 0.0 for angle in first)
    assert all(abs(angle) <= math.radians(10.0) for angle in first)
    assert landed == (0.0, 0.0)


def test_subtle_rotation_resolves_at_bounce_contact():
    placement = _p("tilted", 2, 3, 4, w=2, h=3, d=1, rotation_y=90)

    before_contact = build_animation_states(
        [placement],
        BUILD_ANIMATION_FIXED_MOTION_DURATION * 0.20,
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )[0]
    at_contact = build_animation_states(
        [placement],
        BUILD_ANIMATION_FIXED_MOTION_DURATION * (1.0 / 2.75),
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )[0]
    rebound = build_animation_states(
        [placement],
        BUILD_ANIMATION_FIXED_MOTION_DURATION * 0.45,
        y_offset=100.0,
        stagger=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )[0]

    incoming_tilt = build_tilt_for_progress(
        placement,
        before_contact.contact_progress,
        enabled=True,
        amount_degrees=20.0,
    )
    contact_tilt = build_tilt_for_progress(
        placement,
        at_contact.contact_progress,
        enabled=True,
        amount_degrees=20.0,
    )
    rebound_tilt = build_tilt_for_progress(
        placement,
        rebound.contact_progress,
        enabled=True,
        amount_degrees=20.0,
    )

    assert before_contact.local_progress < 1.0
    assert any(abs(angle) > 0.0 for angle in incoming_tilt)
    assert at_contact.local_progress < 1.0
    assert math.isclose(at_contact.y_offset, 0.0, abs_tol=1.0e-6)
    assert contact_tilt == (0.0, 0.0)
    assert rebound.local_progress < 1.0
    assert rebound.y_offset > 0.0
    assert rebound_tilt == (0.0, 0.0)


def test_tilt_clearance_fades_with_tilt():
    no_tilt = build_tilt_clearance(0.0, 0.0, 3, 3.2, enabled=True)
    disabled = build_tilt_clearance(1.0, 0.0, 3, 3.2, enabled=False)
    quarter_turn = build_tilt_clearance(
        math.pi * 0.5,
        0.0,
        3,
        3.2,
        enabled=True,
    )

    assert math.isclose(no_tilt, 0.0)
    assert math.isclose(disabled, 0.0)
    assert math.isclose(
        quarter_turn,
        3 * 3.2 * BUILD_ANIMATION_TILT_CLEARANCE_MULTIPLIER,
    )


def test_separated_center_matches_low_corner_plus_half_extents():
    placement = _p("wide", 2, 3, 4, w=2, h=3, d=1)
    stud_size = 8.0
    plate_size = 3.2

    low = separated_low_corner(placement, stud_size, plate_size)
    center = separated_center(placement, stud_size, plate_size)

    assert center == (
        low[0] + placement.w * stud_size * 0.5,
        low[1] + placement.h * plate_size * 0.5,
        low[2] + placement.d * stud_size * 0.5,
    )


def test_separated_center_preserves_separation_expansion():
    placements = [
        _p("left", 0, 0, 0, w=1, h=1, d=1),
        _p("right", 2, 0, 0, w=1, h=1, d=1),
    ]
    assembly_center = placement_assembly_center(placements, 8.0, 3.2)

    unseparated = separated_center(
        placements[1],
        8.0,
        3.2,
        assembly_center=assembly_center,
    )
    separated = separated_center(
        placements[1],
        8.0,
        3.2,
        8.0,
        assembly_center=assembly_center,
    )

    assert separated[0] > unseparated[0]
    assert math.isclose(separated[1], unseparated[1])
    assert math.isclose(separated[2], unseparated[2])


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
    # A fully-exposed tall brick now yields a SINGLE cap whose footprint
    # matches the brick below (was previously per-cell 1x1 caps).
    tall = _p("tall", 0, 0, 0, w=4, h=3, d=1)

    none = smooth_top_cap_placements_for_coverage([tall], 0.0)
    full = smooth_top_cap_placements_for_coverage([tall], 1.0)

    assert len(none) == 0
    assert len(full) == 1
    assert (full[0].x, full[0].y, full[0].z, full[0].w, full[0].d) == (0, 3, 0, 4, 1)


def test_top_surface_coverage_limits_existing_and_generated_caps():
    existing = _p("existing", 0, 2, 0, w=1, h=1, d=1)
    tall = _p("tall", 1, 0, 0, w=2, h=3, d=1)
    placements = [existing, tall]

    none_ids, none_caps = smooth_top_cap_selection_for_coverage(placements, 0.0)
    partial_ids, partial_caps = smooth_top_cap_selection_for_coverage(placements, 0.34)
    full_ids, full_caps = smooth_top_cap_selection_for_coverage(placements, 1.0)

    assert none_ids == set()
    assert none_caps == []
    assert partial_ids == {id(existing)}
    assert partial_caps == []
    assert full_ids == set()
    covered = set()
    for p in placements:
        if id(p) not in full_ids:
            continue
        for x in range(p.x, p.x + p.w):
            for z in range(p.z, p.z + p.d):
                covered.add((x, p.y + p.h, z))
    for p in full_caps:
        for x in range(p.x, p.x + p.w):
            for z in range(p.z, p.z + p.d):
                covered.add((x, p.y, z))
    assert covered == {(0, 3, 0), (1, 3, 0), (2, 3, 0)}


def test_full_top_surface_coverage_covers_every_exposed_top_cell():
    low_plate = _p("low_plate", 0, 0, 0, w=1, h=1, d=1)
    tall_full = _p("tall_full", 1, 0, 0, w=2, h=3, d=1)
    tall_partial = _p("tall_partial", 3, 0, 0, w=2, h=3, d=1)
    blocker = _p("blocker", 3, 3, 0, w=1, h=1, d=1)
    placements = [low_plate, tall_full, tall_partial, blocker]

    selected_ids, generated_caps = smooth_top_cap_selection_for_coverage(
        placements,
        1.0,
    )

    covered = set()
    for p in placements:
        if id(p) not in selected_ids:
            continue
        top_y = p.y + p.h
        for x in range(p.x, p.x + p.w):
            for z in range(p.z, p.z + p.d):
                covered.add((x, top_y, z))
    for p in generated_caps:
        for x in range(p.x, p.x + p.w):
            for z in range(p.z, p.z + p.d):
                covered.add((x, p.y, z))

    expected = {
        (0, 1, 0),
        (1, 3, 0),
        (2, 3, 0),
        (3, 4, 0),
        (4, 3, 0),
    }
    assert covered == expected


def test_near_full_top_surface_coverage_uses_full_cell_guarantee():
    placements = [
        _p("a", 0, 0, 0, w=1, h=1, d=1),
        _p("b", 1, 0, 0, w=1, h=1, d=1),
        _p("c", 2, 0, 0, w=1, h=1, d=1),
    ]

    selected_ids, generated_caps = smooth_top_cap_selection_for_coverage(
        placements,
        0.995,
    )

    covered = set()
    for p in generated_caps:
        for x in range(p.x, p.x + p.w):
            for z in range(p.z, p.z + p.d):
                covered.add((x, p.y, z))

    assert selected_ids == set()
    assert covered == {(0, 1, 0), (1, 1, 0), (2, 1, 0)}


def test_shell_exterior_top_cells_exclude_interior_void():
    # The center air cell at y=1 is enclosed by side walls plus occupied
    # cells below/above. The top above y=2 is connected to exterior air.
    occupancy_cells = [
        (1, 0, 1),
        (1, 2, 1),
        (0, 1, 0), (1, 1, 0), (2, 1, 0),
        (0, 1, 1),             (2, 1, 1),
        (0, 1, 2), (1, 1, 2), (2, 1, 2),
    ]
    target = exterior_top_cells_from_occupancy(
        occupancy_cells,
        (3, 3, 3),
    )

    assert (1, 1, 1) not in target
    assert (1, 3, 1) in target


def test_shell_exterior_top_cells_return_none_without_voxel_data():
    assert exterior_top_cells_from_occupancy([], (3, 3, 3)) is None
    assert exterior_top_cells_from_occupancy(None, (3, 3, 3)) is None


def test_shell_smooth_caps_only_target_exterior_top_cells():
    lower_inside_plate = _p("lower_inside_plate", 0, 0, 0, w=1, h=1, d=1)
    upper_shell_brick = _p("upper_shell_brick", 0, 2, 0, w=1, h=1, d=1)
    placements = [lower_inside_plate, upper_shell_brick]
    occupancy_cells = [
        (0, 0, 0),
        (0, 2, 0),
        (-1, 1, -1), (0, 1, -1), (1, 1, -1),
        (-1, 1, 0),              (1, 1, 0),
        (-1, 1, 1),  (0, 1, 1),  (1, 1, 1),
    ]
    target = exterior_top_cells_from_occupancy(
        [(x + 1, y, z + 1) for x, y, z in occupancy_cells],
        (3, 3, 3),
    )
    target = {(x - 1, y, z - 1) for x, y, z in target}

    selected_ids, generated_caps = smooth_top_cap_selection_for_coverage(
        placements,
        1.0,
        target_top_cells=target,
    )

    assert selected_ids == set()
    assert [(p.x, p.y, p.z, p.w, p.d) for p in generated_caps] == [
        (0, 3, 0, 1, 1),
    ]


def test_shell_targets_project_exterior_columns_to_fitted_tops():
    # The fitted top is the renderable surface that needs the cap; interior void
    # data is only used to reject enclosed shell air.
    tall_fit = _p("tall_fit", 0, 2, 0, w=1, h=2, d=1)
    target = shell_smooth_top_target_cells(
        [tall_fit],
        [(0, 2, 0)],
        (1, 3, 1),
        interior_void_cells=[],
    )

    assert (0, 4, 0) in target

    selected_ids, generated_caps = smooth_top_cap_selection_for_coverage(
        [tall_fit],
        1.0,
        target_top_cells=target,
    )

    assert selected_ids == set()
    assert [(p.x, p.y, p.z, p.w, p.d) for p in generated_caps] == [
        (0, 4, 0, 1, 1),
    ]


def test_shell_projected_targets_do_not_cap_lower_interior_tops():
    # Fitted bricks form a closed shell around an interior air cell at
    # (1, 1, 1). The lower plate sitting inside that cavity must not be
    # capped, but the topmost shell brick must.
    lower_inside_plate = _p("lower_inside_plate", 1, 0, 1, w=1, h=1, d=1)
    upper_shell_brick = _p("upper_shell_brick", 1, 2, 1, w=1, h=1, d=1)
    ring = [
        _p("r_xn_zn", 0, 1, 0),
        _p("r_xn_z0", 0, 1, 1),
        _p("r_xn_zp", 0, 1, 2),
        _p("r_x0_zn", 1, 1, 0),
        _p("r_x0_zp", 1, 1, 2),
        _p("r_xp_zn", 2, 1, 0),
        _p("r_xp_z0", 2, 1, 1),
        _p("r_xp_zp", 2, 1, 2),
    ]
    placements = [lower_inside_plate, upper_shell_brick] + ring

    target = shell_smooth_top_target_cells(
        placements,
        [],
        (3, 3, 3),
    )

    assert (1, 1, 1) not in target
    assert (1, 3, 1) in target


def test_shell_targets_include_fitted_open_top_without_voxel_column_match():
    exposed_overhang = _p("exposed_overhang", 1, 2, 0, w=1, h=1, d=1)

    target = shell_smooth_top_target_cells(
        [exposed_overhang],
        [(0, 2, 0)],
        (2, 3, 1),
        interior_void_cells=[],
    )

    assert target == {(1, 3, 0)}


def test_top_surface_coverage_can_use_random_order():
    placements = [
        _p("cap_a", 0, 1, 0, w=1, h=1, d=1),
        _p("cap_b", 1, 1, 0, w=1, h=1, d=1),
        _p("cap_c", 2, 1, 0, w=1, h=1, d=1),
        _p("cap_d", 3, 1, 0, w=1, h=1, d=1),
    ]

    sequential_ids, _ = smooth_top_cap_selection_for_coverage(
        placements,
        0.5,
        random_order=False,
    )
    random_ids, _ = smooth_top_cap_selection_for_coverage(
        placements,
        0.5,
        random_order=True,
    )
    shifted_ids, _ = smooth_top_cap_selection_for_coverage(
        placements,
        0.51,
        random_order=True,
    )

    assert sequential_ids == {id(placements[0]), id(placements[1])}
    assert len(random_ids) == 2
    assert random_ids != sequential_ids
    assert len(shifted_ids) == 2
    assert shifted_ids != random_ids


def test_top_surface_phase_builds_caps_last():
    brick_a = _p("brick_a", 0, 0, 0, h=3)
    cap_a = _cap("cap_a", 0, 3, 0)
    brick_b = _p("brick_b", 1, 0, 0, h=3)
    cap_b = _cap("cap_b", 1, 3, 0)
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
        0.82,
        top_cap_ids=cap_ids,
        top_surface_phase=0.20,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in mid_finish}
    assert by_name["brick_a"].local_progress == 1.0
    assert 0.0 < by_name["cap_a"].local_progress < 1.0
    assert 0.0 < by_name["cap_b"].local_progress < 1.0


def test_top_surface_start_overlaps_structural_build():
    brick_a = _p("brick_a", 0, 0, 0, h=3)
    brick_b = _p("brick_b", 1, 1, 0, h=3)
    cap_a = _cap("cap_a", 0, 3, 0)
    cap_b = _cap("cap_b", 1, 4, 0)
    placements = [cap_b, brick_b, cap_a, brick_a]
    cap_ids = {id(cap_a), id(cap_b)}

    before_caps = phased_build_animation_states(
        placements,
        0.30,
        top_cap_ids=cap_ids,
        top_surface_start=0.40,
        top_surface_phase=0.30,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in before_caps}
    assert by_name["cap_a"].local_progress == 0.0
    assert by_name["cap_b"].local_progress == 0.0
    assert by_name["brick_a"].local_progress > 0.0
    assert by_name["brick_b"].local_progress < 1.0

    overlapping = phased_build_animation_states(
        placements,
        0.55,
        top_cap_ids=cap_ids,
        top_surface_start=0.40,
        top_surface_phase=0.30,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in overlapping}
    assert 0.0 < by_name["cap_a"].local_progress < 1.0
    assert math.isclose(by_name["cap_b"].local_progress, 0.0, abs_tol=1.0e-9)
    assert by_name["brick_b"].local_progress < 1.0


def test_blended_top_caps_use_varied_speeds():
    supports = [
        _p("support_{0}".format(i), i, 0, 0, w=1, h=3, d=1)
        for i in range(8)
    ]
    later_structural = _p("later_structural", 100, 1, 0, w=1, h=3, d=1)
    caps = [
        _cap("cap_{0}".format(i), i, 3, 0)
        for i in range(8)
    ]
    placements = supports + [later_structural] + caps
    cap_ids = {id(cap) for cap in caps}

    states = phased_build_animation_states(
        placements,
        0.53,
        top_cap_ids=cap_ids,
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    cap_progresses = [
        round(state.local_progress, 4)
        for state in states
        if state.placement.name.startswith("cap_")
        and 0.0 < state.local_progress < 1.0
    ]

    assert len(cap_progresses) > 1
    assert len(set(cap_progresses)) > 1


def test_blended_top_caps_varied_speeds_still_land_at_end():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    cap = _cap("cap", 0, 3, 0)

    states = phased_build_animation_states(
        [support, cap],
        1.0,
        top_cap_ids={id(cap)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in states}

    assert by_name["cap"].local_progress == 1.0
    assert math.isclose(by_name["cap"].y_offset, 0.0)


def test_top_surface_caps_wait_for_support_to_land():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    cap = _cap("cap", 0, 3, 0)
    later = _p("later", 1, 1, 0, w=1, h=3, d=1)
    placements = [cap, later, support]

    early = phased_build_animation_states(
        placements,
        0.20,
        top_cap_ids={id(cap)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in early}
    assert by_name["support"].local_progress < 1.0
    assert by_name["cap"].local_progress == 0.0

    after_support = phased_build_animation_states(
        placements,
        0.65,
        top_cap_ids={id(cap)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in after_support}
    assert by_name["support"].local_progress == 1.0
    assert by_name["cap"].local_progress > 0.0


def test_support_lookup_matches_scan_for_blended_caps():
    supports = [
        _p("support_left", 0, 0, 0, w=1, h=4, d=1),
        _p("support_right", 1, 1, 0, w=1, h=3, d=1),
        _p("unrelated", 5, 0, 0, w=2, h=3, d=1),
    ]
    cap = _cap("wide_cap", 0, 4, 0, w=2, d=1)

    scanned = _supporting_placements(cap, supports)
    looked_up = _supporting_placements_from_lookup(
        cap,
        _build_support_lookup(supports),
    )

    assert [p.name for p in looked_up] == [p.name for p in scanned]
    assert [p.name for p in looked_up] == ["support_left", "support_right"]


def test_blended_top_caps_start_from_zero_for_late_supports():
    supports = [
        _p("support_{0}".format(i), i, i, 0, w=1, h=3, d=1)
        for i in range(10)
    ]
    cap = _cap("late_cap", 8, 11, 0)
    placements = supports + [cap]

    just_after_support = phased_build_animation_states(
        placements,
        0.95,
        top_cap_ids={id(cap)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in just_after_support}

    assert by_name["support_8"].local_progress == 1.0
    assert 0.0 < by_name["late_cap"].local_progress < 1.0


def test_blended_top_caps_require_full_footprint_support():
    partial_support = _p("partial_support", 0, 0, 0, w=1, h=3, d=1)
    wide_cap = _cap("wide_cap", 0, 3, 0, w=2, d=1)
    placements = [partial_support, wide_cap]

    states = phased_build_animation_states(
        placements,
        1.0,
        top_cap_ids={id(wide_cap)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in states}

    assert by_name["partial_support"].local_progress == 1.0
    assert by_name["wide_cap"].local_progress == 0.0


def test_existing_smooth_top_plates_stay_in_structural_timeline():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    existing_plate = _p("existing_plate", 0, 3, 0, w=1, h=1, d=1)
    placements = [existing_plate, support]

    states = phased_build_animation_states(
        placements,
        1.0,
        top_cap_ids={id(existing_plate)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in states}

    assert by_name["existing_plate"].local_progress == 1.0


def test_blended_existing_smooth_top_plates_follow_smooth_top_progress():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    existing_plate = _p("existing_plate", 0, 3, 0, w=1, h=1, d=1)
    placements = [existing_plate, support]

    hidden = phased_build_animation_states(
        placements,
        1.0,
        top_progress=0.0,
        top_cap_ids={id(existing_plate)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    visible = phased_build_animation_states(
        placements,
        1.0,
        top_progress=1.0,
        top_cap_ids={id(existing_plate)},
        top_surface_start=0.35,
        top_surface_phase=0.65,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_hidden = {state.placement.name: state for state in hidden}
    by_visible = {state.placement.name: state for state in visible}

    assert by_hidden["support"].local_progress == 1.0
    assert by_hidden["existing_plate"].local_progress == 0.0
    assert by_visible["support"].local_progress == 1.0
    assert by_visible["existing_plate"].local_progress == 1.0


def test_existing_smooth_top_plates_use_final_phase_when_not_blended():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    existing_plate = _p("existing_plate", 0, 3, 0, w=1, h=1, d=1)
    placements = [existing_plate, support]

    before_finish = phased_build_animation_states(
        placements,
        0.80,
        top_cap_ids={id(existing_plate)},
        top_surface_phase=0.20,
        blend_top_surface=False,
        y_offset=10.0,
        stagger=0.0,
    )
    by_name = {state.placement.name: state for state in before_finish}

    assert by_name["support"].local_progress == 1.0
    assert by_name["existing_plate"].local_progress == 0.0


def test_smooth_top_progress_is_independent_from_build_progress():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    cap = _cap("cap", 0, 3, 0)

    held_back = phased_build_animation_states(
        [support, cap],
        1.0,
        top_progress=0.0,
        top_cap_ids={id(cap)},
        top_surface_phase=0.20,
        blend_top_surface=False,
        y_offset=10.0,
        stagger=0.0,
    )
    pushed_forward = phased_build_animation_states(
        [support, cap],
        0.0,
        top_progress=1.0,
        top_cap_ids={id(cap)},
        top_surface_phase=0.20,
        blend_top_surface=False,
        y_offset=10.0,
        stagger=0.0,
    )
    by_held_back = {state.placement.name: state for state in held_back}
    by_pushed_forward = {state.placement.name: state for state in pushed_forward}

    assert by_held_back["support"].local_progress == 1.0
    assert by_held_back["cap"].local_progress == 0.0
    assert by_pushed_forward["support"].local_progress == 0.0
    assert by_pushed_forward["cap"].local_progress == 1.0


def test_blended_smooth_top_progress_still_waits_for_support():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    cap = _cap("cap", 0, 3, 0)

    unsupported = phased_build_animation_states(
        [support, cap],
        0.0,
        top_progress=1.0,
        top_cap_ids={id(cap)},
        top_surface_phase=0.20,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    supported = phased_build_animation_states(
        [support, cap],
        1.0,
        top_progress=1.0,
        top_cap_ids={id(cap)},
        top_surface_phase=0.20,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
    )
    by_unsupported = {state.placement.name: state for state in unsupported}
    by_supported = {state.placement.name: state for state in supported}

    assert by_unsupported["support"].local_progress == 0.0
    assert by_unsupported["cap"].local_progress == 0.0
    assert by_supported["support"].local_progress == 1.0
    assert by_supported["cap"].local_progress == 1.0


def test_smooth_top_curve_starts_after_support_when_sliders_match():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    cap = _cap("cap", 0, 3, 0)

    hidden = phased_build_animation_states(
        [support, cap],
        0.20,
        top_progress=0.20,
        top_time_progress=0.20,
        top_cap_ids={id(cap)},
        top_surface_phase=0.20,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_EASE_OUT,
    )
    animating = phased_build_animation_states(
        [support, cap],
        0.25,
        top_progress=0.25,
        top_time_progress=0.25,
        top_cap_ids={id(cap)},
        top_surface_phase=0.20,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_EASE_OUT,
    )
    by_hidden = {state.placement.name: state for state in hidden}
    by_animating = {state.placement.name: state for state in animating}

    assert by_hidden["cap"].local_progress == 0.0
    assert by_hidden["cap"].y_offset == 10.0
    assert 0.0 < by_animating["cap"].local_progress < 1.0
    assert 0.0 < by_animating["cap"].y_offset < 10.0


def test_smooth_top_bounce_rebounds_when_sliders_match():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    cap = _cap("cap", 0, 3, 0)

    contact = phased_build_animation_states(
        [support, cap],
        0.30,
        top_progress=0.30,
        top_time_progress=0.30,
        top_cap_ids={id(cap)},
        top_surface_phase=0.20,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    rebound = phased_build_animation_states(
        [support, cap],
        0.32,
        top_progress=0.32,
        top_time_progress=0.32,
        top_cap_ids={id(cap)},
        top_surface_phase=0.20,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    by_contact = {state.placement.name: state for state in contact}
    by_rebound = {state.placement.name: state for state in rebound}

    assert by_contact["cap"].drop_t > by_rebound["cap"].drop_t
    assert by_rebound["cap"].y_offset > by_contact["cap"].y_offset


def test_smooth_top_bounce_uses_smooth_top_progress():
    support = _p("support", 0, 0, 0, w=1, h=3, d=1)
    cap = _cap("cap", 0, 3, 0)

    contact = phased_build_animation_states(
        [support, cap],
        1.0,
        top_progress=0.08,
        top_time_progress=0.08,
        top_cap_ids={id(cap)},
        top_surface_phase=0.15,
        blend_top_surface=False,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    rebound = phased_build_animation_states(
        [support, cap],
        1.0,
        top_progress=0.10,
        top_time_progress=0.10,
        top_cap_ids={id(cap)},
        top_surface_phase=0.15,
        blend_top_surface=False,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    by_contact = {state.placement.name: state for state in contact}
    by_rebound = {state.placement.name: state for state in rebound}

    assert by_contact["cap"].drop_t > by_rebound["cap"].drop_t
    assert by_rebound["cap"].y_offset > by_contact["cap"].y_offset


def test_late_smooth_top_bounce_keeps_fixed_duration():
    supports = [
        _p("support_{0}".format(i), i, i, 0, w=1, h=3, d=1)
        for i in range(8)
    ]
    caps = [
        _cap("cap_{0}".format(i), i, i + 3, 0)
        for i in range(8)
    ]
    cap_ids = {id(cap) for cap in caps}
    placements = supports + caps

    dropping = phased_build_animation_states(
        placements,
        1.0,
        top_progress=0.80,
        top_time_progress=0.80,
        top_cap_ids=cap_ids,
        top_surface_phase=0.15,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    rebounding = phased_build_animation_states(
        placements,
        1.0,
        top_progress=0.84,
        top_time_progress=0.84,
        top_cap_ids=cap_ids,
        top_surface_phase=0.15,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    settled = phased_build_animation_states(
        placements,
        1.0,
        top_progress=1.0,
        top_time_progress=1.0,
        top_cap_ids=cap_ids,
        top_surface_phase=0.15,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    by_dropping = {state.placement.name: state for state in dropping}
    by_rebounding = {state.placement.name: state for state in rebounding}
    by_settled = {state.placement.name: state for state in settled}

    assert 0.0 < by_dropping["cap_7"].local_progress < 1.0
    assert by_dropping["cap_7"].y_offset > by_rebounding["cap_7"].y_offset
    assert by_rebounding["cap_7"].y_offset > 0.0
    assert by_settled["cap_7"].local_progress == 1.0
    assert math.isclose(by_settled["cap_7"].y_offset, 0.0)


def test_late_smooth_top_does_not_snap_on_final_progress():
    supports = [
        _p("support_{0}".format(i), i, i, 0, w=1, h=3, d=1)
        for i in range(8)
    ]
    caps = [
        _cap("cap_{0}".format(i), i, i + 3, 0)
        for i in range(8)
    ]
    cap_ids = {id(cap) for cap in caps}
    placements = supports + caps

    almost_done = phased_build_animation_states(
        placements,
        0.9999,
        top_progress=0.9999,
        top_time_progress=0.9999,
        top_cap_ids=cap_ids,
        top_surface_phase=0.15,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    done = phased_build_animation_states(
        placements,
        1.0,
        top_progress=1.0,
        top_time_progress=1.0,
        top_cap_ids=cap_ids,
        top_surface_phase=0.15,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    by_almost_done = {state.placement.name: state for state in almost_done}
    by_done = {state.placement.name: state for state in done}

    assert by_almost_done["cap_7"].local_progress > 0.99
    assert by_almost_done["cap_7"].y_offset < 0.1
    assert by_done["cap_7"].local_progress == 1.0
    assert math.isclose(by_done["cap_7"].y_offset, 0.0)


def test_late_smooth_tops_keep_staggered_tail_timing():
    supports = [
        _p("support_{0}".format(i), i, i, 0, w=1, h=3, d=1)
        for i in range(8)
    ]
    caps = [
        _cap("cap_{0}".format(i), i, i + 3, 0)
        for i in range(8)
    ]
    cap_ids = {id(cap) for cap in caps}
    placements = supports + caps

    states = phased_build_animation_states(
        placements,
        0.78,
        top_progress=0.876,
        top_time_progress=0.876,
        top_cap_ids=cap_ids,
        top_surface_phase=0.15,
        blend_top_surface=True,
        y_offset=10.0,
        stagger=0.0,
        hang_time=0.0,
        motion_curve=BUILD_MOTION_CURVE_BOUNCE,
    )
    by_name = {state.placement.name: state for state in states}
    late_progress = [
        by_name["cap_{0}".format(i)].local_progress
        for i in range(4, 8)
    ]

    assert len({round(value, 3) for value in late_progress}) > 1
    assert any(0.0 < value < 1.0 for value in late_progress)


def test_random_mix_caps_never_overhang_silhouette():
    # An L-shaped pair of tall bricks: the union of their top cells is the
    # silhouette every random cap must lie inside. No cap may extend outside.
    a = _p("a", 0, 0, 0, w=3, h=3, d=1)
    b = _p("b", 0, 0, 1, w=1, h=3, d=2)
    placements = [a, b]
    silhouette = set()
    for p in placements:
        top_y = p.y + p.h
        for x in range(p.x, p.x + p.w):
            for z in range(p.z, p.z + p.d):
                silhouette.add((x, top_y, z))

    caps = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_RANDOM_MIX, seed=7
    )

    # Every cap cell must lie within the silhouette (no overhang).
    for cap in caps:
        for ix in range(cap.w):
            for iz in range(cap.d):
                assert (cap.x + ix, cap.y, cap.z + iz) in silhouette

    # Coverage must be complete: union of cap footprints equals silhouette.
    covered = set()
    for cap in caps:
        for ix in range(cap.w):
            for iz in range(cap.d):
                covered.add((cap.x + ix, cap.y, cap.z + iz))
    assert covered == silhouette


def test_random_mix_caps_are_deterministic_per_seed():
    placements = [_p("tall", 0, 0, 0, w=4, h=3, d=3)]
    caps_a = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_RANDOM_MIX, seed=42
    )
    caps_b = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_RANDOM_MIX, seed=42
    )
    caps_c = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_RANDOM_MIX, seed=43
    )

    sig_a = [(c.x, c.y, c.z, c.w, c.d) for c in caps_a]
    sig_b = [(c.x, c.y, c.z, c.w, c.d) for c in caps_b]
    sig_c = [(c.x, c.y, c.z, c.w, c.d) for c in caps_c]
    assert sig_a == sig_b
    # Different seed must produce a different tiling for a footprint big
    # enough that random choices actually matter.
    assert sig_a != sig_c


def test_merged_cover_unions_adjacent_brick_tops():
    # Two adjacent 1x1 tall bricks at the same y. Match Below would emit
    # two separate 1x1 caps; Merged Cover should union them into one 1x2
    # (or 2x1) library plate.
    a = _p("a", 0, 0, 0, w=1, h=3, d=1)
    b = _p("b", 1, 0, 0, w=1, h=3, d=1)

    match_caps = missing_smooth_top_cap_placements(
        [a, b], cap_style=CAP_STYLE_MATCH_BELOW
    )
    merged_caps = missing_smooth_top_cap_placements(
        [a, b], cap_style=CAP_STYLE_MERGED_COVER
    )

    assert len(match_caps) == 2
    assert len(merged_caps) == 1
    cap = merged_caps[0]
    assert cap.y == 3
    assert cap.w * cap.d == 2


def test_merged_cover_is_deterministic_and_silhouette_safe():
    a = _p("a", 0, 0, 0, w=3, h=3, d=1)
    b = _p("b", 0, 0, 1, w=1, h=3, d=2)
    placements = [a, b]
    silhouette = set()
    for p in placements:
        top_y = p.y + p.h
        for x in range(p.x, p.x + p.w):
            for z in range(p.z, p.z + p.d):
                silhouette.add((x, top_y, z))

    caps_a = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_MERGED_COVER
    )
    caps_b = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_MERGED_COVER
    )
    sig_a = [(c.x, c.y, c.z, c.w, c.d) for c in caps_a]
    sig_b = [(c.x, c.y, c.z, c.w, c.d) for c in caps_b]
    assert sig_a == sig_b  # determinism

    covered = set()
    for c in caps_a:
        for ix in range(c.w):
            for iz in range(c.d):
                cell = (c.x + ix, c.y, c.z + iz)
                assert cell in silhouette  # no overhang
                covered.add(cell)
    assert covered == silhouette  # full coverage


def test_cap_style_honored_with_target_top_cells():
    # Surface-only-plates mode passes target_top_cells. The dispatch must
    # honor cap_style for Random Mix and Largest Merged Plates instead of
    # silently falling back to match-below tiling.
    a = _p("a", 0, 0, 0, w=1, h=3, d=1)
    b = _p("b", 1, 0, 0, w=1, h=3, d=1)
    placements = [a, b]
    target = {(0, 3, 0), (1, 3, 0)}

    match = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_MATCH_BELOW, target_top_cells=target
    )
    merged = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_MERGED_COVER, target_top_cells=target
    )
    random_mix = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_RANDOM_MIX, seed=1, target_top_cells=target
    )

    # Match-below: two adjacent 1x1 tall bricks each get their own 1x1 cap.
    assert len(match) == 2
    # Merged Cover: the two adjacent tops union into a single 1x2 (or 2x1)
    # plate. This is the user-visible distinction that earlier regressed.
    assert len(merged) == 1
    assert merged[0].w * merged[0].d == 2
    # Random Mix uses a 1x1 fallback when no library is provided, so its
    # output is at least different in count or layout from match-below in
    # general — here a 2-cell silhouette with no library ends up as two
    # 1x1 caps. The key assertion is no overhang outside `target`.
    for c in random_mix:
        for ix in range(c.w):
            for iz in range(c.d):
                assert (c.x + ix, c.y, c.z + iz) in target


def test_full_coverage_honors_cap_style():
    # smooth_top_cap_selection_for_coverage at full coverage previously
    # always fell through to the match-below tiler regardless of cap_style.
    a = _p("a", 0, 0, 0, w=1, h=3, d=1)
    b = _p("b", 1, 0, 0, w=1, h=3, d=1)
    placements = [a, b]

    _, match_caps = smooth_top_cap_selection_for_coverage(
        placements, 1.0, cap_style=CAP_STYLE_MATCH_BELOW
    )
    _, merged_caps = smooth_top_cap_selection_for_coverage(
        placements, 1.0, cap_style=CAP_STYLE_MERGED_COVER
    )

    # Same setup as above: match-below emits 2 caps, merged_cover unions to 1.
    assert len(match_caps) == 2
    assert len(merged_caps) == 1
    assert merged_caps[0].w * merged_caps[0].d == 2


def test_random_mix_default_match_below_unchanged():
    # When cap_style isn't passed, behavior must match the legacy match-below
    # path (the existing test suite covers the exact expected output).
    placements = [_p("tall", 0, 0, 0, w=2, h=3, d=2)]
    default_caps = missing_smooth_top_cap_placements(placements)
    explicit_caps = missing_smooth_top_cap_placements(
        placements, cap_style=CAP_STYLE_MATCH_BELOW
    )
    sig_d = sorted((c.x, c.y, c.z, c.w, c.d) for c in default_caps)
    sig_e = sorted((c.x, c.y, c.z, c.w, c.d) for c in explicit_caps)
    assert sig_d == sig_e


def main():
    test_order_bottom_to_top_with_stable_ties()
    test_progress_states_hide_enter_drop_and_land()
    test_adjustable_offset_and_stagger_window()
    test_stagger_does_not_pull_landed_lower_layers_back_up()
    test_stagger_locks_only_nonstaggered_landed_layers()
    test_staggered_bricks_enter_with_smooth_drop_progress()
    test_same_y_bricks_share_build_progress()
    test_stagger_spreads_bricks_within_active_y_layer()
    test_in_layer_stagger_does_not_snap_to_landed_at_layer_boundary()
    test_stagger_visibility_frontier_hides_far_ahead_layers()
    test_incoming_staggered_bricks_get_varied_y_offsets()
    test_landed_staggered_bricks_keep_exact_final_y_offset()
    test_low_nonzero_stagger_has_minimum_visible_window()
    test_motion_curves_are_selectable()
    test_brick_hang_time_controls_initial_drop_motion()
    test_brick_hang_time_preserves_final_landing()
    test_bounce_motion_curve_never_overshoots_landing()
    test_bounce_motion_curve_contacts_then_rebounds()
    test_structural_bounce_keeps_curve_progress_visible()
    test_top_structural_bounce_completes_before_final_frame()
    test_bounce_uses_linear_time_progress_when_build_progress_eases()
    test_non_bounce_curves_ignore_linear_time_progress()
    test_final_blended_cap_bounce_has_pre_end_rebound_window()
    test_custom_motion_curve_is_sampled()
    test_scale_in_uses_small_minimum_scale()
    test_scale_in_resolves_at_bounce_contact()
    test_subtle_rotation_is_stable_and_lands_flat()
    test_subtle_rotation_resolves_at_bounce_contact()
    test_tilt_clearance_fades_with_tilt()
    test_separated_center_matches_low_corner_plus_half_extents()
    test_separated_center_preserves_separation_expansion()
    test_default_animation_values_are_gentler_than_original()
    test_exposed_top_caps_are_final_state_only()
    test_missing_smooth_caps_cover_exposed_studs_on_tall_bricks()
    test_top_surface_coverage_limits_generated_caps()
    test_top_surface_coverage_limits_existing_and_generated_caps()
    test_full_top_surface_coverage_covers_every_exposed_top_cell()
    test_near_full_top_surface_coverage_uses_full_cell_guarantee()
    test_shell_exterior_top_cells_exclude_interior_void()
    test_shell_exterior_top_cells_return_none_without_voxel_data()
    test_shell_smooth_caps_only_target_exterior_top_cells()
    test_shell_targets_project_exterior_columns_to_fitted_tops()
    test_shell_projected_targets_do_not_cap_lower_interior_tops()
    test_shell_targets_include_fitted_open_top_without_voxel_column_match()
    test_top_surface_coverage_can_use_random_order()
    test_top_surface_phase_builds_caps_last()
    test_top_surface_start_overlaps_structural_build()
    test_blended_top_caps_use_varied_speeds()
    test_blended_top_caps_varied_speeds_still_land_at_end()
    test_top_surface_caps_wait_for_support_to_land()
    test_support_lookup_matches_scan_for_blended_caps()
    test_blended_top_caps_start_from_zero_for_late_supports()
    test_blended_top_caps_require_full_footprint_support()
    test_existing_smooth_top_plates_stay_in_structural_timeline()
    test_blended_existing_smooth_top_plates_follow_smooth_top_progress()
    test_existing_smooth_top_plates_use_final_phase_when_not_blended()
    test_smooth_top_progress_is_independent_from_build_progress()
    test_blended_smooth_top_progress_still_waits_for_support()
    test_smooth_top_curve_starts_after_support_when_sliders_match()
    test_smooth_top_bounce_rebounds_when_sliders_match()
    test_smooth_top_bounce_uses_smooth_top_progress()
    test_late_smooth_top_bounce_keeps_fixed_duration()
    test_late_smooth_top_does_not_snap_on_final_progress()
    test_late_smooth_tops_keep_staggered_tail_timing()
    test_random_mix_caps_never_overhang_silhouette()
    test_random_mix_caps_are_deterministic_per_seed()
    test_random_mix_default_match_below_unchanged()
    test_merged_cover_unions_adjacent_brick_tops()
    test_merged_cover_is_deterministic_and_silhouette_safe()
    test_cap_style_honored_with_target_top_cells()
    test_full_coverage_honors_cap_style()
    print("brickit animation regressions passed")


if __name__ == "__main__":
    main()
