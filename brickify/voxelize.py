"""Mesh -> LEGO voxel grid.

Default LEGO physical dimensions are 8 (X) x 3.2 (Y) x 8 (Z) mm, but the
voxel grid is just a non-uniform grid — you can pass any stud_size you
like to voxelize_mesh, in whatever unit your mesh is in. The brick aspect
ratio (plate height = 0.4 * stud width) is preserved by default so bricks
still look like bricks; pass plate_size explicitly to break that.

The voxelizer supports:

  - solid mode: fills the interior of a closed mesh
  - shell mode: only surface voxels are marked, with optional thickness

Color sampling is done by subdividing each triangle into many small samples
and tagging the voxel each sample lands in with the triangle's color. The
final voxel color is the average of all samples that landed in it.
"""
import numpy as np
from scipy import ndimage
from typing import Optional, Callable, Tuple

# Default LEGO physical dimensions (mm) -- used when caller doesn't
# override stud_size / plate_size. The aspect ratio plate_size / stud_size
# = 0.4 is what makes a 3-plate stack equal in height to one stud width
# (roughly), which gives bricks their characteristic chunky look.
STUD_MM = 8.0
PLATE_MM = 3.2
BRICK_MM = 9.6
PLATE_RATIO = PLATE_MM / STUD_MM   # 0.4


