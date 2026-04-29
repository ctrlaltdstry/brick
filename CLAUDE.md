# CLAUDE.md — Brick

Read this file before doing anything. The user has worked with multiple AI
sessions on this and is tired of re-explaining decisions. Default to the
conventions below; only revisit them when the user explicitly says to.

## What this project is

A Cinema 4D plugin that generates structurally-buildable LEGO bricks (and,
eventually, full LEGO assemblies converted from arbitrary 3D models). The
generator runs as a C4D `ObjectData` plugin; the same Python package can
also be driven from the command line.

The C4D port is **live** — `BrickGen` is a working ObjectData
plugin that loads `brickify.brick_geom_hires.make_brick_hires`. Width,
Depth, Height (plates), and Quality are exposed as object parameters.

## Project layout

```
Z:\02_MKE\2026\BRICK\brickify\        ← repo root
  brickify\                            ← Python package
    __init__.py
    brick_geom_hires.py                ← LIVE generator
    brick_geom.py                      ← deprecated SubD-cage version
    mesh.py, fitter.py, voxelize.py, ...
  BrickGen\                      ← C4D plugin source
    c4d_brick_generator.pyp
    c4d_symbols.py
    res\
  tools\
    export_hires_brick.py              ← CLI wrapper around make_brick_hires
    deploy_plugin.ps1                  ← copy plugin → C4D plugins folder
    sanity_check_brick.py, ...
  backup\                              ← old plugin/package snapshots
  CLAUDE.md
```

**Package nesting trap, do not repeat**: the layout is exactly two
levels (`brickify/brickify/*.py`). At one point there was an extra middle
`brickify/` and a stray `brick_geom_hires.py` got written next to the
package instead of inside it. Imports silently resolved to a stale older
copy. If "old-looking" output appears unexpectedly, sanity-check that
there is exactly one `brick_geom_hires.py` on disk and it lives at
`brickify/brickify/brick_geom_hires.py`.

## C4D plugin workflow

C4D loads the plugin from
`%APPDATA%\Maxon\Maxon Cinema 4D 2026_1ABCDC12\plugins\BrickGen`,
not directly from the repo. Edit canonically in `BrickGen/` here,
then deploy with:

```
powershell -ExecutionPolicy Bypass -File tools\deploy_plugin.ps1
```

Geometry-only changes inside `brickify/brickify/*.py` do **not** need
redeployment — the plugin imports the package live from
`Z:\02_MKE\2026\BRICK\brickify` (hardcoded fallback in
`_ensure_brickify_on_path`). Just restart C4D (or recreate the
BrickGen object so its mesh cache invalidates).

The plugin's `BrickGen` ObjectData caches results on
`(width, depth, height, quality)`. Changing any of those re-runs
`make_brick_hires`.

### Daily test-run workflow (after plugin redeploy)

**Operator rule**: whenever the plugin is redeployed, automatically
restart C4D and reopen the standing test scene. Do not ask first unless
the user explicitly says to skip restart/open-scene for that deploy.

Run this from repo root after changes that require plugin redeploy:

```
powershell -ExecutionPolicy Bypass -File tools\deploy_plugin.ps1; $p = Get-Process -Name 'Cinema 4D*' -ErrorAction SilentlyContinue; if ($p) { $p | Stop-Process -Force }; Start-Sleep -Milliseconds 700; Start-Process -FilePath 'Z:\02_MKE\2026\BRICK\TEST FILE.c4d'
```

Use this as the default post-deploy operator loop unless the user asks
to open a different `.c4d` file or skip restart for a specific reason.

## Pipeline (mesh → bricks) — ASSEMBLY pipeline, not yet wired to plugin

The full mesh-to-brick-assembly pipeline is implemented in the package
but not yet exposed in C4D:

1. Load OBJ with named groups (`voxelize.load_obj_grouped`)
2. Voxelize at a resolution chosen by stud_size & plate_size
   (`voxelize.voxelize_mesh`)
3. Greedy fit of brick library to voxel grid (`fitter.BrickFitter`)
4. Build coupling graph and prune to largest connected component
   (`connectivity` module, MANDATORY — structural connectivity is a hard
   requirement)
5. Export as OBJ + JSON manifest grouped by brick_type for MoGraph
   (`exporters.export_json`, `exporters.export_ldraw`)

