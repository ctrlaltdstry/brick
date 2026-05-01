"""Cinema 4D Redshift color-channel probe for BrickIt MoGraph output.

Run inside Cinema 4D's Script Manager with the BrickIt object or generated
MoGraph output root selected. The script creates diagnostic Redshift materials
for likely color channels and writes a report to the desktop.

This does not change production BrickIt code. It only adds diagnostic materials,
optional object user-data values, and one initial texture tag in the open scene.
"""

from __future__ import annotations

import os
import traceback
from datetime import datetime

import c4d

try:
    import maxon
except Exception:  # pragma: no cover - only available inside Cinema 4D.
    maxon = None


RS_NODESPACE_ID = "com.redshift3d.redshift4c4d.class.nodespace"
RS_OUTPUT_NODE_ID = "com.redshift3d.redshift4c4d.node.output"
RS_STANDARD_MATERIAL_NODE_ID = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial"
RS_COLOR_USER_DATA_NODE_ID = "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor"

RS_OUTPUT_SURFACE_PORT = "com.redshift3d.redshift4c4d.node.output.surface"
RS_STANDARD_OUTCOLOR_PORT = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.outcolor"
RS_STANDARD_BASE_COLOR_PORT = "com.redshift3d.redshift4c4d.nodes.core.standardmaterial.base_color"
RS_USER_DATA_OUTCOLOR_PORT = "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.outcolor"

ATTRIBUTE_CANDIDATES = (
    # Redshift's Color User Data Attribute Name field uses these exact
    # case-sensitive identifiers, which are the strings the menu labels
    # ("Object Color", "Display Color", etc.) actually map to.
    ("RSObjectColor", "Redshift object color attribute"),
    ("RSDisplayColor", "Redshift display color attribute"),
    ("RSLayerColor", "Redshift layer color attribute"),
    ("RSMGColor", "Redshift MoGraph clone color attribute"),
    ("RSGeomIDColor", "Redshift per-geometry pseudo-random color"),
    ("Cd", "Houdini/Redshift color convention"),
    ("brickit_color", "BrickIt diagnostic custom user-data"),
)

USER_DATA_NAMES = ("brickit_color", "Cd", "mograph_color", "Color", "color")
ACTIVE_INITIAL_MATERIAL = "RSMGColor"


def _desktop_path() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop")


def _report_path() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(_desktop_path(), "brickit_rs_color_probe_{0}.txt".format(stamp))


class ProbeLog:
    def __init__(self) -> None:
        self.lines = []

    def add(self, message: str) -> None:
        self.lines.append(str(message))
        print("[BrickIt RS Probe] {0}".format(message))

    def section(self, title: str) -> None:
        self.add("")
        self.add("=== {0} ===".format(title))

    def write(self) -> str:
        path = _report_path()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(self.lines))
            handle.write("\n")
        return path


def _iter_objects(root):
    obj = root
    while obj is not None:
        yield obj
        child = obj.GetDown()
        if child is not None:
            for item in _iter_objects(child):
                yield item
        obj = obj.GetNext()


def _selected_target(doc):
    target = doc.GetActiveObject()
    if target is not None:
        return target
    return doc.GetFirstObject()


def _object_color(obj):
    try:
        color = obj[c4d.ID_BASEOBJECT_COLOR]
        if isinstance(color, c4d.Vector):
            return color
    except Exception:
        pass
    return c4d.Vector(1.0, 1.0, 1.0)


def _add_or_update_vector_user_data(obj, name: str, value) -> bool:
    try:
        for desc_id, bc in obj.GetUserDataContainer():
            if bc.GetString(c4d.DESC_NAME) == name:
                obj[desc_id] = value
                return True
    except Exception:
        pass

    try:
        dtype = getattr(c4d, "DTYPE_COLOR", c4d.DTYPE_VECTOR)
        bc = c4d.GetCustomDatatypeDefault(dtype)
        bc[c4d.DESC_NAME] = name
        bc[c4d.DESC_SHORT_NAME] = name
        desc_id = obj.AddUserData(bc)
        obj[desc_id] = value
        return True
    except Exception:
        return False


