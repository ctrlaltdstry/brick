"""One-click Redshift Color User Data material for BrickIt MoGraph output.

Creates a Redshift node material configured as:

    RS Color User Data (Attribute = RSObjectColor)
        --> RS Standard Material (Base Color)
        --> RS Output (Surface)

and attaches it to the BrickIt object via a Texture Tag. RSObjectColor reads
the per-instance display color BrickIt sets on each multi-instance carrier,
which matches the no-material gradient Redshift renders for the BrickIt
output. See `brick.md` -> "Integrated MoGraph color path -- DO NOT REGRESS".

This module is deliberately self-contained: no Redshift install files are
read or modified. We only construct in-document Maxon node graphs through
the public Maxon Cinema 4D Python SDK.
"""
from __future__ import annotations

import traceback

import c4d

from plugin_bootstrap import brick_log as _brick_log

try:
    import maxon  # noqa: F401 - probed at runtime in case Maxon nodes API is unavailable.
except Exception:  # pragma: no cover - C4D environments without Maxon nodes.
    maxon = None


_RS_NODESPACE_ID = "com.redshift3d.redshift4c4d.class.nodespace"
_RS_OUTPUT_NODE_ID = "com.redshift3d.redshift4c4d.node.output"
_RS_STANDARD_NODE_ID = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial"
_RS_USER_DATA_NODE_ID = "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor"

_RS_OUTPUT_SURFACE_PORT = "com.redshift3d.redshift4c4d.node.output.surface"
_RS_STANDARD_OUTCOLOR_PORT = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.outcolor"
_RS_STANDARD_BASE_COLOR_PORT = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.base_color"
_RS_USER_DATA_OUTCOLOR_PORT = "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.out"

_BRICKIT_RS_MATERIAL_NAME = "BrickIt_PerBrick_Color"


def _find_existing_material(doc, name):
    if doc is None:
        return None
    mat = doc.GetFirstMaterial()
    while mat is not None:
        try:
            if mat.GetName() == name:
                return mat
        except Exception:
            pass
        mat = mat.GetNext()
    return None


def _find_port(node, port_names, *, output=False):
    try:
        ports = node.GetOutputs() if output else node.GetInputs()
    except Exception:
        return None
    for name in port_names:
        try:
            port = ports.FindChild(name)
            if port is not None and not port.IsNullValue():
                return port
        except Exception:
            continue
    return None


def _set_port_value(port, value):
    if port is None:
        return False
    try:
        if hasattr(port, "SetPortValue"):
            port.SetPortValue(value)
        else:
            port.SetDefaultValue(value)
        return True
    except Exception:
        return False


def _force_user_data_attribute(graph, log, name="RSObjectColor"):
    """After GraphDescription builds the graph, walk it and explicitly set
    the rsuserdatacolor node's Attribute port.

    The Attribute port is an ENUM (dropdown), not a free-form string.
    Redshift's enum values are integer-indexed; for User Data Color the
    options are roughly: 0=RSMGColor, 1=RSObjectColor, 2=Custom.
    Setting a string literal works on some C4D builds because the maxon
    nodes API will coerce, but on others it silently no-ops and the
    default (RSMGColor) sticks. We try a tuple of value forms — int
    index, str, and an enum-id-like string — and log which one took so
    future-us can see at a glance.
    """
    if maxon is None or graph is None or graph.IsNullValue():
        return False
    try:
        root = graph.GetRoot()
    except Exception:
        return False
    if root is None or root.IsNullValue():
        return False

    target_id = _RS_USER_DATA_NODE_ID
    found_any = False
    candidates = (
        "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.attribute",
        "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.attribute_name",
        "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.attributename",
        "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.name",
        "attribute",
        "attribute_name",
        "Attribute Name",
        "Name",
    )
    # The Attribute Name port is a free-form string field — Redshift reads
    # it at render time to look up the named per-object/per-instance data.
    # The string MUST be exactly "RSObjectColor" (case-sensitive); writing
    # anything else (or an int that gets stringified) yields black output.
    value_forms = (name,)

    def _walk(node):
        nonlocal found_any
        try:
            children = node.GetChildren()
        except Exception:
            children = []
        try:
            iterable = list(children) if children is not None else []
        except Exception:
            iterable = []
        for child in iterable:
            try:
                if child is None or child.IsNullValue():
                    continue
            except Exception:
                continue
            try:
                child_id = str(child.GetId())
            except Exception:
                child_id = ""
            if child_id == target_id:
                set_ok = False
                last_port_name = None
                for candidate in candidates:
                    port = _find_port(child, (candidate,), output=False)
                    if port is None:
                        continue
                    last_port_name = candidate
                    # Walk every value form until one sticks. We can't
                    # easily verify post-set without re-reading the port,
                    # but the AM will reflect the right dropdown selection
                    # the moment one of these takes.
                    for val in value_forms:
                        if _set_port_value(port, val):
                            set_ok = True
                            log(
                                "[brick] RS material: set Attribute on user-data node "
                                "via port '{0}' value={1!r}".format(candidate, val)
                            )
                            break
                    if set_ok:
                        break
                if not set_ok:
                    log(
                        "[brick] RS material: could not force Attribute on user-data node "
                        "(last port tried='{0}'); available inputs={1}".format(
                            last_port_name,
                            _list_port_names(child, output=False),
                        )
                    )
                found_any = True
            _walk(child)

    _walk(root)
    return found_any


