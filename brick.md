# brick.md — Brick

Read this file before doing anything. The user has worked with multiple AI
sessions on this and is tired of re-explaining decisions. Default to the
conventions below; only revisit them when the user explicitly says to.

## What this project is

A Cinema 4D plugin suite for generating structurally-buildable LEGO bricks
and brick assemblies from source meshes. The C4D side runs as ObjectData
plugins; the same Python package can also be driven from the command line.

The C4D port is **live**:

- **BrickGen / Brick** is the single-brick generator. It loads
  `brick.brick_geom_hires.make_brick_hires`; Width, Depth, Height
  (plates), and Quality are exposed as object parameters.
- **BrickIt** is the assembly generator. It fits source meshes into brick
  placements, exposes Proxy/Draft/Standard/Hero preview/render qualities,
  supports build animation, and emits the integrated SOURCE-mode MoGraph
  hierarchy used for effectors, fields, and Redshift per-brick color.

Current pushed checkpoint before this guide refresh:
`e65e10c` (`Update BrickIt animation and proxy workflow`). It includes the
Smooth Top animation controls, proxy quality defaults, integrated MoGraph
animation updates, and `tools/diagnose_brickit_animation_jump.py`.

## Project layout

```
Z:\02_MKE\2026\BRICK\brick\           ← repo root
  brick\                               ← Python package
    __init__.py
    brick_geom_hires.py                ← LIVE generator
    brick_geom.py                      ← deprecated SubD-cage version
    mesh.py, fitter.py, voxelize.py, ...
  BrickGen\                            ← C4D plugin source, deployed as Brick
    c4d_brick_generator.pyp
    c4d_symbols.py
    res\
  tools\
    export_hires_brick.py              ← CLI wrapper around make_brick_hires
    deploy_plugin.ps1                  ← copy plugin → C4D plugins folder
    sanity_check_brick.py, ...
  backup\                              ← old plugin/package snapshots
  brick.md
```

**Package nesting trap, do not repeat**: the implementation package is
`brick/*.py` directly under this repo. At one point there was an extra
middle `brickify/` and a stray `brick_geom_hires.py` got written next to
the package instead of inside it. Imports silently resolved to a stale
older copy. If "old-looking" output appears unexpectedly, sanity-check
that the live `brick_geom_hires.py` lives at `brick/brick_geom_hires.py`.

**Naming / ID trap, do not churn**: project branding is Brick, the source
plugin folder is `BrickGen`, the deployed plugin folder is currently
`Brick`, the assembly object shown in C4D is `BrickIt`, and the canonical
Python package is `brick`. Many internal symbol IDs and resource filenames
still intentionally use legacy `BRICKIFYASSEMBLY` / `obrickifyassembly`
tokens for scene/resource stability. Do not rename those just to make the
strings prettier.

## C4D plugin workflow

C4D loads the plugin from
`%APPDATA%\Maxon\Maxon Cinema 4D 2026_1ABCDC12\plugins\Brick`,
not directly from the repo. Edit canonically in `BrickGen/` here,
then deploy with:

```
powershell -ExecutionPolicy Bypass -File tools\deploy_plugin.ps1
```

Geometry-only changes inside `brick/*.py` do **not** need
redeployment — the plugin imports the package live from
`Z:\02_MKE\2026\BRICK\brick` (hardcoded fallback in
`ensure_brick_on_path`). Just restart C4D (or recreate the
Brick object so its mesh cache invalidates).

`tools/deploy_plugin.ps1` copies repo `BrickGen` to C4D plugin folder
`plugins\Brick`, moves stale sibling plugin folders (`BrickGen`,
`BrickGenerator`, old `.bak_*` folders) into `plugin_backups`, strips
`__pycache__`, and nests `bricklibrary.inline_gui` under the deployed
plugin when the native GUI build is available. If C4D reports duplicate
plugin registration, check for stale plugin folders under the C4D
`plugins` root first.

The plugin's `Brick` ObjectData caches results on
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

## Pipeline (mesh → bricks) / BrickIt assembly

The mesh-to-brick-assembly pipeline is implemented in the package and is
now wired into the C4D plugin through the **BrickIt** ObjectData workflow.
The same core pipeline remains usable from tools/scripts:

1. Load OBJ with named groups (`voxelize.load_obj_grouped`)
2. Voxelize at a resolution chosen by stud_size & plate_size
   (`voxelize.voxelize_mesh`)
