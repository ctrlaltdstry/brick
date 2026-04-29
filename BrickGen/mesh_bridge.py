"""Brick mesh generation and conversion to C4D polygon objects."""
import c4d

from quality_presets import QUALITY_HERO, QUALITY_PRESETS


BRICKGENERATOR_TYPE_PLATE = 1


def mesh_to_polygon_object(mesh, name="brick"):
    """Convert a brick Mesh to a c4d.PolygonObject.

    N-gons are converted to a triangle fan from the polygon centroid so round
    caps stay centered. Polygon-selection tags are emitted for each named mesh
    group so users can assign materials after generation.
    """
    converted_vertices = [
        (float(v[0]), float(v[1]), float(v[2])) for v in mesh.vertices
    ]
    converted_faces = []
    face_index_map = {}
    for orig_fi, face in enumerate(mesh.faces):
        verts = tuple(int(v) for v in face)
        if len(verts) < 3:
            continue
        if len(verts) <= 4:
            converted_index = len(converted_faces)
            converted_faces.append(verts)
            face_index_map.setdefault(orig_fi, []).append(converted_index)
            continue

        cx = sum(converted_vertices[i][0] for i in verts) / float(len(verts))
        cy = sum(converted_vertices[i][1] for i in verts) / float(len(verts))
        cz = sum(converted_vertices[i][2] for i in verts) / float(len(verts))
        center_i = len(converted_vertices)
        converted_vertices.append((cx, cy, cz))
        mapped = []
        for i in range(len(verts)):
            tri = (center_i, verts[i], verts[(i + 1) % len(verts)])
            mapped.append(len(converted_faces))
            converted_faces.append(tri)
        face_index_map[orig_fi] = mapped

    obj = c4d.PolygonObject(len(converted_vertices), len(converted_faces))
    obj.SetName(name)

    for i, v in enumerate(converted_vertices):
        obj.SetPoint(i, c4d.Vector(float(v[0]), float(v[1]), float(v[2])))

    for i, face in enumerate(converted_faces):
        if len(face) == 3:
            obj.SetPolygon(i, c4d.CPolygon(face[0], face[1], face[2], face[2]))
        elif len(face) == 4:
            obj.SetPolygon(i, c4d.CPolygon(face[0], face[1], face[2], face[3]))

    obj.Message(c4d.MSG_UPDATE)

    groups = getattr(mesh, "groups", {}) or {}
    for group_name, face_indices in groups.items():
        sel_tag = obj.MakeTag(c4d.Tpolygonselection)
        sel_tag.SetName(str(group_name))
        sel = sel_tag.GetBaseSelect()
        for fi in face_indices:
            for converted_fi in face_index_map.get(int(fi), []):
                sel.Select(int(converted_fi))

    phong = obj.MakeTag(c4d.Tphong)
    phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = True
    phong[c4d.PHONGTAG_PHONG_ANGLE] = c4d.utils.DegToRad(40.0)

    return obj


def build_brick(
    width,
    depth,
    height_plates,
    quality,
    piece_type=0,
):
    """Return a brick/plate Mesh built by make_brick_hires."""
    from brick.brick_geom_hires import make_brick_hires

    h = max(1, int(height_plates))
    if int(piece_type) == BRICKGENERATOR_TYPE_PLATE:
        h = 1

    kwargs = dict(QUALITY_PRESETS.get(quality, QUALITY_PRESETS[QUALITY_HERO]))
    if int(piece_type) == BRICKGENERATOR_TYPE_PLATE:
        # Plate mode should be the smooth plate variant by default.
        kwargs["with_studs"] = False
    return make_brick_hires(int(width), int(depth), h, **kwargs)