def _build_via_graph_description(doc, log):
    if maxon is None:
        return None
    try:
        mat = c4d.BaseMaterial(c4d.Mmaterial)
        if mat is None:
            log("[brick] RS material: could not allocate BaseMaterial")
            return None
        mat.SetName(_BRICKIT_RS_MATERIAL_NAME)
        redshift_id = maxon.Id(_RS_NODESPACE_ID)
        graph = maxon.GraphDescription.GetGraph(mat, redshift_id, True)
        if graph is None or graph.IsNullValue():
            log("[brick] RS material: GraphDescription.GetGraph returned null")
            return None
        doc.InsertMaterial(mat)
        try:
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, mat)
        except Exception:
            pass
        description = {
            "$type": maxon.Id(_RS_OUTPUT_NODE_ID),
            "Surface": {
                "$type": maxon.Id(_RS_STANDARD_NODE_ID),
                "Base/Color": {
                    "$type": maxon.Id(_RS_USER_DATA_NODE_ID),
                    "Attribute Name": "RSObjectColor",
                    "Default Color": maxon.Color(1.0, 1.0, 1.0),
                },
            },
        }
        maxon.GraphDescription.ApplyDescription(graph, description)
        # GraphDescription's key for the attribute selector isn't honored
        # consistently — Redshift falls back to RSMGColor.  Force the
        # correct value by port id after the description is applied.
        try:
            with graph.BeginTransaction() as transaction:
                _force_user_data_attribute(graph, log, "RSObjectColor")
                transaction.Commit()
        except Exception as exc:
            log("[brick] RS material: post-ApplyDescription enforce failed: {0}".format(exc))
        log(
            "[brick] RS material: built '{0}' via GraphDescription (RSObjectColor)".format(
                _BRICKIT_RS_MATERIAL_NAME
            )
        )
        return mat
    except Exception as exc:
        log("[brick] RS material: GraphDescription path failed: {0}".format(exc))
        log(traceback.format_exc())
        try:
            mat.Remove()
        except Exception:
            pass
        return None


def _node_label(node):
    try:
        return str(node.GetId())
    except Exception:
        try:
            return str(node.GetPath())
        except Exception:
            return "<unknown>"


def _list_port_names(node, *, output):
    names = []
    try:
        ports = node.GetOutputs() if output else node.GetInputs()
    except Exception:
        return names
    try:
        for child in ports.GetChildren():
            try:
                if child is None or child.IsNullValue():
                    continue
            except Exception:
                pass
            names.append(_node_label(child))
    except Exception:
        pass
    return names


