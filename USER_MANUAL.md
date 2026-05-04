# Brick — User Manual

Cinema 4D plugin suite for generating LEGO-style bricks and assemblies. Two
objects ship in the same plugin:

- **Brick** — a single parametric brick.
- **BrickIt** — converts any source mesh into a structurally-buildable brick
  assembly with animation, MoGraph effectors, and per-brick color in Redshift.

This manual covers how to use both. For a quick install, see
[README_INSTALL.md](README_INSTALL.md).

---

## Install

Supported package: Windows + Cinema 4D 2026.

1. Close Cinema 4D.
2. Unzip the release into your Cinema 4D user plugins folder so the plugin
   ends up at:
   ```
   %APPDATA%\Maxon\Maxon Cinema 4D 2026_1ABCDC12\plugins\Brick
   ```
3. Start Cinema 4D. Both objects appear under the plugin menu:
   - `Brick` — single brick generator.
   - `BrickIt` — source-mesh-to-brick assembly.

The package is self-contained — Python dependencies (numpy, scipy) are
vendored. You should not need to install anything yourself.

---

## Brick — single-brick generator

Use this when you want a clean parametric brick (for stills, beauty shots,
hero set dressing, or as the source for your own MoGraph cloner).

### Adding it

Object menu → **Brick**. The default is a 2×4 brick.

### Parameters

- **Type** — Brick (full plate-3 height) or Plate (1/3 height).
- **Width** — studs along X (1–8).
- **Depth** — studs along Z (1–8).
- **Height** — plates tall (1–8). One plate is 3.2 mm, three plates make a
  full brick.
- **Quality** — geometry detail:
  - **Draft** — ~1k tris. Fast.
  - **Standard** — ~5k tris. Good default for layout.
  - **Hero** — ~50k verts on a 2×3, full filleted edges, dense studs and
    tubes. Use for renders.

The mesh is generated with named polygon selections (`body`, `studs`,
`underside`, `tubes`) so you can apply different materials per region.

### Stud Logo (optional)

Replace the default flat stud top with your own embossed logo:

- **Use Custom Stud Logo** — toggles the feature.
- **Logo Source Mesh** — link any polygon object. Its silhouette is
  projected onto each stud top.
- **Logo Rotation** — 0 / 90 / 180 / 270 degrees.
- **Logo Fill %** — how much of the stud top the logo occupies.
- **Logo Height** — embossed depth.
- **Logo Blend** — how softly the logo edges fade into the stud surface.
- **Logo Sink** — recess the logo below the stud surface (useful when you
  want the logo carved in rather than raised).

---

## BrickIt — mesh-to-brick assembly

Drop in any polygon object, link it as the Source Mesh, and BrickIt voxelizes
the mesh and tiles it with bricks. Real-time preview, animation, MoGraph
effectors, Redshift per-brick color all work on the live output.

### Quick start

1. Object menu → **BrickIt**.
2. Drag a polygon object into **Source Mesh** on the Shape tab.
3. The default settings produce a 2×4-brick shaped assembly. Adjust
   **Resolution** and **Target Studs Across** until the silhouette matches
   what you want.
4. Switch **Brick Mesh Detail** (Look tab) to **Hero** for a final render.

The BrickIt object's parameters are organized into six tabs:

- **Shape** — voxelization, build type, surface finishing.
- **Bricks** — which brick sizes to use, plate-stack rules, per-brick
  variation.
- **Look** — render quality, preview mode, custom stud logo, live-update.
- **Animate** — build animation, smooth-top finishing animation.
- **Effectors** — MoGraph effectors that drive matrix and color (and now
  visibility).
- **Tools / Surface Finish** — utility buttons (proxy generator, RS color
  material, hide source mesh).

---

### Shape tab

This is where you decide how the source mesh is sampled and what brick
"texture" the assembly has.

**Source**

- **Source Mesh** — the polygon object BrickIt fits bricks into. Any
  polygon object works (Polygon Object, Spline Polygonized, Mesh Object,
  primitives made editable). The source's *world transform* defines where
  the brick assembly appears — moving the source moves the bricks; scaling
  it scales the assembly.

**Voxelization**

- **Resolution** — slider 0.1–1.0 controlling how many voxels are sampled.
  Lower = chunkier bricks, faster builds. Higher = finer detail, slower.