The fitter stores raw RGB on each `BrickPlacement`. Palette quantization
is optional and decoupled from the pipeline — by design.

`assembly.py` still calls the old `make_brick_mesh`, not
`make_brick_hires`. Swap before next full pipeline run.

### BrickIt Make Physically Accurate mode contract — DO NOT REGRESS

This took several visual-debug rounds to get right. The checkbox is not
just a cosmetic label for pruning:

- **Unchecked = artist-friendly mode.** It must preserve the source model's
  visible boundary/silhouette as closely as possible, even when the selected
  brick footprint cannot tile that boundary cleanly. Do not let large selected
  bricks drift/overhang outside the model. Instead, keep strict selected-brick
  placement and use exact `artist_fill_1x1_h*` visual filler placements for
  leftover occupied boundary cells.
- **Checked = physically accurate mode.** It may apply connectivity pruning,
  but pruning must remove small floating debris only. Do not collapse every fit
  to one largest component when that amputates meaningful architectural chunks
  like a tower top.
- C4D Volume shell sampling intentionally uses the native Maxon
  `MeshToVolume` SDF band (`abs(sdf) <= shell_threshold`). Do not switch it to
  inside-only shell sampling unless the user explicitly asks; that made both
  shell and solid workflows worse in the standing Empire test scene.

Guardrail test:

```
python tools/test_artist_mode_regression.py
```

Run it before changing `brickify/fitter.py`, `brickify/pipeline.py`, or the
`Make Physically Accurate` wiring in `BrickGen/c4d_brick_generator.pyp`.

## The brick generator (current focus)

Two implementations exist. **Use `brick_geom_hires.py`. The other one
(`brick_geom.py`) is the deprecated SubD-cage version — do not extend
it.**

### `brick_geom_hires.py` design rules

- **Direct geometric fillet tessellation. NO Catmull-Clark / no SubD at
  any point.** The user explicitly rejected the SubD approach. Every
  fillet is a swept arc baked as actual triangles. Open the OBJ in any
  viewer and the fillets are present.
- Quads are fine, tris are fine, n-gons are fine. **It does not need to
  be quad-only.** Don't waste effort preserving quad topology.
- Build by sweeping 2D profiles around their axis (revolved features) or
  along their edge (cylindrical edge fillets, sphere octants for
  corners).
- Final `mesh.weld_vertices(tol=1e-4)` call seals seams between
  independently emitted components (rim ↔ body bottom edge, rib saddle
  patches ↔ adjacent fillets, etc.). Don't remove this.

### Quality presets

Defined identically in `tools/export_hires_brick.py` and
`BrickGen/c4d_brick_generator.pyp`. If you change one, change the
other.

- **draft** — `body_corner_segments=4, stud_segments=16, tube_segments=16,
  rib_segments=2`. ~1k tris.
- **standard** — `body_corner_segments=8, stud_segments=32,
  tube_segments=32, rib_segments=4`. ~5k tris. Default for the C4D
  plugin.
- **hero** — `body_corner_segments=16, stud_segments=100,
  tube_segments=100, rib_segments=8`. Plus
  `body_fillet_radius=0.4, stud_fillet_radius=0.18,
  tube_fillet_radius=0.18, rib_fillet_radius=0.10`. ~50k verts on a 2×3.
  Hero is what the user wants for renders.

`make_brick_hires` returns a `Mesh` with named polygon groups (`body`,
`studs`, `underside`, `tubes`); `mesh_to_polygon_object` in the .pyp
converts each group into a `Tpolygonselection` tag for material
assignment in C4D.

### Brick anatomy & placement rules

The user has corrected me on these multiple times. Get them right:

- **Studs**: 1 per (x,z) lattice cell, on top. Revolved profile with
  concave base fillet (body→stud) and convex top edge (cylinder→cap).
- **Connector tubes** (interior, between studs along the long axis):
  only for bricks ≥ 2 in both width and depth. Hollow cylinders with
  concave outward-flaring top fillet (the air sees concave; flares OUT
  from the cylinder wall toward the ceiling, NOT inward). Filleted
  bottom rim too.
- **Stud-position ceiling indents**: small dimples in the cavity ceiling
  under each stud. `stud_indent_outer_ratio=0.18` produces a visible-but-
  small dimple matching the reference. Anything bigger looks wrong.
