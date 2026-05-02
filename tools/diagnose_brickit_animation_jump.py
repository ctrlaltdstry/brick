"""Diagnose BrickIt animation transform jumps inside Cinema 4D.

Run from Cinema 4D's Script Manager with the BrickIt object selected.

The script samples the selected BrickIt generator across the document timeline,
forces generator evaluation, and reports:
  - Build Progress / Smooth Top Progress values per sampled frame
  - generated instance counts
  - visibility flips
  - largest per-instance transform jumps between adjacent sampled frames

The report is printed to the C4D console and also written to the Desktop as:
    brickit_animation_jump_report.txt
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import c4d


ID_BRICKIFYASSEMBLY = 1069998
BRICKIFYASSEMBLY_BUILD_PROGRESS = 2047
BRICKIFYASSEMBLY_SMOOTH_TOP_PROGRESS = 2097
BRICKIFYASSEMBLY_BUILD_MOTION_CURVE = 2071
BRICKIFYASSEMBLY_BUILD_STAGGER = 2049
BRICKIFYASSEMBLY_BUILD_HANG_TIME = 2096
BRICKIFYASSEMBLY_TOP_SURFACE_BLEND = 2086
BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE = 2070
BRICKIFYASSEMBLY_BRICK_SEPARATION = 2076

SAMPLE_WHOLE_TIMELINE = True
SAMPLE_EVERY_N_FRAMES = 1
SAMPLE_FRAMES_BEFORE_END = 24  # Used only when SAMPLE_WHOLE_TIMELINE=False.
SAMPLE_FRAMES_AFTER_END = 2
MAX_DELTA_SUMMARIES = 30
MAX_OBJECT_ROWS = 30
JUMP_WARN_DISTANCE = 0.5
Y_JUMP_WARN_DISTANCE = 0.25
PARKED_COORD_THRESHOLD = 1000000.0


@dataclass
class InstanceSample:
    key: str
    name: str
    path: str
    x: float
    y: float
    z: float
    visible_editor: int
    visible_render: int
    is_smooth: bool
    matrix_count: int
    ref_name: str


@dataclass
class FrameSample:
    frame: int
    build_progress: float
    smooth_progress: float
    motion_curve: int
    cache_name: str
    instance_count: int
    smooth_count: int
    samples: dict


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _obj_name(obj):
    try:
        return obj.GetName()
    except Exception:
        return "<unnamed>"


def _obj_path(obj):
    names = []
    cur = obj
    while cur is not None:
        names.append(_obj_name(cur))
        try:
            cur = cur.GetUp()
        except Exception:
            cur = None
    return "/".join(reversed(names))


def _find_brickit(doc):
    active = doc.GetActiveObject()
    if active is not None and active.GetType() == ID_BRICKIFYASSEMBLY:
        return active

    def walk(obj):
        while obj is not None:
            if obj.GetType() == ID_BRICKIFYASSEMBLY:
                return obj
            child = obj.GetDown()
            found = walk(child) if child is not None else None
            if found is not None:
                return found
            obj = obj.GetNext()
        return None

    return walk(doc.GetFirstObject())


def _walk(obj):
    while obj is not None:
        yield obj
        child = obj.GetDown()
        if child is not None:
            for item in _walk(child):
                yield item
        obj = obj.GetNext()


def _get_cache_root(op):
    try:
        return op.GetCache()
    except Exception:
        return None


def _get_reference_name(obj):
    ref = None
    try:
        ref = obj.GetReferenceObject()
    except Exception:
        pass
    if ref is None:
        try:
            ref = obj[c4d.INSTANCEOBJECT_LINK]
        except Exception:
            ref = None
    return _obj_name(ref) if ref is not None else ""


def _get_instance_matrix_offset(obj):
    """Return (offset, matrix_count), preferring the single MI matrix."""
    try:
        matrices = obj.GetInstanceMatrices()
        if matrices:
            m = matrices[0]
            return m.off, len(matrices)
    except Exception:
        pass

    try:
        m = obj.GetMg()
        return m.off, 0
    except Exception:
        pass

    try:
        m = obj.GetMl()
        return m.off, 0
    except Exception:
        return c4d.Vector(0.0, 0.0, 0.0), 0


def _object_visibility(obj, cid):
    try:
        return _safe_int(obj[cid], default=-999)
    except Exception:
        return -999


def _is_instance_like(obj):
    try:
        if obj.GetType() == c4d.Oinstance:
            return True
    except Exception:
        pass
    try:
        return obj.__class__.__name__.lower().find("instance") >= 0
    except Exception:
        return False


def _collect_instances(cache_root):
    out = {}
    if cache_root is None:
        return out
    for obj in _walk(cache_root):
        if not _is_instance_like(obj):
            continue
        name = _obj_name(obj)
        path = _obj_path(obj)
        ref_name = _get_reference_name(obj)
        offset, matrix_count = _get_instance_matrix_offset(obj)
        is_smooth = (
            "_smooth" in ref_name
            or "smooth" in ref_name.lower()
            or "visual_smooth" in ref_name.lower()
        )
        key = name
        if key in out:
            key = path
        out[key] = InstanceSample(
            key=key,
            name=name,
            path=path,
            x=float(offset.x),
            y=float(offset.y),
            z=float(offset.z),
            visible_editor=_object_visibility(obj, c4d.ID_BASEOBJECT_VISIBILITY_EDITOR),
            visible_render=_object_visibility(obj, c4d.ID_BASEOBJECT_VISIBILITY_RENDER),
            is_smooth=bool(is_smooth),
            matrix_count=int(matrix_count),
            ref_name=ref_name,
        )
    return out


def _execute_frame(doc, frame, fps):
    doc.SetTime(c4d.BaseTime(int(frame), int(fps)))
    try:
        doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    except Exception:
        try:
            doc.ExecutePasses(None, True, True, True, 0)
        except Exception:
            pass
    c4d.EventAdd()


def _sample_frame(doc, op, frame, fps):
    _execute_frame(doc, frame, fps)
    cache = _get_cache_root(op)
    samples = _collect_instances(cache)
    smooth_count = sum(1 for s in samples.values() if s.is_smooth)
    return FrameSample(
        frame=int(frame),
        build_progress=_safe_float(op[BRICKIFYASSEMBLY_BUILD_PROGRESS]),
        smooth_progress=_safe_float(op[BRICKIFYASSEMBLY_SMOOTH_TOP_PROGRESS]),
        motion_curve=_safe_int(op[BRICKIFYASSEMBLY_BUILD_MOTION_CURVE]),
        cache_name=_obj_name(cache) if cache is not None else "<no cache>",
        instance_count=len(samples),
        smooth_count=smooth_count,
        samples=samples,
    )


def _frame_range(doc, fps):
    try:
        min_frame = doc.GetLoopMinTime().GetFrame(fps)
        max_frame = doc.GetLoopMaxTime().GetFrame(fps)
        if max_frame > min_frame:
            return int(min_frame), int(max_frame)
    except Exception:
        pass

    try:
        min_frame = doc.GetMinTime().GetFrame(fps)
        max_frame = doc.GetMaxTime().GetFrame(fps)
        if max_frame > min_frame:
            return int(min_frame), int(max_frame)
    except Exception:
        pass

    return 0, 90


def _distance(a, b):
    dx = b.x - a.x
    dy = b.y - a.y
    dz = b.z - a.z
    return math.sqrt((dx * dx) + (dy * dy) + (dz * dz))


def _is_parked(sample):
    return (
        abs(sample.x) >= PARKED_COORD_THRESHOLD
        or abs(sample.y) >= PARKED_COORD_THRESHOLD
        or abs(sample.z) >= PARKED_COORD_THRESHOLD
    )


def _delta_stats(prev, cur):
    common = sorted(set(prev.samples.keys()) & set(cur.samples.keys()))
    appeared = sorted(set(cur.samples.keys()) - set(prev.samples.keys()))
    disappeared = sorted(set(prev.samples.keys()) - set(cur.samples.keys()))

    max_dist = 0.0
    max_abs_dy = 0.0
    jump_count = 0
    visibility_count = 0
    smooth_jump_count = 0
    parked_transition_count = 0
    for key in common:
        a = prev.samples[key]
        b = cur.samples[key]
        if _is_parked(a) or _is_parked(b):
            if _is_parked(a) != _is_parked(b):
                parked_transition_count += 1
            continue
        dist = _distance(a, b)
        abs_dy = abs(b.y - a.y)
        max_dist = max(max_dist, dist)
        max_abs_dy = max(max_abs_dy, abs_dy)
        if dist >= JUMP_WARN_DISTANCE or abs_dy >= Y_JUMP_WARN_DISTANCE:
            jump_count += 1
            if b.is_smooth or a.is_smooth:
                smooth_jump_count += 1
        if (
            a.visible_editor != b.visible_editor
            or a.visible_render != b.visible_render
        ):
            visibility_count += 1

    return {
        "prev": prev,
        "cur": cur,
        "max_dist": max_dist,
        "max_abs_dy": max_abs_dy,
        "jump_count": jump_count,
        "smooth_jump_count": smooth_jump_count,
        "visibility_count": visibility_count,
        "parked_transition_count": parked_transition_count,
        "appeared": len(appeared),
        "disappeared": len(disappeared),
        "score": (
            max_dist
            + max_abs_dy
            + float(jump_count) * 0.01
            + float(visibility_count) * 0.02
            + float(len(appeared) + len(disappeared)) * 0.05
        ),
    }


def _describe_delta(prev, cur):
    common = sorted(set(prev.samples.keys()) & set(cur.samples.keys()))
    appeared = sorted(set(cur.samples.keys()) - set(prev.samples.keys()))
    disappeared = sorted(set(prev.samples.keys()) - set(cur.samples.keys()))

    jumps = []
    visibility_flips = []
    for key in common:
        a = prev.samples[key]
        b = cur.samples[key]
        if _is_parked(a) or _is_parked(b):
            continue
        dist = _distance(a, b)
        dy = b.y - a.y
        if dist >= JUMP_WARN_DISTANCE or abs(dy) >= Y_JUMP_WARN_DISTANCE:
            jumps.append((dist, abs(dy), dy, key, a, b))
        if (
            a.visible_editor != b.visible_editor
            or a.visible_render != b.visible_render
        ):
            visibility_flips.append((key, a, b))

    jumps.sort(key=lambda item: (item[0], item[1]), reverse=True)
    visibility_flips.sort(key=lambda item: item[0])

    lines = []
    lines.append(
        "Delta f{0}->f{1}: count {2}->{3}, smooth {4}->{5}, appeared={6}, disappeared={7}".format(
            prev.frame,
            cur.frame,
            prev.instance_count,
            cur.instance_count,
            prev.smooth_count,
            cur.smooth_count,
            len(appeared),
            len(disappeared),
        )
    )
    if jumps:
        lines.append("  largest transform jumps:")
        for dist, abs_dy, dy, key, a, b in jumps[:MAX_OBJECT_ROWS]:
            lines.append(
                "    {0}: dist={1:.3f}, dy={2:.3f}, y {3:.3f}->{4:.3f}, smooth={5}, ref={6}".format(
                    key,
                    dist,
                    dy,
                    a.y,
                    b.y,
                    b.is_smooth,
                    b.ref_name,
                )
            )
    if visibility_flips:
        lines.append("  visibility flips:")
        for key, a, b in visibility_flips[:MAX_OBJECT_ROWS]:
            lines.append(
                "    {0}: editor {1}->{2}, render {3}->{4}, smooth={5}, ref={6}".format(
                    key,
                    a.visible_editor,
                    b.visible_editor,
                    a.visible_render,
                    b.visible_render,
                    b.is_smooth,
                    b.ref_name,
                )
            )
    if appeared:
        lines.append("  appeared examples: {0}".format(", ".join(appeared[:10])))
    if disappeared:
        lines.append("  disappeared examples: {0}".format(", ".join(disappeared[:10])))
    return lines


def _write_report(lines):
    path = os.path.join(
        os.path.expanduser("~"),
        "Desktop",
        "brickit_animation_jump_report.txt",
    )
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.write("\n")
        return path
    except Exception:
        return None


def main():
    doc = c4d.documents.GetActiveDocument()
    if doc is None:
        print("[brick diag] No active document.")
        return

    op = _find_brickit(doc)
    if op is None:
        print("[brick diag] Select a BrickIt object, or add one to the scene.")
        return

    fps = int(doc.GetFps() or 30)
    min_frame, max_frame = _frame_range(doc, fps)
    if SAMPLE_WHOLE_TIMELINE:
        start_frame = min_frame
        end_frame = max_frame + SAMPLE_FRAMES_AFTER_END
    else:
        start_frame = max(min_frame, max_frame - SAMPLE_FRAMES_BEFORE_END)
        end_frame = max_frame + SAMPLE_FRAMES_AFTER_END
    step = max(1, int(SAMPLE_EVERY_N_FRAMES))
    frames = list(range(int(start_frame), int(end_frame) + 1, step))

    lines = []
    lines.append("BrickIt animation jump diagnostic")
    lines.append("Object: {0}".format(_obj_name(op)))
    lines.append("Timeline: {0}..{1} @ {2} fps".format(min_frame, max_frame, fps))
    lines.append(
        "Sampled frames: {0}..{1}, step={2}, whole_timeline={3}".format(
            frames[0],
            frames[-1],
            step,
            bool(SAMPLE_WHOLE_TIMELINE),
        )
    )
    lines.append(
        "Params now: build={0:.3f}, smooth={1:.3f}, curve={2}, stagger={3:.3f}, hang={4:.3f}, top_blend={5}, coverage={6:.3f}, separation={7:.3f}".format(
            _safe_float(op[BRICKIFYASSEMBLY_BUILD_PROGRESS]),
            _safe_float(op[BRICKIFYASSEMBLY_SMOOTH_TOP_PROGRESS]),
            _safe_int(op[BRICKIFYASSEMBLY_BUILD_MOTION_CURVE]),
            _safe_float(op[BRICKIFYASSEMBLY_BUILD_STAGGER]),
            _safe_float(op[BRICKIFYASSEMBLY_BUILD_HANG_TIME]),
            bool(op[BRICKIFYASSEMBLY_TOP_SURFACE_BLEND]),
            _safe_float(op[BRICKIFYASSEMBLY_TOP_SURFACE_COVERAGE]),
            _safe_float(op[BRICKIFYASSEMBLY_BRICK_SEPARATION]),
        )
    )
    lines.append("")

    samples = []
    old_time = doc.GetTime()
    try:
        for frame in frames:
            sample = _sample_frame(doc, op, frame, fps)
            samples.append(sample)
            lines.append(
                "Frame {0}: build={1:.3f}, smooth={2:.3f}, curve={3}, cache={4}, instances={5}, smooth={6}".format(
                    sample.frame,
                    sample.build_progress,
                    sample.smooth_progress,
                    sample.motion_curve,
                    sample.cache_name,
                    sample.instance_count,
                    sample.smooth_count,
                )
            )
        lines.append("")
        delta_stats = [
            _delta_stats(prev, cur)
            for prev, cur in zip(samples, samples[1:])
        ]
        interesting = [
            stat for stat in delta_stats
            if (
                stat["jump_count"]
                or stat["visibility_count"]
                or stat["appeared"]
                or stat["disappeared"]
            )
        ]
        interesting.sort(key=lambda item: item["score"], reverse=True)

        lines.append("Top suspicious deltas:")
        if not interesting:
            lines.append("  none above thresholds")
        for stat in interesting[:MAX_DELTA_SUMMARIES]:
            lines.append(
                "  f{0}->f{1}: max_dist={2:.3f}, max_abs_dy={3:.3f}, jumps={4}, smooth_jumps={5}, vis={6}, parked_transitions={7}, appeared={8}, disappeared={9}, build {10:.3f}->{11:.3f}, smooth {12:.3f}->{13:.3f}".format(
                    stat["prev"].frame,
                    stat["cur"].frame,
                    stat["max_dist"],
                    stat["max_abs_dy"],
                    stat["jump_count"],
                    stat["smooth_jump_count"],
                    stat["visibility_count"],
                    stat["parked_transition_count"],
                    stat["appeared"],
                    stat["disappeared"],
                    stat["prev"].build_progress,
                    stat["cur"].build_progress,
                    stat["prev"].smooth_progress,
                    stat["cur"].smooth_progress,
                )
            )
        lines.append("")

        # Detail the worst few frame pairs so the report stays readable even
        # over a full timeline scan.
        detailed = interesting[:5]
        if detailed:
            lines.append("Detailed worst deltas:")
            for stat in detailed:
                lines.extend(_describe_delta(stat["prev"], stat["cur"]))
                lines.append("")
    finally:
        doc.SetTime(old_time)
        try:
            doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        except Exception:
            pass
        c4d.EventAdd()

    report_path = _write_report(lines)
    for line in lines:
        print(line)
    if report_path:
        print("[brick diag] Wrote report: {0}".format(report_path))
    else:
        print("[brick diag] Could not write Desktop report; console output only.")


if __name__ == "__main__":
    main()
