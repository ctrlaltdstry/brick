"""MessagePlugin that auto-appends newly-created MoGraph Effectors to the
Effectors list of any BrickIt object that is currently selected.

Mirrors the native Cinema 4D behavior where creating an Effector while a
Cloner / Fracture is selected automatically wires the new Effector into
the generator's Effectors list. The native commands only recognize
`Omgcloner` / `Omgfracture` / etc., so BrickIt has to do this itself.

C4D 2026's Python SDK no longer exposes `SceneHookData`, so we use a
`MessageData` plugin and listen for `EVMSG_CHANGE`. On each change event
we diff the active doc's Effector list against a snapshot and append
every newly-created Effector to every BrickIt currently selected.
"""

import time

import c4d
from c4d import plugins

from c4d_symbols import (
    ID_BRICKIT_EFFECTORS_AUTOHOOK,
    ID_BRICKIFYASSEMBLY,
    BRICKIFYASSEMBLY_MOGRAPH_EFFECTORS,
)


# Type id of `Obaseeffector` — every MoGraph Effector instance is an
# instance of this class. Hardcoded because the symbol may not exist on
# every C4D build but the value has been stable for many years.
_OBASEEFFECTOR = 1018643

# Prefer explicit flags: `GetActiveObjects(0)` is ambiguous across SDK versions.
_GETACTIVEOBJECTFLAGS_NONE = int(
    getattr(c4d, "GETACTIVEOBJECTFLAGS_NONE", 0) or 0
)

_EFFECTOR_TYPE_IDS = {
    int(v)
    for v in (
        getattr(c4d, "Obaseeffector", _OBASEEFFECTOR),
        getattr(c4d, "Omgplain", None),
        getattr(c4d, "Omgrandom", None),
        getattr(c4d, "Omgshader", None),
        getattr(c4d, "Omgdelay", None),
        getattr(c4d, "Omgformula", None),
        getattr(c4d, "Omgstep", None),
        getattr(c4d, "Omgsound", None),
        getattr(c4d, "Omgtime", None),
        getattr(c4d, "Omgpushapart", None),
        getattr(c4d, "Omginheritance", None),
        getattr(c4d, "Omgpython", None),
        getattr(c4d, "Omgreeffector", None),
        getattr(c4d, "Omgeffectortarget", None),
        getattr(c4d, "Oweighteffector", None),
    )
    if v is not None
}

_DEBUG = False


def _dbg(msg):
    if not _DEBUG:
        return
    try:
        print("[brick autohook]", msg)
    except Exception:
        pass


def _iter_subtree(node):
    while node:
        yield node
        child = node.GetDown()
        if child is not None:
            for sub in _iter_subtree(child):
                yield sub
        node = node.GetNext()


def _is_effector(obj):
    if obj is None:
        return False
    try:
        if obj.IsInstanceOf(_OBASEEFFECTOR):
            return True
    except Exception:
        pass
    try:
        if int(obj.GetType()) in _EFFECTOR_TYPE_IDS:
            return True
    except Exception:
        pass
    return False


def _active_effectors(doc):
    if doc is None:
        return []
    try:
        active = doc.GetActiveObjects(_GETACTIVEOBJECTFLAGS_NONE) or []
    except Exception:
        return []
    return [obj for obj in active if _is_effector(obj)]


def _doc_effectors(doc):
    """Return {guid: BaseObject} for every Effector currently in `doc`."""
    out = {}
    if doc is None:
        return out
    first = doc.GetFirstObject()
    if first is None:
        return out
    for obj in _iter_subtree(first):
        try:
            if not _is_effector(obj):
                continue
            out[obj.GetGUID()] = obj
        except Exception:
            continue
    return out


def _is_brickit(obj):
    """True if `obj` is our BrickIt ObjectData plugin instance.

    `IsInstanceOf(plugin_id)` is not reliable for custom generators; the
    rest of BrickGen uses `GetType() == ID_BRICKIFYASSEMBLY`. Match that here
    so selection caching sees BrickIt when it is active.
    """
    if obj is None:
        return False
    try:
        if int(obj.GetType()) == int(ID_BRICKIFYASSEMBLY):
            return True
    except Exception:
        pass
    try:
        if obj.IsInstanceOf(ID_BRICKIFYASSEMBLY):
            return True
    except Exception:
        pass
    return False


