"""BrickIt build-progress ordering and animation helpers."""
from dataclasses import dataclass
import math


BUILD_ANIMATION_DEFAULT_Y_OFFSET = 25.0
BUILD_ANIMATION_DEFAULT_STAGGER = 0.10
BUILD_ANIMATION_MIN_EFFECTIVE_STAGGER = 0.03
BUILD_ANIMATION_SLAM_EXPONENT = 3.0

BUILD_MOTION_CURVE_EASE = 0
BUILD_MOTION_CURVE_EASE_IN = 1
BUILD_MOTION_CURVE_EASE_OUT = 2
BUILD_MOTION_CURVE_SPRING = 3
BUILD_MOTION_CURVE_SLAM = 4
BUILD_MOTION_CURVE_QUADRATIC = 5
BUILD_MOTION_CURVE_CUSTOM = 6


@dataclass(frozen=True)
class BuildAnimationState:
    placement: object
    order_index: int
    local_progress: float
    drop_t: float
    y_offset: float


@dataclass(frozen=True)
class VisualCapBrickType:
    name: str = "visual_smooth_cap_1x1"
    width: int = 1
    depth: int = 1
    height: int = 1
    ldraw_code: str = "visual_smooth_cap_1x1"


@dataclass(frozen=True)
class VisualCapPlacement:
    brick: object
    x: int
    y: int
    z: int
    rotation_y: int = 0
    color_idx: int = -1
    rgb: tuple = (180, 180, 180)

    @property
    def w(self):
        return 1

    @property
    def d(self):
        return 1

    @property
    def h(self):
        return 1


def _occupied_cells(placements):
    occupied = set()
    for p in placements:
        for x in range(int(getattr(p, "x", 0)), int(getattr(p, "x", 0) + getattr(p, "w", 1))):
            for y in range(int(getattr(p, "y", 0)), int(getattr(p, "y", 0) + getattr(p, "h", 1))):
                for z in range(int(getattr(p, "z", 0)), int(getattr(p, "z", 0) + getattr(p, "d", 1))):
                    occupied.add((x, y, z))
    return occupied


def exposed_top_cap_ids(placements):
    """Return ids for one-plate placements with any visible final top area."""
    placements = list(placements or [])
    occupied = _occupied_cells(placements)

    out = set()
    for p in placements:
        if int(getattr(p, "h", 1)) != 1:
            continue
        top_y = int(getattr(p, "y", 0) + getattr(p, "h", 1))
        exposed = False
        for x in range(int(getattr(p, "x", 0)), int(getattr(p, "x", 0) + getattr(p, "w", 1))):
            for z in range(int(getattr(p, "z", 0)), int(getattr(p, "z", 0) + getattr(p, "d", 1))):
                if (x, top_y, z) not in occupied:
                    exposed = True
                    break
            if exposed:
                break
        if exposed:
            out.add(id(p))
    return out


def missing_smooth_top_cap_placements(placements):
    """Create visual 1x1 smooth caps for exposed studs on taller bricks."""
    placements = list(placements or [])
    occupied = _occupied_cells(placements)
    cap_brick = VisualCapBrickType()
    caps = []
    seen = set()
    for p in placements:
        if int(getattr(p, "h", 1)) <= 1:
            continue
        top_y = int(getattr(p, "y", 0) + getattr(p, "h", 1))
        rgb = tuple(getattr(p, "rgb", (180, 180, 180)))
        color_idx = int(getattr(p, "color_idx", -1))
        for x in range(int(getattr(p, "x", 0)), int(getattr(p, "x", 0) + getattr(p, "w", 1))):
            for z in range(int(getattr(p, "z", 0)), int(getattr(p, "z", 0) + getattr(p, "d", 1))):
                key = (x, top_y, z)
                if key in occupied or key in seen:
                    continue
                seen.add(key)
                caps.append(
                    VisualCapPlacement(
                        brick=cap_brick,
                        x=x,
                        y=top_y,
                        z=z,
                        rotation_y=0,
                        color_idx=color_idx,
                        rgb=rgb,
                    )
                )
    return caps


def smooth_top_cap_placements_for_coverage(placements, coverage):
    """Return generated smooth caps for the requested coverage amount."""
    caps = missing_smooth_top_cap_placements(placements)
    if not caps:
        return []
    amount = _clamp01(coverage)
    n_visible = int(round(float(len(caps)) * amount))
    if n_visible <= 0:
        return []
    if n_visible >= len(caps):
        return caps
    return ordered_placements(caps)[:n_visible]


def _placement_sort_key(index, placement):
    return (
        int(getattr(placement, "y", 0)),
        int(getattr(placement, "z", 0)),
        int(getattr(placement, "x", 0)),
        int(getattr(placement, "h", 1)),
        int(getattr(placement, "d", 1)),
        int(getattr(placement, "w", 1)),
        int(getattr(placement, "rotation_y", 0)),
        int(index),
    )


def ordered_placements(placements):
    """Return placements in deterministic bottom-to-top build order."""
    return [
        placement
        for _, placement in sorted(
            enumerate(placements or []),
            key=lambda item: _placement_sort_key(item[0], item[1]),
        )
    ]


def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def _effective_stagger(value):
    stagger = _clamp01(value)
    if stagger <= 0.0:
        return 0.0
    return max(BUILD_ANIMATION_MIN_EFFECTIVE_STAGGER, stagger)