3. Greedy fit of brick library to voxel grid (`fitter.BrickFitter`)
4. Build coupling graph and prune according to the active mode
   (`connectivity` module; structural connectivity remains a hard
   requirement for physical output)
5. Export as OBJ + JSON manifest grouped by brick_type for MoGraph
   (`exporters.export_json`, `exporters.export_ldraw`)

The fitter stores raw RGB on each `BrickPlacement`. Palette quantization
is optional and decoupled from the pipeline — by design.

`assembly.py` is legacy/offline plumbing and may still refer to older
single-brick APIs. The live C4D BrickIt path is split across
`BrickGen/brickit_fit.py`, `BrickGen/brickit_view.py`,
`BrickGen/brickit_runtime.py`, and the core `brick.pipeline` /
`brick.fitter` modules.

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

Run it before changing `brick/fitter.py`, `brick/pipeline.py`, or the
`Make Physically Accurate` wiring in `BrickGen/c4d_brick_generator.pyp`.

### Integrated MoGraph color path — DO NOT REGRESS

The integrated MoGraph output is now the **default and only** SOURCE-mode
behavior. There is no `MoGraph Output` checkbox and no `Create Fracture`
button — both were removed once the integrated path proved stable. The
runtime gates the integrated hierarchy purely on
`visualization_mode == BRICKIFYASSEMBLY_VISUALIZATION_MODE_SOURCE`. The
debug viz modes (Shell Wireframe / Voxel Debug / Brick Size / Shell
Depth) still go through the legacy `_build_hierarchy` in
`BrickGen/brickit_view.py`. `Create Proxies`, `Proxy / High Res`, and
`Create RS Color Material` remain in the Library group. Old saved scenes
that referenced parameter IDs `2092` (`MOGRAPH_OUTPUT`) or `2048`
(`CREATE_MOGRAPH`) will produce a one-time "unknown parameter" log on
load and silently drop them — this is expected.

The integrated MoGraph output (effectors/fields driving per-brick color
without an external Fracture object) cost several rounds to get right.
The locked-in answer:

- BrickIt outputs **one `InstanceObject` per brick**, in
  `INSTANCEOBJECT_RENDERINSTANCE_MODE_MULTIINSTANCE` with a single entry
  (`SetInstanceMatrices([m])`, `SetInstanceColors([c])`), and also sets
  `ID_BASEOBJECT_USECOLOR=ALWAYS` + `ID_BASEOBJECT_COLOR=c` on each
  carrier. This is the "expanded one-instance-per-carrier" mode in
  `BrickGen/brickit_mograph_generator.py`. Do not switch the default
  back to grouped multi-instance carriers — that shuffles `RSObjectColor`
  vs the no-material gradient (per-clone index disagrees with the carrier
  multi-instance index).
- Effector evaluation runs through the native `BrickMoGraphEvaluatorTag`
  in `MSG_EXECUTE_EFFECTOR` mode only (`skip_field_override=True`).
  Manually re-applying `FieldList.SampleListSimple` after effectors
  ran was producing colors that disagreed with Redshift's no-material
  gradient. The effector message alone now produces the same colors RS
  reads in the no-material fallback.
- If native effector evaluation returns non-finite or absurd matrices,
  the integrated path falls back to that brick's pre-effector matrix and
  logs one warning instead of letting a bad field/effector state explode
  the scene. Separate caveat: if every Field layer is removed from a Plain
  Effector, C4D can apply the effector at full strength (for example,
  scale-to-zero). Disappearing bricks in that case may be legitimate
  C4D effector behavior, not a BrickIt transform bug.
- The Redshift material the user must wire on the BrickIt object is a
  **`Color User Data` node with Attribute Name = `RSObjectColor`**.
  That is the exact, case-sensitive attribute string Redshift maps the
  per-instance display color to. Menu labels like "Object Color" /
  "Display Color" are UI presets — they store `RSObjectColor` /
  `RSDisplayColor` as the actual lookup string. Do not test with the
  literal label string; it returns black.
