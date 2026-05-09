"""Diagnose why BrickIt freezes / doesn't rebuild when bind-to-source is on.

Run from Cinema 4D's Script Manager with the BrickIt object selected.
Bind to Source Deformation must already be ON and an initial fit must
already exist before running.

Usage:
  1. Select the BrickIt object.
  2. Run this script. It installs probes on the BrickIt's Python instance
     and starts streaming events to:
        Desktop/brickit_bind_rebuild_log.txt
     in real time (each event flushed immediately, so a force-quit during
     a freeze keeps the data).
  3. Reproduce the failing action.
  4. If C4D freezes, force-quit. The log file on Desktop is complete up
     to the moment of the freeze — open it and find the LAST event line
     to see what was running.
  5. If C4D didn't freeze, re-run the script to dump a summary.

The probe records every entry/exit of:
  - Message (command + post-set-parameter)
  - GetVirtualObjects
  - _refit_if_needed
  - _get_cached_source_arrays  (with force_csto flag)

with re-entry depth and elapsed time per call. The very last log line
before the freeze identifies which call hung.
"""

from __future__ import annotations

import os
import threading
import time
import traceback

import c4d


ID_BRICKIFYASSEMBLY = 1069998

LOG_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "brickit_bind_rebuild_log.txt")
PROBE_FLAG = "_brickit_bind_rebuild_probe_installed"
LOG_LOCK_ATTR = "_brickit_bind_rebuild_log_lock"
DEPTH_ATTR = "_brickit_bind_rebuild_depth"


def _find_brickit(doc):
    sel = doc.GetActiveObject()
    if sel is not None and sel.GetType() == ID_BRICKIFYASSEMBLY:
        return sel
    obj = doc.GetFirstObject()
    stack = []
    while obj is not None:
        if obj.GetType() == ID_BRICKIFYASSEMBLY:
            return obj
        d = obj.GetDown()
        if d is not None:
            stack.append(obj.GetNext())
            obj = d
            continue
        nx = obj.GetNext()
        if nx is None and stack:
            obj = stack.pop()
        else:
            obj = nx
    return None


def _get_python_instance(brickit_op):
    for call in (
        lambda o: o.GetNodeData(),
        lambda o: o.GetNodeData(ID_BRICKIFYASSEMBLY),
    ):
        try:
            inst = call(brickit_op)
        except Exception:
            inst = None
        if inst is not None and hasattr(inst, "_resolve_params"):
            return inst
    return None


def _doc_frame(doc):
    try:
        return int(doc.GetTime().GetFrame(doc.GetFps()))
    except Exception:
        return -1


def _state(self):
    fp = getattr(self, "_fit_placements", None)
    return {
        "fr": getattr(self, "_force_rebuild", "?"),
        "bfr": getattr(self, "_bind_force_rebind", "?"),
        "csto_in_prog": getattr(self, "_csto_in_progress", False),
        "fk_none": getattr(self, "_fit_cache_key", None) is None,
        "hk_none": getattr(self, "_hierarchy_cache_key", None) is None,
        "bk_none": getattr(self, "_bind_cache_key", None) is None,
        "sk_none": getattr(self, "_source_cache_key", None) is None,
        "fp_len": len(fp) if fp is not None else None,
    }