def sample_custom_curve(curve_data, t):
    """Sample a C4D SplineData-like curve at normalized progress."""
    if curve_data is None or not hasattr(curve_data, "GetPoint"):
        return t
    try:
        point = curve_data.GetPoint(_clamp01(t))
        value = getattr(point, "y", None)
        if value is None:
            value = point[1]
        return _clamp01(value)
    except Exception:
        return t


def custom_curve_signature(curve_data, samples=11):
    """Return a compact sampled signature for cache invalidation."""
    if curve_data is None:
        return None
    count = max(2, int(samples))
    return tuple(
        round(sample_custom_curve(curve_data, i / float(count - 1)), 4)
        for i in range(count)
    )


def apply_motion_curve(t, curve=BUILD_MOTION_CURVE_SLAM, custom_curve=None):
    """Map local progress through the selected build motion curve."""
    t = _clamp01(t)
    curve = int(curve)
    if curve == BUILD_MOTION_CURVE_CUSTOM:
        return sample_custom_curve(custom_curve, t)
    if curve == BUILD_MOTION_CURVE_EASE:
        return t * t * (3.0 - 2.0 * t)
    if curve == BUILD_MOTION_CURVE_EASE_IN:
        return t * t * t
    if curve == BUILD_MOTION_CURVE_EASE_OUT:
        inv = 1.0 - t
        return 1.0 - (inv * inv * inv)
    if curve == BUILD_MOTION_CURVE_SPRING:
        # A damped overshoot, clamped for matrix offsets so bricks never pass
        # through their final position.
        value = 1.0 - (math.cos(t * math.pi * 4.5) * math.exp(-6.0 * t))
        return _clamp01(value)
    if curve == BUILD_MOTION_CURVE_QUADRATIC:
        return t * t
    return t ** BUILD_ANIMATION_SLAM_EXPONENT


def build_animation_states(
    placements,
    progress,
    *,
    y_offset=BUILD_ANIMATION_DEFAULT_Y_OFFSET,
    stagger=BUILD_ANIMATION_DEFAULT_STAGGER,
    motion_curve=BUILD_MOTION_CURVE_SLAM,
    custom_curve=None,
    order_offset=0,
):
    """Return per-placement animation states in chronological order."""
    ordered = ordered_placements(placements)
    return _build_animation_states_for_ordered(
        ordered,
        progress,
        y_offset=y_offset,
        stagger=stagger,
        motion_curve=motion_curve,
        custom_curve=custom_curve,
        order_offset=order_offset,
    )


def _build_animation_states_for_ordered(
    ordered,
    progress,
    *,
    y_offset,
    stagger,
    motion_curve=BUILD_MOTION_CURVE_SLAM,
    custom_curve=None,
    order_offset=0,
):
    n = len(ordered)
    if n <= 0:
        return []

    duration_slots = 1.0 + (_effective_stagger(stagger) * float(max(0, n - 1)))
    timeline_slots = float(n) + duration_slots - 1.0
    build_cursor = _clamp01(progress) * timeline_slots
    start_offset = max(0.0, float(y_offset))
    states = []
    for i, placement in enumerate(ordered):
        local_progress = _clamp01((build_cursor - float(i)) / duration_slots)
        drop_t = apply_motion_curve(local_progress, motion_curve, custom_curve)
        animated_y_offset = (1.0 - drop_t) * start_offset
        states.append(
            BuildAnimationState(
                placement=placement,
                order_index=int(order_offset) + i,
                local_progress=local_progress,
                drop_t=drop_t,
                y_offset=animated_y_offset,
            )
        )
    return states


def phased_build_animation_states(
    placements,
    progress,
    *,
    top_cap_ids=None,
    top_surface_phase=0.0,
    y_offset=BUILD_ANIMATION_DEFAULT_Y_OFFSET,
    stagger=BUILD_ANIMATION_DEFAULT_STAGGER,
    motion_curve=BUILD_MOTION_CURVE_SLAM,
    custom_curve=None,
):
    """Animate structural placements first, then exposed smooth top caps."""
    top_cap_ids = set(top_cap_ids or ())
    ordered = ordered_placements(placements)
    if not ordered:
        return []

    cap_phase = _clamp01(top_surface_phase)
    if not top_cap_ids or cap_phase <= 0.0:
        return _build_animation_states_for_ordered(
            ordered,
            progress,
            y_offset=y_offset,
            stagger=stagger,
            motion_curve=motion_curve,
            custom_curve=custom_curve,
        )

    structural = [p for p in ordered if id(p) not in top_cap_ids]
    caps = [p for p in ordered if id(p) in top_cap_ids]
    if not structural or not caps:
        return _build_animation_states_for_ordered(
            ordered,
            progress,
            y_offset=y_offset,
            stagger=stagger,
            motion_curve=motion_curve,
            custom_curve=custom_curve,
        )

    p = _clamp01(progress)
    structural_phase = max(0.0001, 1.0 - cap_phase)
    structural_progress = _clamp01(p / structural_phase)
    cap_progress = _clamp01((p - structural_phase) / cap_phase)
    return (
        _build_animation_states_for_ordered(
            structural,
            structural_progress,
            y_offset=y_offset,
            stagger=stagger,
            motion_curve=motion_curve,
            custom_curve=custom_curve,
            order_offset=0,
        )
        + _build_animation_states_for_ordered(
            caps,
            cap_progress,
            y_offset=y_offset,
            stagger=stagger,
            motion_curve=motion_curve,
            custom_curve=custom_curve,
            order_offset=len(structural),
        )
    )