- The BrickIt AM has a one-click **Create RS Color Material** button
  that builds exactly this material (`BrickIt_PerBrick_Color`) and
  attaches it to the BrickIt object. Implementation in
  `BrickGen/brickit_rs_material.py`. Two non-obvious things in there
  to keep working: (1) `CreateEmptyGraph` must be called BEFORE
  `doc.InsertMaterial`, then re-fetch with `GetGraph`, then
  `BeginTransaction`. (2) Redshift's Color User Data output port is
  named `…rsuserdatacolor.out`, NOT `outcolor` like every other RS
  node. Don't "fix" the port name; it's correct.
- `RSMGColor` does not work for our output and we do not target it.
  We are not a real MoGraph cloner and there is no persistent MoData
  tag on a parent generator that RS can index. The Maxon SDK shipped
  with this project does not expose `Tmgdata` / `MGDATATAG` / the
  MoData custom datatype IDs needed to forge one. If a future session
  is asked to "make `RSMGColor` work too", do not synthesize MoData
  tags from guessed numeric IDs — that's the path that previously
  correlated with Redshift load failures.

Diagnostic probe lives at `tools/c4d_redshift_color_material_probe.py`.
It generates `BrickIt_RSProbe_UserData_RSObjectColor` (and a few other
attribute candidates) for fast bisection if this regresses.

#### Failed experiment: wrapping carriers in `Omgfracture` — DO NOT REPEAT

We tried adding an opt-in toggle that parented the per-brick
`Oinstance` carriers to a real `Omgfracture` (Mode =
`MGFRACTUREOBJECT_MODE_NONE`, empty effector list) instead of the
plain `bricks` Null, with BrickIt's `BrickMoGraphEvaluatorTag`
remaining authoritative for matrices/colors and the Fracture acting
purely as a passive MoData wrapper.

Tested in the standing test scene with a Plain effector + Random Field
gradient setup. Result:

- No-material gradient: still worked.
- `RSObjectColor` material: still worked.
- `RSMGColor` material: **all bricks rendered flat black**.