- **Target Studs Across** — sets the brick assembly width by stud count.
  Increase to get finer detail at the same source size; decrease for a
  blockier look.
- **Use Custom Scale** + **Stud Size** — override the auto-derived stud
  size with a fixed value. Useful when the brickified output needs to
  match a specific real-world scale.

- **Algorithm** — voxelization backend:
  - **Simple** — internal voxelizer. Faster, less precise on thin features.
  - **Detailed** — Cinema 4D Volume (`MeshToVolume`) sampling. Slower but
    handles thin walls and concave surfaces much better. Recommended for
    most production work.

**Build Type**

- **Solid** — fill the entire interior with bricks.
- **Shell** — only place bricks within `Wall Thickness` of the surface.
  Lighter assemblies, hollow inside.
- **Wall Thickness** — only used in Shell mode. Number of brick layers
  inward from the surface.

**Brick Size Style** — how aggressively BrickIt picks larger bricks vs
smaller ones:

- **Simple** — favors larger brick sizes; fewest pieces.
- **Balanced** — default mix.
- **Preserve Small Features** — tries hardest to keep thin source details
  visible, even if it means many small bricks.

**Surface finishing**

- **Make Physically Accurate** — when ON, the assembly must be a single
  connected structure (drops floating clusters; you can build it with
  real bricks). When OFF, BrickIt prioritizes silhouette accuracy and
  fills boundary cells with 1×1s as needed; physically separate islands
  are kept.
- **Keep Tiny Gaps** — preserves narrow gaps in the source by allowing
  smaller bricks; off by default for cleaner output.
- **Clean Small Details** — removes stray single-brick protrusions that
  read as noise rather than detail.

**Smooth Top Surfaces** — replace the lumpy top of the assembly with flat
plates. When enabled:

- **Cap Style** —
  - **Match Brick Below** — cap each top column with a plate the same
    footprint as the brick beneath it (most uniform look).
  - **Largest Merged Plates** — pack the top with the biggest plates that
    fit (cleanest geometric look).
  - **Random Library Mix** — random plates from your library selection.
- **Cap Random Seed** — seed for the Random Library Mix style.
- **Top Finish Starts At** / **Top Finish Duration** — animation timing
  for when the smooth-top plates appear during Build Progress (see
  Animate tab).
- **Smooth Top Coverage** — fraction of top cells that get smoothed
  (1.0 = full coverage; lower values leave some studs poking through).
- **Randomize Top Finish** / **Blend Top Finish** — animation order and
  cross-fade behavior for the cap-on-top reveal.

---

### Bricks tab

Controls *which* brick sizes BrickIt is allowed to use and how plates and
heights are handled.

**Choose Bricks**

A thumbnail picker showing the 22 stock brick sizes (1×1 through 2×8 plus
3×3, 3×4, 3×6, 3×8). Click a thumbnail to toggle that size in/out of the
active library. The current selection is the search space the fitter draws
from.

**Quick Select** buttons:

- **All** — enable every brick.
- **None** — disable everything (you'll get an empty assembly until you
  add at least one).
- **Invert** — flip the current selection.
- **Bricks** / **Plates** — limit to one brick height class.
- **1×1 Only** — useful for a "voxel-perfect" look that ignores larger
  bricks entirely.

**Open Thumbnail Picker** — pops up a larger floating picker (handy on
small monitors).

**Plate behavior**

- **Use Plates** — when ON, the fitter can use 1-plate-tall bricks
  (plates) in addition to 3-plate bricks. Lets the assembly hug curves
  more tightly at the cost of more total pieces.
- **Brick Height (preset)** — quick preset for the height search:
  - **Fine** — allow plates and tall bricks.
  - **Balanced** — default.
  - **Blocky** — bias toward full bricks.
- **Vary Brick Heights** — randomly mix tall and short bricks across the
  assembly for a less grid-uniform look.
- **Variation Seed** / **Variation Amount** — seed and intensity for that
  randomization.
- **Merge Plate Stacks into Bricks** — when three vertically-aligned
  plates can be replaced by one brick, do so. Reduces piece count.

**Per-Brick Variation**

- **Brick Separation** — adds a tiny gap between bricks (in scene units).
  Useful for renders where you want to read the seams. 0 = bricks touch
  exactly.