def _install_probes(self, op):
    if getattr(self, PROBE_FLAG, False):
        return False

    log_lock = threading.Lock()
    setattr(self, LOG_LOCK_ATTR, log_lock)
    setattr(self, DEPTH_ATTR, {"gvo": 0, "refit": 0, "src": 0, "msg": 0, "seq": 0})
    depth = getattr(self, DEPTH_ATTR)

    # Truncate log on install so each probe session is self-contained.
    try:
        with open(LOG_PATH, "w", encoding="utf-8") as fh:
            fh.write("# BrickIt bind-rebuild log; install at {0}\n".format(time.strftime("%H:%M:%S")))
    except Exception:
        pass

    install_t0 = time.perf_counter()

    orig_message = self.Message
    orig_gvo = self.GetVirtualObjects
    orig_refit = self._refit_if_needed
    orig_get_src = self._get_cached_source_arrays

    def _flush(line):
        with log_lock:
            try:
                with open(LOG_PATH, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                    fh.flush()
                    try:
                        os.fsync(fh.fileno())
                    except Exception:
                        pass
            except Exception:
                pass

    def _emit(kind, **kw):
        depth["seq"] += 1
        seq = depth["seq"]
        rel = time.perf_counter() - install_t0
        try:
            frame = _doc_frame(op.GetDocument())
        except Exception:
            frame = -1
        st = _state(self)
        depths = "g{gvo}/r{refit}/s{src}/m{msg}".format(**depth)
        parts = [
            "#{0:05d}".format(seq),
            "t={0:8.3f}".format(rel),
            "f={0:>4d}".format(frame),
            "d={0}".format(depths),
            kind,
        ]
        for k in sorted(kw.keys()):
            parts.append("{0}={1}".format(k, kw[k]))
        parts.append(
            "st[fr={fr} bfr={bfr} csto={csto_in_prog} fk_none={fk_none} hk_none={hk_none} fp={fp_len}]".format(**st)
        )
        _flush(" ".join(parts))

    def probed_message(op_, msg_type, data):
        if msg_type == c4d.MSG_DESCRIPTION_COMMAND:
            try:
                desc_id = data["id"][0].id
            except Exception:
                desc_id = -1
            depth["msg"] += 1
            _emit("MSG.cmd.enter", desc_id=desc_id)
            t0 = time.perf_counter()
            try:
                rv = orig_message(op_, msg_type, data)
            except Exception as exc:
                _emit("MSG.cmd.RAISED", desc_id=desc_id, error=repr(exc))
                depth["msg"] -= 1
                raise
            _emit(
                "MSG.cmd.exit",
                desc_id=desc_id,
                rv=bool(rv),
                ms="{0:.1f}".format((time.perf_counter() - t0) * 1000.0),
            )
            depth["msg"] -= 1
            return rv
        if msg_type == c4d.MSG_DESCRIPTION_POSTSETPARAMETER:
            try:
                desc_id = data["descid"][0].id
            except Exception:
                try:
                    desc_id = data["id"][0].id
                except Exception:
                    desc_id = -1
            depth["msg"] += 1
            _emit("MSG.post.enter", desc_id=desc_id)
            t0 = time.perf_counter()
            try:
                rv = orig_message(op_, msg_type, data)
            except Exception as exc:
                _emit("MSG.post.RAISED", desc_id=desc_id, error=repr(exc))
                depth["msg"] -= 1
                raise
            _emit(
                "MSG.post.exit",
                desc_id=desc_id,
                rv=bool(rv),
                ms="{0:.1f}".format((time.perf_counter() - t0) * 1000.0),
            )
            depth["msg"] -= 1
            return rv
        return orig_message(op_, msg_type, data)

    def probed_gvo(op_, hh):
        depth["gvo"] += 1
        _emit("GVO.enter")
        t0 = time.perf_counter()
        result = None
        result_kind = "?"
        try:
            result = orig_gvo(op_, hh)
            if result is None:
                result_kind = "None"
            else:
                try:
                    result_kind = "{0}({1})".format(type(result).__name__, result.GetName())
                except Exception:
                    result_kind = type(result).__name__
        except Exception as exc:
            _emit("GVO.RAISED", error=repr(exc), tb=repr(traceback.format_exc()))
            depth["gvo"] -= 1
            raise
        _emit(
            "GVO.exit",
            result=result_kind,
            ms="{0:.1f}".format((time.perf_counter() - t0) * 1000.0),
        )
        depth["gvo"] -= 1
        return result

    def probed_refit(op_, doc, params=None):
        depth["refit"] += 1
        param_summary = ""
        if params is not None:
            param_summary = (
                "lib_mask={lm} studs_across={sa} bind={bd} mirror_x={mx} "
                "voxel_mode={vm} max_h={mh}"
            ).format(
                lm=params.get("lib_mask"),
                sa=params.get("studs_across"),
                bd=params.get("bind_to_source_deformation"),
                mx=params.get("mirror_x"),
                vm=params.get("voxel_mode"),
                mh=params.get("max_brick_height"),
            )
        _emit("refit.enter", params=param_summary)
        t0 = time.perf_counter()
        try:
            ok = orig_refit(op_, doc, params=params)
        except Exception as exc:
            _emit("refit.RAISED", error=repr(exc), tb=repr(traceback.format_exc()))
            depth["refit"] -= 1
            raise
        _emit(
            "refit.exit",
            ok=bool(ok),
            ms="{0:.1f}".format((time.perf_counter() - t0) * 1000.0),
        )
        depth["refit"] -= 1
        return ok

    def probed_get_src(op_, doc, force_csto=False):
        depth["src"] += 1
        _emit("src.enter", force_csto=bool(force_csto))
        t0 = time.perf_counter()
        try:
            data = orig_get_src(op_, doc, force_csto=force_csto)
        except Exception as exc:
            _emit("src.RAISED", error=repr(exc), tb=repr(traceback.format_exc()))
            depth["src"] -= 1
            raise
        if data is None:
            kind = "None"
        else:
            try:
                kind = "ok verts={0} faces={1}".format(len(data[1]), len(data[2]))
            except Exception:
                kind = "ok ?"
        _emit(
            "src.exit",
            result=kind,
            ms="{0:.1f}".format((time.perf_counter() - t0) * 1000.0),
        )
        depth["src"] -= 1
        return data

    self.Message = probed_message
    self.GetVirtualObjects = probed_gvo
    self._refit_if_needed = probed_refit
    self._get_cached_source_arrays = probed_get_src
    setattr(self, PROBE_FLAG, True)
    return True


def main():
    doc = c4d.documents.GetActiveDocument()
    if doc is None:
        print("[probe] No active document.")
        return
    brickit = _find_brickit(doc)
    if brickit is None:
        print("[probe] No BrickIt object in scene. Select one first.")
        return
    inst = _get_python_instance(brickit)
    if inst is None:
        print("[probe] Could not retrieve BrickIt's Python instance.")
        return

    if getattr(inst, PROBE_FLAG, False):
        # Already armed — just report log location and tail status.
        try:
            sz = os.path.getsize(LOG_PATH)
        except Exception:
            sz = -1
        print("[probe] Already armed. Log file: {0} ({1} bytes).".format(LOG_PATH, sz))
        print("[probe] Open the log to inspect the trace. Force-quit C4D to keep current trace.")
        return

    if _install_probes(inst, brickit):
        print("[probe armed] BrickIt: {0}.".format(brickit.GetName()))
        print("[probe] Streaming events to: {0}".format(LOG_PATH))
        print("[probe] Reproduce the freeze. The LAST line in the log is what was running when C4D hung.")
    else:
        print("[probe] Install failed.")


if __name__ == "__main__":
    main()