def _stamp_diagnostic_user_data(target, log: ProbeLog) -> None:
    log.section("Diagnostic User Data")
    count = 0
    for obj in _iter_objects(target):
        if obj is None:
            continue
        obj_type = obj.GetType()
        if obj is target or obj_type in (
            getattr(c4d, "Oinstance", -1),
            getattr(c4d, "Onull", -2),
        ):
            color = _object_color(obj)
            for name in USER_DATA_NAMES:
                _add_or_update_vector_user_data(obj, name, color)
            count += 1
    log.add("Stamped {0} object(s) with user-data names: {1}".format(count, ", ".join(USER_DATA_NAMES)))
    log.add("These values are per-carrier/object diagnostics, not a production per-brick data model.")


def _find_port(node, port_names, *, output=False):
    ports = node.GetOutputs() if output else node.GetInputs()
    for name in port_names:
        try:
            port = ports.FindChild(name)
            if port and not port.IsNullValue():
                return port, name
        except Exception:
            continue
    return None, None


def _iter_graph_children(node):
    try:
        children = node.GetChildren()
    except Exception:
        return
    try:
        iterator = iter(children)
    except TypeError:
        iterator = ()
    for child in iterator:
        try:
            if child and not child.IsNullValue():
                yield child
        except Exception:
            yield child


def _node_label(node) -> str:
    parts = []
    for getter in ("GetId", "GetPath"):
        try:
            parts.append("{0}={1}".format(getter, node.__getattribute__(getter)()))
        except Exception:
            pass
    return ", ".join(parts) if parts else str(node)


def _first_port(node, *, output=False):
    ports = node.GetOutputs() if output else node.GetInputs()
    for child in _iter_graph_children(ports):
        return child, _node_label(child)
    return None, None


def _log_node_ports(node, label: str, log: ProbeLog) -> None:
    log.add("{0} input ports:".format(label))
    for child in _iter_graph_children(node.GetInputs()):
        log.add("  IN  {0}".format(_node_label(child)))
    log.add("{0} output ports:".format(label))
    for child in _iter_graph_children(node.GetOutputs()):
        log.add("  OUT {0}".format(_node_label(child)))


def _set_first_available_port(node, names, value, log: ProbeLog) -> str | None:
    port, name = _find_port(node, names, output=False)
    if port is None:
        return None
    try:
        if hasattr(port, "SetPortValue"):
            port.SetPortValue(value)
        else:
            port.SetDefaultValue(value)
        return name
    except Exception as exc:
        log.add("Could not set port {0}: {1}".format(name, exc))
        return None


def _create_material_base(doc, name: str):
    mat = c4d.BaseMaterial(c4d.Mmaterial)
    if mat is None:
        raise MemoryError("Could not allocate material {0}".format(name))
    mat.SetName(name)
    doc.InsertMaterial(mat)
    return mat


def _create_standard_control_material(doc, log: ProbeLog):
    mat = _create_material_base(doc, "BrickIt_RSProbe_Control_C4DMaterial")
    try:
        mat[c4d.MATERIAL_COLOR_COLOR] = c4d.Vector(1.0, 0.0, 1.0)
        mat[c4d.MATERIAL_COLOR_BRIGHTNESS] = 1.0
        mat.Message(c4d.MSG_UPDATE)
    except Exception as exc:
        log.add("Control C4D material setup warning: {0}".format(exc))
    return mat


def _create_redshift_graph_material(doc, name: str, log: ProbeLog):
    if maxon is None:
        raise RuntimeError("maxon module is unavailable; Redshift node materials cannot be built.")

    mat = _create_material_base(doc, name)
    node_material = mat.GetNodeMaterialReference()
    if node_material is None:
        raise RuntimeError("Material has no NodeMaterial reference.")

    node_space_id = maxon.Id(RS_NODESPACE_ID)
    graph = node_material.CreateEmptyGraph(node_space_id)
    if graph is None or graph.IsNullValue():
        raise RuntimeError("Could not create Redshift graph.")
    return mat, graph