def _build_material_graph(doc, log):
    if maxon is None:
        log("[brick] RS material: maxon module unavailable; cannot build node graph")
        return None

    via_description = _build_via_graph_description(doc, log)
    if via_description is not None:
        return via_description

    mat = c4d.BaseMaterial(c4d.Mmaterial)
    if mat is None:
        log("[brick] RS material: could not allocate BaseMaterial")
        return None
    mat.SetName(_BRICKIT_RS_MATERIAL_NAME)

    node_material = mat.GetNodeMaterialReference()
    if node_material is None:
        log("[brick] RS material: material has no NodeMaterial reference")
        return None

    redshift_id = maxon.Id(_RS_NODESPACE_ID)
    try:
        graph = node_material.CreateEmptyGraph(redshift_id)
    except Exception as exc:
        log("[brick] RS material: CreateEmptyGraph failed: {0}".format(exc))
        return None
    if graph is None or graph.IsNullValue():
        log("[brick] RS material: empty Redshift graph could not be created")
        return None

    doc.InsertMaterial(mat)
    try:
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, mat)
    except Exception:
        pass

    try:
        graph = node_material.GetGraph(redshift_id)
    except Exception:
        pass
    if graph is None or graph.IsNullValue():
        log("[brick] RS material: graph reference unavailable after insertion")
        return None

    try:
        with graph.BeginTransaction() as transaction:
            output_node = graph.AddChild(maxon.Id(), maxon.Id(_RS_OUTPUT_NODE_ID))
            standard_node = graph.AddChild(maxon.Id(), maxon.Id(_RS_STANDARD_NODE_ID))
            user_data_node = graph.AddChild(maxon.Id(), maxon.Id(_RS_USER_DATA_NODE_ID))

            std_out = _find_port(standard_node, (_RS_STANDARD_OUTCOLOR_PORT,), output=True)
            out_surface = _find_port(output_node, (_RS_OUTPUT_SURFACE_PORT,), output=False)
            ud_out = _find_port(
                user_data_node,
                (
                    _RS_USER_DATA_OUTCOLOR_PORT,
                    "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.outcolor",
                    "out",
                    "outcolor",
                    "Out Color",
                ),
                output=True,
            )
            std_base = _find_port(
                standard_node,
                (_RS_STANDARD_BASE_COLOR_PORT, "base_color", "Base/Color"),
                output=False,
            )
            if (
                std_out is None
                or out_surface is None
                or ud_out is None
                or std_base is None
            ):
                log(
                    "[brick] RS material: missing ports - std_out={0}, out_surface={1}, "
                    "ud_out={2}, std_base={3}".format(
                        std_out is not None,
                        out_surface is not None,
                        ud_out is not None,
                        std_base is not None,
                    )
                )
                log(
                    "[brick] RS material: standard node outputs={0}".format(
                        _list_port_names(standard_node, output=True)
                    )
                )
                log(
                    "[brick] RS material: standard node inputs={0}".format(
                        _list_port_names(standard_node, output=False)
                    )
                )
                log(
                    "[brick] RS material: output node inputs={0}".format(
                        _list_port_names(output_node, output=False)
                    )
                )
                log(
                    "[brick] RS material: user-data node outputs={0}".format(
                        _list_port_names(user_data_node, output=True)
                    )
                )
                return None

            std_out.Connect(out_surface)
            ud_out.Connect(std_base)

            attr_port = None
            for candidate in (
                "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.attribute",
                "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.attribute_name",
                "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.attributename",
                "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.name",
                "attribute",
                "attribute_name",
                "Attribute Name",
                "Name",
            ):
                attr_port = _find_port(user_data_node, (candidate,), output=False)
                if attr_port is not None:
                    break
            # Attribute Name is a free-form string field — Redshift looks
            # it up by exact name at render time. Must be "RSObjectColor"
            # (case-sensitive) for the per-instance brick colors to flow
            # through. Any other value (or an int) yields black bricks.
            if not _set_port_value(attr_port, "RSObjectColor"):
                log(
                    "[brick] RS material: could not set Color User Data attribute; "
                    "set Attribute Name to 'RSObjectColor' manually if needed"
                )

            for candidate in (
                "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.defaultcolor",
                "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.default_color",
                "defaultcolor",
                "default_color",
                "Default Color",
            ):
                port = _find_port(user_data_node, (candidate,), output=False)
                if port is not None:
                    _set_port_value(port, maxon.Color(1.0, 1.0, 1.0))
                    break

            transaction.Commit()
    except Exception as exc:
        log("[brick] RS material: graph construction failed: {0}".format(exc))
        log(traceback.format_exc())
        return None

    return mat