- **Humanize Bricks** — when ON, every brick gets a small random offset
  and rotation so the assembly looks hand-built rather than CNC-perfect.
- **Humanize Seed** — controls the random pattern.
- **Position Variation** / **Rotation Variation** — magnitude of the
  jitter (each 0–1 or 0–2). Use small values; the effect compounds.

---

### Look tab

Render quality, custom stud logos, preview/debug modes, live update.

**Render Quality**

- **Brick Mesh Detail** — geometry density per brick:
  - **Proxy** — hollow shell + coarse studs, no tubes/ribs/indents.
    Lightest possible. Use for layout, animation playback, MoGraph effector
    setup. This is the default.
  - **Draft** — ~1k tris, plain studs, low detail.
  - **Standard** — ~5k tris, full anatomy, render-passable for distant
    shots.
  - **Hero** — ~50k verts per brick with full edge fillets, dense studs
    and tubes, baked stud logos. Use for hero renders.

**Custom Logo** (same controls as the Brick object): replace the flat
top-of-stud with a custom embossed logo. Only baked at Hero quality —
Proxy/Draft/Standard skip stud logos for performance.

**Preview Mode**

- **Source Color** — the live brick assembly with per-brick color from the
  source mesh. This is the normal working mode.
- **Shell Wireframe** — debug mode showing brick outlines on the source
  shell. Useful for checking voxelization results.
- **Voxel Overlay** — debug mode showing raw voxel cells, color-coded by
  shell depth.

**Live Update / Rebuild Now**

- **Live Update** ON (default) — the assembly rebuilds whenever a slider
  changes. Best for interactive scrubbing.
- **Live Update** OFF — sliders only update the cached state. Press
  **Rebuild Now** to commit. Use this on heavy scenes when scrubbing feels
  sluggish.

---

### Animate tab

Per-brick build animation. Bricks fall in from above, optionally bounce or
tilt, and smooth-top plates can fade in last.

**Core sliders**

- **Build Progress** — 0 → 1 reveals the assembly. 0 = empty, 1 = fully
  built. Keyframe this for a "build" animation.
- **Smooth Top Progress** — 0 → 1 reveals the smooth-top cap separately
  from the body. Has no effect unless Smooth Top Surfaces is on.

**Drop physics**

- **Lift Height** — how far above its final position each brick starts
  (in scene units).
- **Stagger Amount** — 0 = all bricks land simultaneously; higher values
  spread the landing across the timeline by Y-layer (lower bricks land
  first).
- **Brick Hang Time** — adds a pause before the brick starts moving. Lets
  later bricks build anticipation.
- **Motion Style** — easing curve:
  - **Ease**, **Ease In**, **Ease Out**, **Quadratic** — classic curves.
  - **Spring**, **Bounce** — bricks overshoot and settle.
  - **Slam** — fast drop with hard stop (default; gives the LEGO snap).
  - **Custom Curve** — use the **Custom Motion Curve** field to draw your
    own.

**Polish**

- **Scale Bricks In** — bricks scale from a point up to full size as they
  land (rather than appearing at full size and falling).
- **Use Rotation** — bricks tumble slightly while falling.
- **Tilt Amount** — how strong the tumble is. Keyframeable.

**Top finish timing** (only matters with Smooth Top Surfaces on):

- **Top Finish Starts At** — fraction of Build Progress at which the cap
  starts revealing.
- **Top Finish Duration** — how long the cap reveal takes.
- **Smooth Top Coverage**, **Randomize Top Finish**, **Blend Top Finish**
  — already covered on the Shape tab.

---

### Effectors tab

BrickIt accepts standard Cinema 4D MoGraph effectors and drives per-brick
matrix and color from them.

**Effectors list**

The list at the top is an InExclude that stores which effectors apply to
this BrickIt. Drag effectors in manually, or rely on auto-link: when you
**create** a new MoGraph effector while a BrickIt object is selected, that
new effector is automatically appended to BrickIt's Effectors list.
(Pre-existing effectors are not auto-added — only newly-created ones.)

**Supported effectors**

Plain, Random, Shader, Delay, Formula, Step, Sound, Time, Push Apart,
Inheritance, Python, ReEffector, Effector Target, Weight Effector, plus
anything that derives from the C4D base effector class. They all can drive:

- **Position / Rotation / Scale** — per-brick transform deltas.
- **Color** (Color Mode = User Defined or Field) — per-brick display color
  that flows into the **Create RS Color Material** path.
- **Visibility** — toggling the Plain effector's Visibility checkbox with
  a connected Field hides bricks where the field touches them.
  Hidden bricks drop out of both viewport and Redshift draw lists, not
  just shrink to zero.

**Per-brick color in Redshift**

Effectors that set color need a material that reads it. Click **Create RS
Color Material** (Tools tab) and BrickIt builds and assigns
`BrickIt_PerBrick_Color` — a Redshift node graph wired to the
`RSObjectColor` user data attribute. After that, any color set by an
effector (or by the source mesh sampling) shows up at render time.

If you build the material yourself, the only requirement is a `Color User
Data` node with **Attribute Name** = `RSObjectColor` (the case-sensitive
attribute string Redshift maps the per-instance color to). The "Object
Color" preset works because it stores `RSObjectColor` under the hood.

---

### Tools tab — Surface Finish / utility actions

- **Hide Source Mesh** — toggles the source polygon object's editor +
  render visibility. Convenient because the source usually overlaps the
  brick assembly.
- **Create Proxies** — bakes the live brick assembly into a static
  hierarchy under the BrickIt object: one Fracture object containing
  grouped Nulls per source-mesh region, with per-brick instances inside.
  This is what you reach for when you want to do dynamics, manual selection,
  or any work that needs real edit-able geometry instead of a live cache.
- **Proxy / High Res** — toggles the proxy hierarchy between Proxy-quality
  carrier meshes (light) and current-Brick-Mesh-Detail meshes (renderable).
  Quick way to hide the proxies during interaction and bring them back for
  the render pass.
- **Create RS Color Material** — see the Effectors section above.

---

## Workflow recipes

### Render a hero shot

1. Drop a BrickIt, link your source.
2. On the Shape tab, **Algorithm = Detailed**.
3. On the Bricks tab, pick the brick sizes you want and a sensible
   variation.
4. On the Look tab, **Brick Mesh Detail = Hero**.
5. **Create RS Color Material** (Tools tab) so per-brick color renders.
6. Render.

### Set up a build animation

1. With BrickIt configured to your liking on the Shape and Bricks tabs:
2. Animate tab → keyframe **Build Progress** from 0 (start of timeline) to
   1 (end of timeline).
3. Pick a Motion Style (Slam is the default LEGO drop). Adjust **Lift
   Height** and **Stagger Amount** to taste.
4. If you have Smooth Top Surfaces on, also keyframe **Smooth Top
   Progress** so the cap finishes after the body builds.
5. Render with Brick Mesh Detail at Hero. (For animation playback, switch
   to Proxy quality first.)

### Field-driven color and visibility

1. Drop a BrickIt and a Plain effector. The Plain auto-links into BrickIt's
   Effectors list.
2. On the Plain effector, set **Color Mode = Field** and add a Field (e.g.
   Random Field, Spherical Field) under Falloff.
3. **Create RS Color Material** to wire the per-brick color path.
4. To hide bricks the field touches: enable **Visibility** on the Plain
   effector and set Field strength such that touched clones turn off.
   Hidden bricks fall completely out of the scene rather than scaling to
   zero, so a moving Field is much lighter to interact with.

### Big assembly, slow viewport

1. **Brick Mesh Detail = Proxy** during interaction.
2. Turn **Live Update** off; press **Rebuild Now** when you want to see a
   change.
3. Use **Hide Source Mesh** so you only see the brick output.
4. Switch back to Hero only for the final render.

### Bricks that follow a deforming mesh + collide with each other

When the source is deforming (cloth dynamics, an Alembic point cache,
deformer chains), BrickIt can lock each brick to the closest triangle
on the source and ride the deformation per frame. Combined with C4D's
Rigid Body Dynamics, you can have the bricks track the mesh while
collisions push them apart instead of overlapping.

1. **Set up the source.** Apply your deformer/cloth/Alembic to the
   source mesh and link it as BrickIt's Source.