def _connect_standard_to_output(graph, standard_node, output_node):
    out_color, _ = _find_port(standard_node, (RS_STANDARD_OUTCOLOR_PORT,), output=True)
    surface, _ = _find_port(output_node, (RS_OUTPUT_SURFACE_PORT,), output=False)
    if out_color is None or surface is None:
        raise RuntimeError("Could not find Standard Material output or Output surface port.")
    out_color.Connect(surface)


def _create_rs_control_material(doc, log: ProbeLog):
    name = "BrickIt_RSProbe_Control_Redshift_BaseColor"
    mat, graph = _create_redshift_graph_material(doc, name, log)
    with graph.BeginTransaction() as transaction:
        output_node = graph.AddChild(maxon.Id(), maxon.Id(RS_OUTPUT_NODE_ID))
        standard_node = graph.AddChild(maxon.Id(), maxon.Id(RS_STANDARD_MATERIAL_NODE_ID))
        _connect_standard_to_output(graph, standard_node, output_node)
        port_name = _set_first_available_port(
            standard_node,
            (RS_STANDARD_BASE_COLOR_PORT, "base_color", "Base/Color"),
            maxon.Color(1.0, 0.0, 1.0),
            log,
        )
        transaction.Commit()
    log.add("Created {0}; base-color port set via {1}".format(name, port_name or "no matched port"))
    return mat


def _create_rs_user_data_material(doc, attr_name: str, label: str, log: ProbeLog):
    safe_attr = "".join(ch if ch.isalnum() else "_" for ch in attr_name)
    name = "BrickIt_RSProbe_UserData_{0}".format(safe_attr)
    mat, graph = _create_redshift_graph_material(doc, name, log)

    set_port = None
    with graph.BeginTransaction() as transaction:
        output_node = graph.AddChild(maxon.Id(), maxon.Id(RS_OUTPUT_NODE_ID))
        standard_node = graph.AddChild(maxon.Id(), maxon.Id(RS_STANDARD_MATERIAL_NODE_ID))
        user_data_node = graph.AddChild(maxon.Id(), maxon.Id(RS_COLOR_USER_DATA_NODE_ID))
        _connect_standard_to_output(graph, standard_node, output_node)

        user_data_color, _ = _find_port(user_data_node, (RS_USER_DATA_OUTCOLOR_PORT, "outcolor", "Out Color"), output=True)
        if user_data_color is None:
            user_data_color, fallback_name = _first_port(user_data_node, output=True)
            if user_data_color is not None:
                log.add(
                    "Using first Color User Data output port for '{0}': {1}".format(
                        attr_name,
                        fallback_name,
                    )
                )
        base_color, _ = _find_port(standard_node, (RS_STANDARD_BASE_COLOR_PORT, "base_color", "Base/Color"), output=False)
        if user_data_color is None or base_color is None:
            _log_node_ports(user_data_node, "Color User Data node", log)
            _log_node_ports(standard_node, "Standard Material node", log)
            raise RuntimeError("Could not connect Color User Data output to Standard Material base color.")
        user_data_color.Connect(base_color)

        attr_port_candidates = (
            "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.attribute",
            "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.attribute_name",
            "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.attributename",
            "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.name",
            "attribute",
            "attribute_name",
            "Attribute Name",
            "Name",
        )
        set_port = _set_first_available_port(user_data_node, attr_port_candidates, attr_name, log)

        default_port_candidates = (
            "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.defaultcolor",
            "com.redshift3d.redshift4c4d.nodes.core.rsuserdatacolor.default_color",
            "defaultcolor",
            "default_color",
            "Default Color",
        )
        _set_first_available_port(user_data_node, default_port_candidates, maxon.Color(0.0, 1.0, 1.0), log)
        transaction.Commit()

    log.add(
        "Created {0}: attr='{1}' ({2}); attribute port={3}".format(
            name,
            attr_name,
            label,
            set_port or "not found; set manually in node if needed",
        )
    )
    return mat