def _selected_brickits(doc):
    if doc is None:
        return []
    try:
        active = doc.GetActiveObjects(_GETACTIVEOBJECTFLAGS_NONE) or []
    except Exception:
        return []
    out = []
    for obj in active:
        try:
            if _is_brickit(obj):
                out.append(obj)
        except Exception:
            continue
    return out


def _append_effectors_to_brickit(brickit, effectors, doc):
    """Append `effectors` to brickit's Effectors InExclude list, skipping
    any that are already present. Returns True if the list was modified."""
    try:
        incl = brickit[BRICKIFYASSEMBLY_MOGRAPH_EFFECTORS]
    except Exception:
        incl = None
    if incl is None:
        try:
            incl = c4d.InExcludeData()
        except Exception:
            return False

    existing_guids = set()
    try:
        for i in range(incl.GetObjectCount()):
            obj = incl.ObjectFromIndex(doc, i)
            if obj is not None:
                try:
                    existing_guids.add(obj.GetGUID())
                except Exception:
                    pass
    except Exception:
        pass

    changed = False
    for eff in effectors:
        if eff is None:
            continue
        try:
            guid = eff.GetGUID()
        except Exception:
            continue
        if guid in existing_guids:
            continue
        try:
            incl.InsertObject(eff, 1)
            existing_guids.add(guid)
            changed = True
        except Exception:
            continue

    if changed:
        try:
            brickit[BRICKIFYASSEMBLY_MOGRAPH_EFFECTORS] = incl
        except Exception:
            return False
        try:
            brickit.SetDirty(c4d.DIRTYFLAGS_DATA)
        except Exception:
            pass
    return changed