2. **Bind.** On the Layout tab → Bind to Source Deformation group,
   check **Bind Bricks to Source Deformation**. The bricks will now
   ride the surface in the live preview.
   - **Brick Orientation = Follow Surface Normal** tilts each brick to
     match the local surface orientation. **Orientation Smoothing**
     dampens the per-face-normal jitter that small / heavily deformed
     triangles produce; 0.7 is a good default.
   - **Stretch Cull Threshold** hides bricks whose anchor triangle
     compresses below the threshold ratio of its rest-pose area —
     useful when the cloth bunches up tight enough that bricks would
     otherwise overlap.
   - **Re-bind to Current Frame** re-fits and re-binds with the
     current deformed pose as the new rest pose.
3. **Make Proxies.** Once you're happy with the binding, click
   **Create Proxies** (Tools tab) to spawn a real proxy hierarchy
   under a `BrickIt_ProxySim_<source>` Null. The proxies follow the
   deformation via a **BrickIt Follow Surface** tag added to that
   Null automatically.
4. **Set the timeline preview range** to the frames you want to bake
   (Edit → Project Settings or the timeline header).
5. **Bake to Keyframes.** Select the Follow Surface tag and click
   **Bake to Keyframes (Preview Range)**. The bake:
   - Iterates each frame and writes position + rotation keyframes on
     every brick.
   - Converts each brick instance into a real polygon mesh.
   - Flattens the hierarchy into a single `bricks` Null containing all
     polygon bricks.
   - Adds a Rigid Body tag (PBD) to each brick with Follow Position
     and Follow Rotation set high.
   - Disables the Follow Surface tag so the keyframes drive the
     bricks unobstructed.
6. **Run the simulation.** Scrub or play — the per-brick RBD pulls each
   brick toward its keyframed target while collisions push neighbors
   apart. **Cache the simulation** (Project → Simulation → Cache) so
   playback is stable.
7. **Swap to high-res for render.** On the Follow Surface tag, set
   **Quality** (Draft / Standard / Hero) and click **Swap Quality**.
   Each baked brick's mesh data is replaced in-place with a polygon at
   the chosen render fidelity. Animation tracks, RBD tags, and the
   dynamics cache stay intact — the swap only changes mesh data.
   Templates are built lazily on first click; subsequent swaps at the
   same quality are near-instant.

Notes:

- The Source BrickIt must still exist when you click Swap Quality — the
  swap looks up the original BrickIt's brick library and template
  builder via a hidden link on the Follow Surface tag. Don't delete the
  BrickIt object until after your final render.
- The bake is a one-shot per preview range. To rebake at a different
  range, re-do the workflow from Make Proxies.
- Cloth + Bullet PBD doesn't read scripted matrices as Follow targets,
  which is why Bake to Keyframes is required — it materializes the
  follower's per-frame transforms into animation tracks the simulator
  can read.

---

## Tips and troubleshooting

**Bricks render flat black in Redshift.** Wire a Redshift material with a
Color User Data node, Attribute Name = `RSObjectColor`. The **Create RS
Color Material** button does this for you. Don't use the literal string
"Object Color" — Redshift maps it via the underlying attribute string,
not the menu label.

**The assembly jumps when I add a MoGraph effector.** This is fixed in the
current build (effectors now anchor correctly to the source mesh's world
position even when BrickIt sits at a different transform). If you see it,
you're probably running an older build — update to the latest preview.

**Animation is sluggish when an effector is active.** Drop to Proxy quality
on the Look tab while you scrub, switch back to Hero for the render. The
effector-active fast path rebuilds carrier instances each frame; Proxy
geometry makes that ~10× cheaper.

**The brickified output is missing pieces in interior cavities.** That's
Shell mode at work — switch the Shape tab to **Solid** if you want the
interior filled.

**Adding 1×1 bricks to fill a boundary creates noise.** Turn on **Clean
Small Details** on the Shape tab, or switch **Brick Size Style** to
**Simple** so the fitter prefers larger pieces.

**Make Editable produces selection or material chaos.** The non-Make-
Editable workflow (using **Create RS Color Material**) is the recommended
path for most renders. If you do need Make Editable, **Create Proxies**
first — that produces a clean static hierarchy organized by source-mesh
region (one Null per source child, sub-Nulls per disconnected polygon
island) which is much easier to select and assign materials in.