`Omgfracture`'s MoData generation does NOT surface a child
`Oinstance` carrier's display color (`ID_BASEOBJECT_COLOR` /
`SetInstanceColors([c])`) into the MoData color array, so
`RSMGColor` has nothing to read. The toggle was removed (it was
misleading user-facing UI that didn't deliver `RSMGColor`); the
revert was simple because the only behavior change was a one-line
swap of the `bricks` Null for an `Omgfracture` parent. Don't add
this back — `Omgfracture`-as-MoData-shim is a dead end for our
output topology.

The only remaining theoretically-viable path for `RSMGColor` is a
real `Omgcloner` per template with object-link arrays driving the
clones (one Cloner per `(width, depth, height)` template, fed by an
array of per-brick matrices and colors). That is a structural
refactor of `BrickGen/brickit_mograph_generator.py` and shall not
be started without explicit user go-ahead. Continue to recommend
`RSObjectColor` via the **Create RS Color Material** button —
that's the supported path for per-brick color in Redshift.

### Integrated MoGraph template shape — DO NOT REGRESS

Each per-type template proto in
`BrickGen/brickit_mograph_generator.py::_get_template_obj` must be a
`Null` containing **exactly one** polygon child. In high-res template
paths, stud logos are baked into that one polygon child via
`_bake_template_logos_into_mesh`. Proxy templates intentionally do not
bake stud logos, but the one-polygon-child invariant still applies.
Do not regress to attaching logo polygon children alongside the
brick mesh under the same Null.

Why: Redshift's `SceneMesh.cpp(1256)` assertion fires once per render
when an `Oinstance` reference resolves to a Null with multiple
polygon children. The integrated path puts every carrier on a
per-template proto, so a Null with mesh + N logo children triggers
the assertion at every render. Baking logos into the brick mesh
keeps the proto shape `Null { merged_polygon }`, which Redshift
accepts cleanly. Logo positions use the same centered-coordinate
offsets the previous Null-children layout used, so the rendered
result is identical.

### Integrated MoGraph animation path — DO NOT REGRESS

The integrated MoGraph generator (`BrickGen/brickit_mograph_generator.py`)
must run the same per-placement animation pipeline as the standard view
path, or sliders on the Animate tab silently no-op:

- Compute `phased_build_animation_states(...)` with the same arguments
  the view uses: `build_progress`, linear `build_progress_time`,
  independent `smooth_top_progress` / `smooth_top_progress_time`,
  `top_cap_ids`, `top_surface_start`, `top_surface_phase`,
  `top_surface_blend`, `build_y_offset`, `build_stagger`,
  `build_hang_time`, `build_motion_curve`, and `build_custom_curve`.
- Filter placements to `state.local_progress > 0.0` so bricks correctly
  appear/disappear with Build Progress.
- Per placement, build the matrix at the brick's CENTER pivot
  (`separated_center`, not `separated_low_corner`), then apply
  `build_tilt_for_progress`, `build_tilt_clearance`,
  `build_scale_for_progress`, and `apply_humanize_to_center_matrix`.
- Tilt and scale-in use `BuildAnimationState.contact_progress`, not raw
  rebound progress, so rotation/scale finish by first landing/contact and
  a bounce rebound does not reintroduce tilt or tiny scale.
- Stagger is timed from an upward Y-layer frontier. Lower layers that have
  already landed must not un-settle when the Stagger slider changes.
- `BRICKIFYASSEMBLY_BUILD_TILT_AMOUNT` must stay keyframeable (`ANIM ON`
  in `obrickifyassembly.res`).
- Templates emitted under `templates_root` must be **centered** —
  shift the mesh points by `-(w/2, h/2, d/2)` (and shift logo offsets
  by the same amount inside the template). Do not regress to
  low-corner templates / `apply_humanize_to_low_corner_matrix`; the
  matrix math above assumes a centered pivot.

`BrickGen/brickit_runtime.py` has an animation fast path for SOURCE mode:
when topology is unchanged and only animation/effectors move, it mutates
the existing hierarchy's matrices/colors/visibility instead of rebuilding
all objects. Set `BRICKIT_LOG_ANIMATION_FAST_PATH=1` to log timing while
debugging scrubbing or playback performance.

If the Animate tab sliders ever stop affecting the integrated MoGraph
output, the first thing to check is whether `phased_build_animation_states`
is still being called and whether `_make_animated_centered_matrix` is
still wired up.

Guardrail / diagnostic:

```
python tools/test_brickit_animation.py
```

Run this before changing BrickIt animation, Smooth Top, stagger, bounce,
hang time, scale-in, tilt, or integrated animation matrix code. For C4D
timeline jumps that only show up in-scene, run
`tools/diagnose_brickit_animation_jump.py` from Cinema 4D's Script Manager
with the BrickIt object selected; it writes
`brickit_animation_jump_report.txt` to the Desktop.

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

`BrickGen/quality_presets.py` is the single source of truth for quality
IDs and hires geometry presets. `tools/export_hires_brick.py`,
`BrickGen/brickgen_object.py`, `BrickGen/mesh_bridge.py`, and BrickIt
modules import from there. Do not reintroduce duplicated segment dictionaries
in `tools/export_hires_brick.py` or `BrickGen/c4d_brick_generator.pyp`.

- **proxy** — BrickIt-only SOURCE preview mode using
  `make_proxy_collider`: hollow underside shell plus coarse studs,
  no tubes/ribs/indents and no baked stud logos. This is the default
  lightweight interaction/playback mode for BrickIt assemblies. Numeric ID
  is `3`; keep it out of `QUALITY_PRESET_NAME_TO_ID` because the CLI hires
  exporter only accepts Draft/Standard/Hero.
- **draft** — `body_corner_segments=4, stud_segments=16, tube_segments=16,
  rib_segments=2`. ~1k tris. In BrickIt this is the previous low hires
  mesh detail option, distinct from proxy.
- **standard** — `body_corner_segments=8, stud_segments=32,
  tube_segments=32, rib_segments=4`. ~5k tris. Default for the single-brick
  Brick/BrickGen object.
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
  in favor of an older copy inside the actual package. Layout is now the
  repo root plus the canonical `brick/` package.

## What's NOT done yet

- `brick_geom_hires.py` does not natively emit SVG-extruded logos as part
  of the core single-brick mesh. BrickIt handles logos at the template
  level and the integrated MoGraph path bakes them into a single polygon
  child when needed. Keep that distinction clear.
- `assembly.py` is legacy/offline plumbing and may still refer to older
  single-brick APIs. Do not treat it as the live BrickIt C4D path without
  checking the current `BrickGen/brickit_*` modules first.
- The old "plugin only generates single bricks" statement is obsolete.
  BrickIt is the live C4D assembly object. What is still future work is
  broader assembly intelligence beyond the current fitter/preview/render
  workflow.
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