def register():
    """Register the MessagePlugin. Catches all SDK incompatibilities so
    a registration failure can never block the rest of BrickIt."""
    _dbg("register() entered")
    base_cls = getattr(plugins, "MessageData", None)
    if base_cls is None:
        _dbg("MessageData not available; auto-add disabled.")
        return False
    register_fn = getattr(plugins, "RegisterMessagePlugin", None)
    if register_fn is None:
        _dbg("RegisterMessagePlugin not available; auto-add disabled.")
        return False

    class BrickItEffectorsAutoHook(base_cls):
        # Minimum interval between full scene-tree walks. Scene-load and
        # MoGraph evaluation can fire dozens of EVMSG_CHANGE per second;
        # collapsing them to one walk per RECONCILE_THROTTLE_SEC keeps
        # the autohook from contributing to scene-open freeze.
        RECONCILE_THROTTLE_SEC = 0.05

        def __init__(self):
            # doc_key -> set of effector GUIDs known on last scan
            self._effector_snapshot = {}
            # doc_key -> list of weak-ish BrickIt refs from previous reconcile
            # (creating an effector selects it and deselects the BrickIt, so
            # by the time we see EVMSG_CHANGE the current selection is wrong;
            # we use the *prior* selection instead).
            self._last_brickit_selection = {}
            self._last_reconcile_at = 0.0

        def CoreMessage(self, id_, bc):
            evmsg_change = getattr(c4d, "EVMSG_CHANGE", None)
            if evmsg_change is not None and id_ != evmsg_change:
                return True
            now = time.perf_counter()
            if (now - self._last_reconcile_at) < self.RECONCILE_THROTTLE_SEC:
                return True
            self._last_reconcile_at = now
            try:
                self._reconcile()
            except Exception as exc:
                _dbg("reconcile raised: {0}".format(exc))
            return True

        def _doc_key(self, doc):
            """Stable identifier for a doc across CoreMessage calls.
            `c4d.documents.GetActiveDocument()` returns a fresh Python
            wrapper on every call, so id(doc) is not stable. Use the
            document's path+name (and a fallback first-object id when
            the doc is unsaved) to keep snapshots aligned."""
            try:
                path = doc.GetDocumentPath() or ""
                name = doc.GetDocumentName() or ""
            except Exception:
                path = ""
                name = ""
            if path or name:
                return "{0}|{1}".format(path, name)
            try:
                first = doc.GetFirstObject()
                if first is None:
                    return "untitled|noroot"
                # Python `id(first)` is not stable across CoreMessage calls
                # (wrapper churn). Use the root object's GUID for this session.
                try:
                    return "untitled|rootguid|{0}".format(first.GetGUID())
                except Exception:
                    return "untitled|norootguid"
            except Exception:
                return "untitled|0"

        def _reconcile(self):
            try:
                doc = c4d.documents.GetActiveDocument()
            except Exception:
                doc = None
            if doc is None:
                _dbg("reconcile: no active doc")
                return

            doc_key = self._doc_key(doc)

            # Cheap short-circuit: if nothing is selected AND we don't have
            # a cached "prior BrickIt selection" for this doc, there is no
            # possible target for auto-link, so skip the scene-tree walk
            # entirely. This is the common case during scene-load and
            # animation playback.
            try:
                active_count = doc.GetActiveObjectCount()
            except Exception:
                active_count = -1
            prior = self._last_brickit_selection.get(doc_key)
            if (
                active_count == 0
                and not prior
                and doc_key in self._effector_snapshot
            ):
                return

            current = _doc_effectors(doc)
            current_guids = set(current.keys())
            prev_guids = self._effector_snapshot.get(doc_key)
            _dbg("reconcile doc={0} effectors={1} prev={2}".format(
                doc_key, len(current_guids),
                len(prev_guids) if prev_guids is not None else "None"))

            if prev_guids is None:
                # First time we've seen this doc — snapshot only. Pre-existing
                # effectors are intentionally NOT auto-added (matches native
                # Cloner behavior of only auto-linking on creation).
                self._effector_snapshot[doc_key] = current_guids
                cur_sel = _selected_brickits(doc)
                if cur_sel:
                    self._last_brickit_selection[doc_key] = cur_sel
                return

            for eff in _active_effectors(doc):
                try:
                    current[eff.GetGUID()] = eff
                except Exception:
                    pass
            current_guids = set(current.keys())
            new_guids = current_guids - prev_guids
            if not new_guids:
                # No new effectors: update the cached BrickIt selection so the
                # next "new effector" event uses the freshest pre-deselect set.
                cur_sel = _selected_brickits(doc)
                if cur_sel:
                    self._last_brickit_selection[doc_key] = cur_sel
                # And update effector snapshot in case effectors were deleted.
                if current_guids != prev_guids:
                    self._effector_snapshot[doc_key] = current_guids
                return

            new_effectors = [current[g] for g in new_guids if g in current]
            # Prefer the prior snapshot of selected BrickIts: creating the
            # effector itself shifted the active selection to that effector,
            # so the *current* selection no longer contains the BrickIt.
            prior = self._last_brickit_selection.get(doc_key, [])
            brickits = [b for b in prior if b is not None and b.IsAlive()] if prior else []
            if not brickits:
                brickits = _selected_brickits(doc)
            _dbg("new effectors: {0}, selected brickits: {1} (prior={2})".format(
                len(new_effectors), len(brickits), len(prior)))
            any_changed = False
            for brickit in brickits:
                try:
                    if _append_effectors_to_brickit(
                        brickit, new_effectors, doc
                    ):
                        any_changed = True
                        _dbg("appended {0} effector(s) to '{1}'".format(
                            len(new_effectors), brickit.GetName()))
                except Exception as exc:
                    _dbg("append raised: {0}".format(exc))

            self._effector_snapshot[doc_key] = current_guids
            # Clear the cached selection after using it, mirroring native
            # behavior: only the FIRST effector created with a BrickIt
            # active gets auto-linked. Subsequent effectors created in a
            # row select themselves and don't re-attach.
            if any_changed and doc_key in self._last_brickit_selection:
                del self._last_brickit_selection[doc_key]
            if any_changed:
                try:
                    c4d.EventAdd()
                except Exception:
                    pass

    try:
        ok = register_fn(
            id=ID_BRICKIT_EFFECTORS_AUTOHOOK,
            str="BrickIt Effectors AutoHook",
            info=0,
            dat=BrickItEffectorsAutoHook(),
        )
        _dbg("RegisterMessagePlugin -> {0}".format(ok))
        return bool(ok)
    except Exception as exc:
        _dbg("RegisterMessagePlugin raised: {0}".format(exc))
        return False