- **Wall ribs**: rectangular pads (NOT pill-shaped). One rib per stud
  column on each wall — `depth_studs` ribs per long wall, `width_studs`
  ribs per short wall, each centered at `(i+0.5)*stud_size`. All ribs
  protrude INWARD into the cavity. The user has corrected the rib count
  multiple times; the final answer is one-per-stud.
  - `rib_protrusion_ratio=0.04` (current — halved from earlier 0.08).
  - Rib top extends to `ceiling_panel_y` (flush with cap); the part of
    the rib above `wall_top_y` sits inside the wall's solid material so
    it's hidden.
  - **Back-corner saddle patches**: each rib has 4 Coons-patch
    quadrilaterals at the back corners filling the gap where one convex
    side fillet meets two concave back fillets. The wall-plane edge is
    left as an open boundary by design (hidden behind the wall).
- **Body fillets**: every 90° edge is filleted via cylindrical edge
  fillets + sphere octants at corners. `body_fillet_radius=0.4` is the
  hero default and looks right. Both top AND bottom edges get fillets
  even when `skip_bottom=True` (the bottom panel is removed but the
  bottom edge fillets still exist).
- **Body top panel under studs**: emitted via `_emit_ceiling_with_holes`
  with one circular hole per stud at radius `stud_r + stud_fillet_radius`
  and `segs=stud_segments`. Hole rim verts coincide exactly with each
  stud's first profile ring → `weld_vertices` fuses them manifold-clean.
  Do NOT just emit a flat rectangle under the studs (creates hidden
  discs inside the merged solid).

### Cavity topology — the part that took 4 rounds to get right

This is the watertight body+cavity shell. **Test
`mesh.weld_vertices` then count boundary edges; if non-zero in
body+cavity only (no studs/tubes/etc.), there's a bug.** Inserted
features (studs/tubes/indents/saddles) introduce boundary edges by
design — that's expected and harmless.

The cavity has these surfaces:
- 4 inner walls — **trapezoids**, NOT rectangles. Top edge inset by the
  ceiling fillet radius (`cz_lo..cz_hi`); bottom edge full extent
  (`z0..z1`).
- 1 ceiling — tessellated with `_emit_ceiling_with_holes` using
  `scipy.spatial.Delaunay`. Holes for ALL circular features (indents
  AND tube tops). Tube tops MUST be in the hole list, otherwise the
  ceiling occludes the tubes.
- 4 ceiling-to-wall cylindrical fillets at the top edges
- 4 ceiling-corner sphere octants
- **4 corner filler triangle fans** at each interior cavity corner.
  These go from the cavity bottom corner `(x1, 0, z1)` up to N+1 points
  along the ceiling corner sphere octant's bottom arc. Without these
  there's a triangular gap at each interior corner — the failure mode
  the user caught.
- Bottom rim frame — **4 simple trapezoidal quads, sharp corners.** Don't
  try to make the rim outer perimeter follow a rounded arc. The body's
  bottom panel boundary at y=0 is a SHARP rectangle. The rounding only
  exists for y > 0 via the bottom-edge fillets and corner sphere octants
  (whose y=0 tip is a single point at each corner). I tried tracing an
  arc rim once; that was wrong. See "Recovered mistakes" below.

### Tube top fillet direction

