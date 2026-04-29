"""BrickIt brick-library selection state and picker dialog."""
import c4d
from c4d import plugins

from c4d_symbols import *  # noqa: F401,F403 - C4D resource IDs are constants.


# Order matches brick.library.DEFAULT_LIBRARY and the resource/icon IDs.
BRICK_TOGGLE_NAMES = [
    "brick_1x1", "brick_1x2", "brick_1x3", "brick_1x4",
    "brick_1x6", "brick_1x8",
    "brick_2x2", "brick_2x3", "brick_2x4", "brick_2x6", "brick_2x8",
    "brick_3x3", "brick_3x4", "brick_3x6", "brick_3x8",
]
BRICK_LIBRARY_ALL_MASK = (1 << len(BRICK_TOGGLE_NAMES)) - 1
PLATE_LIBRARY_NAMES = (
    "plate_1x1", "plate_1x2", "plate_1x3", "plate_1x4",
    "plate_1x6", "plate_1x8",
    "plate_2x2", "plate_2x3", "plate_2x4", "plate_2x6", "plate_2x8",
    "plate_3x3", "plate_3x4", "plate_3x6", "plate_3x8",
)


def toggle_id(idx):
    return BRICKIFYASSEMBLY_BRICK_BASE + idx


def read_library_mask(op):
    """Read library bitmask from op; derive from toggles for legacy scenes."""
    try:
        raw_mask = int(op[BRICKIFYASSEMBLY_LIBRARY_MASK] or 0)
        mask = raw_mask & BRICK_LIBRARY_ALL_MASK
        legacy_base_count = 11
        has_legacy_upper_bits = bool(raw_mask >> len(BRICK_TOGGLE_NAMES))
        if has_legacy_upper_bits:
            legacy_plate_bits = (raw_mask >> legacy_base_count) & ((1 << legacy_base_count) - 1)
            mask |= legacy_plate_bits
        return mask & BRICK_LIBRARY_ALL_MASK
    except Exception:
        mask = 0
        for i in range(len(BRICK_TOGGLE_NAMES)):
            try:
                if bool(op[toggle_id(i)]):
                    mask |= (1 << i)
            except Exception:
                mask |= (1 << i)
        return mask & BRICK_LIBRARY_ALL_MASK


def apply_library_mask_to_toggles(op, mask):
    """Mirror bitmask state into legacy per-brick bool toggles."""
    m = int(mask) & BRICK_LIBRARY_ALL_MASK
    for i in range(len(BRICK_TOGGLE_NAMES)):
        op[toggle_id(i)] = bool(m & (1 << i))


def sync_library_mask_from_toggles(op):
    """Write BRICKIFYASSEMBLY_LIBRARY_MASK from the bool toggles."""
    mask = 0
    for i in range(len(BRICK_TOGGLE_NAMES)):
        try:
            if bool(op[toggle_id(i)]):
                mask |= (1 << i)
        except Exception:
            mask |= (1 << i)
    op[BRICKIFYASSEMBLY_LIBRARY_MASK] = int(mask & BRICK_LIBRARY_ALL_MASK)


def apply_library_preset_to_object(op, preset_id):
    if op is None:
        return
    if preset_id == BRICKIFYASSEMBLY_LIB_PRESET_ALL:
        for i in range(len(BRICK_TOGGLE_NAMES)):
            op[toggle_id(i)] = True
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_NONE:
        for i in range(len(BRICK_TOGGLE_NAMES)):
            op[toggle_id(i)] = False
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_BRICKS:
        for i, n in enumerate(BRICK_TOGGLE_NAMES):
            op[toggle_id(i)] = n.startswith("brick_")
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_PLATES:
        try:
            op[BRICKIFYASSEMBLY_ENABLE_PLATES] = True
        except Exception:
            pass
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_1X1:
        for i, n in enumerate(BRICK_TOGGLE_NAMES):
            op[toggle_id(i)] = (n == "brick_1x1")
    elif preset_id == BRICKIFYASSEMBLY_LIB_PRESET_INVERT:
        for i in range(len(BRICK_TOGGLE_NAMES)):
            op[toggle_id(i)] = not bool(op[toggle_id(i)])
    sync_library_mask_from_toggles(op)
    op.SetDirty(c4d.DIRTYFLAGS_DATA)
    c4d.EventAdd()


def active_brick_object():
    try:
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return None
        op = doc.GetActiveObject()
        if op is not None and op.GetType() == ID_BRICKIFYASSEMBLY:
            return op
    except Exception:
        pass
    return None