def _ensure_texture_tag(op, mat, log):
    if op is None or mat is None:
        return False

    cur = None
    try:
        cur = op.GetFirstTag()
    except Exception:
        cur = None
    matched_tag = None
    while cur is not None:
        try:
            if cur.GetType() == c4d.Ttexture:
                try:
                    tag_mat = cur[c4d.TEXTURETAG_MATERIAL]
                except Exception:
                    tag_mat = None
                if tag_mat is not None and tag_mat.GetName() == mat.GetName():
                    matched_tag = cur
                    break
        except Exception:
            pass
        try:
            cur = cur.GetNext()
        except Exception:
            cur = None

    if matched_tag is not None:
        try:
            matched_tag[c4d.TEXTURETAG_MATERIAL] = mat
        except Exception as exc:
            log("[brick] RS material: could not refresh existing texture tag: {0}".format(exc))
            return False
        log(
            "[brick] RS material: refreshed existing texture tag on '{0}'".format(
                op.GetName()
            )
        )
        return True

    try:
        tag = op.MakeTag(c4d.Ttexture)
    except Exception as exc:
        log("[brick] RS material: MakeTag(Ttexture) failed: {0}".format(exc))
        return False
    if tag is None:
        log("[brick] RS material: MakeTag(Ttexture) returned None")
        return False
    try:
        tag.SetName(_BRICKIT_RS_MATERIAL_NAME)
        tag[c4d.TEXTURETAG_MATERIAL] = mat
    except Exception as exc:
        log("[brick] RS material: failed to bind material to tag: {0}".format(exc))
        return False
    log(
        "[brick] RS material: created texture tag on '{0}' linked to '{1}'".format(
            op.GetName(),
            mat.GetName(),
        )
    )
    return True


def _graph_is_empty(node_material, redshift_id):
    if node_material is None or redshift_id is None:
        return True
    try:
        graph = node_material.GetGraph(redshift_id)
    except Exception:
        return True
    if graph is None or graph.IsNullValue():
        return True
    try:
        root = graph.GetRoot()
        if root is None or root.IsNullValue():
            return True
        children = root.GetChildren()
    except Exception:
        return True
    try:
        for _ in children:
            return False
    except TypeError:
        try:
            if len(children) > 0:
                return False
        except Exception:
            return True
    return True


def _remove_material(doc, mat):
    if doc is None or mat is None:
        return
    try:
        doc.AddUndo(c4d.UNDOTYPE_DELETEOBJ, mat)
    except Exception:
        pass
    try:
        mat.Remove()
    except Exception:
        pass


def _create_rs_color_material(self, op):
    """Create or refresh the BrickIt per-brick Redshift color material."""
    log = _brick_log
    if op is None:
        log("[brick] RS material: missing BrickIt object")
        return False
    doc = op.GetDocument()
    if doc is None:
        log("[brick] RS material: BrickIt object is not in a document")
        return False

    doc.StartUndo()
    try:
        existing = _find_existing_material(doc, _BRICKIT_RS_MATERIAL_NAME)
        rebuild = True
        if existing is not None and maxon is not None:
            try:
                node_material = existing.GetNodeMaterialReference()
                redshift_id = maxon.Id(_RS_NODESPACE_ID)
            except Exception:
                node_material = None
                redshift_id = None
            if (
                node_material is not None
                and redshift_id is not None
                and not _graph_is_empty(node_material, redshift_id)
            ):
                rebuild = False
                log(
                    "[brick] RS material: existing '{0}' has wired graph; reusing".format(
                        _BRICKIT_RS_MATERIAL_NAME
                    )
                )

        if rebuild:
            if existing is not None:
                log(
                    "[brick] RS material: removing stale '{0}' and rebuilding".format(
                        _BRICKIT_RS_MATERIAL_NAME
                    )
                )
                _remove_material(doc, existing)
            mat = _build_material_graph(doc, log)
            if mat is None:
                return False
        else:
            mat = existing

        if not _ensure_texture_tag(op, mat, log):
            log("[brick] RS material: failed to attach texture tag to BrickIt")
            return False

        op.Message(c4d.MSG_UPDATE)
        c4d.EventAdd()
        log(
            "[brick] RS material: '{0}' is wired (RSColorUserData(RSObjectColor) "
            "-> Standard.base_color) and attached to '{1}'".format(
                _BRICKIT_RS_MATERIAL_NAME,
                op.GetName(),
            )
        )
        return True
    except Exception as exc:
        log("[brick] RS material: unexpected error: {0}".format(exc))
        log(traceback.format_exc())
        return False
    finally:
        doc.EndUndo()