def load_obj(path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Minimal OBJ parser. Returns (vertices, faces, vertex_colors).

    vertex_colors is None if no `v x y z r g b` color lines are present.
    Faces are triangulated (fan triangulation for n>3 polygons).
    """
    verts, faces, colors = [], [], []
    has_colors = False
    with open(path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == "v":
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
                if len(parts) >= 7:
                    colors.append([float(parts[4]), float(parts[5]), float(parts[6])])
                    has_colors = True
                else:
                    colors.append([0.7, 0.7, 0.7])
            elif parts[0] == "f":
                idxs = [int(p.split("/")[0]) - 1 for p in parts[1:]]
                for i in range(1, len(idxs) - 1):
                    faces.append([idxs[0], idxs[i], idxs[i + 1]])
    return (
        np.array(verts, dtype=np.float64),
        np.array(faces, dtype=np.int64),
        np.array(colors, dtype=np.float64) if has_colors else None,
    )


def load_obj_grouped(path: str):
    """OBJ loader that ALSO tracks the active 'o NAME' / 'g NAME' object
    each face belongs to. Returns:

        verts:      (N, 3) float64
        faces:      (M, 3) int64
        face_group: (M,) int     index into group_names per face
        group_names: list of str

    Faces declared before any 'o'/'g' line go into a synthetic group ''.
    """
    verts: list = []
    faces: list = []
    face_group: list = []
    group_names: list = [""]
    cur_group_idx = 0
    with open(path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == "v":
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif parts[0] in ("o", "g"):
                name = " ".join(parts[1:]) if len(parts) > 1 else ""
                if name in group_names:
                    cur_group_idx = group_names.index(name)
                else:
                    group_names.append(name)
                    cur_group_idx = len(group_names) - 1
            elif parts[0] == "f":
                idxs = [int(p.split("/")[0]) - 1 for p in parts[1:]]
                for i in range(1, len(idxs) - 1):
                    faces.append((idxs[0], idxs[i], idxs[i + 1]))
                    face_group.append(cur_group_idx)
    return (
        np.array(verts, dtype=np.float64),
        np.array(faces, dtype=np.int64),
        np.array(face_group, dtype=np.int32),
        group_names,
    )


# ---------- procedural test meshes ----------

def make_sphere(radius: float = 50.0, subdivisions: int = 3):
    """An icosphere. Returns (verts, faces)."""
    t = (1.0 + 5 ** 0.5) / 2.0
    v = np.array([
        [-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
        [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
        [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1],
    ], dtype=np.float64)
    v /= np.linalg.norm(v, axis=1)[:, None]
    f = np.array([
        [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
        [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
        [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
        [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
    ], dtype=np.int64)
    for _ in range(subdivisions):
        new_f, midcache = [], {}
        def midpoint(a, b):
            key = (min(a, b), max(a, b))
            if key in midcache:
                return midcache[key]
            m = (v[a] + v[b]) / 2.0
            m /= np.linalg.norm(m)
            idx = len(midcache) + len(v)
            midcache[key] = idx
            return idx
        new_verts = list(v)
        for tri in f:
            a, b, c = tri
            ab = midpoint(a, b); bc = midpoint(b, c); ca = midpoint(c, a)
            new_f += [[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]]
        # rebuild vertex list
        full = list(v)
        # midpoints in cache index order
        ordered = sorted(midcache.items(), key=lambda kv: kv[1])
        for (a, b), _idx in ordered:
            m = (v[a] + v[b]) / 2.0
            m /= np.linalg.norm(m)
            full.append(m)
        v = np.array(full)
        f = np.array(new_f, dtype=np.int64)
    return v * radius, f


def make_torus(R: float = 40.0, r: float = 15.0, n_major: int = 48, n_minor: int = 24):
    """Returns (verts, faces) for a torus."""
    u = np.linspace(0, 2 * np.pi, n_major, endpoint=False)
    v = np.linspace(0, 2 * np.pi, n_minor, endpoint=False)
    uu, vv = np.meshgrid(u, v, indexing="ij")
    x = (R + r * np.cos(vv)) * np.cos(uu)
    y = r * np.sin(vv)
    z = (R + r * np.cos(vv)) * np.sin(uu)
    verts = np.stack([x, y, z], axis=-1).reshape(-1, 3)
    faces = []
    for i in range(n_major):
        for j in range(n_minor):
            i2 = (i + 1) % n_major
            j2 = (j + 1) % n_minor
            a = i * n_minor + j
            b = i2 * n_minor + j
            c = i2 * n_minor + j2
            d = i * n_minor + j2
            faces += [[a, b, c], [a, c, d]]
    return verts, np.array(faces, dtype=np.int64)


def make_duck(scale: float = 50.0):
    """A stylized procedural 'duck' built from overlapping spheres.
    Returns (verts, faces, vertex_colors)."""
    parts = [
        # body (yellow)
        (np.array([0, 0, 0]),    1.0,  (1.0, 0.85, 0.1)),
        # head (yellow)
        (np.array([0.0, 0.85, 0.7]), 0.55, (1.0, 0.85, 0.1)),
        # beak (orange)
        (np.array([0.0, 0.7, 1.25]), 0.22, (0.95, 0.5, 0.1)),
        # tail (yellow)
        (np.array([0.0, 0.4, -0.95]), 0.35, (1.0, 0.85, 0.1)),
    ]
    all_v, all_f, all_c = [], [], []
    voff = 0
    for center, rad, color in parts:
        v, f = make_sphere(radius=rad * scale, subdivisions=2)
        v = v + center * scale
        all_v.append(v)
        all_f.append(f + voff)
        all_c.append(np.tile(np.array(color), (len(v), 1)))
        voff += len(v)
    return np.vstack(all_v), np.vstack(all_f), np.vstack(all_c)


def _ellipsoid(radius: float, scale_xyz: tuple, subdivisions: int = 2):
    """Sphere scaled per axis (not a true ellipsoid voxelization but
    its triangulation is what voxelize_mesh wants)."""
    v, f = make_sphere(radius=radius, subdivisions=subdivisions)
    v = v * np.array(scale_xyz)
    return v, f


def make_monkey(scale: float = 50.0):
    """A Suzanne-flavored procedural head: ellipsoidal skull, two ears,
    snout, eye protrusions, brow ridge. Returns (verts, faces, vertex_colors).

    Designed to stress-test the brickifier with: thin parts (ears), concavity
    near eyes, multiple colors, and a non-symmetric mass distribution
    front-to-back."""
    BROWN  = (0.62, 0.43, 0.28)
    TAN    = (0.78, 0.62, 0.45)
    BLACK  = (0.10, 0.08, 0.08)
    PINK   = (0.85, 0.50, 0.50)

    parts = [
        # main head: slightly squashed top-bottom, elongated front-back
        ("head_main",  np.array([0.0, 0.0, 0.0]),
         _ellipsoid(1.0, (1.0, 0.95, 1.15), 3), BROWN),
        # snout: smaller ellipsoid pushed forward and slightly down
        ("snout",      np.array([0.0, -0.18, 0.85]),
         _ellipsoid(0.6, (0.9, 0.75, 1.0), 2), TAN),
        # nose tip -- pulled back into the snout for solid connection
        ("nose",       np.array([0.0, -0.20, 1.25]),
         _ellipsoid(0.22, (1.1, 1.0, 1.0), 2), BLACK),
        # left ear -- moved inward so it overlaps the head firmly
        ("ear_L",      np.array([-0.92, 0.55, 0.0]),
         _ellipsoid(0.5, (0.55, 1.0, 0.75), 2), BROWN),
        ("ear_R",      np.array([+0.92, 0.55, 0.0]),
         _ellipsoid(0.5, (0.55, 1.0, 0.75), 2), BROWN),
        # ear interior cups (slightly forward of the ears)
        ("ear_cup_L",  np.array([-0.95, 0.55, 0.05]),
         _ellipsoid(0.32, (0.30, 0.75, 0.5), 2), PINK),
        ("ear_cup_R",  np.array([+0.95, 0.55, 0.05]),
         _ellipsoid(0.32, (0.30, 0.75, 0.5), 2), PINK),
        # eyes -- larger so they read clearly through voxelization
        ("eye_L",      np.array([-0.40, 0.20, 0.90]),
         _ellipsoid(0.22, (1.0, 1.0, 1.0), 2), BLACK),
        ("eye_R",      np.array([+0.40, 0.20, 0.90]),
         _ellipsoid(0.22, (1.0, 1.0, 1.0), 2), BLACK),
        # brow ridge above the eyes
        ("brow",       np.array([0.0, 0.45, 0.85]),
         _ellipsoid(0.55, (1.15, 0.20, 0.5), 2), BROWN),
    ]

    all_v, all_f, all_c = [], [], []
    voff = 0
    for _name, center, (v, f), color in parts:
        v = v + center
        v = v * scale
        all_v.append(v)
        all_f.append(f + voff)
        all_c.append(np.tile(np.array(color), (len(v), 1)))
        voff += len(v)
    return np.vstack(all_v), np.vstack(all_f), np.vstack(all_c)


# ---------- voxelization ----------


def _silhouette_lock_mask(occupancy: np.ndarray, *, band_width: int) -> np.ndarray:
    """Return a per-layer boundary band mask from the dominant silhouette.

    The mask keeps a thin horizontal band around each layer's largest
    connected occupied island. This preserves facade/shelf boundaries that can
    otherwise get clipped by cleanup passes.
    """
    if band_width <= 0:
        return np.zeros_like(occupancy, dtype=bool)

    Nx, Ny, Nz = occupancy.shape
    mask = np.zeros((Nx, Ny, Nz), dtype=bool)
    layer_structure = np.ones((3, 3), dtype=bool)
    for y in range(Ny):
        layer = occupancy[:, y, :]
        if not layer.any():
            continue
        labels, n_comp = ndimage.label(layer, structure=layer_structure)
        if n_comp <= 0:
            continue
        counts = np.bincount(labels.ravel())
        if counts.size <= 1:
            continue
        counts[0] = 0
        keep_label = int(np.argmax(counts))
        dominant = labels == keep_label
        if not dominant.any():
            continue
        dist = ndimage.distance_transform_cdt(dominant, metric="chessboard")
        mask[:, y, :] = dominant & (dist <= int(band_width))
    return mask

def voxelize_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    vertex_colors: Optional[np.ndarray] = None,
    face_colors: Optional[np.ndarray] = None,
    color_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    default_color=(180, 180, 180),
    mode: str = "solid",
    shell_thickness: int = 1,
    fill_threshold: float = 0.5,
    stud_size: float = STUD_MM,
    plate_size: Optional[float] = None,
    min_column_voxels: int = 0,
    cleanup_protrusions: int = 0,
    protrusion_layer_threshold: int = 9,
    preserve_silhouette: bool = False,
):
    """Voxelize a triangle mesh into the LEGO grid.

    The voxel cell is (stud_size, plate_size, stud_size) -- non-uniform Y
    because a plate is shorter than a stud is wide. plate_size defaults
    to 0.4 * stud_size (the real LEGO ratio) if not specified.

    For C4D usage: stud_size is in whatever units your mesh is in. So if
    your mesh is 100 cm tall and you want it built from ~25 plates tall,
    set stud_size = 100 / 25 / 0.4 = 10 cm. Or simply use the
    `studs_across` helper in the demo to compute it automatically.

    Parameters
    ----------
    vertices : (N, 3) array, mesh units
    faces    : (M, 3) int array, indexes into vertices
    vertex_colors : optional (N, 3) array in 0..1 for per-vertex color
    face_colors   : optional (M, 3) array in 0..1 for per-FACE color
                    (takes precedence over vertex_colors)
    color_fn : optional fn(points (K,3)) -> (K,3) RGB 0..1, e.g. texture sampler
                    (takes precedence over both *_colors)
    default_color : RGB 0..255 for cells with no color sample
    mode : "solid" | "shell"
    shell_thickness : extra dilation passes when shelling
    fill_threshold : 0..1; how much of a voxel must be inside to be "filled"
                     (currently used as a soft surface-density gate)
    stud_size : size of one stud in mesh units (default 8.0, real LEGO mm)
    plate_size : size of one plate (vertical) in mesh units. Defaults to
                 0.4 * stud_size (real LEGO ratio) if None.

    Returns
    -------
    occupancy : (Nx, Ny, Nz) bool array
    colors    : (Nx, Ny, Nz, 3) uint8 array (RGB 0..255)
    origin    : (3,) world-space mesh-units coords of voxel (0,0,0)'s corner
    """
    if plate_size is None:
        plate_size = stud_size * PLATE_RATIO
    if len(faces) == 0:
        raise ValueError("Mesh has no faces.")

    v = vertices
    bbox_min = v.min(axis=0)
    bbox_max = v.max(axis=0)
    voxel_mm = np.array([stud_size, plate_size, stud_size])

    # Pad 1 voxel on each side so flood-fill from outside works, then snap the
    # voxel lattice to world-axis voxel increments. Without snapping, tiny
    # sub-voxel bbox jitter can phase-shift the lattice between resolutions and
    # cause visibly uneven side rows on otherwise symmetric architecture.
    grid_min = np.floor((bbox_min - voxel_mm) / voxel_mm) * voxel_mm
    grid_max = np.ceil((bbox_max + voxel_mm) / voxel_mm) * voxel_mm
    dims = np.maximum(1, np.round((grid_max - grid_min) / voxel_mm).astype(int))
    Nx, Ny, Nz = int(dims[0]), int(dims[1]), int(dims[2])

    occ_surface = np.zeros((Nx, Ny, Nz), dtype=bool)
    color_sum = np.zeros((Nx, Ny, Nz, 3), dtype=np.float64)
    color_count = np.zeros((Nx, Ny, Nz), dtype=np.int32)

    def world_to_voxel(p: np.ndarray) -> np.ndarray:
        return ((p - grid_min) / voxel_mm).astype(np.int64)

    # Sample each triangle densely with a deterministic barycentric lattice.
    # This avoids random per-run jitter near boundaries, which can otherwise
    # create directional artifacts on stepped architectural facades.
    for tri_idx in range(len(faces)):
        ia, ib, ic = faces[tri_idx]
        a, b, c = v[ia], v[ib], v[ic]
        # Approximate density: how many voxel-diagonals across the triangle
        edge_vox = np.array([
            np.linalg.norm((b - a) / voxel_mm),
            np.linalg.norm((c - b) / voxel_mm),
            np.linalg.norm((a - c) / voxel_mm),
        ])
        max_edge = max(edge_vox.max(), 1.0)
        n_subdiv = max(int(np.ceil(max_edge * 1.5)), 1)
        # Triangular lattice: (i, j, k) with i+j+k=n_subdiv.
        ijs = [
            (i, j)
            for i in range(n_subdiv + 1)
            for j in range(n_subdiv + 1 - i)
        ]
        if not ijs:
            continue
        ij = np.asarray(ijs, dtype=np.float64)
        u = ij[:, 0] / float(n_subdiv)
        w = ij[:, 1] / float(n_subdiv)
        bary = np.stack([1.0 - u - w, u, w], axis=-1)
        pts = bary @ np.stack([a, b, c], axis=0)
        ijk = world_to_voxel(pts)
        # clip
        valid = np.all((ijk >= 0) & (ijk < dims), axis=1)
        ijk = ijk[valid]
        # mark
        occ_surface[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = True
        # color
        if color_fn is not None:
            cols = color_fn(pts[valid])
        elif face_colors is not None:
            cols = np.tile(face_colors[tri_idx], (len(ijk), 1))
        elif vertex_colors is not None:
            cols = bary[valid] @ np.stack(
                [vertex_colors[ia], vertex_colors[ib], vertex_colors[ic]], axis=0
            )
        else:
            cols = np.tile(np.array(default_color) / 255.0, (len(ijk), 1))
        # accumulate (clip to 0..1 then store as 0..255 floats)
        cols = np.clip(cols, 0, 1) * 255.0
        np.add.at(color_sum, (ijk[:, 0], ijk[:, 1], ijk[:, 2]), cols)
        np.add.at(color_count, (ijk[:, 0], ijk[:, 1], ijk[:, 2]), 1)

        # Also rasterize triangle edges densely in voxel space. The interior
        # random sampling above can occasionally miss thin/step-like facade
        # boundaries on architectural meshes; explicit edge coverage keeps
        # silhouette loops closed and improves footprint fidelity.
        for p0, p1 in ((a, b), (b, c), (c, a)):
            edge_len_vox = np.linalg.norm((p1 - p0) / voxel_mm)
            n_edge = max(int(edge_len_vox * 2.0), 1)
            t = np.linspace(0.0, 1.0, n_edge + 1, dtype=np.float64)
            epts = (1.0 - t)[:, None] * p0[None, :] + t[:, None] * p1[None, :]
            eijk = world_to_voxel(epts)
            valid_e = np.all((eijk >= 0) & (eijk < dims), axis=1)
            eijk = eijk[valid_e]
            if eijk.size == 0:
                continue
            occ_surface[eijk[:, 0], eijk[:, 1], eijk[:, 2]] = True

    # Build a robust filled volume first. Solid mode uses it directly;
    # shell mode derives a boundary skin from it below. This is more stable
    # than using raw triangle-sampled surface voxels as the shell, because
    # large flat faces can otherwise under-sample and make sections vanish.
    if mode in ("solid", "shell"):
        # Axis-agnostic interior solve: flood outside air in 3D from grid
        # boundaries, then treat everything else as occupied interior/surface.
        # A light close seals tiny rasterization pinholes first.
        seal_structure = np.ones((3, 3, 3), dtype=bool)
        # Two close iterations robustly seal tiny rasterization pinholes.
        # With one iteration some architectural meshes can leak/flood badly
        # after grid-phase changes, producing unstable base occupancy.
        sealed_surface = ndimage.binary_closing(
            occ_surface, structure=seal_structure, iterations=2
        )
        empty = ~sealed_surface
        outside_seed = np.zeros_like(empty, dtype=bool)
        outside_seed[0, :, :] = empty[0, :, :]
        outside_seed[-1, :, :] = empty[-1, :, :]
        outside_seed[:, 0, :] |= empty[:, 0, :]
        outside_seed[:, -1, :] |= empty[:, -1, :]
        outside_seed[:, :, 0] |= empty[:, :, 0]
        outside_seed[:, :, -1] |= empty[:, :, -1]
        outside = ndimage.binary_propagation(
            outside_seed,
            structure=ndimage.generate_binary_structure(3, 1),
            mask=empty,
        )
        occ = (~outside) | occ_surface
    else:
        raise ValueError(f"unknown mode: {mode}")

    # Trim "ghost floor" / "ghost roof" slabs.
    #
    # Source meshes that are closed solids (which is most of them) have a
    # closed bottom face and/or top face that triangulates as a single flat
    # quad spanning the full footprint. When voxelized, that flat face fills
    # an entire 1-voxel-tall layer at the bottom (or top) of the bbox,
    # extending well beyond the building's actual wall silhouette.
    #
    # In shell mode this slab survives erosion (because it's exactly 1 voxel
    # thick) and shows up as a wide skirt of bricks past the body's outline.
    # In solid mode it just becomes a fat ground-floor plate that doesn't
    # match the architecture above it.
    #
    # We detect this when the bottom-most (or top-most) occupied layer is
    # dramatically wider than the adjacent inner layer, and trim it down to
    # the inner layer's silhouette. For closed solid meshes the interior fill
    # is constant across small vertical sections, so the floor/ceiling slab's
    # footprint should match the body just inside it; any extra cells are the
    # phantom floor face. This is conservative: it only kicks in when the
    # wide layer is clearly an outlier (>= 2x the inner layer), so genuine
    # plinths/setbacks (which span multiple layers) are preserved.
    y_active = occ.any(axis=(0, 2))
    if y_active.any():
        y_indices = np.where(y_active)[0]
        y_lo = int(y_indices[0])
        y_hi = int(y_indices[-1])
        if y_lo + 1 <= y_hi:
            layer_lo = occ[:, y_lo, :]
            layer_above = occ[:, y_lo + 1, :]
            n_lo = int(layer_lo.sum())
            n_above = int(layer_above.sum())
            if n_lo >= 20 and n_lo > n_above * 2:
                occ[:, y_lo, :] = layer_lo & layer_above
        if y_hi - 1 >= y_lo:
            layer_hi = occ[:, y_hi, :]
            layer_below = occ[:, y_hi - 1, :]
            n_hi = int(layer_hi.sum())
            n_below = int(layer_below.sum())
            if n_hi >= 20 and n_hi > n_below * 2:
                occ[:, y_hi, :] = layer_hi & layer_below

    # color: surface voxels get their averaged color; interior voxels get
    # nearest-neighbor color from the surface
    colors = np.zeros((Nx, Ny, Nz, 3), dtype=np.uint8)
    has_color = color_count > 0
    safe = np.where(has_color, color_count, 1)
    avg = (color_sum / safe[..., None]).astype(np.uint8)
    colors[has_color] = avg[has_color]

    if mode == "solid":
        # for interior voxels (occupied but not on surface), nearest-color from
        # any voxel that has a color sample
        if has_color.any():
            distance, nearest = ndimage.distance_transform_edt(
                ~has_color, return_indices=True
            )
            occ_no_color = occ & ~has_color
            ix, iy, iz = np.where(occ_no_color)
            if len(ix):
                src = (nearest[0][ix, iy, iz],
                       nearest[1][ix, iy, iz],
                       nearest[2][ix, iy, iz])
                colors[ix, iy, iz] = colors[src]

    # default fill where still empty
    colors[(colors == 0).all(axis=-1) & occ] = np.array(default_color, dtype=np.uint8)

    silhouette_lock = None
    if preserve_silhouette:
        lock_band = 1 if mode == "shell" else 2
        silhouette_lock = _silhouette_lock_mask(occ, band_width=lock_band)

    # Optional cleanup: drop entire (x, z) columns that are too short
    # to be "real" geometry. Catches ground planes, shadow catchers,
    # and stray flat polygons that voxelize as a 1-plate-tall sheet.
    # min_column_voxels counts vertical voxels (plates) per (x, z).
    if min_column_voxels > 0:
        col_count = occ.sum(axis=1)  # (Nx, Nz)
        cull = col_count > 0
        cull &= col_count < int(min_column_voxels)
        if cull.any():
            occ[cull[:, None, :].repeat(Ny, axis=1)] = False

    # Optional cleanup: remove detached 3D voxel islands conservatively.
    #
    # This intentionally avoids per-layer morphology (opening/closing), since
    # those operations can carve valid shelves and ledges on stepped facades.
    # Instead, we cull only small disconnected components and always preserve
    # the largest connected component.
    cleanup_passes = int(cleanup_protrusions)
    if cleanup_passes > 0:
        cc_structure = ndimage.generate_binary_structure(3, 1)  # 6-neighborhood
        for pass_idx in range(cleanup_passes):
            labels, n_comp = ndimage.label(occ, structure=cc_structure)
            if n_comp <= 1:
                break

            counts = np.bincount(labels.ravel())
            if counts.size <= 1:
                break
            counts[0] = 0  # background
            largest = int(np.argmax(counts))

            # Threshold grows with pass count and layer-thickness heuristic.
            # Keeps meaningful secondary masses while removing thin stragglers.
            min_component_voxels = max(
                4,
                int(protrusion_layer_threshold) + (2 * pass_idx),
            )
            keep_labels = {largest}
            for lid in range(1, n_comp + 1):
                if lid == largest:
                    continue
                if int(counts[lid]) >= min_component_voxels:
                    keep_labels.add(lid)

            cleaned = np.isin(labels, list(keep_labels))
            if not np.any(occ & ~cleaned):
                break
            occ = cleaned

    if mode == "shell":
        thickness = max(1, int(shell_thickness))
        structure = np.ones((3, 3, 3), dtype=bool)
        eroded = ndimage.binary_erosion(
            occ,
            structure=structure,
            iterations=thickness,
            border_value=0,
        )
        occ = occ & ~eroded

    if silhouette_lock is not None:
        occ = occ | silhouette_lock

    return occ, colors, grid_min