class BrickLibraryPickerDialog(c4d.gui.GeDialog):
    """Safe thumbnail picker outside the .res description parser."""

    DLG_HERO = 50000
    DLG_PRESET_ALL = 50001
    DLG_PRESET_NONE = 50002
    DLG_PRESET_BRICKS = 50003
    DLG_PRESET_PLATES = 50004
    DLG_PRESET_1X1 = 50005
    DLG_PRESET_INVERT = 50006
    DLG_THUMB_BASE = 51000
    DLG_TOGGLE_BASE = 52000

    def __init__(self):
        super().__init__()
        self._target = None
        self._last_target_name = ""

    def set_target(self, op):
        self._target = op
        try:
            name = op.GetName() if op is not None else ""
        except Exception:
            name = ""
        self._last_target_name = name
        title = "Brick Library Picker"
        if name:
            title = "Brick Library Picker - {0}".format(name)
        try:
            self.SetTitle(title)
        except Exception:
            pass
        if self.IsOpen():
            self._sync_from_target()

    def _sync_from_target(self):
        op = self._target
        if op is None:
            return
        for i in range(len(BRICK_TOGGLE_NAMES)):
            try:
                on = bool(op[toggle_id(i)])
            except Exception:
                on = True
            try:
                self.SetBool(self.DLG_TOGGLE_BASE + i, on)
            except Exception:
                pass

    def CreateLayout(self):
        self.SetTitle("Brick Library Picker")
        if not self.GroupBegin(999, c4d.BFH_SCALEFIT, cols=1):
            return True
        hero_bc = c4d.BaseContainer()
        hero_bc.SetBool(c4d.BITMAPBUTTON_BUTTON, False)
        hero_bc.SetBool(c4d.BITMAPBUTTON_BORDER, False)
        hero_bc.SetLong(c4d.BITMAPBUTTON_ICONID1, int(ICON_BRICKIFY_HERO))
        self.AddCustomGui(
            self.DLG_HERO,
            c4d.CUSTOMGUI_BITMAPBUTTON,
            "",
            c4d.BFH_CENTER,
            820,
            120,
            hero_bc,
        )
        self.GroupEnd()

        if not self.GroupBegin(1000, c4d.BFH_SCALEFIT, cols=4):
            return True
        self.AddButton(self.DLG_PRESET_ALL, c4d.BFH_SCALEFIT, name="All")
        self.AddButton(self.DLG_PRESET_NONE, c4d.BFH_SCALEFIT, name="None")
        self.AddButton(self.DLG_PRESET_INVERT, c4d.BFH_SCALEFIT, name="Invert")
        self.AddButton(self.DLG_PRESET_1X1, c4d.BFH_SCALEFIT, name="1x1")
        self.GroupEnd()

        if not self.GroupBegin(1001, c4d.BFH_SCALEFIT, cols=11):
            return True
        for i, name in enumerate(BRICK_TOGGLE_NAMES):
            cell = 53000 + i
            self.GroupBegin(cell, c4d.BFH_CENTER, cols=1)

            bc = c4d.BaseContainer()
            bc.SetBool(c4d.BITMAPBUTTON_BUTTON, True)
            bc.SetLong(c4d.BITMAPBUTTON_ICONID1, int(ICON_BRICKIFY_BRICK_BASE + i))
            bc.SetBool(c4d.BITMAPBUTTON_BORDER, False)
            self.AddCustomGui(
                self.DLG_THUMB_BASE + i,
                c4d.CUSTOMGUI_BITMAPBUTTON,
                "",
                c4d.BFH_CENTER,
                28,
                28,
                bc,
            )
            self.AddCheckbox(self.DLG_TOGGLE_BASE + i, c4d.BFH_CENTER, 0, 0, name.split("_")[-1])
            self.GroupEnd()
        self.GroupEnd()
        return True

    def InitValues(self):
        self._sync_from_target()
        return True

    def CoreMessage(self, mid, bc):
        try:
            doc = c4d.documents.GetActiveDocument()
            if doc is not None:
                op = active_brick_object()
                if op is not None:
                    if op is not self._target:
                        self.set_target(op)
                elif self._target is not None:
                    pass
        except Exception:
            pass
        return True

    def _apply_and_refresh(self):
        op = self._target
        if op is None:
            return
        sync_library_mask_from_toggles(op)
        op.SetDirty(c4d.DIRTYFLAGS_DATA)
        c4d.EventAdd()
        self._sync_from_target()

    def Command(self, cid, msg):
        op = self._target
        if op is None:
            return True

        preset_map = {
            self.DLG_PRESET_ALL: BRICKIFYASSEMBLY_LIB_PRESET_ALL,
            self.DLG_PRESET_NONE: BRICKIFYASSEMBLY_LIB_PRESET_NONE,
            self.DLG_PRESET_1X1: BRICKIFYASSEMBLY_LIB_PRESET_1X1,
            self.DLG_PRESET_INVERT: BRICKIFYASSEMBLY_LIB_PRESET_INVERT,
        }
        if cid in preset_map:
            apply_library_preset_to_object(op, preset_map[cid])
            self._apply_and_refresh()
            return True

        if self.DLG_THUMB_BASE <= cid < self.DLG_THUMB_BASE + len(BRICK_TOGGLE_NAMES):
            i = int(cid - self.DLG_THUMB_BASE)
            tid = toggle_id(i)
            op[tid] = not bool(op[tid])
            self._apply_and_refresh()
            return True

        if self.DLG_TOGGLE_BASE <= cid < self.DLG_TOGGLE_BASE + len(BRICK_TOGGLE_NAMES):
            i = int(cid - self.DLG_TOGGLE_BASE)
            tid = toggle_id(i)
            op[tid] = bool(self.GetBool(cid))
            self._apply_and_refresh()
            return True
        return True


_LIBRARY_PANEL_DIALOG = None


def ensure_library_panel_dialog():
    global _LIBRARY_PANEL_DIALOG
    if _LIBRARY_PANEL_DIALOG is None:
        _LIBRARY_PANEL_DIALOG = BrickLibraryPickerDialog()
    return _LIBRARY_PANEL_DIALOG


def open_library_panel(target=None):
    dlg = ensure_library_panel_dialog()
    if target is None:
        target = active_brick_object()
    dlg.set_target(target)
    dlg.Open(
        c4d.DLG_TYPE_ASYNC,
        pluginid=ID_BRICKLIBRARYPANEL,
        defaultw=860,
        defaulth=330,
    )
    return dlg


class BrickLibraryPanelCommand(plugins.CommandData):
    def Execute(self, doc):
        open_library_panel(active_brick_object())
        return True

    def RestoreLayout(self, secret):
        dlg = ensure_library_panel_dialog()
        return dlg.Restore(pluginid=ID_BRICKLIBRARYPANEL, secret=secret)
