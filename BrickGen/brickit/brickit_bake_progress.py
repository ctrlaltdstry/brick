"""Native progress dialog that DRIVES the per-frame fit bake via a Timer.

Why Timer-driven: a blocking Python loop on the main thread cannot process
events, so Cancel/ESC never fire and the bar can't repaint (C4D exposes no
message-pump from Python). Driving the bake from the dialog's Timer — one
frame per tick — returns to C4D's event loop between frames, so the native
progress bar animates and Cancel/ESC stay responsive.

Why this is safe now: the bake runs on a CLONED document (see brickit_fit
_bake_*). The earlier Timer version crashed because it re-evaluated the LIVE
document, re-entering this generator's own evaluation (gv_world). Stepping a
clone never touches the live generator, so Timer + clone is safe.
"""
import c4d
from c4d import gui

_GADGET_BAR = 3001
_GADGET_TEXT = 3002
_TIMER_MS = 1  # one frame per tick, as fast as the host allows


class _BakeDialog(gui.GeDialog):
    def __init__(self, owner, state, step_fn, finish_fn):
        super().__init__()
        self._owner = owner
        self._state = state
        self._step = step_fn
        self._finish = finish_fn
        self._bar = None
        self._cancel = False
        self._wrapped = False

    def CreateLayout(self):
        self.SetTitle("Cubify — Caching Fit")
        self.GroupBegin(1000, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)
        self.GroupBorderSpace(14, 12, 14, 12)
        self._bar = self.AddCustomGui(
            _GADGET_BAR, c4d.CUSTOMGUI_PROGRESSBAR, "",
            c4d.BFH_SCALEFIT, 380, 14, c4d.BaseContainer(),
        )
        self.AddStaticText(_GADGET_TEXT, c4d.BFH_SCALEFIT, 0, 0, "Starting…", 0)
        self.AddDlgGroup(c4d.DLG_CANCEL)
        self.GroupEnd()
        return True

    def InitValues(self):
        self.SetTimer(_TIMER_MS)
        self._set_bar(0.0, "Starting…")
        return True

    def _set_bar(self, frac, label):
        try:
            msg = c4d.BaseContainer(c4d.BFM_SETSTATUSBAR)
            msg[c4d.BFM_STATUSBAR_PROGRESSON] = True
            msg[c4d.BFM_STATUSBAR_PROGRESS] = max(0.0, min(1.0, float(frac)))
            self.SendMessage(_GADGET_BAR, msg)
        except Exception:
            pass
        if label:
            try:
                self.SetString(_GADGET_TEXT, label)
            except Exception:
                pass

    def Timer(self, msg):
        st = self._state
        if self._cancel or st.finished:
            self._wrap_up()
            return
        # Process one frame on the clone.
        try:
            self._step(self._owner, st)
        except Exception:
            pass
        self._set_bar(
            st.done / st.total,
            "Frame {0} / {1}   ({2} of {3})".format(
                min(st.frame, st.end_frame), st.end_frame, st.done, st.total,
            ),
        )
        if st.finished:
            self._wrap_up()

    def _wrap_up(self):
        if self._wrapped:
            return
        self._wrapped = True
        try:
            self.SetTimer(0)
        except Exception:
            pass
        try:
            self._finish(self._owner, self._state, cancelled=self._cancel)
        except Exception:
            pass
        # Rebuild the viewport from the fresh cache.
        try:
            self._state.live_op.SetDirty(c4d.DIRTYFLAGS_DATA)
            c4d.EventAdd()
        except Exception:
            pass
        self.Close()

    def Command(self, cid, msg):
        if cid == c4d.DLG_CANCEL:
            self._cancel = True
        return True

    def AskClose(self):
        # ESC / window close -> cancel, and allow the close.
        self._cancel = True
        return False


# Keep a module ref so the async dialog isn't garbage-collected while its
# Timer keeps firing after run_bake returns.
_active_dialog = None


def run_bake(owner, state):
    """Open the async bake dialog; its Timer drives the clone-based bake to
    completion while keeping the bar + Cancel + ESC responsive."""
    global _active_dialog
    from .brickit_fit import _bake_step, _bake_finish
    _active_dialog = _BakeDialog(owner, state, _bake_step, _bake_finish)
    _active_dialog.Open(c4d.DLG_TYPE_ASYNC, defaultw=400, defaulth=96)
    return True