Inner top fillet's center is at `(inner_r - top_fillet, ceiling_y -
top_fillet)`. Sweep angle 0 → π/2. This makes the fillet flare OUT
toward the ceiling, smooth and concave from the underside view.

If it ever looks like the inner bore "necks down" before reaching the
ceiling, the fillet center is on the wrong side. Don't ship that — the
user caught this once already.

## Conventions / settings the user has locked in

- **Stud size** = 8mm, **plate height** = 3.2mm (real LEGO units).
  `stud_size` and `plate_size` are unit-agnostic parameters; the
  algorithm doesn't care, only the defaults are 8 and 3.2.
- Coordinates: Y is up. The brick sits with its bottom panel at y=0,
  studs poking up.
- The brick is built as a `Mesh` with named polygon groups (`body`,
  `studs`, `underside`, `tubes`). C4D uses these for selection sets and
  material assignment.
- All sizes 1×N through 2×8 in `library.DEFAULT_LIBRARY`. 22 brick types.
- Color palette in `palette.DEFAULT_PALETTE` (~26 LEGO colors). Matching
  via CIELAB ΔE. Optional — pipeline carries raw RGB by default.

## Communicating with the user

- The user is an experienced 3D artist (uses Cinema 4D + Houdini). They
  read wireframes faster than I do, and they're often right when they
  say something looks wrong. Trust their visual feedback.
- They don't want me to second-guess every design choice with multiple
  options. When they say "use approach X", do approach X.
- Don't over-confirm. If they ask for a fix, fix it and move on. Don't
  re-render four angles to "verify" things they didn't ask about.
- "[no preference]" means "you decide and stop asking". Take that
  signal.

## Render setup

Matplotlib's 3D z-sort is broken for non-convex shapes — the brick body
will look like its cavity is showing through the outer wall. Don't trust
matplotlib renders for verifying interior geometry.

For visual checks, the simplest path is to open the OBJ in Cinema 4D or
any viewport (Houdini, Blender, etc.). For programmatic verification,
use `tools/sanity_check_brick.py` and `tools/analyze_obj_features.py`
which check manifoldness and boundary edge counts.

`render_wireframe` in `wireframe.py` is fine for quad topology
visualization but not for hero shots.

## Recovered mistakes (don't repeat)

- **SubD cage exported without subdividing**: shipped sharp-edged OBJ
  for several iterations. Resolution: bake fillets into geometry
  directly.
- **Pill-shaped ribs**: should be rectangular. The pill geometry was
  over-engineered.
- **Outward-facing ribs on short walls**: was a sign error in `axis="x"`
  protrude direction. Now correct.
- **Ceiling cell-grid tessellation**: had unfillable gaps at cell
  boundaries. Replaced with Delaunay.
- **Indents too big** (`stud_indent_outer_ratio=0.34`): nearly
  stud-sized. Now 0.18.
- **Inverted tube top fillet**: center on wrong side made fillet flare
  inward. Fixed center position.
- **Arc-traced rim outer perimeter**: I tried to make the rim trace the
  body's bottom-edge fillet curvature. Wrong — the body has no geometry
  at y=0 along that arc. The rim is a flat sharp-cornered annulus and
  the body's corners terminate at the rim's sharp corners.
- **Cavity wall corner gaps**: walls were rectangles `cz_lo..cz_hi`, rim
  was at `z0..z1`. The gap between them at the corner is filled by
  trapezoid walls + corner triangle fans. Watertightness verified by
  boundary-edge count.
- **Hidden discs under each stud**: the body top panel used to be a
  solid rectangle, leaving a hidden disc inside the merged stud+body
  solid under each stud. Replaced with `_emit_ceiling_with_holes(face_up=True)`
  with hole rims that fuse to stud profiles at weld time.
- **Open back-corner saddles on ribs**: the 3-fillet meeting point at
  each rib's back corners used to be an open gap. Now sealed by Coons
  patches.
- **Three-level package nesting**: an extra middle `brickify/` directory
  caused new code written one level too shallow to silently get ignored
  in favor of an older copy inside the actual package. Layout flattened
  to standard two levels.

## What's NOT done yet

- Logo support (SVG-extruded polygons on each stud) is in `brick_geom.py`
  but not in `brick_geom_hires.py`. Re-wire when needed.
- `assembly.py` still calls the old `make_brick_mesh`, not
  `make_brick_hires`. Swap before next full pipeline run.
- Full mesh→assembly pipeline (voxelize → fit → connectivity → export)
  is not yet exposed as a C4D command. The plugin currently generates
  single bricks only.
- v2 features: SNOT, articulation repair, region color clustering,
  anti-stud plates, OBJ instance dedup, bracket library. Don't start any
  of these without explicit user request.

## Test inputs / reference outputs

- `brick_2x3_h3_hero_filletfix.obj` at the repo root — last signed-off
  hero output. 47,496 verts / 49,428 faces, manifold-clean,
  ~400 boundary edges from intentional inserted-feature boundaries.
  Use this as the reference when validating geometry changes.
- The user has uploaded multiple wireframe and shaded screenshots of a
  Houdini reference brick. The reference is what we're matching, not
  improving on.