def _add_probe_note_object(doc, target, report_path: str) -> None:
    note = c4d.BaseObject(c4d.Onull)
    if note is None:
        return
    note.SetName("BrickIt_RS_ColorProbe_REPORT")
    try:
        note[c4d.NULLOBJECT_DISPLAY] = getattr(c4d, "NULLOBJECT_DISPLAY_CIRCLE", 2)
    except Exception:
        pass
    bc = c4d.GetCustomDatatypeDefault(c4d.DTYPE_STRING)
    bc[c4d.DESC_NAME] = "Report Path"
    desc_id = note.AddUserData(bc)
    note[desc_id] = report_path
    if target is not None:
        note.InsertAfter(target)
    else:
        doc.InsertObject(note)


def _apply_initial_material(target, material, log: ProbeLog) -> None:
    if target is None or material is None:
        return
    try:
        tag = c4d.TextureTag()
    except AttributeError:
        tag = c4d.BaseTag(c4d.Ttexture)
    if tag is None:
        log.add("Could not allocate texture tag for initial material.")
        return
    tag.SetName("BrickIt_RSProbe_ACTIVE_{0}".format(material.GetName()))
    tag[c4d.TEXTURETAG_MATERIAL] = material
    target.InsertTag(tag)
    log.add("Applied initial material tag to selected target: {0}".format(material.GetName()))
    log.add("Swap this tag's material to each BrickIt_RSProbe_* material for the matrix test.")


def _create_probe_materials(doc, log: ProbeLog):
    materials = []
    log.section("Material Creation")
    materials.append(_create_standard_control_material(doc, log))

    try:
        materials.append(_create_rs_control_material(doc, log))
    except Exception as exc:
        log.add("Redshift control material not created: {0}".format(exc))
        log.add(traceback.format_exc())

    for attr_name, label in ATTRIBUTE_CANDIDATES:
        try:
            materials.append(_create_rs_user_data_material(doc, attr_name, label, log))
        except Exception as exc:
            log.add("User-data material for '{0}' not created: {1}".format(attr_name, exc))
            log.add(traceback.format_exc())

    return materials


def _log_scene_context(doc, target, log: ProbeLog) -> None:
    log.section("Scene Context")
    log.add("C4D version: {0}".format(c4d.GetC4DVersion()))
    log.add("Redshift node space ID: {0}".format(RS_NODESPACE_ID))
    log.add("Target: {0}".format(target.GetName() if target is not None else "None"))
    if target is not None:
        sample_count = 0
        for obj in _iter_objects(target):
            if sample_count >= 20:
                break
            color = _object_color(obj)
            log.add(
                "Object sample: name='{0}', type={1}, objectColor=({2:.3f}, {3:.3f}, {4:.3f})".format(
                    obj.GetName(),
                    obj.GetType(),
                    color.x,
                    color.y,
                    color.z,
                )
            )
            sample_count += 1
    log.add("Existing material count before probe: {0}".format(len(list(_iter_materials(doc)))))


def _iter_materials(doc):
    mat = doc.GetFirstMaterial()
    while mat is not None:
        yield mat
        mat = mat.GetNext()


def main() -> None:
    doc = globals().get("doc") or c4d.documents.GetActiveDocument()
    if doc is None:
        raise RuntimeError("No active C4D document.")

    log = ProbeLog()
    target = _selected_target(doc)
    _log_scene_context(doc, target, log)

    doc.StartUndo()
    try:
        if target is not None:
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, target)
            _stamp_diagnostic_user_data(target, log)

        materials = _create_probe_materials(doc, log)
        initial = None
        for mat in materials:
            if ACTIVE_INITIAL_MATERIAL in mat.GetName():
                initial = mat
                break
        if initial is None and materials:
            initial = materials[0]
        _apply_initial_material(target, initial, log)

        report_path = log.write()
        _add_probe_note_object(doc, target, report_path)
        log.add("Report written to: {0}".format(report_path))
    finally:
        doc.EndUndo()

    c4d.EventAdd()


if __name__ == "__main__":
    main()
